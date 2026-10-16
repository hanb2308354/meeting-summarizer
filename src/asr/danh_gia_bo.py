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
    python src/asr/danh_gia_bo.py --so-sanh A B          (so 2 cấu hình, có khoảng tin cậy 95%)
    python src/asr/danh_gia_bo.py --chi-doan ID          (chạy lại 1 đoạn, in chi tiết để chẩn đoán)
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
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402
import danh_gia_wer  # noqa: E402

# Phần sửa lỗi nhận dạng của bước tiền xử lý văn bản (src/tien_xu_ly), để đo nó có giúp không
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tien_xu_ly"))
from lam_sach import chuan_hoa_unicode, sua_loi_nhan_dang  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THU_MUC_GOC = asr.THU_MUC_GOC
THU_MUC_BO = THU_MUC_GOC / "data" / "bo_danh_gia"
THU_MUC_BAO_CAO = THU_MUC_GOC / "outputs" / "danh_gia_asr"
# Tên cấu hình giữ đúng cách đặt của các lần đo trước, để file kết quả cũ vẫn so được:
# "medium" = câu mở đầu + từ khóa, thử lại tới 1.0 (cấu hình cũ)
HAU_TO_GOI_Y = {"day_du": "", "khong": "_khong_goi_y", "tu_khoa": "_chi_tu_khoa",
                "cau_mo_dau": "_chi_cau_mo_dau"}


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
    (r"\b(\w+) chục\b", r"\1 mươi"),              # "hai chục" như "20" -> "hai mươi"
    (r"\b(?:vắc xin|vaccine|vacxin|vắcxin)\b", "vắc xin"),
]


# Đơn vị viết tắt và cách đọc: "10km" và "mười ki lô mét" là một
DON_VI = {"km": "ki lô mét", "kg": "ki lô gam", "cm": "xen ti mét", "mm": "mi li mét",
          "m2": "mét vuông", "m²": "mét vuông", "ha": "héc ta"}
MAU_DON_VI = re.compile(r"(?<=\d)\s*(" + "|".join(map(re.escape, DON_VI)) + r")\b")
MAU_DON_VI_DOC = re.compile(r"\b(ki|xen|mi)[\s-]+(lô|ti|li)[\s-]+(mét|gam)\b")

# Chính tả có hai cách viết đều đúng: không tính là nghe sai
# - i/y: kì/kỳ, lí/lý, mĩ/mỹ...   - bỏ dấu kiểu cũ/mới: hoà/hòa, thuỷ/thủy
I_Y = {"kỳ": "kì", "ký": "kí", "kỷ": "kỉ", "lý": "lí", "mỹ": "mĩ", "sỹ": "sĩ", "hy": "hi", "qui": "quy"}
MAU_I_Y = re.compile(r"\b(" + "|".join(I_Y) + r")\b")
DAU_KIEU_CU = {"oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
               "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
               "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy"}
MAU_DAU_KIEU_CU = re.compile(r"(?<!q)(" + "|".join(DAU_KIEU_CU) + r")\b")   # "quý" giữ nguyên


def chuan_hoa_danh_gia(van_ban):
    van_ban = unicodedata.normalize("NFC", van_ban.lower())
    van_ban = MAU_DON_VI.sub(lambda m: " " + DON_VI[m[1]], van_ban)
    van_ban = MAU_DON_VI_DOC.sub(r"\1 \2 \3", van_ban)   # ki-lô-mét -> ki lô mét
    van_ban = re.sub(r"(\d+)\s*h\s*(\d+)?\b", lambda m: f"{m[1]} giờ {m[2] or ''}", van_ban)
    van_ban = re.sub(r"\b\d{1,3}(?:\.\d{3})+\b", lambda m: m[0].replace(".", ""), van_ban)  # 1.000.000
    van_ban = re.sub(r"(\d+)[,.](\d+)", r"\1 phẩy \2", van_ban)                              # 2,5
    van_ban = van_ban.replace("%", " phần trăm ")
    van_ban = re.sub(r"\d+", lambda m: f" {doc_so(m[0])} ", van_ban)
    van_ban = danh_gia_wer.chuan_hoa(van_ban)
    for mau, thay in BIEN_THE_SO:
        van_ban = re.sub(mau, thay, van_ban)
    van_ban = MAU_I_Y.sub(lambda m: I_Y[m[1]], van_ban)
    van_ban = MAU_DAU_KIEU_CU.sub(lambda m: DAU_KIEU_CU[m[1]], van_ban)
    return van_ban


# ======================================================================
# CHẠY ASR
# ======================================================================
def ten_model(model):
    """Tên ngắn của model để đặt tên file kết quả: thư mục models/phowhisper-medium-ct2 -> phowhisper-medium-ct2."""
    return re.split(r"[\\/]", model.rstrip("\\/"))[-1].lower() if re.search(r"[\\/]", model) else model


def ten_cau_hinh(args):
    ten = ten_model(args.model) + HAU_TO_GOI_Y[args.goi_y]
    if args.kieu_tinh != asr.KIEU_TINH:
        ten += f"_{args.kieu_tinh}"
    if args.thu_lai == "gioi_han":
        ten += "_gioi_han_thu_lai"
    if args.theo_khuc:
        ten += "_theo_khuc"
    if args.tung_luot:
        ten += "_tung_luot"
    if args.khong_moc_thoi_gian:
        ten += "_khong_moc"
    if args.dem_im_lang:
        ten += "_dem_lang"
    if args.beam != asr.BEAM:
        ten += f"_beam{args.beam}"
    if (args.token_moi_giay, args.token_cong_them) != (asr.TOKEN_MOI_GIAY, asr.TOKEN_CONG_THEM):
        ten += f"_token{args.token_moi_giay}-{args.token_cong_them}"
    if args.so_luong != asr.SO_LUONG_CPU:   # chỉ đổi tốc độ, nhưng để riêng cho số "xử lý ...x" so được
        ten += f"_luong{args.so_luong}"
    if args.khong_tien_xu_ly:
        ten += "_khong_tien_xu_ly"
    if args.loc_nhieu:
        ten += "_loc_nhieu"
    return ten


def nhan_dang_mot_doan(model, duong_dan, args):
    """Trả về chữ máy nghe được, các dòng [LOẠI], độ dài (giây) và thời gian xử lý."""
    bat_dau = time.time()
    song_am = asr.doc_am_thanh(duong_dan)
    if not args.khong_tien_xu_ly:
        song_am, _ = asr.tien_xu_ly_am_thanh(song_am, args.loc_nhieu)
    dau_ra = io.StringIO()
    nhat_ky = []
    with contextlib.redirect_stdout(dau_ra):  # nhan_dang in từng đoạn: gom lại, chỉ giữ dòng [LOẠI]
        nhiet_do = asr.NHIET_DO_THU_LAI if args.thu_lai == "gioi_han" else None
        cac_tu, _ = asr.nhan_dang(model, song_am, goi_y=args.goi_y, nhiet_do=nhiet_do,
                                  theo_khuc=args.theo_khuc, tung_luot=args.tung_luot, nhat_ky=nhat_ky,
                                  khong_moc_thoi_gian=args.khong_moc_thoi_gian, dem_im_lang=args.dem_im_lang,
                                  beam=args.beam, token_moi_giay=args.token_moi_giay,
                                  token_cong_them=args.token_cong_them)
    return {
        "du_doan": " ".join(cau["text"] for cau in asr.tach_cau(cac_tu)),
        "bi_loai": [d.strip() for d in dau_ra.getvalue().splitlines() if "[LOẠI" in d],
        "do_dai": round(len(song_am) / asr.TAN_SO_MAU, 2),
        "thoi_gian": round(time.time() - bat_dau, 2),
        "chi_tiet": nhat_ky,   # từng đoạn model trả về + các lượt VAD: để chẩn đoán, không dùng tính WER
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
    return (f"{ten[:24]:<24} {s['doan']:>4} đoạn {s['tu']:>6} từ | sai {s['sai']:>4} | thiếu {s['thieu']:>4} "
            f"| thừa {s['thua']:>4} | WER {wer_cua(s):6.1%} | xử lý {toc_do:.2f}x độ dài")


def so_voi_doan_ngan(kq, cau_hinh):
    """Bộ file dài (ghep_file_dai.py): WER khi nghe từng đoạn ngắn của chính các đoạn đã ghép."""
    cac_dong = []
    tong_dai, tong_ngan = Counter(), Counter()
    for _, muc, ket, dap_an, du_doan in kq["tung_doan"]:
        if "tu_doan" not in muc:
            continue
        thu_muc_nguon = THU_MUC_BO / muc["nguon_bo"]
        nhan = {m["id"]: m for m in doc_json(thu_muc_nguon / "nhan.json", [])}
        ket_ngan = doc_json(thu_muc_nguon / f"ket_qua__{cau_hinh}.json", {})
        if not all(i in ket_ngan and "loi" not in ket_ngan[i] for i in muc["tu_doan"]):
            cac_dong.append(f"  {muc['id']}: chưa có kết quả nghe từng đoạn ngắn của bộ "
                            f"{muc['nguon_bo']} (cấu hình {cau_hinh}) để so")
            continue
        ngan = Counter()
        for i in muc["tu_doan"]:
            goc = chuan_hoa_danh_gia(nhan[i]["text"])
            ngan.update(tu=len(goc.split()), loi=so_loi(goc, chuan_hoa_danh_gia(ket_ngan[i]["du_doan"])))
        dai = Counter(tu=len(dap_an.split()), loi=so_loi(dap_an, du_doan))
        tong_dai.update(dai)
        tong_ngan.update(ngan)
        cac_dong.append(f"  {muc['id']} ({ket['do_dai'] / 60:.1f} phút): file dài WER {dai['loi'] / dai['tu']:.1%}"
                        f" | nghe từng đoạn ngắn {ngan['loi'] / ngan['tu']:.1%}"
                        f" | đoạn bị [LOẠI] {len(ket['bi_loai'])}")
    if not cac_dong:
        return []
    d = ["\nSO VỚI NGHE TỪNG ĐOẠN NGẮN (cùng lời, cùng cấu hình)  ← file dài tệ hơn nhiều = lỗi riêng của file dài"]
    d += cac_dong
    if tong_dai["tu"] and tong_ngan["tu"]:
        d.append(f"  TỔNG: file dài {tong_dai['loi'] / tong_dai['tu']:.1%} | "
                 f"từng đoạn ngắn {tong_ngan['loi'] / tong_ngan['tu']:.1%}")
    return d


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

    d += so_voi_doan_ngan(kq, cau_hinh)

    # Model bị kẹt (thử lại nhiều lần ở nhiệt độ cao) thì chạy lâu gấp nhiều lần bình thường
    ti_le = [(k["thoi_gian"] / k["do_dai"], m, k) for _, m, k, _, _ in kq["tung_doan"] if k["do_dai"]]
    if len(ti_le) >= 5:
        trung_vi = sorted(t for t, _, _ in ti_le)[len(ti_le) // 2]
        lau = sorted([x for x in ti_le if x[0] > 3 * trung_vi], key=lambda x: -x[0])
        d.append(f"\nĐOẠN XỬ LÝ LÂU BẤT THƯỜNG (> 3 lần mức thường {trung_vi:.1f}x): {len(lau)}"
                 "  ← thường là model bị kẹt, hay đi kèm chữ bịa hoặc ra trống")
        for t, muc, ket in lau:
            d.append(f"  {muc['id']} ({muc['nhom']}): {ket['thoi_gian']:.0f}s cho {ket['do_dai']:.0f}s âm thanh"
                     f" ({t:.1f}x) | máy nghe: {ket['du_doan'][:80] or '(trống)'}")

    if kq["doan_loi"]:
        d.append(f"\nĐOẠN KHÔNG ĐỌC ĐƯỢC ({len(kq['doan_loi'])}):")
        for muc, loi in kq["doan_loi"]:
            d.append(f"  {muc['id']}: {loi}")
    return "\n".join(d)


def so_sanh_cau_hinh(ten_bo, cac_cau_hinh):
    """So các cấu hình đã chạy trên cùng các đoạn: bảng tổng, theo nhóm, và các đoạn khác biệt nhiều."""
    thu_muc = THU_MUC_BO / ten_bo
    cac_muc = doc_json(thu_muc / "nhan.json", [])
    d = [f"SO SÁNH CẤU HÌNH: bộ {ten_bo}", "=" * 100]
    ket = {}
    for ch in cac_cau_hinh:
        tep = thu_muc / f"ket_qua__{ch}.json"
        if not tep.exists():
            co = sorted(t.stem.split("__", 1)[1] for t in thu_muc.glob("ket_qua__*.json"))
            d.append(f"  (chưa chạy cấu hình {ch}; đã có: {', '.join(co) or 'chưa có'})")
            continue
        ket[ch] = doc_json(tep, {})
    # Chỉ so trên các đoạn mà mọi cấu hình đều đã chạy xong, cho công bằng
    chung = [m for m in cac_muc if all(m["id"] in k for k in ket.values())]
    if len(ket) < 2 or not chung:
        d.append("Cần ít nhất 2 cấu hình đã chạy trên cùng các đoạn.")
        return "\n".join(d)
    d.append(f"Trên {len(chung)} đoạn mọi cấu hình đều đã chạy:\n")
    phan = {ch: phan_tich(chung, k) for ch, k in ket.items()}
    for ch, kq in phan.items():
        d.append("  " + dong_so_lieu(ch, kq["tong"]))
    cac_nhom = sorted({m["nhom"] for m in chung})
    if len(cac_nhom) > 1:
        d.append("\nWER theo nhóm:")
        d.append("  " + f"{'':<24}" + "".join(f"{ch[:22]:>24}" for ch in phan))
        for nhom in cac_nhom:
            d.append("  " + f"{nhom[:24]:<24}" + "".join(
                f"{wer_cua(kq['theo_nhom'][nhom]):>24.1%}" for kq in phan.values()))

    d += khac_biet_that_hay_ngau_nhien(chung, ket)

    wer_doan = {ch: {m["id"]: (w, du) for w, m, _, _, du in kq["tung_doan"]} for ch, kq in phan.items()}
    khac = []
    for muc in chung:
        cac_wer = [wer_doan[ch].get(muc["id"], (None, ""))[0] for ch in phan]
        if None not in cac_wer and max(cac_wer) - min(cac_wer) >= 0.2:
            khac.append((max(cac_wer) - min(cac_wer), muc))
    d.append(f"\nĐOẠN KHÁC BIỆT NHIỀU GIỮA CÁC CẤU HÌNH (WER lệch >= 20 điểm): {len(khac)}")
    for _, muc in sorted(khac, key=lambda x: -x[0]):
        d.append(f"  {muc['id']} ({muc['nhom']})")
        d.append(f"      {'Đáp án':<22}: {chuan_hoa_danh_gia(muc['text'])[:130]}")
        for ch in phan:
            w, du = wer_doan[ch][muc["id"]]
            d.append(f"      {ch[:16]:<16} {w:>4.0%}: {du[:130] or '(trống)'}")
    return "\n".join(d)


SO_LAN_LAY_MAU = 2000


def khoang_tin_cay(cac_cap, so_lan=SO_LAN_LAY_MAU, hat_giong=0):
    """Bootstrap ghép cặp: bốc ngẫu nhiên có lặp lại các đoạn, tính lại chênh WER (B - A) nhiều lần.

    cac_cap: [(số từ, lỗi cấu hình A, lỗi cấu hình B)] trên CÙNG các đoạn.
    Trả về (chênh WER, cận dưới 95%, cận trên 95%) tính bằng tỉ lệ (0.01 = 1 điểm).
    """
    tu, a, b = (np.array(c, dtype=float) for c in zip(*cac_cap))
    chi_so = np.random.default_rng(hat_giong).integers(0, len(tu), (so_lan, len(tu)))
    tong_tu = tu[chi_so].sum(axis=1)
    chenh = (b[chi_so].sum(axis=1) - a[chi_so].sum(axis=1)) / np.maximum(tong_tu, 1)
    return (b.sum() - a.sum()) / tu.sum(), float(np.percentile(chenh, 2.5)), float(np.percentile(chenh, 97.5))


def loi_theo_doan_ghep(muc, du_doan):
    """File dài ghép từ nhiều đoạn ngắn: chia lỗi về từng đoạn ngắn đã ghép.

    Lời gốc của file dài là lời các đoạn nối theo thứ tự, nên sau khi căn chữ máy nghe với lời gốc,
    mỗi lỗi sai/thiếu thuộc về đoạn chứa từ gốc đó; từ thừa tính cho đoạn đứng ngay trước nó.
    4 file dài thành ~100 đơn vị, khoảng tin cậy hẹp lại. Trả về [(số từ, số lỗi)] theo từng đoạn,
    hoặc None nếu không chia được (thiếu lời gốc của bộ nguồn).
    """
    nhan = {m["id"]: m for m in doc_json(THU_MUC_BO / muc["nguon_bo"] / "nhan.json", [])}
    if not all(i in nhan for i in muc["tu_doan"]):
        return None
    cac_tu_goc, thuoc_doan = [], []
    for so, i in enumerate(muc["tu_doan"]):
        tu = chuan_hoa_danh_gia(nhan[i]["text"]).split()
        cac_tu_goc += tu
        thuoc_doan += [so] * len(tu)
    if not cac_tu_goc:
        return None
    dem = [[0, 0] for _ in muc["tu_doan"]]
    for so in thuoc_doan:
        dem[so][0] += 1
    do = jiwer.process_words(" ".join(cac_tu_goc), du_doan or "")
    for khuc in do.alignments[0]:
        if khuc.type in ("substitute", "delete"):
            for vi_tri in range(khuc.ref_start_idx, khuc.ref_end_idx):
                dem[thuoc_doan[vi_tri]][1] += 1
        elif khuc.type == "insert":
            so = thuoc_doan[max(0, min(khuc.ref_start_idx, len(thuoc_doan)) - 1)]
            dem[so][1] += khuc.hyp_end_idx - khuc.hyp_start_idx
    return [(tu, loi) for tu, loi in dem if tu]


def khac_biet_that_hay_ngau_nhien(chung, ket):
    """So từng cấu hình với cấu hình ĐẦU TIÊN: chênh WER kèm khoảng tin cậy 95%.

    Khoảng tin cậy chứa 0 nghĩa là chênh lệch có thể chỉ do may rủi của các đoạn được chọn:
    chưa đủ bằng chứng để đổi mặc định.
    """
    cac_ch = list(ket)
    goc = cac_ch[0]
    d = [f"\nKHÁC BIỆT THẬT HAY NGẪU NHIÊN? (so với {goc}, khoảng tin cậy 95%, bootstrap theo đoạn)"]
    for ch in cac_ch[1:]:
        cac_cap, tot, te, so_muc = [], 0, 0, 0
        for muc in chung:
            ka, kb = ket[goc][muc["id"]], ket[ch][muc["id"]]
            dap_an = chuan_hoa_danh_gia(muc["text"])
            if "loi" in ka or "loi" in kb or not dap_an:
                continue
            la = so_loi(dap_an, chuan_hoa_danh_gia(ka["du_doan"]))
            lb = so_loi(dap_an, chuan_hoa_danh_gia(kb["du_doan"]))
            tot += lb < la
            te += lb > la
            so_muc += 1
            if "tu_doan" in muc:   # file dài: lấy mẫu theo từng đoạn ngắn đã ghép, không theo cả file
                chia_a = loi_theo_doan_ghep(muc, chuan_hoa_danh_gia(ka["du_doan"]))
                chia_b = loi_theo_doan_ghep(muc, chuan_hoa_danh_gia(kb["du_doan"]))
                if chia_a and chia_b:
                    cac_cap += [(tu, a, b) for (tu, a), (_, b) in zip(chia_a, chia_b)]
                    continue
            cac_cap.append((len(dap_an.split()), la, lb))
        if not cac_cap:
            continue
        chenh, duoi, tren = khoang_tin_cay(cac_cap)
        if duoi > 0:
            ket_luan = "TỆ HƠN THẬT"
        elif tren < 0:
            ket_luan = "TỐT HƠN THẬT"
        else:
            ket_luan = "CHƯA CHẮC (có thể chỉ do ngẫu nhiên)"
        d.append(f"  {ch[:40]:<40} WER {chenh * 100:+.1f} điểm  [95%: {duoi * 100:+.1f} .. {tren * 100:+.1f}]"
                 f"  -> {ket_luan} | tốt hơn ở {tot} đoạn, tệ hơn ở {te}, bằng nhau {so_muc - tot - te}")
        if len(cac_cap) > so_muc:
            d.append(f"      (file dài: lấy mẫu trên {len(cac_cap)} đoạn ngắn đã ghép thành {so_muc} file)")
        if len(cac_cap) < 20:
            d.append(f"      (chỉ có {len(cac_cap)} đơn vị: khoảng tin cậy kém chính xác, nên đo thêm)")
    return d


DAU_HIEU = [
    (lambda c: c["khong_co_tieng"] > 0.6 and c["do_tin_cay"] < -0.7,
     "model nghĩ chỗ này KHÔNG có tiếng mà vẫn ra chữ -> nghi bịa"),
    (lambda c: c["ty_le_nen"] > 2.4, "chữ lặp nhiều (tỉ lệ nén cao) -> nghi kẹt vòng lặp"),
    (lambda c: (c["nhiet_do"] or 0) > 0, "model phải thử lại ở nhiệt độ cao -> lần đầu ra kết quả tệ"),
    (lambda c: c["do_tin_cay"] < -1.0, "độ tin cậy rất thấp -> nghe không rõ / giọng khó"),
]


def bao_cao_chi_doan(ten_bo, cau_hinh, muc, kq, kq_cu=None):
    """Mọi thứ cần để biết VÌ SAO một đoạn sai: lỗi theo vị trí, các lượt VAD, chỉ số từng đoạn."""
    d = [f"CHẨN ĐOÁN ĐOẠN {muc['id']} (bộ {ten_bo}, nhóm {muc['nhom']}, cấu hình {cau_hinh})",
         f"File: data/bo_danh_gia/{ten_bo}/{muc['tep']}", "=" * 100]
    if "loi" in kq:
        return "\n".join(d + [f"Không đọc được: {kq['loi']}"])
    dap_an, du_doan = chuan_hoa_danh_gia(muc["text"]), chuan_hoa_danh_gia(kq["du_doan"])
    do = jiwer.process_words(dap_an, du_doan)
    so_tu = len(dap_an.split())
    d.append(f"WER {so_loi(dap_an, du_doan) / max(so_tu, 1):.1%} ({so_tu} từ: sai {do.substitutions}, "
             f"thiếu {do.deletions}, thừa {do.insertions}) | {kq['do_dai']:.1f}s âm thanh, xử lý {kq['thoi_gian']:.1f}s")
    if kq_cu and "loi" not in kq_cu:
        d.append(f"Kết quả đã lưu trước đó (cùng cấu hình): WER "
                 f"{so_loi(dap_an, chuan_hoa_danh_gia(kq_cu['du_doan'])) / max(so_tu, 1):.1%}"
                 "  ← khác nhiều = code đã đổi hành vi ở đoạn này")
    d.append(f"\nĐáp án : {dap_an}")
    d.append(f"Máy nghe: {du_doan or '(trống)'}")

    d.append("\nCHỖ SAI (theo thứ tự trong câu)")
    tu_goc, tu_may = do.references[0], do.hypotheses[0]
    for khuc in do.alignments[0]:
        goc = " ".join(tu_goc[khuc.ref_start_idx:khuc.ref_end_idx])
        may = " ".join(tu_may[khuc.hyp_start_idx:khuc.hyp_end_idx])
        if khuc.type == "substitute":
            d.append(f"  [nghe nhầm] {goc}  ->  {may}")
        elif khuc.type == "delete":
            d.append(f"  [bỏ sót]    {goc}")
        elif khuc.type == "insert":
            d.append(f"  [thêm vào]  {may}")

    chi_tiet = kq.get("chi_tiet", [])
    luot = [c["luot"] for c in chi_tiet if "luot" in c]
    if luot:
        d.append(f"\nCÁC LƯỢT NÓI VAD CẮT RA: {len(luot)}")
        d.append("  " + ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in luot))
    thu_lai = [c for c in chi_tiet if "thu_lai" in c]
    if thu_lai:
        d.append("\nLƯỢT BỊ NGHE HỎNG (quá ít chữ so với độ dài) VÀ CÁC LẦN NHẬN DẠNG LẠI")
        for c in thu_lai:
            if c["thu_lai"] == "chọn":
                d.append(f"  => chọn: {c['cach']}")
            else:
                d.append(f"  {c['thu_lai']:<24} {c['so_chu']:>3} chữ thật | {c['chu'] or '(trống)'}")
    ngoai = [c for c in chi_tiet if "ngoai_am_thanh" in c]
    if ngoai:
        d.append("\nCHỮ BỎ VÌ NẰM SAU CUỐI ÂM THANH THẬT CỦA LƯỢT (trong phần im lặng đệm thêm)")
        for c in ngoai:
            d.append(f"  sau {c['sau_giay']:.1f}s: {c['ngoai_am_thanh'][:150]}")
    cac_doan = [c for c in chi_tiet if "text" in c]
    d.append(f"\nCÁC ĐOẠN MODEL TRẢ VỀ: {len(cac_doan)}"
             "  (tin cậy: gần 0 là chắc chắn; không tiếng: xác suất model nghĩ chỗ đó im lặng)")
    for c in cac_doan:
        d.append(f"  [{c['start']:7.2f} -> {c['end']:7.2f}] tin cậy {c['do_tin_cay']:+.2f} | không tiếng "
                 f"{c['khong_co_tieng']:.2f} | nén {c['ty_le_nen']:.1f} | nhiệt độ {c['nhiet_do']}"
                 f" | {c.get('so_token', '?')} token / {len(c['text'].split())} từ"
                 + (f" | BỊ LOẠI: {c['loai']}" if c["loai"] else ""))
        d.append(f"      {c['text'][:150]}")
        for dieu_kien, y_nghia in DAU_HIEU:
            if dieu_kien(c):
                d.append(f"      ⚠ {y_nghia}")
    if not chi_tiet:
        d.append("  (kết quả này chưa có chi tiết: chạy lại với --chi-doan)")
    cac_doan_co_token = [c for c in cac_doan if "so_token" in c]
    if cac_doan_co_token:
        giu = [c for c in cac_doan_co_token if not c["loai"]]
        bo = [c for c in cac_doan_co_token if c["loai"]]
        d.append(f"\nTOKEN MODEL ĐÃ SINH: {sum(c['so_token'] for c in cac_doan_co_token)} "
                 f"(giữ {sum(c['so_token'] for c in giu)}, bị loại {sum(c['so_token'] for c in bo)})"
                 f" | token/từ của lời được giữ: "
                 f"{sum(c['so_token'] for c in giu) / max(1, sum(len(c['text'].split()) for c in giu)):.2f}"
                 "  ← token bị loại nhiều = thời gian chạy đổ vào chữ bịa")
    return "\n".join(d)


def so_loi(dap_an, du_doan):
    do = jiwer.process_words(dap_an, du_doan) if dap_an else None
    return (do.substitutions + do.deletions + do.insertions) if do else 0


def kiem_sua_loi(ten_bo, cau_hinh):
    """Đo bảng sửa lỗi (src/tien_xu_ly SUA_LOI) trên chữ máy nghe được: sửa đúng hay sửa sai.

    Không chạy ASR: dùng kết quả đã lưu của cấu hình cau_hinh.
    """
    thu_muc = THU_MUC_BO / ten_bo
    cac_muc = doc_json(thu_muc / "nhan.json", [])
    ket_qua = doc_json(thu_muc / f"ket_qua__{cau_hinh}.json", {})
    d = [f"KIỂM BẢNG SỬA LỖI (src/tien_xu_ly): bộ {ten_bo}, kết quả ASR của cấu hình {cau_hinh}",
         "=" * 100]
    if not ket_qua:
        d.append(f"Chưa có kết quả cấu hình {cau_hinh}. Chạy danh_gia_bo.py trước.")
        return "\n".join(d)
    tong_tu = tong_truoc = tong_sau = 0
    tot, xau, doi_khong_anh_huong = [], [], []
    for muc in cac_muc:
        kq = ket_qua.get(muc["id"])
        if not kq or "loi" in kq:
            continue
        dap_an = chuan_hoa_danh_gia(muc["text"])
        truoc = kq["du_doan"]
        sau = sua_loi_nhan_dang(chuan_hoa_unicode(truoc))
        loi_truoc = so_loi(dap_an, chuan_hoa_danh_gia(truoc))
        loi_sau = so_loi(dap_an, chuan_hoa_danh_gia(sau))
        tong_tu += len(dap_an.split())
        tong_truoc += loi_truoc
        tong_sau += loi_sau
        if chuan_hoa_danh_gia(truoc) != chuan_hoa_danh_gia(sau):
            nhom = tot if loi_sau < loi_truoc else xau if loi_sau > loi_truoc else doi_khong_anh_huong
            nhom.append((muc, truoc, sau, loi_truoc, loi_sau))
    if not tong_tu:
        d.append("Không có đoạn nào để đo.")
        return "\n".join(d)
    d.append(f"WER trước khi sửa: {tong_truoc / tong_tu:.1%} | sau khi sửa: {tong_sau / tong_tu:.1%} "
             f"({tong_tu} từ)")
    d.append(f"Đoạn bị bảng sửa lỗi đổi chữ: {len(tot) + len(xau) + len(doi_khong_anh_huong)} "
             f"(sửa đúng {len(tot)}, sửa SAI {len(xau)}, đổi nhưng không ảnh hưởng {len(doi_khong_anh_huong)})")
    for tieu_de, cac in (("SỬA SAI (luật sửa lỗi bắt nhầm, cần thu hẹp)", xau),
                         ("SỬA ĐÚNG", tot), ("ĐỔI NHƯNG KHÔNG ẢNH HƯỞNG WER", doi_khong_anh_huong)):
        if cac:
            d.append(f"\n{tieu_de}:")
            for muc, truoc, sau, a, b in cac:
                d.append(f"  {muc['id']} (lỗi {a} -> {b})")
                d.append(f"      Đáp án : {muc['text'][:150]}")
                d.append(f"      Trước  : {truoc[:150]}")
                d.append(f"      Sau    : {sau[:150]}")
    return "\n".join(d)


# ======================================================================
# CHƯƠNG TRÌNH CHÍNH
# ======================================================================
def loc_lai(ten_bo, cau_hinh):
    """Chấm lại kết quả ĐÃ LƯU với bộ lọc [LOẠI] hiện tại, không chạy lại nhận dạng (vài giây).

    Dựng lại chữ máy nghe từ "chi_tiet" (các đoạn model trả về), bỏ đoạn mà bộ lọc hiện tại loại.
    Là ƯỚC TÍNH: không tái hiện được việc nghe lại lượt hỏng (cần chạy model). Ghi ra cấu hình
    <cau_hinh>_loc_lai để so bằng --so-sanh; muốn số chính xác thì chạy lại thật với --chay-lai.
    """
    from types import SimpleNamespace
    thu_muc = THU_MUC_BO / ten_bo
    cu = doc_json(thu_muc / f"ket_qua__{cau_hinh}.json", {})
    moi, thieu_chi_tiet, so_doan_bo = {}, 0, 0
    for id_doan, kq in cu.items():
        cac_doan = [c for c in kq.get("chi_tiet", []) if "text" in c]
        if "loi" in kq or not cac_doan:
            thieu_chi_tiet += "loi" not in kq
            moi[id_doan] = kq
            continue
        giu, bi_loai = [], []
        for c in cac_doan:
            doan = SimpleNamespace(text=c["text"], start=c["start"], end=c["end"], avg_logprob=c["do_tin_cay"],
                                   no_speech_prob=c["khong_co_tieng"], compression_ratio=c["ty_le_nen"], words=None)
            ly_do = c["loai"] or asr.ly_do_loai(doan)
            (bi_loai if ly_do else giu).append((c, ly_do))
        so_doan_bo += sum(1 for c, _ in bi_loai if not c["loai"])
        moi[id_doan] = dict(kq, du_doan=" ".join(c["text"] for c, _ in giu),
                            bi_loai=[f"[LOẠI - {l}] [{c['start']:7.2f} --> {c['end']:7.2f}] {c['text']}"
                                     for c, l in bi_loai])
    ten_moi = f"{cau_hinh}_loc_lai"
    ghi_json(moi, thu_muc / f"ket_qua__{ten_moi}.json")
    return ten_moi, so_doan_bo, thieu_chi_tiet


class DoThoiGian:
    """Bọc model CTranslate2 bên trong faster-whisper: đếm số lần gọi và thời gian từng bước
    (encode = nghe cửa sổ 30 giây, generate = sinh chữ, kể cả các lần thử lại ở nhiệt độ cao hơn,
    align = dò mốc thời gian theo từ). Phần còn lại là tính phổ âm thanh, VAD, lọc, tách câu."""

    BUOC = ("encode", "generate", "align")

    def __init__(self, goc):
        self._goc = goc
        self.so_lan = Counter()
        self.giay = Counter()
        self.so_token = 0

    def __getattr__(self, ten):
        thuoc_tinh = getattr(self._goc, ten)
        if ten not in self.BUOC:
            return thuoc_tinh

        def bao(*a, **k):
            bat_dau = time.time()
            kq = thuoc_tinh(*a, **k)
            self.giay[ten] += time.time() - bat_dau
            self.so_lan[ten] += 1
            if ten == "generate":
                self.so_token += sum(len(r.sequences_ids[0]) for r in kq if getattr(r, "sequences_ids", None))
            return kq
        return bao

    def bao_cao(self, tong_giay, so_giay_am_thanh, so_lan_nghe):
        d = [f"\nTHỜI GIAN TỪNG BƯỚC: {tong_giay:.0f}s cho {so_giay_am_thanh:.0f}s âm thanh "
             f"({tong_giay / max(so_giay_am_thanh, 1):.1f}x), {so_lan_nghe} lần gọi nhận dạng (lượt + nghe lại)"]
        for ten, y_nghia in (("encode", "nghe cửa sổ 30 giây"), ("generate", "sinh chữ (gồm thử lại nhiệt độ)"),
                             ("align", "dò mốc thời gian theo từ")):
            d.append(f"  {ten:<9} {y_nghia:<32} {self.so_lan[ten]:>4} lần  {self.giay[ten]:7.1f}s "
                     f"({self.giay[ten] / max(tong_giay, 1e-9):5.1%})")
        con_lai = tong_giay - sum(self.giay.values())
        d.append(f"  {'khác':<9} {'phổ âm thanh, VAD, lọc, tách câu':<32} {'':>4}       {con_lai:7.1f}s "
                 f"({con_lai / max(tong_giay, 1e-9):5.1%})")
        d.append(f"  token đã sinh: {self.so_token} | lần sinh chữ / lần gọi nhận dạng: "
                 f"{self.so_lan['generate'] / max(so_lan_nghe, 1):.2f}  ← > 1 là có thử lại ở nhiệt độ cao hơn")
        return "\n".join(d)


CAC_GIOI_HAN_THU = [(20, 30), (16, 20), (14, 15), (12, 15), (12, 10), (10, 10), (8, 10)]


def tim_tokenizer(model):
    """tokenizer.json của Whisper (PhoWhisper dùng chung bộ tách token với Whisper đa ngôn ngữ)."""
    cac_cho = [Path(model) / "tokenizer.json"] + sorted((THU_MUC_GOC / "models").glob("*/tokenizer.json"))
    for tep in cac_cho:
        if tep.exists():
            from tokenizers import Tokenizer
            return Tokenizer.from_file(str(tep))
    return None


def thong_ke_token(cac_bo, cau_hinh, model):
    """Mỗi lượt nói: số token của lời được giữ (ước tính bằng chính bộ tách token của model) so với
    giới hạn token. Lượt có lời thật nhiều token hơn giới hạn = giới hạn đó sẽ cắt mất lời.

    Không chạy model. Lời được giữ đã bỏ câu bịa, nên đây là số token model CẦN sinh; phần
    giới hạn còn dư là số token PhoWhisper (không biết dừng) sinh phí cho câu bịa."""
    tach = tim_tokenizer(model)
    d = [f"THỐNG KÊ TOKEN MỖI LƯỢT: cấu hình {cau_hinh}", "=" * 100]
    if tach is None:
        return "\n".join(d + ["Không tìm thấy tokenizer.json (cần thư mục models/<model>-ct2)."])
    cac_luot = []   # (giây, số token lời thật, id đoạn)
    for ten_bo in cac_bo:
        for id_doan, kq in doc_json(THU_MUC_BO / ten_bo / f"ket_qua__{cau_hinh}.json", {}).items():
            chi_tiet = kq.get("chi_tiet", [])
            luot = [c["luot"] for c in chi_tiet if "luot" in c]
            doan = [c for c in chi_tiet if "text" in c and not c["loai"]]
            for a, b in luot:
                trong = [c for c in doan if a <= (c["start"] + c["end"]) / 2 < b + asr.LE_CUOI_LUOT]
                # +2 token mốc thời gian mỗi đoạn, +1 token kết thúc
                so = sum(len(tach.encode(" " + c["text"]).ids) + 2 for c in trong) + 1
                cac_luot.append((b - a, so, id_doan))
    if not cac_luot:
        return "\n".join(d + ["Chưa có kết quả có chi tiết lượt nói (chạy lại cấu hình này)."])
    toc_do = sorted(so / max(g, 0.5) for g, so, _ in cac_luot)
    phan_vi = lambda p: toc_do[min(len(toc_do) - 1, int(p * len(toc_do)))]
    d.append(f"{len(cac_luot)} lượt, {sum(g for g, _, _ in cac_luot):.0f} giây. Token lời thật / giây: "
             f"trung vị {phan_vi(0.5):.1f}, 95% {phan_vi(0.95):.1f}, 99% {phan_vi(0.99):.1f}, cao nhất {toc_do[-1]:.1f}")
    d.append("\nGIỚI HẠN (token/giây x giây + cộng thêm) | lượt bị cắt lời | tổng token tối đa so với hiện tại")
    goc = sum(min(int(asr.TOKEN_MOI_GIAY * g) + asr.TOKEN_CONG_THEM, asr.TOKEN_TOI_DA) for g, _, _ in cac_luot)
    for a, b in CAC_GIOI_HAN_THU:
        gioi_han = [min(int(a * g) + b, asr.TOKEN_TOI_DA) for g, _, _ in cac_luot]
        bi_cat = [(g, so, i) for (g, so, i), gh in zip(cac_luot, gioi_han) if so > gh]
        d.append(f"  {a:>2} x giây + {b:<3} | {len(bi_cat):>3} lượt | {sum(gioi_han) / goc:6.1%}"
                 + (f"  vd {bi_cat[0][2]}: {bi_cat[0][0]:.1f}s cần {bi_cat[0][1]} token" if bi_cat else ""))
    d.append("\nChọn giới hạn sát nhất mà 0 lượt bị cắt, rồi chạy thật để đo tốc độ và WER.")
    return "\n".join(d)


def chay_chi_doan(cac_bo, args, cau_hinh, tai_model):
    con_lai = list(dict.fromkeys(args.chi_doan))
    so_giay, thoi_gian = 0.0, 0.0
    for ten_bo in cac_bo:
        thu_muc = THU_MUC_BO / ten_bo
        nhan = {m["id"]: m for m in doc_json(thu_muc / "nhan.json", [])}
        ket_cu = doc_json(thu_muc / f"ket_qua__{cau_hinh}.json", {})
        for id_doan in [i for i in con_lai if i in nhan]:
            con_lai.remove(id_doan)
            muc = nhan[id_doan]
            print(f"Đang nhận dạng lại {id_doan}...")
            try:
                kq = nhan_dang_mot_doan(tai_model(), thu_muc / muc["tep"], args)
            except asr.LoiDauVao as loi:
                kq = {"loi": str(loi)}
            so_giay += kq.get("do_dai", 0.0)
            thoi_gian += kq.get("thoi_gian", 0.0)
            bao_cao = bao_cao_chi_doan(ten_bo, cau_hinh, muc, kq, ket_cu.get(id_doan))
            tep = THU_MUC_BAO_CAO / f"{id_doan}__{cau_hinh}__chi_tiet.txt"
            tep.write_text(bao_cao + "\n", encoding="utf-8")
            print("\n" + bao_cao + f"\n\nĐã lưu: {asr.hien_thi(tep)}\n")
    if con_lai:
        print(f"Không tìm thấy đoạn: {', '.join(con_lai)} (trong các bộ {', '.join(cac_bo)})")
    return so_giay, thoi_gian


def main():
    parser = argparse.ArgumentParser(description="Đo WER của ASR trên các bộ dữ liệu đã tải.")
    parser.add_argument("bo", nargs="*", help="Tên bộ trong data/bo_danh_gia/ (bỏ trống = tất cả)")
    parser.add_argument("--model", default=asr.TEN_MODEL, help=f"Model Whisper (mặc định {asr.TEN_MODEL})")
    parser.add_argument("--kieu-tinh", default=asr.KIEU_TINH, choices=["int8", "int8_float32", "float32"],
                        help=f"Kiểu tính trên CPU (mặc định {asr.KIEU_TINH}); float32 chậm hơn nhưng không làm tròn trọng số")
    parser.add_argument("--so-mau", type=int, default=0, help="Chỉ chạy N đoạn đầu mỗi bộ (chạy thử nhanh)")
    parser.add_argument("--goi-y", choices=list(HAU_TO_GOI_Y), default=asr.GOI_Y_MAC_DINH,
                        help=f"Cách gợi ý cho model (mặc định {asr.GOI_Y_MAC_DINH}, giống chuyen_giong_noi.py)")
    parser.add_argument("--thu-lai", choices=["gioi_han", "day_du"], default="gioi_han",
                        help=f"gioi_han: thử lại ở nhiệt độ {asr.NHIET_DO_THU_LAI} (mặc định); "
                             "day_du: như faster-whisper gốc, thử tới 1.0")
    parser.add_argument("--theo-khuc", action="store_true",
                        help="Nhận dạng theo lô của faster-whisper (đã đo: tệ hơn ở file dài)")
    parser.add_argument("--tung-luot", action="store_true",
                        help="Cắt file theo từng lượt nói rồi nhận dạng từng lượt (đã là mặc định)")
    parser.add_argument("--ca-file", action="store_true",
                        help="Nhận dạng cả file một lượt như trước (so sánh với chế độ từng lượt)")
    parser.add_argument("--beam", type=int, default=asr.BEAM,
                        help=f"Số nhánh dò chữ (mặc định {asr.BEAM}); 1 nhanh hơn nhiều")
    parser.add_argument("--token-moi-giay", type=int, default=asr.TOKEN_MOI_GIAY,
                        help=f"Giới hạn token mỗi lượt = số này x số giây + --token-cong-them "
                             f"(mặc định {asr.TOKEN_MOI_GIAY})")
    parser.add_argument("--token-cong-them", type=int, default=asr.TOKEN_CONG_THEM,
                        help=f"(mặc định {asr.TOKEN_CONG_THEM})")
    parser.add_argument("--so-luong", type=int, default=asr.SO_LUONG_CPU,
                        help="Số luồng CPU cho model (mặc định 0 = 4 luồng của faster-whisper)")
    parser.add_argument("--do-thoi-gian", action="store_true",
                        help="Dùng với --chi-doan: đo thời gian từng bước (nghe, sinh chữ, dò mốc thời gian)")
    parser.add_argument("--thong-ke-token", metavar="CAU_HINH",
                        help="Không chạy ASR: từ kết quả đã lưu, đếm số token lời thật mỗi lượt và ước tính "
                             "giới hạn token sát nhất mà không cắt mất lời")
    parser.add_argument("--dem-im-lang", action="store_true",
                        help="Đệm im lặng thật cho mỗi lượt đủ 30 giây (như thư viện gốc), thay vì đệm số 0 của faster-whisper")
    parser.add_argument("--khong-moc-thoi-gian", action="store_true",
                        help="Model không đoán mốc thời gian theo đoạn (cần cho PhoWhisper)")
    parser.add_argument("--khong-tien-xu-ly", action="store_true", help="Tắt tiền xử lý âm thanh")
    parser.add_argument("--loc-nhieu", action="store_true", help="Bật giảm tạp âm")
    parser.add_argument("--chay-lai", action="store_true", help="Bỏ kết quả cũ, nhận dạng lại từ đầu")
    parser.add_argument("--kiem-sua-loi", metavar="CAU_HINH", nargs="?", const="",
                        help="Không chạy ASR: đo bảng sửa lỗi của src/tien_xu_ly trên kết quả đã có "
                             "(mặc định: cấu hình hiện tại)")
    parser.add_argument("--chi-doan", nargs="+", metavar="ID",
                        help="Chạy lại riêng các đoạn này với cấu hình đang chọn và in chi tiết để chẩn đoán "
                             "(không ghi đè kết quả đã lưu)")
    parser.add_argument("--loc-lai", metavar="CAU_HINH",
                        help="Không chạy ASR: chấm lại kết quả đã lưu với bộ lọc hiện tại (ước tính nhanh)")
    parser.add_argument("--so-sanh", nargs="+", metavar="CAU_HINH",
                        help="Không chạy ASR, chỉ so các cấu hình đã chạy "
                             "(vd: --so-sanh medium medium_khong_goi_y)")
    args = parser.parse_args()
    if args.theo_khuc + args.tung_luot + args.ca_file > 1:
        sys.exit("Chọn một trong --theo-khuc, --tung-luot, --ca-file.")
    if not (args.theo_khuc or args.ca_file):
        args.tung_luot = asr.TUNG_LUOT_MAC_DINH

    co_san = sorted(p.name for p in THU_MUC_BO.iterdir() if (p / "nhan.json").exists()) \
        if THU_MUC_BO.exists() else []
    if not co_san:
        sys.exit("Chưa có bộ dữ liệu nào. Chạy trước:  python src/asr/tai_bo_danh_gia.py")
    cac_bo = args.bo or co_san
    thieu = [b for b in cac_bo if b not in co_san]
    if thieu:
        sys.exit(f"Chưa tải bộ: {', '.join(thieu)}. Đã có: {', '.join(co_san)}")

    if args.kiem_sua_loi is not None:
        THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
        cau_hinh = args.kiem_sua_loi or ten_cau_hinh(args)
        for ten_bo in cac_bo:
            bao_cao = kiem_sua_loi(ten_bo, cau_hinh)
            tep = THU_MUC_BAO_CAO / f"{ten_bo}__kiem_sua_loi.txt"
            tep.write_text(bao_cao + "\n", encoding="utf-8")
            print("\n" + bao_cao + f"\n\nĐã lưu: {asr.hien_thi(tep)}")
        return

    if args.loc_lai:
        THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
        for ten_bo in cac_bo:
            ten_moi, so_doan_bo, thieu = loc_lai(ten_bo, args.loc_lai)
            cac_muc = doc_json(THU_MUC_BO / ten_bo / "nhan.json", [])
            ket = doc_json(THU_MUC_BO / ten_bo / f"ket_qua__{ten_moi}.json", {})
            bao_cao = viet_bao_cao(ten_bo, ten_moi, phan_tich(cac_muc, ket))
            tep = THU_MUC_BAO_CAO / f"{ten_bo}__{ten_moi}.txt"
            tep.write_text(bao_cao + "\n", encoding="utf-8")
            print(f"\n=== {ten_bo}: bộ lọc hiện tại bỏ thêm {so_doan_bo} đoạn"
                  + (f"; {thieu} kết quả chưa có chi tiết, giữ nguyên" if thieu else "") + " ===")
            print(bao_cao.split("\n\nCÁC CẶP")[0])
            print(f"Đã lưu: {asr.hien_thi(tep)}  |  so sánh: --so-sanh {args.loc_lai} {ten_moi}")
        return

    if args.thong_ke_token:
        THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
        bao_cao = thong_ke_token(cac_bo, args.thong_ke_token, args.model)
        tep = THU_MUC_BAO_CAO / f"thong_ke_token__{args.thong_ke_token}.txt"
        tep.write_text(bao_cao + "\n", encoding="utf-8")
        print("\n" + bao_cao + f"\n\nĐã lưu: {asr.hien_thi(tep)}")
        return

    if args.so_sanh:
        THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
        for ten_bo in cac_bo:
            bao_cao = so_sanh_cau_hinh(ten_bo, args.so_sanh)
            tep = THU_MUC_BAO_CAO / f"{ten_bo}__so_sanh.txt"
            tep.write_text(bao_cao + "\n", encoding="utf-8")
            print("\n" + bao_cao + f"\n\nĐã lưu: {asr.hien_thi(tep)}")
        return

    model = []

    def tai_model():  # chỉ tải model khi thật sự có đoạn cần nhận dạng
        if not model:
            print(f"Đang tải model {args.model}...")
            if asr.loi_thu_muc_model(args.model):
                sys.exit(asr.loi_thu_muc_model(args.model))
            try:
                model.append(asr.WhisperModel(args.model, device="cpu", compute_type=args.kieu_tinh,
                                              cpu_threads=args.so_luong))
                if args.do_thoi_gian:
                    model[0].model = DoThoiGian(model[0].model)
                    goc_transcribe = model[0].transcribe

                    def dem_transcribe(*a, **k):
                        model[0].so_lan_nghe = getattr(model[0], "so_lan_nghe", 0) + 1
                        return goc_transcribe(*a, **k)
                    model[0].transcribe = dem_transcribe
            except Exception as loi:
                sys.exit(f"Không tải được model {args.model}: {type(loi).__name__}: {loi}")
        return model[0]

    cau_hinh = ten_cau_hinh(args)
    THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
    if args.chi_doan:
        so_giay, thoi_gian = chay_chi_doan(cac_bo, args, cau_hinh, tai_model)
        if args.do_thoi_gian and model:
            print(model[0].model.bao_cao(thoi_gian, so_giay, getattr(model[0], "so_lan_nghe", 0)))
        return
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
