# Tiền xử lý transcript: sửa lỗi nhận dạng, bỏ từ đệm, đánh dấu câu xã giao, tách từ
# Người phụ trách: Hân (chuyển từ src/nlp sang).
#
# VỊ TRÍ TRONG HỆ THỐNG:
#   src/asr         -> data/transcripts/<tên>.json   (Hân: âm thanh -> chữ)
#   src/tien_xu_ly  -> data/processed/<tên>.json     (Hân: chữ -> văn bản sạch)  <- FILE NÀY
#   src/nlp         -> outputs/<tên>.json, .md        (Anh: văn bản sạch -> tóm tắt, trích xuất)
#
# Cách dùng:
#   python src/tien_xu_ly/tien_xu_ly.py data/transcripts/thu_nghiem.json
#   python src/tien_xu_ly/tien_xu_ly.py data/transcripts/      (cả thư mục)
#
# ĐẦU RA data/processed/<tên>.json (đã thống nhất với phần NLP, KHÔNG ĐƯỢC ĐỔI):
#   [{"stt", "speaker", "start", "end", "goc", "sach", "tach_tu", "xa_giao"}]
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from pyvi import ViTokenizer

from doc_transcript import doc_transcript
from tu_dien_tien_xu_ly import (
    MAU_THOI_GIAN,
    MAU_XA_GIAO,
    SO_TU_TOI_DA_XA_GIAO,
    SUA_LOI,
    TU_DEM,
    TU_GHEP,
    VE_KET_XA_GIAO,
)

# In tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Đường dẫn tính theo vị trí file code, chạy từ thư mục nào cũng đúng
THU_MUC_GOC = Path(__file__).resolve().parents[2]
THU_MUC_RA = THU_MUC_GOC / "data" / "processed"


def chuan_hoa_unicode(van_ban):
    """Đưa về một cách mã hóa dấu tiếng Việt (NFC).

    Phải làm ĐẦU TIÊN: cùng một chữ "à" có 2 cách mã hóa, nếu không chuẩn hóa
    thì bảng sửa lỗi và danh sách từ đệm có thể không khớp.
    """
    return unicodedata.normalize("NFC", van_ban)


def sua_loi_nhan_dang(van_ban):
    """Sửa các từ Whisper hay nhận sai theo bảng SUA_LOI."""
    for mau, thay_the in SUA_LOI:
        van_ban = re.sub(mau, thay_the, van_ban, flags=re.IGNORECASE)
    return van_ban


def bo_tu_dem(van_ban):
    """Bỏ các từ đệm như ờ, ừm, à, nha, nhé.

    Lặp tới khi không đổi nữa: bỏ một từ đệm có thể làm lộ ra từ đệm khác
    ("lúc 10 giờ ok nhé." -> bỏ "nhé" xong mới thấy "ok" đứng cuối câu).
    """
    while True:
        moi = re.sub(TU_DEM, "", van_ban, flags=re.IGNORECASE)
        if moi == van_ban:
            return moi
        van_ban = moi


def chuan_hoa_khoang_trang(van_ban):
    """Dọn khoảng trắng và dấu câu thừa còn sót lại sau khi bỏ từ đệm."""
    van_ban = re.sub(r"\s+", " ", van_ban)
    van_ban = re.sub(r"\s+([,.?!;:])", r"\1", van_ban)       # "a ," -> "a,"
    van_ban = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", van_ban)  # "a,, b" -> "a, b"
    van_ban = re.sub(r"[,;:]\s*([.?!])", r"\1", van_ban)      # "a, ." -> "a."
    van_ban = re.sub(r"^[,.;:?!\s]+", "", van_ban)            # dấu câu đầu câu
    # Không tự viết hoa chữ đầu sau khi bỏ từ đệm: phần trích xuất ghép mệnh đề
    # giữa các câu, viết hoa sẽ sinh ra kiểu "rà soát lại Phần database".
    return van_ban.strip()


def la_cau_rong(van_ban):
    """Câu không còn chữ nào (chỉ có từ đệm và dấu câu, vd "Ừm.")."""
    return not re.search(r"\w", van_ban)


# Giữa các chữ có thể là khoảng trắng hoặc "_" (PyVi nối được một phần, vd "ban giám_đốc")
_TU_GHEP = [
    re.compile(r"(?<!\S)" + r"[\s_]+".join(map(re.escape, cum.split())) + r"(?!\S)", re.IGNORECASE)
    for cum in TU_GHEP
]


def tach_tu(van_ban):
    """Tách từ bằng PyVi, rồi nối thêm các cụm PyVi hay bỏ sót ("hạn chót" -> "hạn_chót")."""
    ket_qua = ViTokenizer.tokenize(van_ban)
    for mau in _TU_GHEP:
        ket_qua = mau.sub(lambda m: re.sub(r"[\s_]+", "_", m.group(0)), ket_qua)
    return ket_qua


def la_xa_giao(van_ban):
    """Câu ngắn chỉ gồm chào hỏi/cảm ơn/hỏi ý kiến thì coi là xã giao.

    Phần NLP BỎ QUA câu xã giao khi trích việc và tóm tắt, nên phải chặt:
    - Mọi vế trong câu đều là xã giao, hoặc là vế kết quen thuộc ("vậy thôi").
      "Có ai ý kiến không, anh Bình phụ trách báo cáo" -> KHÔNG phải xã giao.
    - Câu có mốc thời gian -> KHÔNG phải xã giao ("bắt đầu họp lúc 9h thứ hai").
    """
    if len(van_ban.split()) >= SO_TU_TOI_DA_XA_GIAO:
        return False
    if re.search(MAU_THOI_GIAN, van_ban, flags=re.IGNORECASE):
        return False
    cac_ve = [ve.strip() for ve in re.split(r"[,.?!;]", van_ban) if ve.strip()]

    def co_mau(ve):
        return any(re.search(mau, ve, flags=re.IGNORECASE) for mau in MAU_XA_GIAO)

    def la_ve_ket(ve):
        return re.search(VE_KET_XA_GIAO, ve, flags=re.IGNORECASE) is not None

    return any(map(co_mau, cac_ve)) and all(co_mau(ve) or la_ve_ket(ve) for ve in cac_ve)


def tien_xu_ly(danh_sach_cau):
    """Nhận danh sách câu từ ASR, trả về câu đã xử lý với gốc, sạch và tách từ."""
    ket_qua = []
    for i, cau in enumerate(danh_sach_cau):
        van_ban = cau["text"]
        if not isinstance(van_ban, str):
            raise ValueError(f"câu số {i}: trường text phải là chuỗi, đang là {type(van_ban).__name__}")
        da_chuan_hoa = chuan_hoa_unicode(van_ban)
        da_sua = sua_loi_nhan_dang(da_chuan_hoa)
        da_bo_tu_dem = bo_tu_dem(da_sua)
        sach = chuan_hoa_khoang_trang(da_bo_tu_dem)
        if la_cau_rong(sach):
            continue  # Câu chỉ có từ đệm, không mang thông tin; stt vẫn đánh liên tục
        ket_qua.append(
            {
                "stt": len(ket_qua),
                "speaker": cau["speaker"],
                "start": cau["start"],
                "end": cau["end"],
                "goc": van_ban,
                "sach": sach,
                "tach_tu": tach_tu(sach),
                "xa_giao": la_xa_giao(sach),
            }
        )
    return ket_qua


def hien_thi(duong_dan):
    """Đường dẫn gọn để in ra: tương đối với thư mục dự án nếu được."""
    try:
        return duong_dan.relative_to(THU_MUC_GOC)
    except ValueError:
        return duong_dan


def luu_json(ket_qua, ten):
    """Ghi ra file tạm rồi mới đổi tên: phần NLP không bao giờ đọc phải file ghi dở."""
    THU_MUC_RA.mkdir(parents=True, exist_ok=True)
    tep_json = THU_MUC_RA / f"{ten}.json"
    tep_tam = tep_json.with_suffix(".json.tmp")
    try:
        with open(tep_tam, "w", encoding="utf-8") as f:
            json.dump(ket_qua, f, ensure_ascii=False, indent=2)
        os.replace(tep_tam, tep_json)
    finally:
        if tep_tam.exists():
            tep_tam.unlink()  # Lỗi giữa chừng thì không để lại file tạm
    return tep_json


def xu_ly_mot_file(duong_dan):
    """Đọc transcript, làm sạch, in ra màn hình và lưu vào data/processed/."""
    ket_qua = tien_xu_ly(doc_transcript(duong_dan))
    if not ket_qua:
        # Phần NLP coi danh sách rỗng là lỗi, nên không ghi file
        raise ValueError("bỏ từ đệm xong không còn câu nào, không ghi file.")
    for cau in ket_qua:
        danh_dau = "[xã giao] " if cau["xa_giao"] else ""
        print(f"{cau['stt']:2d}. {danh_dau}{cau['sach']}")
    return luu_json(ket_qua, duong_dan.stem)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/tien_xu_ly/tien_xu_ly.py <file transcript JSON hoặc thư mục>")

    cac_file = []
    for p in map(Path, sys.argv[1:]):
        cac_file += sorted(p.glob("*.json")) if p.is_dir() else [p]
    if not cac_file:
        sys.exit("Không có file transcript nào để xử lý.")

    so_loi = 0
    for duong_dan in cac_file:
        if len(cac_file) > 1:
            print(f"\n=== {duong_dan.name} ===")
        try:
            if not duong_dan.exists():
                raise FileNotFoundError("không tìm thấy file")
            tep_json = xu_ly_mot_file(duong_dan)
            print(f"Đã lưu vào {hien_thi(tep_json)}")
        except Exception as loi:
            so_loi += 1
            print(f"  ✗ Lỗi khi xử lý {duong_dan}: {loi}")
    if so_loi:
        sys.exit(1)
