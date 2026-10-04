# Nhận diện tên người trong câu transcript đã làm sạch
import re

from tu_dien import DANH_SACH_TU_CHUC_NANG


def chuan_hoa_ten(ten):
    """Viết hoa chữ cái đầu của tên người, giữ nguyên cách viết nhiều từ."""
    if not ten:
        return ten
    ten = ten.strip()
    if not ten:
        return ten
    chuoi = []
    for phan in ten.split():
        if phan.lower() in {"bạn", "anh", "chị", "em", "cô", "thầy"}:
            continue
        chuoi.append(phan[0].upper() + phan[1:] if phan else phan)
    return " ".join(chuoi)


def loai_bo_ten_cong_ty(van_ban):
    """Bỏ cụm tên công ty/tổ chức khỏi danh sách tên người để tránh nhầm người."""
    return re.sub(r"\bcông ty\s+[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)?", "", van_ban, flags=re.IGNORECASE)


def _ten_hop_le(ten_name):
    """Tên hợp lệ phải là danh từ người, không phải từ chức năng hoặc mảnh câu."""
    if not ten_name:
        return False
    ten_name = ten_name.strip()
    if not ten_name:
        return False
    if ten_name.lower() in {"mình", "tôi", "em", "anh", "chị", "bạn", "mọi người", "người chủ trì", "để", "ok", "nếu", "còn", "về", "đầu", "tiếp", "xong", "phụ trách", "làm", "đã", "trước", "thứ", "hôm", "này"}:
        return False
    if re.fullmatch(r"(?:[A-ZÀ-Ỹa-zà-ỹ]+|[A-ZÀ-Ỹa-zà-ỹ]+\s+[A-ZÀ-Ỹa-zà-ỹ]+)", ten_name) is None:
        return False
    return len(ten_name.split()) <= 2


def tim_ten_biet(cac_cau):
    """Dựng danh sách tên người đã biết qua cả cuộc họp."""
    ten = set()
    for cau in cac_cau:
        text = loai_bo_ten_cong_ty(cau["sach"])
        for match in re.finditer(
            r"\b(?:bạn|anh|chị|em)\s+([A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*)(?:\s+[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*)?\b",
            text,
            flags=re.IGNORECASE,
        ):
            ten_name = chuan_hoa_ten(match.group(1))
            if _ten_hop_le(ten_name):
                ten.add(ten_name)

        for match in re.finditer(
            r"\b([A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*)(?=\s+(?:bên|làm|sẽ|phải|nên|cần|nhớ|gửi|viết|cập nhật|update|fix|sửa|upload|phụ trách|xong|chạy|theo|test|thiết kế))",
            text,
        ):
            ten_name = chuan_hoa_ten(match.group(1))
            if _ten_hop_le(ten_name):
                ten.add(ten_name)

    return sorted(ten, key=len, reverse=True)


def lay_ten_nguoi_phan_anh(van_ban, ten_biet):
    """Tìm người phụ trách theo các mẫu tên người, ưu tiên tên đã biết."""
    van_ban = loai_bo_ten_cong_ty(van_ban)
    if re.search(r"\bmọi người\b.*\b(làm|nộp|upload|gửi|viết|cập nhật|chạy|ghi|xong)\b", van_ban, flags=re.IGNORECASE):
        return "Mọi người"

    for ten in ten_biet:
        if re.search(rf"\b(?:bạn|anh|chị|em)?\s*{re.escape(ten)}\b", van_ban, flags=re.IGNORECASE):
            if re.search(rf"\b{re.escape(ten)}\b.*(?:sẽ|phải|nên|làm|gửi|viết|update|fix|sửa|upload|cập nhật|phụ trách|nhớ|chạy|xong|test)\b", van_ban, flags=re.IGNORECASE):
                return ten
            if re.search(rf"\b(?:giao cho|phụ trách)\s+(?:bạn\s+)?{re.escape(ten)}\b", van_ban, flags=re.IGNORECASE):
                return ten

    for mau in [
        r"\b(?:giao cho|phụ trách)\s+(?:bạn\s+)?([A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)*)\b",
        r"\b([A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)*)\s+(?:sẽ|phải|nên)\s+",
        r"\b([A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)*)\s+(?:làm|viết|gửi|upload|update|fix|sửa|cập nhật|phụ trách|chạy|test)\b",
        r"\b(?:bạn|anh|chị|em)\s+([A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)*)\b.*(?:sẽ|phải|nên|làm|viết|gửi|update|fix|sửa|upload|cập nhật|chạy|test)\b",
    ]:
        match = re.search(mau, van_ban, flags=re.IGNORECASE)
        if match:
            ten_name = chuan_hoa_ten(match.group(1) if match.lastindex else match.group(0))
            if any(word.lower() in {"mình", "tôi", "em", "anh", "chị", "bạn"} for word in ten_name.split()):
                continue
            if len(ten_name.split()) <= 2 and ten_name and ten_name.lower() not in DANH_SACH_TU_CHUC_NANG and ten_name.lower() not in {"mọi người", "người chủ trì"}:
                return ten_name

    if re.search(r"\b(mình|tôi|em)\b.*\b(làm|sẽ|gửi|viết|update|fix|upload|cập nhật|xong)\b", van_ban, flags=re.IGNORECASE):
        return "Người chủ trì"
    return None
