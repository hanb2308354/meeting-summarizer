# -*- coding: utf-8 -*-
"""
Tải một phần nhỏ các bộ dữ liệu giọng nói tiếng Việt CÓ LỜI GỐC để đo chất lượng ASR
trên nhiều giọng, nhiều kiểu nói (không phải chỉ vài file tự thu).

Không tải cả bộ (hàng trăm GB): chỉ lấy ngẫu nhiên N đoạn, chia đều theo nhóm (vùng miền,
kênh) và giới hạn số đoạn mỗi người nói / mỗi video để mẫu đa dạng.
    - vimd: lấy từng trang dòng qua API xem dữ liệu của Hugging Face (bộ gốc là file
      parquet ~450 MB mỗi phần, tải nguyên phần quá nặng)
    - vietsuperspeech: tải danh sách dev.json rồi tải thẳng từng file .wav

Hugging Face giới hạn số lần gọi khi không đăng nhập (lỗi 429). Nếu hay gặp, đặt token
(loại Read) trước khi chạy:   $env:HF_TOKEN="hf_..."

Kết quả (KHÔNG đưa lên git, đã có trong .gitignore):
    data/bo_danh_gia/<tên bộ>/audio/<id>.wav
    data/bo_danh_gia/<tên bộ>/nhan.json   [{"id", "tep", "text", "nhom", "nguon", "row_idx"}]

Cách dùng:
    python src/asr/tai_bo_danh_gia.py                    (mọi bộ, mỗi bộ 30 đoạn)
    python src/asr/tai_bo_danh_gia.py vimd --so-mau 60   (thêm cho đủ 60 đoạn, giữ đoạn đã tải)
Sau đó chạy:  python src/asr/danh_gia_bo.py
"""
import argparse
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THU_MUC_GOC = Path(__file__).resolve().parents[2]
THU_MUC_BO = THU_MUC_GOC / "data" / "bo_danh_gia"
API = "https://datasets-server.huggingface.co/rows"
TEP_HUB = "https://huggingface.co/datasets/{dataset}/resolve/main/{duong_dan}"
SO_DONG_MOI_LAN = 20          # số dòng lấy mỗi lần gọi API (tối đa 100)
NGHI_GIUA_LAN_GOI = 1.0       # giây; gọi dồn dập dễ bị chặn (lỗi 429)
CHO_KHI_LOI = [5, 15, 30, 60, 90]   # máy chủ bận: chờ lâu dần rồi thử lại
LOI_THU_LAI = (429, 500, 502, 503, 504)
SO_TU_TOI_THIEU = 3           # bỏ đoạn quá ngắn: WER của 1-2 từ không có ý nghĩa

# Mỗi bộ: nhóm để chia đều + báo cáo riêng, nguồn để giới hạn số đoạn cùng người/cùng video
CAC_BO = {
    "vimd": {
        "dataset": "nguyendv02/ViMD_Dataset",
        "split": "test",          # lấy qua API xem dữ liệu
        "mo_ta": "Giọng 63 tỉnh thành (Bắc, Trung, Nam)",
        "giay_phep": "CC BY-NC-ND 4.0, chỉ dùng cho nghiên cứu",
        "nhom": lambda dong: dong.get("region") or "?",
        "so_nhom": 3,              # Bắc, Trung, Nam: mỗi miền khoảng 1/3 số đoạn
        "nguon": lambda dong: dong.get("speakerID") or "?",
        "toi_da_moi_nguon": 2,
    },
    "vietsuperspeech": {
        "dataset": "thanhnew2001/VietSuperSpeech",
        "danh_sach": "dev.json",   # [{"audio": "audio/<kênh>/<video>_segNNN.wav", "text", ...}]
        "mo_ta": "Nói chuyện tự nhiên từ YouTube (trò chuyện, vlog, phỏng vấn)",
        "giay_phep": "chưa ghi giấy phép; lời gốc có thể do máy tạo, xem như tham khảo",
        "nhom": lambda dong: ten_kenh(dong.get("audio") or ""),
        "so_nhom": 4,              # 4 kênh YouTube: mỗi kênh khoảng 1/4 số đoạn
        "nguon": lambda dong: dong.get("source") or dong.get("audio", "?").rsplit("_seg", 1)[0],
        "toi_da_moi_nguon": 2,
    },
}


class LoiTai(Exception):
    pass


def ten_kenh(duong_dan_audio):
    """audio/asr_segments_vietcetera_part00/x.wav -> vietcetera"""
    thu_muc = duong_dan_audio.split("/")[1] if duong_dan_audio.count("/") >= 2 else "?"
    return re.sub(r"^asr_segments_|_part\d+$", "", thu_muc)


def lay_token():
    """Token Hugging Face nếu có (biến môi trường HF_TOKEN hoặc đã `hf auth login`)."""
    token = os.environ.get("HF_TOKEN")
    if token:
        return token.strip()
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:
        return None


def mo_url(url):
    """Mở URL, tự chờ và thử lại khi máy chủ bận (429/5xx) hoặc mạng chập chờn."""
    tieu_de = {"User-Agent": "meeting-summarizer-danh-gia-asr/1.0"}
    token = lay_token()
    if token and "Signature=" not in url:  # link đã ký sẵn thì không gửi token
        tieu_de["Authorization"] = f"Bearer {token}"
    for lan, cho in enumerate(CHO_KHI_LOI + [None]):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=tieu_de), timeout=120)
        except urllib.error.HTTPError as loi:
            if loi.code in (401, 403):
                raise LoiTai(f"Bị từ chối truy cập ({loi.code}). Kiểm tra lại HF_TOKEN, hoặc bộ dữ liệu "
                             "yêu cầu bấm đồng ý điều khoản trên trang Hugging Face.")
            if loi.code not in LOI_THU_LAI or cho is None:
                goi_y = " Đặt HF_TOKEN để được gọi nhiều hơn." if loi.code == 429 and not token else ""
                raise LoiTai(f"Máy chủ trả lỗi {loi.code} ({loi.reason}).{goi_y}")
            try:
                cho = min(int(loi.headers.get("Retry-After", cho)), 120)
            except (TypeError, ValueError):
                pass
            ly_do = "bị giới hạn số lần gọi" if loi.code == 429 else f"máy chủ lỗi {loi.code}"
            print(f"    ({ly_do}, chờ {cho} giây rồi thử lại {lan + 1}/{len(CHO_KHI_LOI)}...)")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as loi:
            if cho is None:
                raise LoiTai(f"Không kết nối được tới Hugging Face: {loi}")
            print(f"    (mạng chập chờn, chờ {cho} giây rồi thử lại...)")
        time.sleep(cho)


def goi_api(dataset, split, offset, so_dong):
    """Lấy một trang dòng dữ liệu qua API xem dữ liệu của Hugging Face."""
    tham_so = urllib.parse.urlencode({"dataset": dataset, "config": "default", "split": split,
                                      "offset": offset, "length": so_dong})
    with mo_url(f"{API}?{tham_so}") as phan_hoi:
        return json.loads(phan_hoi.read().decode("utf-8"))


def link_am_thanh(o_audio):
    """Ô audio của API là [{"src": url, "type": "audio/wav"}] (đôi khi là một dict)."""
    if isinstance(o_audio, list) and o_audio:
        o_audio = o_audio[0]
    if isinstance(o_audio, dict) and o_audio.get("src"):
        return o_audio["src"], o_audio.get("type") or ""
    return None, ""


def tai_file(url, duong_dan):
    """Ghi ra file tạm rồi đổi tên: ngắt giữa chừng không để lại file hỏng."""
    tep_tam = duong_dan.with_name(duong_dan.name + ".tmp")
    try:
        with mo_url(url) as phan_hoi, open(tep_tam, "wb") as f:
            while khoi := phan_hoi.read(1 << 16):
                f.write(khoi)
        os.replace(tep_tam, duong_dan)
    except (OSError, urllib.error.URLError) as loi:
        raise LoiTai(f"Tải dở thì bị ngắt: {loi}")
    finally:
        if tep_tam.exists():
            tep_tam.unlink()


def chon_dong(cac_dong, cau_hinh, so_mau, da_co):
    """Chọn dòng theo hạn mức mỗi nhóm và mỗi nguồn. da_co: các mục đã tải từ trước.

    Trả về danh sách dòng được chọn (không trùng row_idx với da_co).
    """
    han_muc_nhom = math.ceil(so_mau / cau_hinh["so_nhom"])
    dem_nhom = Counter(muc["nhom"] for muc in da_co)
    dem_nguon = Counter(muc["nguon"] for muc in da_co)
    da_lay = {muc["row_idx"] for muc in da_co}
    chon = []
    for row_idx, dong in cac_dong:
        if len(da_co) + len(chon) >= so_mau:
            break
        if row_idx in da_lay:
            continue
        van_ban = (dong.get("text") or "").strip()
        if len(van_ban.split()) < SO_TU_TOI_THIEU:
            continue
        nhom, nguon = cau_hinh["nhom"](dong), cau_hinh["nguon"](dong)
        if dem_nhom[nhom] >= han_muc_nhom or dem_nguon[nguon] >= cau_hinh["toi_da_moi_nguon"]:
            continue
        dem_nhom[nhom] += 1
        dem_nguon[nguon] += 1
        da_lay.add(row_idx)
        chon.append((row_idx, dong))
    return chon


def doc_nhan(tep_nhan):
    if not tep_nhan.exists():
        return []
    cac_muc = json.loads(tep_nhan.read_text(encoding="utf-8"))
    # Bỏ mục mà file âm thanh đã bị xóa tay, để lần này tải bù
    return [m for m in cac_muc if (tep_nhan.parent / m["tep"]).exists()]


def luu_nhan(cac_muc, tep_nhan):
    tep_tam = tep_nhan.with_name(tep_nhan.name + ".tmp")
    tep_tam.write_text(json.dumps(cac_muc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tep_tam, tep_nhan)


def cac_lo_dong_qua_api(cau_hinh, hat_giong):
    """Trả dần từng trang dòng (row_idx, dòng), đi qua các trang theo thứ tự ngẫu nhiên."""
    tong_so_dong, loi_cuoi = 0, None
    for offset in (0, 100, 500):  # trang đầu lỗi thì hỏi số dòng qua trang khác
        try:
            tong_so_dong = goi_api(cau_hinh["dataset"], cau_hinh["split"], offset, 1).get("num_rows_total") or 0
            break
        except LoiTai as loi:
            loi_cuoi = loi
            print(f"  ⚠ chưa lấy được số dòng: {loi}")
    if loi_cuoi and not tong_so_dong:
        raise LoiTai(f"{loi_cuoi} Đợi vài phút rồi chạy lại lệnh.")
    if not tong_so_dong:
        raise LoiTai("API không trả về số dòng, có thể bộ dữ liệu đang tạm khóa xem trước.")
    # Thứ tự ngẫu nhiên cố định theo hạt giống: mẫu rải khắp bộ, chạy lại vẫn ra cùng
    # một tập đoạn nên kết quả đo các lần so được với nhau
    cac_trang = list(range(0, tong_so_dong, SO_DONG_MOI_LAN))
    random.Random(hat_giong).shuffle(cac_trang)
    so_trang_loi = 0
    for offset in cac_trang:
        time.sleep(NGHI_GIUA_LAN_GOI)
        try:
            trang = goi_api(cau_hinh["dataset"], cau_hinh["split"], offset, SO_DONG_MOI_LAN)
        except LoiTai as loi:
            # Một trang lỗi thì bỏ qua lấy trang khác; lỗi liên tục mới dừng
            so_trang_loi += 1
            print(f"  ⚠ bỏ qua trang {offset}: {loi}")
            if so_trang_loi >= 3:
                raise LoiTai("Máy chủ lỗi liên tục, dừng lại. Đợi vài phút rồi chạy lại lệnh "
                             "(các đoạn đã tải được giữ nguyên).")
            continue
        so_trang_loi = 0
        cac_dong = [(d["row_idx"], d["row"]) for d in trang.get("rows", [])]
        random.Random(hat_giong + offset).shuffle(cac_dong)
        yield cac_dong


def cac_lo_dong_qua_danh_sach(cau_hinh, thu_muc, hat_giong):
    """Tải file danh sách (một lần, lưu lại), trả các dòng theo thứ tự ngẫu nhiên."""
    tep = thu_muc / cau_hinh["danh_sach"]
    if not tep.exists():
        print(f"  Tải danh sách {cau_hinh['danh_sach']}...")
        tai_file(TEP_HUB.format(dataset=cau_hinh["dataset"], duong_dan=cau_hinh["danh_sach"]), tep)
    noi_dung = tep.read_text(encoding="utf-8-sig").strip()
    try:
        cac_dong = json.loads(noi_dung)
    except json.JSONDecodeError:  # phòng khi là JSON Lines (mỗi dòng một bản ghi)
        cac_dong = [json.loads(d) for d in noi_dung.splitlines() if d.strip()]
    cac_dong = [(i, d) for i, d in enumerate(cac_dong) if isinstance(d, dict) and d.get("audio")]
    if not cac_dong:
        raise LoiTai(f"File {cau_hinh['danh_sach']} không có bản ghi nào (định dạng đã đổi?).")
    random.Random(hat_giong).shuffle(cac_dong)
    for i in range(0, len(cac_dong), 50):
        yield cac_dong[i:i + 50]


def link_cua_dong(dong, cau_hinh):
    """Trả (url, đuôi file) để tải âm thanh của một dòng."""
    if "danh_sach" in cau_hinh:
        duong_dan = urllib.parse.quote(dong["audio"])
        return TEP_HUB.format(dataset=cau_hinh["dataset"], duong_dan=duong_dan), Path(dong["audio"]).suffix or ".wav"
    url, kieu = link_am_thanh(dong.get("audio"))
    return url, ".mp3" if "mpeg" in kieu or "mp3" in kieu else ".wav"


def tai_mot_bo(ten_bo, so_mau, hat_giong):
    cau_hinh = CAC_BO[ten_bo]
    thu_muc = THU_MUC_BO / ten_bo
    (thu_muc / "audio").mkdir(parents=True, exist_ok=True)
    tep_nhan = thu_muc / "nhan.json"
    cac_muc = doc_nhan(tep_nhan)

    print(f"\n=== {ten_bo}: {cau_hinh['mo_ta']} ===")
    print(f"Nguồn: huggingface.co/datasets/{cau_hinh['dataset']} ({cau_hinh['giay_phep']})")
    if len(cac_muc) >= so_mau:
        print(f"Đã có {len(cac_muc)} đoạn, không cần tải thêm.")
        return cac_muc
    if cac_muc:
        print(f"Đã có {len(cac_muc)} đoạn, tải bù {so_mau - len(cac_muc)} đoạn.")

    cac_lo = (cac_lo_dong_qua_danh_sach(cau_hinh, thu_muc, hat_giong) if "danh_sach" in cau_hinh
              else cac_lo_dong_qua_api(cau_hinh, hat_giong))
    so_loi_tai = 0
    for cac_dong in cac_lo:
        if len(cac_muc) >= so_mau:
            break
        for row_idx, dong in chon_dong(cac_dong, cau_hinh, so_mau, cac_muc):
            url, duoi = link_cua_dong(dong, cau_hinh)
            if not url:
                continue
            tep = Path("audio") / f"{ten_bo}_{row_idx:06d}{duoi}"
            try:
                tai_file(url, thu_muc / tep)
            except LoiTai as loi:
                so_loi_tai += 1
                print(f"  ✗ dòng {row_idx}: {loi}")
                if so_loi_tai >= 5:
                    raise LoiTai("Lỗi tải nhiều lần liên tiếp, dừng lại. Chạy lại lệnh để tải tiếp.")
                continue
            so_loi_tai = 0
            cac_muc.append({
                "id": f"{ten_bo}_{row_idx:06d}", "tep": tep.as_posix(), "text": dong["text"].strip(),
                "nhom": cau_hinh["nhom"](dong), "nguon": cau_hinh["nguon"](dong), "row_idx": row_idx,
            })
            luu_nhan(cac_muc, tep_nhan)  # lưu sau mỗi đoạn: ngắt giữa chừng vẫn giữ phần đã tải
            print(f"  [{len(cac_muc):>3}/{so_mau}] {cac_muc[-1]['nhom']:<18} {cac_muc[-1]['text'][:55]}")

    dem = Counter(m["nhom"] for m in cac_muc)
    print(f"Có {len(cac_muc)} đoạn: " + ", ".join(f"{k} {v}" for k, v in sorted(dem.items())))
    if len(cac_muc) < so_mau:
        print(f"  ⚠ Chỉ lấy được {len(cac_muc)}/{so_mau} đoạn thỏa điều kiện chia đều.")
    return cac_muc


def main():
    parser = argparse.ArgumentParser(description="Tải mẫu các bộ dữ liệu giọng nói để đánh giá ASR.")
    parser.add_argument("bo", nargs="*", help=f"Tên bộ: {', '.join(CAC_BO)} (bỏ trống = tất cả)")
    parser.add_argument("--so-mau", type=int, default=30, help="Số đoạn mỗi bộ (mặc định 30)")
    parser.add_argument("--hat-giong", type=int, default=42,
                        help="Hạt giống ngẫu nhiên (giữ nguyên để lần nào cũng ra cùng tập đoạn)")
    args = parser.parse_args()
    if args.so_mau < 1:
        sys.exit("--so-mau phải từ 1 trở lên.")
    sai_ten = [b for b in args.bo if b not in CAC_BO]
    if sai_ten:
        sys.exit(f"Không có bộ {', '.join(sai_ten)}. Các bộ hiện có: {', '.join(CAC_BO)}")

    so_bo_loi = 0
    for ten_bo in args.bo or list(CAC_BO):
        try:
            tai_mot_bo(ten_bo, args.so_mau, args.hat_giong)
        except LoiTai as loi:
            so_bo_loi += 1
            print(f"  ✗ {ten_bo}: {loi}")
    print(f"\nDữ liệu nằm trong {THU_MUC_BO.relative_to(THU_MUC_GOC)}/ (không đưa lên git).")
    print("Bước tiếp theo: python src/asr/danh_gia_bo.py")
    if so_bo_loi:
        sys.exit(1)


if __name__ == "__main__":
    main()
