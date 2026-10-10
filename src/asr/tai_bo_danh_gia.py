# -*- coding: utf-8 -*-
"""
Tải một phần các bộ dữ liệu giọng nói tiếng Việt CÓ LỜI GỐC để đo chất lượng ASR
trên nhiều giọng, nhiều kiểu nói (không phải chỉ vài file tự thu).

Mỗi bộ chỉ lấy ngẫu nhiên N đoạn, chia đều theo nhóm (loại nội dung, phương ngữ, kênh...)
và giới hạn số đoạn mỗi người nói / mỗi video để mẫu đa dạng. Tải thẳng file từ kho
Hugging Face (ổn định hơn API xem dữ liệu, vốn hay lỗi 500/429).

    hop_va_dien_thoai : 200 đoạn họp trực tuyến, gọi điện... (1 file ~83 MB)
    phuong_ngu        : LSVSC, có nhãn phương ngữ (1 file ~390 MB, lấy mẫu trong đó)
    tu_nhien          : VietSuperSpeech, trò chuyện YouTube (tải từng file .wav nhỏ)
    vimd              : ViMD, giọng 63 tỉnh (3 file ~450 MB mỗi file) - KHÔNG chạy mặc định

Kết quả (KHÔNG đưa lên git, đã có trong .gitignore):
    data/bo_danh_gia/<tên bộ>/audio/<id>.<đuôi>
    data/bo_danh_gia/<tên bộ>/nhan.json   [{"id", "tep", "text", "nhom", "nguon", "row_idx"}]
    data/bo_danh_gia/<tên bộ>/_tai_ve/    file gốc đã tải (giữ lại để tải bù không phải tải lại)

Cách dùng:
    pip install -r requirements.txt                       (cần pyarrow để đọc file .parquet)
    python src/asr/tai_bo_danh_gia.py                     (các bộ mặc định, mỗi bộ 30 đoạn)
    python src/asr/tai_bo_danh_gia.py phuong_ngu --so-mau 100   (tải bù cho đủ 100 đoạn)
Hugging Face giới hạn số lần tải khi không đăng nhập (lỗi 429). Nếu hay gặp, đặt token
(loại Read) trước khi chạy:   $env:HF_TOKEN="hf_..."
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
TEP_HUB = "https://huggingface.co/datasets/{dataset}/resolve/main/{duong_dan}"
CHO_KHI_LOI = [5, 15, 30, 60, 90]   # máy chủ bận: chờ lâu dần rồi thử lại
LOI_THU_LAI = (429, 500, 502, 503, 504)
SO_TU_TOI_THIEU = 3                 # bỏ đoạn quá ngắn: WER của 1-2 từ không có ý nghĩa


def ten_kenh(duong_dan_audio):
    """audio/asr_segments_vietcetera_part00/x.wav -> vietcetera"""
    thu_muc = duong_dan_audio.split("/")[1] if duong_dan_audio.count("/") >= 2 else "?"
    return re.sub(r"^asr_(?:segments|dataset)_|_part\d+$", "", thu_muc)


# Mỗi bộ:
#   kieu      : "parquet" (tải vài file .parquet chứa sẵn âm thanh) hoặc "danh_sach"
#               (tải file danh sách rồi tải từng file âm thanh)
#   van_ban   : các cột lời gốc, lấy cột đầu tiên có chữ
#   nhom      : để chia đều số đoạn và báo cáo WER riêng; so_nhom: số nhóm dự kiến
#   nguon     : người nói / video, mỗi nguồn lấy tối đa toi_da_moi_nguon đoạn (None: không giới hạn)
CAC_BO = {
    "hop_va_dien_thoai": {
        "dataset": "DataStudio/Vietnamese_ASR_TestingData",
        "kieu": "parquet",
        "cac_tep": ["data/test-00000-of-00001.parquet"],
        "mo_ta": "Họp trực tuyến, gọi điện... (bộ kiểm thử ASR, nói tự nhiên)",
        "giay_phep": "giấy phép 'other', chỉ dùng để đánh giá",
        # "speak format" viết số bằng chữ đúng như lời nói, so công bằng hơn "label"
        "van_ban": ["speak format", "label"],
        "nhom": lambda dong: dong.get("type of content") or "?",
        "so_nhom": 10,
        "nguon": None,
        "toi_da_moi_nguon": None,
    },
    "phuong_ngu": {
        "dataset": "doof-ferb/LSVSC",
        "kieu": "parquet",
        "cac_tep": ["data/test-00000-of-00003.parquet"],
        "mo_ta": "LSVSC: nhiều phương ngữ, chủ đề, giới tính, độ tuổi",
        "giay_phep": "CC BY 4.0",
        "van_ban": ["transcription", "text"],
        "nhom": lambda dong: dong.get("dialect") or "?",
        "so_nhom": 5,
        "nguon": None,
        "toi_da_moi_nguon": None,
    },
    "tu_nhien": {
        "dataset": "thanhnew2001/VietSuperSpeech",
        "kieu": "danh_sach",
        "danh_sach": "dev.json",   # [{"audio": "audio/<kênh>/<video>_segNNN.wav", "text", ...}]
        "mo_ta": "VietSuperSpeech: trò chuyện, vlog, phỏng vấn trên YouTube",
        "giay_phep": "chưa ghi giấy phép; lời gốc có thể do máy tạo, xem như tham khảo",
        "van_ban": ["text"],
        "nhom": lambda dong: ten_kenh(dong.get("audio") or ""),
        "so_nhom": 4,
        "nguon": lambda dong: dong.get("source") or dong.get("audio", "?").rsplit("_seg", 1)[0],
        "toi_da_moi_nguon": 2,
    },
    "vimd": {
        "dataset": "nguyendv02/ViMD_Dataset",
        "kieu": "parquet",
        # Mỗi file chỉ chứa vài tỉnh liền nhau: lấy 3 file rải đầu-giữa-cuối để có đủ 3 miền
        "cac_tep": ["data/test-00000-of-00014.parquet", "data/test-00007-of-00014.parquet",
                    "data/test-00013-of-00014.parquet"],
        "mo_ta": "ViMD: giọng 63 tỉnh thành (Bắc, Trung, Nam) - tải nặng, khoảng 1,3 GB",
        "giay_phep": "CC BY-NC-ND 4.0, chỉ dùng cho nghiên cứu",
        "van_ban": ["text"],
        "nhom": lambda dong: dong.get("region") or "?",
        "so_nhom": 3,
        "nguon": lambda dong: dong.get("speakerID") or "?",
        "toi_da_moi_nguon": 2,
        "khong_mac_dinh": True,
    },
}


class LoiTai(Exception):
    pass


# ======================================================================
# MẠNG
# ======================================================================
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
    if token:
        tieu_de["Authorization"] = f"Bearer {token}"
    for lan, cho in enumerate(CHO_KHI_LOI + [None]):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=tieu_de), timeout=120)
        except urllib.error.HTTPError as loi:
            if loi.code in (401, 403):
                raise LoiTai(f"Bị từ chối truy cập ({loi.code}). Kiểm tra lại HF_TOKEN, hoặc bộ dữ liệu "
                             "yêu cầu bấm đồng ý điều khoản trên trang Hugging Face.")
            if loi.code not in LOI_THU_LAI or cho is None:
                goi_y = " Đặt HF_TOKEN để được tải nhiều hơn." if loi.code == 429 and not token else ""
                raise LoiTai(f"Máy chủ trả lỗi {loi.code} ({loi.reason}).{goi_y}")
            try:
                cho = min(int(loi.headers.get("Retry-After", cho)), 120)
            except (TypeError, ValueError):
                pass
            ly_do = "bị giới hạn số lần tải" if loi.code == 429 else f"máy chủ lỗi {loi.code}"
            print(f"    ({ly_do}, chờ {cho} giây rồi thử lại {lan + 1}/{len(CHO_KHI_LOI)}...)")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as loi:
            if cho is None:
                raise LoiTai(f"Không kết nối được tới Hugging Face: {loi}")
            print(f"    (mạng chập chờn, chờ {cho} giây rồi thử lại...)")
        time.sleep(cho)


def tai_file(url, duong_dan, bao_tien_do=False):
    """Ghi ra file tạm rồi đổi tên: ngắt giữa chừng không để lại file hỏng."""
    tep_tam = duong_dan.with_name(duong_dan.name + ".tmp")
    try:
        with mo_url(url) as phan_hoi, open(tep_tam, "wb") as f:
            tong = int(phan_hoi.headers.get("Content-Length") or 0)
            da_tai, moc_in = 0, 0.1
            while khoi := phan_hoi.read(1 << 20):
                f.write(khoi)
                da_tai += len(khoi)
                if bao_tien_do and tong and da_tai / tong >= moc_in:
                    print(f"    đã tải {da_tai / 2**20:.0f}/{tong / 2**20:.0f} MB")
                    moc_in += 0.1
        os.replace(tep_tam, duong_dan)
    except (OSError, urllib.error.URLError) as loi:
        raise LoiTai(f"Tải dở thì bị ngắt: {loi}. Chạy lại lệnh để tải lại.")
    finally:
        if tep_tam.exists():
            tep_tam.unlink()


def link_hub(dataset, duong_dan):
    return TEP_HUB.format(dataset=dataset, duong_dan=urllib.parse.quote(duong_dan))


# ======================================================================
# ĐỌC DỮ LIỆU GỐC
# ======================================================================
def nhap_pyarrow():
    try:
        import pyarrow.parquet as pq
        return pq
    except ImportError:
        raise LoiTai("Chưa cài thư viện đọc file .parquet. Chạy:  pip install -r requirements.txt")


def tai_ve_neu_chua_co(cau_hinh, duong_dan, thu_muc):
    """Tải một file gốc về _tai_ve/ (chỉ tải lần đầu)."""
    tep = thu_muc / "_tai_ve" / Path(duong_dan).name
    if not tep.exists():
        tep.parent.mkdir(parents=True, exist_ok=True)
        print(f"  Tải {duong_dan} (chỉ tải lần đầu)...")
        tai_file(link_hub(cau_hinh["dataset"], duong_dan), tep, bao_tien_do=True)
    return tep


def cac_dong_parquet(cau_hinh, thu_muc):
    """Đọc phần chữ của mọi dòng (chưa đọc âm thanh). Trả [(row_idx, dòng)]."""
    pq = nhap_pyarrow()
    cac_dong = []
    for so_tep, duong_dan in enumerate(cau_hinh["cac_tep"]):
        tep = tai_ve_neu_chua_co(cau_hinh, duong_dan, thu_muc)
        bang = pq.ParquetFile(tep)
        cot = [c for c in bang.schema_arrow.names if c != "audio"]
        for i, dong in enumerate(bang.read(columns=cot).to_pylist()):
            dong["_tep"], dong["_dong"] = tep, i
            cac_dong.append((so_tep * 1_000_000 + i, dong))
    return cac_dong


def cac_dong_danh_sach(cau_hinh, thu_muc):
    tep = tai_ve_neu_chua_co(cau_hinh, cau_hinh["danh_sach"], thu_muc)
    noi_dung = tep.read_text(encoding="utf-8-sig").strip()
    try:
        cac_dong = json.loads(noi_dung)
    except json.JSONDecodeError:  # phòng khi là JSON Lines (mỗi dòng một bản ghi)
        cac_dong = [json.loads(d) for d in noi_dung.splitlines() if d.strip()]
    return [(i, d) for i, d in enumerate(cac_dong) if isinstance(d, dict) and d.get("audio")]


_bo_nho_parquet = {}


def am_thanh_parquet(tep, so_dong):
    """Lấy bytes âm thanh của một dòng: chỉ đọc nhóm dòng (row group) chứa nó."""
    pq = nhap_pyarrow()
    if tep not in _bo_nho_parquet:
        _bo_nho_parquet[tep] = {"file": pq.ParquetFile(tep), "nhom": None, "du_lieu": None}
    bo_nho = _bo_nho_parquet[tep]
    f = bo_nho["file"]
    bat_dau = 0
    for nhom in range(f.num_row_groups):
        so = f.metadata.row_group(nhom).num_rows
        if so_dong < bat_dau + so:
            if bo_nho["nhom"] != nhom:  # giữ nhóm vừa đọc: các dòng cùng nhóm không đọc lại
                bo_nho["nhom"] = nhom
                bo_nho["du_lieu"] = f.read_row_group(nhom, columns=["audio"]).column("audio")
            o = bo_nho["du_lieu"][so_dong - bat_dau].as_py() or {}
            return o.get("bytes"), o.get("path") or ""
        bat_dau += so
    return None, ""


def duoi_file(du_lieu, ten_goc=""):
    """Đoán đuôi file từ vài byte đầu (cột path trong parquet thường để trống)."""
    if du_lieu[:4] == b"RIFF":
        return ".wav"
    if du_lieu[:4] == b"fLaC":
        return ".flac"
    if du_lieu[:4] == b"OggS":
        return ".ogg"
    if du_lieu[:3] == b"ID3" or du_lieu[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    return Path(ten_goc).suffix or ".wav"


# ======================================================================
# CHỌN MẪU
# ======================================================================
def lay_van_ban(dong, cau_hinh):
    for cot in cau_hinh["van_ban"]:
        if isinstance(dong.get(cot), str) and dong[cot].strip():
            return dong[cot].strip()
    return ""


def ten_nguon(dong, row_idx, cau_hinh):
    return str(cau_hinh["nguon"](dong)) if cau_hinh["nguon"] else str(row_idx)


def chon_dong(cac_dong, cau_hinh, so_mau, da_co, chia_deu=True):
    """Chọn dòng theo hạn mức mỗi nhóm và mỗi nguồn. da_co: các mục đã tải từ trước.

    chia_deu=False: bỏ hạn mức nhóm (dùng khi có ít nhóm hơn dự kiến), vẫn giữ hạn mức nguồn.
    """
    han_muc_nhom = math.ceil(so_mau / cau_hinh["so_nhom"]) if chia_deu else so_mau
    toi_da_nguon = cau_hinh["toi_da_moi_nguon"]
    dem_nhom = Counter(muc["nhom"] for muc in da_co)
    dem_nguon = Counter(muc["nguon"] for muc in da_co)
    da_lay = {muc["row_idx"] for muc in da_co}
    chon = []
    for row_idx, dong in cac_dong:
        if len(da_co) + len(chon) >= so_mau:
            break
        if row_idx in da_lay or len(lay_van_ban(dong, cau_hinh).split()) < SO_TU_TOI_THIEU:
            continue
        nhom, nguon = str(cau_hinh["nhom"](dong)), ten_nguon(dong, row_idx, cau_hinh)
        if dem_nhom[nhom] >= han_muc_nhom or (toi_da_nguon and dem_nguon[nguon] >= toi_da_nguon):
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


def luu_am_thanh(ten_bo, row_idx, dong, cau_hinh, thu_muc):
    """Ghi file âm thanh của một dòng vào audio/, trả về đường dẫn tương đối."""
    if cau_hinh["kieu"] == "parquet":
        du_lieu, ten_goc = am_thanh_parquet(dong["_tep"], dong["_dong"])
        if not du_lieu:
            raise LoiTai("dòng không có dữ liệu âm thanh")
        tep = Path("audio") / f"{ten_bo}_{row_idx:07d}{duoi_file(du_lieu, ten_goc)}"
        (thu_muc / tep).write_bytes(du_lieu)
    else:
        tep = Path("audio") / f"{ten_bo}_{row_idx:07d}{Path(dong['audio']).suffix or '.wav'}"
        tai_file(link_hub(cau_hinh["dataset"], dong["audio"]), thu_muc / tep)
    return tep


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

    cac_dong = (cac_dong_parquet(cau_hinh, thu_muc) if cau_hinh["kieu"] == "parquet"
                else cac_dong_danh_sach(cau_hinh, thu_muc))
    if not cac_dong:
        raise LoiTai("Không đọc được dòng dữ liệu nào (định dạng bộ dữ liệu đã đổi?).")
    # Thứ tự ngẫu nhiên cố định theo hạt giống: chạy lại vẫn ra cùng tập đoạn,
    # nên kết quả đo các lần (các cấu hình) so được với nhau
    random.Random(hat_giong).shuffle(cac_dong)

    so_loi_tai = 0
    # Lượt 1 chia đều theo nhóm; bộ có ít nhóm hơn dự kiến thì lượt 2 lấy bù không chia đều
    for chia_deu in (True, False):
        for row_idx, dong in chon_dong(cac_dong, cau_hinh, so_mau, cac_muc, chia_deu):
            try:
                tep = luu_am_thanh(ten_bo, row_idx, dong, cau_hinh, thu_muc)
            except LoiTai as loi:
                so_loi_tai += 1
                print(f"  ✗ dòng {row_idx}: {loi}")
                if so_loi_tai >= 5:
                    raise LoiTai("Lỗi tải nhiều lần liên tiếp, dừng lại. Chạy lại lệnh để tải tiếp.")
                continue
            so_loi_tai = 0
            cac_muc.append({
                "id": f"{ten_bo}_{row_idx:07d}", "tep": tep.as_posix(),
                "text": lay_van_ban(dong, cau_hinh), "nhom": str(cau_hinh["nhom"](dong)),
                "nguon": ten_nguon(dong, row_idx, cau_hinh), "row_idx": row_idx,
            })
            luu_nhan(cac_muc, tep_nhan)  # lưu sau mỗi đoạn: ngắt giữa chừng vẫn giữ phần đã tải
            print(f"  [{len(cac_muc):>3}/{so_mau}] {cac_muc[-1]['nhom'][:18]:<18} {cac_muc[-1]['text'][:55]}")
        if len(cac_muc) >= so_mau:
            break

    dem = Counter(m["nhom"] for m in cac_muc)
    print(f"Có {len(cac_muc)} đoạn: " + ", ".join(f"{k} {v}" for k, v in sorted(dem.items())))
    if len(cac_muc) < so_mau:
        print(f"  ⚠ Bộ này chỉ có {len(cac_muc)} đoạn thỏa điều kiện.")
    return cac_muc


def main():
    mac_dinh = [b for b, ch in CAC_BO.items() if not ch.get("khong_mac_dinh")]
    parser = argparse.ArgumentParser(description="Tải mẫu các bộ dữ liệu giọng nói để đánh giá ASR.")
    parser.add_argument("bo", nargs="*",
                        help=f"Tên bộ: {', '.join(CAC_BO)} (bỏ trống = {', '.join(mac_dinh)})")
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
    for ten_bo in args.bo or mac_dinh:
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
