# Nhận diện tên người trong câu transcript đã làm sạch
import re

from tu_dien import DANH_SACH_DONG_TU, DANH_SACH_TU_CHUC_NANG


def chuan_hoa_ten(ten):
    """Viết hoa chữ cái đầu của tên người, giữ nguyên cách viết nhiều từ."""
    if not ten:
        return ten
    ten = ten.strip()
    if not ten:
        return ten
    chuoi = []
    for phan in ten.split():
        # Danh xưng hợp lệ; "thầy" không tính (giảng viên, không tham dự họp)
        if phan.lower() in {"bạn", "anh", "chị", "em", "cô", "chú"}:
            continue
        chuoi.append(phan[0].upper() + phan[1:] if phan else phan)
    return " ".join(chuoi)


def loai_bo_ten_cong_ty(van_ban):
    """Bỏ cụm tên công ty/tổ chức khỏi danh sách tên người để tránh nhầm người."""
    return re.sub(r"\bcông ty\s+[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)?", "", van_ban, flags=re.IGNORECASE)


# Danh xưng hợp lệ (quy tắc a): chỉ nhận tên người khi đứng sau danh xưng này
# hoặc khi là chữ viết hoa giữa câu (quy tắc b). "thầy" không dùng vì đó là
# giảng viên, không phải người trong cuộc họp.
DANH_XUNG = r"(?:bạn|anh|chị|em|cô|chú)"

# Động từ/từ đứng ngay sau tên viết hoa giữa câu (quy tắc b).
MAU_SAU_TEN_VIET_HOA = (
    r"(?:bên|làm|sẽ|phải|nên|cần|nhớ|gửi|viết|cập nhật|update|fix|sửa|upload|"
    r"phụ trách|xong|chạy|theo|test|thiết kế)"
)

# Chữ hoa đứng trước tên nhưng KHÔNG phải họ/tên đệm: danh từ chung, số/thứ, buổi,
# từ nối hay đứng đầu câu, danh xưng. (Tạm để ở đây; khi dọn kỹ thuật thì chuyển sang tu_dien.py.)
TU_KHONG_PHAI_HO_DEM = {
    "phần", "mục", "việc", "tôi", "thứ", "ngày", "dạ", "chốt",
    "hai", "ba", "tư", "năm", "sáu", "bảy", "nhật",
    "sáng", "trưa", "chiều", "tối", "đêm", "giờ", "lúc",
    "hiện", "tạm", "sớm", "nhưng", "với", "cho", "các", "những",
    "cả", "tất", "thế", "ừ",
    "còn", "và", "rồi", "vậy", "thì", "nếu", "ok", "để", "về", "đã",
    "này", "hôm", "tuần", "tháng",
    "mình", "em", "anh", "chị", "bạn", "cô", "chú", "thầy",
}

def _la_dau_cau(van_ban, vi_tri):
    """Vị trí có phải đầu câu (đầu chuỗi hoặc sau dấu . ! ?) không."""
    if vi_tri <= 0:
        return True
    return re.search(r"[.!?]\s*$", van_ban[:vi_tri]) is not None


# Chữ thường sau danh xưng chỉ là tên khi đứng ở vị trí người làm/người nhận việc.
# Lý do: "anh thấy", "em xem", "anh không muốn", "anh bảo vệ" là tự xưng + từ thường,
# không phải tên. (Tạm để ở đây; khi dọn kỹ thuật thì chuyển sang tu_dien.py.)
MAU_SAU_TEN_THUONG = re.compile(
    r"^\s+(?:bên\s+\w+(?:\s+\w+)?\s+)?(?:sẽ|phải|nên|cần|nhớ|cố\s+gắng|đang|"
    + "|".join(re.escape(d) for d in DANH_SACH_DONG_TU)
    + r")\b",
    flags=re.IGNORECASE,
)
MAU_TRUOC_NGUOI_NHAN = re.compile(
    r"(?:giao\s+cho|chuyển\s+(?:sang\s+)?cho|nhờ|phụ\s+trách)\s+$",
    flags=re.IGNORECASE,
)


def _chu_thuong_la_ten(danh, truoc, sau):
    """Chữ thường sau danh xưng: chỉ "bạn" mới nhận, và phải ở vị trí người làm/người nhận."""
    if (danh or "").strip().lower() != "bạn":
        return False
    return bool(MAU_SAU_TEN_THUONG.match(sau) or MAU_TRUOC_NGUOI_NHAN.search(truoc))


def _tu_hop_le_sau_danh_xung(danh, chu_dau, truoc="", sau=""):
    """Quy tắc (a): chữ đầu sau danh xưng.
    "cô/chú" chỉ nhận tên khi chữ đứng sau viết hoa (isupper() trên ký tự đầu);
    chữ thường chỉ nhận khi danh xưng là "bạn" và đứng ở vị trí người làm/người nhận
    (xem _chu_thuong_la_ten); chữ thường nằm trong DANH_SACH_TU_CHUC_NANG hoặc
    DANH_SACH_DONG_TU không bao giờ là tên.
    truoc: phần văn bản đứng trước danh xưng; sau: phần đứng ngay sau chữ đó.
    """
    if not chu_dau or chu_dau.lower() in DANH_SACH_TU_CHUC_NANG:
        return None
    if danh and danh.strip().lower() in {"cô", "chú"}:
        if not chu_dau[0].isupper():
            return None
    elif chu_dau.lower() in DANH_SACH_DONG_TU and not chu_dau[0].isupper():
        return None
    elif not chu_dau[0].isupper() and not _chu_thuong_la_ten(danh, truoc, sau):
        return None
    return chuan_hoa_ten(chu_dau)


def _tu_hop_le_viet_hoa(van_ban, vi_tri, chu_dau):
    """Quy tắc (b): chữ viết hoa, không ở đầu câu, không từ chức năng, không sau "thầy"."""
    if not chu_dau or not chu_dau[0].isupper():
        return None
    if chu_dau.lower() in DANH_SACH_TU_CHUC_NANG:
        return None
    if _la_dau_cau(van_ban, vi_tri):
        return None
    if re.search(r"thầy\s+$", van_ban[:vi_tri], flags=re.IGNORECASE):
        return None
    return chuan_hoa_ten(chu_dau)


def _gop_chu_thu_hai(ten_name, chu_thu_hai):
    """Chữ thứ hai chỉ gộp vào tên khi viết hoa và không phải từ chức năng hay động từ."""
    if not chu_thu_hai:
        return ten_name
    chu_thu_hai = chu_thu_hai.strip()
    if not chu_thu_hai[0].isupper():
        return ten_name
    if chu_thu_hai.lower() in DANH_SACH_TU_CHUC_NANG:
        return ten_name
    if chu_thu_hai.lower() in DANH_SACH_DONG_TU:
        return ten_name
    return f"{ten_name} {chu_thu_hai}"


def _chu_hai_tai(van_ban, vi_tri):
    """Chữ hoa ngay sau vị trí (nếu có) để gộp tên hai chữ."""
    match = re.match(r"\s+([A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*)", van_ban[vi_tri:])
    return match.group(1) if match else None

def _them_ho_dem(cac_chu):
    """cac_chu: các chữ hoa liên tiếp trước động từ, chữ cuối là tên chính.
    Trả về họ/tên đệm đứng ngay trước tên chính (đi ngược từ phải sang trái),
    dừng ở chữ đầu tiên không phải họ/đệm."""
    ho_dem = []
    for chu in reversed(cac_chu[:-1]):
        thuong = chu.lower()
        if not chu[0].isupper():
            break
        if (thuong in TU_KHONG_PHAI_HO_DEM
                or thuong in DANH_SACH_TU_CHUC_NANG
                or thuong in DANH_SACH_DONG_TU):
            break
        ho_dem.insert(0, chu)
    return ho_dem

def _ten_tu_match(van_ban, match):
    """Tên hợp lệ từ một match mẫu cấu trúc (quy tắc a/b), không thì None."""
    groups = match.groupdict()
    danh = groups.get("danh")
    chu_dau = groups.get("chu_dau")
    chu_hai = groups.get("chu_hai")
    if not chu_dau:
        return None
    if danh is not None:
        ten_name = _tu_hop_le_sau_danh_xung(
            danh, chu_dau,
            truoc=van_ban[: match.start("danh")], sau=van_ban[match.end("chu_dau"):],
        )
    else:
        ten_name = _tu_hop_le_viet_hoa(van_ban, match.start("chu_dau"), chu_dau)
    if ten_name is None:
        return None
    ten_name = _gop_chu_thu_hai(ten_name, chu_hai)
    if any(tu.lower() in {"mình", "tôi", "em", "anh", "chị", "bạn"} for tu in ten_name.split()):
        return None
    if ten_name.lower() in DANH_SACH_TU_CHUC_NANG:
        return None
    if ten_name.lower() in {"mọi người", "người chủ trì"}:
        return None
    return ten_name


def _ten_hop_le(ten_name):
    """Tên hợp lệ phải là danh từ người, không phải từ chức năng hoặc mảnh câu."""
    if not ten_name:
        return False
    ten_name = ten_name.strip()
    if not ten_name:
        return False
    if ten_name.lower() in {"mình", "tôi", "em", "anh", "chị", "bạn", "mọi người", "người chủ trì", "để", "ok", "nếu", "còn", "về", "đầu", "tiếp", "xong", "phụ trách", "làm", "đã", "trước", "thứ", "hôm", "này"}:
        return False
    if ten_name.lower() in DANH_SACH_TU_CHUC_NANG:
        return False
    if re.fullmatch(r"[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+){0,2}", ten_name) is None:
        return False
    return len(ten_name.split()) <= 3

def tim_ten_biet(cac_cau):
    """Dựng danh sách tên người đã biết qua cả cuộc họp."""
    ten = set()
    for cau in cac_cau:
        text = loai_bo_ten_cong_ty(cau["sach"])

        # (a) đứng sau danh xưng: "bạn Thanh Hà"; "bạn thảo" (thường, một chữ) vẫn nhận
        for match in re.finditer(
            rf"\b(?P<danh>{DANH_XUNG})\s+(?P<chu_dau>[A-ZÀ-Ỹa-zà-ỹ]+)",
            text,
            flags=re.IGNORECASE,
        ):
            ten_name = _tu_hop_le_sau_danh_xung(
                match.group("danh"), match.group("chu_dau"),
                truoc=text[: match.start()], sau=text[match.end():],
            )
            if ten_name is None:
                continue
            ten_name = _gop_chu_thu_hai(ten_name, _chu_hai_tai(text, match.end()))
            if _ten_hop_le(ten_name):
                ten.add(ten_name)

                # (b) 1-3 chữ hoa liên tiếp trước động từ, không ở đầu câu, không phải từ chức năng.
        # Chữ cuối là tên chính; họ/tên đệm đứng trước được gộp theo _them_ho_dem.
        # Giữ cả dạng đầy đủ lẫn dạng một chữ để lần nhắc ngắn ("Trâm sẽ…") vẫn khớp.
        for match in re.finditer(
            r"\b(?P<chuoi>[A-ZÀ-Ỹ][A-Za-zà-ỹÀ-Ỹ]*(?:\s+[A-ZÀ-Ỹ][A-Za-zà-ỹÀ-Ỹ]*){0,2})"
            rf"(?=\s+{MAU_SAU_TEN_VIET_HOA})",
            text,
        ):
            cac_chu = match.group("chuoi").split()
            chu_cuoi = cac_chu[-1]
            vi_tri_cuoi = match.end("chuoi") - len(chu_cuoi)
            ten_chinh = _tu_hop_le_viet_hoa(text, vi_tri_cuoi, chu_cuoi)
            if ten_chinh is None:
                continue
            ho_dem = [chuan_hoa_ten(chu) for chu in _them_ho_dem(cac_chu)]
            for ten_name in {" ".join(ho_dem + [ten_chinh]), ten_chinh}:
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
            if re.search(rf"\b{re.escape(ten)}\b.*(?:sẽ|phải|nên|làm|gửi|viết|update|fix|sửa|upload|cập nhật|phụ trách|nhớ|chạy|xong|test|cố gắng|hoàn thành|nộp|thiết kế|thực hiện|hỗ trợ)\b", van_ban, flags=re.IGNORECASE):
                return ten
            if re.search(rf"\b(?:giao cho|phụ trách)\s+(?:bạn\s+)?{re.escape(ten)}\b", van_ban, flags=re.IGNORECASE):
                return ten

    # Mẫu tên theo cấu trúc (không viết cứng tên hay câu mẫu): có danh xưng
    # (quy tắc a) hoặc chữ viết hoa giữa câu (quy tắc b); chữ thứ hai chỉ gộp
    # khi viết hoa và không phải từ chức năng hay động từ (xem _gop_chu_thu_hai).
    mau_ten = (
        rf"(?P<danh>(?i:{DANH_XUNG})\s+)?"
        r"(?P<chu_dau>[A-ZÀ-Ỹa-zà-ỹ]+)"
        r"(?P<chu_hai>\s+[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*)?"
    )
    for mau in [
        rf"\b(?i:giao\s+cho|phụ\s+trách)\s+{mau_ten}",
        rf"\b{mau_ten}\s+(?i:sẽ|phải|nên)\b",
        rf"\b{mau_ten}\s+(?i:làm|viết|gửi|upload|update|fix|sửa|cập nhật|phụ trách|chạy|test)\b",
        rf"\b(?P<danh>(?i:{DANH_XUNG})\s+)(?P<chu_dau>[A-ZÀ-Ỹa-zà-ỹ]+)(?P<chu_hai>\s+[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*)?\b.*(?i:sẽ|phải|nên|làm|viết|gửi|update|fix|sửa|upload|cập nhật|chạy|test)\b",
    ]:
        for match in re.finditer(mau, van_ban):
            ten_name = _ten_tu_match(van_ban, match)
            if ten_name:
                return ten_name

    if re.search(r"\b(mình|tôi|em)\b.*\b(làm|sẽ|gửi|viết|update|fix|upload|cập nhật|xong)\b", van_ban, flags=re.IGNORECASE):
        return "Người chủ trì"
    return None
