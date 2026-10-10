# -*- coding: utf-8 -*-
"""
Chạy ASR trên các bộ dữ liệu đã tải (src/asr/tai_bo_danh_gia.py) rồi đo WER, để biết
ASR sai Ở ĐÂU chứ không chỉ sai BAO NHIÊU:
    - WER gộp từng bộ, từng nhóm (vd: giọng Bắc / Trung / Nam)
    - Các cặp từ hay nghe nhầm nhất (đáp án -> máy nghe): nguồn để thêm luật sửa lỗi
    - Từ hay bị bỏ sót / bị thêm vào
    - Đoạn bị bộ lọc [LOẠI] cắt bỏ: kiểm tra bộ lọc có xóa nhầm lời thật không
    - Các đoạn sai nhiều nhất để nghe lại

Kết quả từng đoạn được lưu lại sau mỗi đoạn: ngắt giữa chừng rồi chạy lại sẽ làm tiếp.
Báo cáo: outputs/danh_gia_asr/<bộ>__<cấu hình>.txt

Cách dùng:
    python src/asr/danh_gia_bo.py                        (mọi bộ đã tải, cấu hình mặc định)
    python src/asr/danh_gia_bo.py vimd
    python src/asr/danh_gia_bo.py --khong-goi-y          (so sánh: tắt câu mở đầu + từ khóa gợi ý)
    python src/asr/danh_gia_bo.py --khong-tien-xu-ly     (so sánh: tắt lọc ù + chuẩn hóa âm lượng)
    python src/asr/danh_gia_bo.py --loc-nhieu            (so sánh: bật giảm tạp âm)
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import jiwer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402
import danh_gia_wer  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THU_MUC_GOC = asr.THU_MUC_GOC
THU_MUC_BO = THU_MUC_GOC / "data" / "bo_danh_gia"
THU_MUC_BAO_CAO = THU_MUC_GOC / "outputs" / "danh_gia_asr"


# ======================================================================
# CHUẨN HÓA ĐỂ SO SÁNH CÔNG BẰNG
# Whisper hay viết số bằng chữ số ("20 tháng 10"), còn lời gốc của các bộ dữ liệu
# thường viết bằng chữ ("hai mươi tháng mười"). Không đưa về cùng một dạng thì một
# con số đúng cũng bị tính là 3-4 lỗi.
# ======================================================================
CHU_SO = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
HANG = [(10 ** 9, "tỷ"), (10 ** 6, "triệu"), (10 ** 3, "nghìn")]


def doc_ba_chu_so(n, day_du):
    """Đọc số 0..999. day_du=True khi phía trước còn hàng lớn hơn (1005 -> một nghìn không trăm linh năm)."""
    tram, chuc, dv = n // 100, n // 10 % 10, n % 10
    tu = []
    if tram or day_du:
        tu += [CHU_SO[tram], "trăm"]
    if chuc == 0:
        if dv and tu:
            tu.append("linh")
        if dv:
            tu.append(CHU_SO[dv])
    else:
        tu.append("mười" if chuc == 1 else f"{CHU_SO[chuc]} mươi")
        if dv == 1 and chuc > 1:
            tu.append("mốt")
        elif dv == 5:
            tu.append("lăm")
        elif dv:
            tu.append(CHU_SO[dv])
    return " ".join(tu)


def doc_so(chuoi_so):
    """Đọc dãy chữ số thành chữ tiếng Việt. Dãy bắt đầu bằng 0 (số điện thoại) đọc từng số."""
    if len(chuoi_so) > 1 and chuoi_so.startswith("0") or len(chuoi_so) > 12:
        return " ".join(CHU_SO[int(c)] for c in chuoi_so)
    n = int(chuoi_so)
    if n == 0:
        return "không"
    phan = []
    for gia_tri, ten in HANG:
        if n >= gia_tri:
            phan.append(f"{doc_ba_chu_so(n // gia_tri, bool(phan))} {ten}")
            n %= gia_tri
    if n:
        phan.append(doc_ba_chu_so(n, bool(phan)))
    return " ".join(phan)


# Cùng một cách đọc số nhưng mỗi vùng nói một kiểu: đưa về một dạng
BIEN_THE_SO = [
    (r"\b(mươi|mười) (?:tư)\b", r"\1 bốn"),
    (r"\b(mươi|mười) (?:lăm|nhăm)\b", r"\1 năm"),
    (r"\b(mươi) (?:một)\b", r"\1 mốt"),
    (r"\bngàn\b", "nghìn"),
    (r"\btỉ\b", "tỷ"),
    (r"\btrăm lẻ\b", "trăm linh"),
]


def chuan_hoa_danh_gia(van_ban):
    van_ban = unicodedata.normalize("NFC", van_ban.lower())
    van_ban = re.sub(r"(\d+)\s*h\s*(\d+)?\b", lambda m: f"{m[1]} giờ {m[2] or ''}", van_ban)
    van_ban = re.sub(r"\b\d{1,3}(?:\.\d{3})+\b", lambda m: m[0].replace(".", ""), van_ban)  # 1.000.000
    van_ban = re.sub(r"(\d+)[,.](\d+)", r"\1 phẩy \2", van_ban)                              # 2,5
    van_ban = van_ban.replace("%", " phần trăm ")
    van_ban = re.sub(r"\d+", lambda m: f" {doc_so(m[0])} ", van_ban)
    van_ban = danh_gia_wer.chuan_hoa(van_ban)
    for mau, thay in BIEN_THE_SO:
        van_ban = re.sub(mau, thay, van_ban)
    return van_ban


# ======================================================================
# CHẠY ASR
# ======================================================================
def ten_cau_hinh(args):
    phan = [args.model]
    if args.khong_goi_y:
        phan.append("khong_goi_y")
    if args.khong_tien_xu_ly:
        phan.append("khong_tien_xu_ly")
    if args.loc_nhieu:
        phan.append("loc_nhieu")
    return "_".join(phan)


def nhan_dang_mot_doan(model, duong_dan, args):
    """Trả về chữ máy nghe được, các dòng [LOẠI], độ dài (giây) và thời gian xử lý."""
    bat_dau = time.time()
    song_am = asr.doc_am_thanh(duong_dan)
    if not args.khong_tien_xu_ly:
        song_am, _ = asr.tien_xu_ly_am_thanh(song_am, args.loc_nhieu)
    dau_ra = io.StringIO()
    with contextlib.redirect_stdout(dau_ra):  # nhan_dang in từng đoạn: gom lại, chỉ giữ dòng [LOẠI]
        cac_tu, _ = asr.nhan_dang(model, song_am, goi_y=not args.khong_goi_y)
    return {
        "du_doan": " ".join(cau["text"] for cau in asr.tach_cau(cac_tu)),
        "bi_loai": [d.strip() for d in dau_ra.getvalue().splitlines() if "[LOẠI" in d],
        "do_dai": round(len(song_am) / asr.TAN_SO_MAU, 2),
        "thoi_gian": round(time.time() - bat_dau, 2),
    }


def doc_json(tep, mac_dinh):
    return json.loads(tep.read_text(encoding="utf-8")) if tep.exists() else mac_dinh


def ghi_json(du_lieu, tep):
    tep_tam = tep.with_name(tep.name + ".tmp")
    tep_tam.write_text(json.dumps(du_lieu, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tep_tam, tep)


def chay_mot_bo(ten_bo, model_hoac_ham_tai, args):
    """Nhận dạng mọi đoạn chưa có kết quả. model_hoac_ham_tai: model, hoặc hàm tải model khi cần."""
    thu_muc = THU_MUC_BO / ten_bo
    cac_muc = doc_json(thu_muc / "nhan.json", [])
    if args.so_mau:
        cac_muc = cac_muc[:args.so_mau]
    tep_ket_qua = thu_muc / f"ket_qua__{ten_cau_hinh(args)}.json"
    ket_qua = {} if args.chay_lai else doc_json(tep_ket_qua, {})

    can_chay = [m for m in cac_muc if m["id"] not in ket_qua]
    print(f"\n=== {ten_bo}: {len(cac_muc)} đoạn, cần nhận dạng {len(can_chay)} ===")
    model = None
    for i, muc in enumerate(can_chay, 1):
        if model is None:
            model = model_hoac_ham_tai() if callable(model_hoac_ham_tai) else model_hoac_ham_tai
        try:
            ket_qua[muc["id"]] = nhan_dang_mot_doan(model, thu_muc / muc["tep"], args)
        except asr.LoiDauVao as loi:
            ket_qua[muc["id"]] = {"loi": str(loi)}
        ghi_json(ket_qua, tep_ket_qua)  # lưu sau mỗi đoạn để chạy lại làm tiếp
        kq = ket_qua[muc["id"]]
        print(f"  [{i:>3}/{len(can_chay)}] {muc['id']}: "
              + (f"✗ {kq['loi']}" if "loi" in kq else f"{kq['thoi_gian']:.1f}s | {kq['du_doan'][:60]}"))
    return cac_muc, ket_qua


# ======================================================================
# PHÂN TÍCH LỖI
# ======================================================================
def phan_tich(cac_muc, ket_qua):
    tong = Counter()
    theo_nhom = defaultdict(Counter)
    cap_nham, bo_sot, them_vao = Counter(), Counter(), Counter()
    tung_doan, doan_bi_loai, doan_loi = [], [], []

    for muc in cac_muc:
        kq = ket_qua.get(muc["id"])
        if not kq:
            continue
        if "loi" in kq:
            doan_loi.append((muc, kq["loi"]))
            continue
        dap_an = chuan_hoa_danh_gia(muc["text"])
        du_doan = chuan_hoa_danh_gia(kq["du_doan"])
        if not dap_an:
            continue
        do = jiwer.process_words(dap_an, du_doan)
        so_tu = len(dap_an.split())
        so_lieu = Counter(tu=so_tu, sai=do.substitutions, thieu=do.deletions, thua=do.insertions,
                          doan=1, do_dai=kq["do_dai"], thoi_gian=kq["thoi_gian"])
        tong.update(so_lieu)
        theo_nhom[muc["nhom"]].update(so_lieu)

        tu_goc, tu_may = do.references[0], do.hypotheses[0]
        for khuc in do.alignments[0]:
            goc = " ".join(tu_goc[khuc.ref_start_idx:khuc.ref_end_idx])
            may = " ".join(tu_may[khuc.hyp_start_idx:khuc.hyp_end_idx])
            if khuc.type == "substitute":
                # Ghép từng cặp từ: "dự án" -> "du an" tính là 2 cặp riêng, dễ đọc hơn
                for g, m in zip(goc.split(), may.split()):
                    cap_nham[(g, m)] += 1
            elif khuc.type == "delete":
                bo_sot.update(goc.split())
            elif khuc.type == "insert":
                them_vao.update(may.split())

        wer = (do.substitutions + do.deletions + do.insertions) / so_tu
        tung_doan.append((wer, muc, kq, dap_an, du_doan))
        if kq["bi_loai"]:
            doan_bi_loai.append((muc, kq, do.deletions, so_tu))

    return {"tong": tong, "theo_nhom": theo_nhom, "cap_nham": cap_nham, "bo_sot": bo_sot,
            "them_vao": them_vao, "tung_doan": tung_doan, "doan_bi_loai": doan_bi_loai,
            "doan_loi": doan_loi}


def wer_cua(so_lieu):
    return (so_lieu["sai"] + so_lieu["thieu"] + so_lieu["thua"]) / so_lieu["tu"] if so_lieu["tu"] else 0.0


def dong_so_lieu(ten, s):
    toc_do = s["thoi_gian"] / s["do_dai"] if s["do_dai"] else 0.0
    return (f"{ten:<16} {s['doan']:>4} đoạn {s['tu']:>6} từ | sai {s['sai']:>4} | thiếu {s['thieu']:>4} "
            f"| thừa {s['thua']:>4} | WER {wer_cua(s):6.1%} | xử lý {toc_do:.2f}x độ dài")


def viet_bao_cao(ten_bo, cau_hinh, kq):
    d = []
    d.append(f"BÁO CÁO ĐÁNH GIÁ ASR: bộ {ten_bo}, cấu hình {cau_hinh}")
    d.append("=" * 100)
    if not kq["tong"]["tu"]:
        d.append("Chưa có đoạn nào đo được.")
        return "\n".join(d)
    d.append(dong_so_lieu("TỔNG", kq["tong"]))
    if len(kq["theo_nhom"]) > 1:
        d.append("\nTheo nhóm:")
        for nhom, s in sorted(kq["theo_nhom"].items(), key=lambda x: -wer_cua(x[1])):
            d.append("  " + dong_so_lieu(nhom, s))
    if kq["tong"]["tu"] < 1000:
        d.append(f"\n(Lưu ý: mới {kq['tong']['tu']} từ, WER còn dao động; nên tải thêm bằng --so-mau)")

    d.append("\nCÁC CẶP HAY NGHE NHẦM NHẤT (đáp án -> máy nghe)  ← nguồn để thêm luật sửa lỗi")
    for (goc, may), n in kq["cap_nham"].most_common(30):
        d.append(f"  {n:>3} lần | {goc} -> {may}")
    d.append("\nTỪ HAY BỊ BỎ SÓT  ← nhiều từ ngắn (à, ừ, thì, mà) là do model tự lược, ít hại;")
    d.append("                    từ có nghĩa bị sót nhiều thì cần xem lại VAD / bộ lọc [LOẠI]")
    d.append("  " + (", ".join(f"{t} ({n})" for t, n in kq["bo_sot"].most_common(25)) or "(không có)"))
    d.append("\nTỪ HAY BỊ THÊM VÀO  ← từ gợi ý (deadline, meeting...) xuất hiện ở đây là gợi ý gây bịa chữ")
    d.append("  " + (", ".join(f"{t} ({n})" for t, n in kq["them_vao"].most_common(25)) or "(không có)"))

    d.append(f"\nĐOẠN CÓ PHẦN BỊ BỘ LỌC [LOẠI] CẮT BỎ: {len(kq['doan_bi_loai'])}")
    d.append("  (thiếu nhiều từ so với đáp án = bộ lọc đã xóa nhầm lời thật -> cần chỉnh ngưỡng)")
    for muc, ket, thieu, so_tu in sorted(kq["doan_bi_loai"], key=lambda x: -x[2] / x[3])[:15]:
        d.append(f"  {muc['id']} ({muc['nhom']}): thiếu {thieu}/{so_tu} từ")
        for dong in ket["bi_loai"]:
            d.append(f"      {dong}")
        d.append(f"      Đáp án: {muc['text'][:150]}")

    d.append("\n15 ĐOẠN SAI NHIỀU NHẤT (mở file âm thanh nghe lại để biết vì sao)")
    for wer, muc, ket, dap_an, du_doan in sorted(kq["tung_doan"], key=lambda x: -x[0])[:15]:
        d.append(f"  {muc['id']} ({muc['nhom']}) WER {wer:.0%} | data/bo_danh_gia/{ten_bo}/{muc['tep']}")
        d.append(f"      Đáp án : {dap_an[:160]}")
        d.append(f"      Máy nghe: {du_doan[:160]}")

    if kq["doan_loi"]:
        d.append(f"\nĐOẠN KHÔNG ĐỌC ĐƯỢC ({len(kq['doan_loi'])}):")
        for muc, loi in kq["doan_loi"]:
            d.append(f"  {muc['id']}: {loi}")
    return "\n".join(d)


# ======================================================================
# CHƯƠNG TRÌNH CHÍNH
# ======================================================================
def main():
    parser = argparse.ArgumentParser(description="Đo WER của ASR trên các bộ dữ liệu đã tải.")
    parser.add_argument("bo", nargs="*", help="Tên bộ trong data/bo_danh_gia/ (bỏ trống = tất cả)")
    parser.add_argument("--model", default=asr.TEN_MODEL, help=f"Model Whisper (mặc định {asr.TEN_MODEL})")
    parser.add_argument("--so-mau", type=int, default=0, help="Chỉ chạy N đoạn đầu mỗi bộ (chạy thử nhanh)")
    parser.add_argument("--khong-goi-y", action="store_true", help="Tắt câu mở đầu và từ khóa gợi ý")
    parser.add_argument("--khong-tien-xu-ly", action="store_true", help="Tắt tiền xử lý âm thanh")
    parser.add_argument("--loc-nhieu", action="store_true", help="Bật giảm tạp âm")
    parser.add_argument("--chay-lai", action="store_true", help="Bỏ kết quả cũ, nhận dạng lại từ đầu")
    args = parser.parse_args()

    co_san = sorted(p.name for p in THU_MUC_BO.iterdir() if (p / "nhan.json").exists()) \
        if THU_MUC_BO.exists() else []
    if not co_san:
        sys.exit("Chưa có bộ dữ liệu nào. Chạy trước:  python src/asr/tai_bo_danh_gia.py")
    cac_bo = args.bo or co_san
    thieu = [b for b in cac_bo if b not in co_san]
    if thieu:
        sys.exit(f"Chưa tải bộ: {', '.join(thieu)}. Đã có: {', '.join(co_san)}")

    model = []

    def tai_model():  # chỉ tải model khi thật sự có đoạn cần nhận dạng
        if not model:
            print(f"Đang tải model {args.model}...")
            try:
                model.append(asr.WhisperModel(args.model, device="cpu", compute_type="int8"))
            except Exception as loi:
                sys.exit(f"Không tải được model {args.model}: {type(loi).__name__}: {loi}")
        return model[0]

    cau_hinh = ten_cau_hinh(args)
    THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
    tom_tat = []
    for ten_bo in cac_bo:
        cac_muc, ket_qua = chay_mot_bo(ten_bo, tai_model, args)
        kq = phan_tich(cac_muc, ket_qua)
        bao_cao = viet_bao_cao(ten_bo, cau_hinh, kq)
        tep = THU_MUC_BAO_CAO / f"{ten_bo}__{cau_hinh}.txt"
        tep.write_text(bao_cao + "\n", encoding="utf-8")
        print("\n" + bao_cao)
        print(f"\nĐã lưu báo cáo: {asr.hien_thi(tep)}")
        if kq["tong"]["tu"]:
            tom_tat.append(dong_so_lieu(ten_bo, kq["tong"]))

    if len(tom_tat) > 1:
        print(f"\nTÓM TẮT ({cau_hinh}):")
        for dong in tom_tat:
            print("  " + dong)


if __name__ == "__main__":
    main()
