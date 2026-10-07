# Tiền xử lý transcript: sửa lỗi nhận dạng, bỏ từ đệm, đánh dấu câu xã giao, tách từ
import re
import sys
import unicodedata
from pathlib import Path

from pyvi import ViTokenizer

from doc_transcript import doc_transcript
from tu_dien import (
    MAU_XA_GIAO,
    SO_TU_TOI_DA_XA_GIAO,
    SUA_LOI,
    TU_DEM,
)

# In tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
sys.stdout.reconfigure(encoding="utf-8")


def sua_loi_nhan_dang(van_ban):
    """Sửa các từ Whisper hay nhận sai theo bảng SUA_LOI."""
    for mau, thay_the in SUA_LOI:
        van_ban = re.sub(mau, thay_the, van_ban, flags=re.IGNORECASE)
    return van_ban


def bo_tu_dem(van_ban):
    """Bỏ các từ đệm như ờ, ừm, à, nha, nhé."""
    return re.sub(TU_DEM, "", van_ban, flags=re.IGNORECASE)


def chuan_hoa_khoang_trang(van_ban):
    """Chuẩn hóa Unicode, dọn khoảng trắng và dấu câu thừa sau khi bỏ từ."""
    van_ban = unicodedata.normalize("NFC", van_ban)
    van_ban = re.sub(r"\s+", " ", van_ban)
    van_ban = re.sub(r"\s+([,.?!])", r"\1", van_ban)
    van_ban = re.sub(r"^[,.;:?!\s]+", "", van_ban)
    van_ban = re.sub(r"\s{2,}", " ", van_ban)
    return van_ban.strip()


def la_xa_giao(van_ban):
    """Câu ngắn chứa mẫu chào hỏi/cảm ơn/hỏi ý kiến thì coi là xã giao."""
    if len(van_ban.split()) >= SO_TU_TOI_DA_XA_GIAO:
        return False
    return any(re.search(mau, van_ban, flags=re.IGNORECASE) for mau in MAU_XA_GIAO)


def tien_xu_ly(danh_sach_cau):
    """Nhận danh sách câu từ ASR, trả về câu đã xử lý với gốc, sạch và tách từ."""
    ket_qua = []
    for stt, cau in enumerate(danh_sach_cau):
        van_ban = cau["text"]
        da_sua = sua_loi_nhan_dang(van_ban)
        da_bỏ_từ_đệm = bo_tu_dem(da_sua)
        sach = chuan_hoa_khoang_trang(da_bỏ_từ_đệm)
        ket_qua.append(
            {
                "stt": stt,
                "speaker": cau["speaker"],
                "start": cau["start"],
                "end": cau["end"],
                "goc": van_ban,
                "sach": sach,
                "tach_tu": ViTokenizer.tokenize(sach),
                "xa_giao": la_xa_giao(sach),
            }
        )
    return ket_qua


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/tien_xu_ly.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    for cau in tien_xu_ly(doc_transcript(duong_dan)):
        danh_dau = "[xã giao] " if cau["xa_giao"] else ""
        print(f"{cau['stt']:2d}. {danh_dau}{cau['sach']}")