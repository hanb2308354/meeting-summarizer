# Nhận diện hạn chót trong câu transcript đã làm sạch
import re

# Các dạng ngày/mốc thời gian: "thứ 6", "thứ 6 tuần này", "chủ nhật", "ngày 20 tháng 11",
# "5/11", "ngày mai", "cuối tuần"...
THU = r"thứ\s+(?:\d+|hai|ba|tư|bốn|năm|sáu|bảy)\b(?:\s+tuần\s+(?:này|sau|tới))?"
CHU_NHAT = r"chủ\s+nhật(?:\s+tuần\s+(?:này|sau|tới))?"
NGAY_THANG = r"(?:ngày\s+)?\d{1,2}\s+tháng\s+\d{1,2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?"
MOC_KHAC = (
    r"hôm\s+nay|ngày\s+mai|ngày\s+kia|cuối\s+tuần(?:\s+này)?|cuối\s+tháng(?:\s+này)?"
    r"|tuần\s+(?:này|sau|tới)|tháng\s+(?:này|sau|tới)"
)
MAU_NGAY = re.compile(
    rf"\b(?:{THU}|{CHU_NHAT}|{NGAY_THANG}|{MOC_KHAC})(?!\w)(?!\s+(?:tuần|tháng)\s+trước)",
    flags=re.IGNORECASE,
)

# Cụm có từ khóa hạn: "hạn là X", "deadline gửi bản này là X", "hạn chót: X"
MAU_NHAN_HAN = re.compile(
    r"\b(?:deadline|hạn\s+chót|chậm\s+nhất|hạn)\b[^,.:;?!]{0,40}?(?:\blà\b|:)\s*(?P<gia_tri>[^,.;?!]+)",
    flags=re.IGNORECASE,
)

# Câu nói về hạn cũ/hạn dự kiến: không phải hạn hiện hành
MAU_HAN_CU = re.compile(r"\b(?:ban\s+đầu|lúc\s+đầu|hạn\s+cũ|hạn\s+(?:chót\s+)?dự\s+kiến)\b", flags=re.IGNORECASE)
# Ngày đứng sau "tuần trước/hôm trước" là quá khứ; sau "không để/đừng để" là hạn bị bác bỏ
MAU_TRUOC_NGAY_QUA_KHU = re.compile(r"(?:tuần|tháng|hôm|ngày)\s+trước\s*$", flags=re.IGNORECASE)
MAU_PHU_DINH = re.compile(r"(?:không|đừng)\s+(?:để\s+)?(?:đến|vào|trước)?\s*$", flags=re.IGNORECASE)
# Từ đi trước ngày cho thấy đây là hạn (ưu tiên cao hơn ngày trần)
MAU_TIEN_TO_HAN = re.compile(r"(?:trước|chậm\s+nhất|vào|đến|xong)\s*$", flags=re.IGNORECASE)
MAU_DUOI_THUA = re.compile(r"\s+(?:luôn|nhé|nha|nữa|thôi|ạ)$", flags=re.IGNORECASE)


def tim_han_chot(van_ban):
    """Trích xuất hạn chót từ mệnh đề hoặc câu; trả danh sách, phần tử đầu là hạn chính."""
    van_ban = van_ban.strip()
    if not van_ban:
        return []
    van_ban = re.sub(r"(?:,\s*)?(?:còn\s+)?(?:ai\s+có\s+ý\s+kiến\s+gì\s+không\?|có\s+ai\s+.*\bý\s+kiến\b.*\?|cảm\s+ơn.*)$", "", van_ban, flags=re.IGNORECASE)
    if re.match(r"^thứ\s+\d+\s+là\b", van_ban, flags=re.IGNORECASE):
        return []
    if MAU_HAN_CU.search(van_ban):
        return []

    ung_vien = []  # (mức ưu tiên, vị trí, giá trị); ưu tiên 0 là có từ khóa hạn
    for khop in MAU_NHAN_HAN.finditer(van_ban):
        gia_tri = khop.group("gia_tri").strip()
        gia_tri = re.sub(r"^(?:đó\s+là|đây\s+là)\s*", "", gia_tri, flags=re.IGNORECASE)
        ngay = MAU_NGAY.search(gia_tri)
        if ngay:
            gia_tri = gia_tri[: ngay.end()].strip()
        else:
            gia_tri = MAU_DUOI_THUA.sub("", gia_tri).strip()
            if re.search(r"\b(?:điều này|ý kiến|có ai|đến|gặp|lúc)\b", gia_tri, flags=re.IGNORECASE):
                continue
        if gia_tri and gia_tri.lower() not in {"là", "đây", "đó"}:
            ung_vien.append((0, khop.start(), gia_tri))

    for khop in MAU_NGAY.finditer(van_ban):
        truoc = van_ban[: khop.start()]
        if MAU_TRUOC_NGAY_QUA_KHU.search(truoc) or MAU_PHU_DINH.search(truoc):
            continue
        uu_tien = 1 if MAU_TIEN_TO_HAN.search(truoc) else 2
        ung_vien.append((uu_tien, khop.start(), khop.group(0).strip()))

    ung_vien.sort(key=lambda x: (x[0], x[1]))
    return list(dict.fromkeys(gia_tri for _, _, gia_tri in ung_vien))