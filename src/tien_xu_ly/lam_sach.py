# Tiền xử lý transcript: sửa lỗi nhận dạng, bỏ từ đệm, đánh dấu câu xã giao, tách từ
# Người phụ trách: Hân.
#
# File này CHỈ chứa logic làm sạch (không đọc/ghi file), để hai nơi cùng dùng:
#   - src/tien_xu_ly/tien_xu_ly.py : chạy dòng lệnh, ghi data/processed/<tên>.json
#   - src/nlp/tien_xu_ly.py         : cầu nối cho phần NLP của Anh
#                                     (from tien_xu_ly import tien_xu_ly)
# Tên file khác "tien_xu_ly" để không trùng tên với file cầu nối bên src/nlp.
#
# ĐẦU RA của tien_xu_ly() (đã thống nhất với phần NLP, KHÔNG ĐƯỢC ĐỔI):
#   [{"stt", "speaker", "start", "end", "goc", "sach", "tach_tu", "xa_giao"}]
import re
import unicodedata

from pyvi import ViTokenizer

from tu_dien_tien_xu_ly import (
    MAU_THOI_GIAN,
    MAU_XA_GIAO,
    SO_TU_TOI_DA_XA_GIAO,
    SUA_LOI,
    TU_DEM,
    TU_GHEP,
    VE_KET_XA_GIAO,
)


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
