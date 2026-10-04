# Nhận diện và trích xuất lịch họp tiếp theo từ transcript đã làm sạch
import re


def la_lich_hop(van_ban):
    """Nhận diện câu/chữ về lịch họp tiếp theo."""
    if re.search(r"\b(?:bắt đầu|mở đầu|chào mọi người).*\b(?:buổi\s+họp|họp\s+giao\s+ban)\b", van_ban, flags=re.IGNORECASE):
        return False
    if re.search(r"họp\s+(?:tiếp theo|sau|tiếp)|buổi\s+họp\s+(?:tiếp theo|sau)", van_ban, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(?:tối|sáng|chiều|buổi|ngày)\s+.*(?:họp|meeting)\b", van_ban, flags=re.IGNORECASE) and re.search(r"\b(?:lúc|tại|online|Google Meet|thứ)\b", van_ban, flags=re.IGNORECASE):
        return True
    return False


def lay_lich_hop(cac_cau):
    """Trích xuất thời gian và địa điểm của buổi họp tiếp theo."""
    for i, cau in enumerate(cac_cau):
        text = cau["sach"]
        if not la_lich_hop(text):
            continue
        thoi_gian = None
        dia_diem = None

        match = re.search(r"(?:họp\s+(?:tiếp theo|sau)|buổi\s+họp\s+(?:tiếp theo|sau))\s*(?:là|:)?\s*(.*?)(?:\.|$)", text, flags=re.IGNORECASE)
        if match:
            gia_tri = match.group(1).strip()
            if "," in gia_tri:
                phan_thoi_gian, phan_dia_diem = [p.strip() for p in gia_tri.split(",", 1)]
                if re.search(r"\b(?:tại|ở|online|Google Meet|phòng|trên|room)\b", phan_dia_diem, flags=re.IGNORECASE):
                    dia_diem = phan_dia_diem.strip().rstrip(".")
                    phan_thoi_gian = phan_thoi_gian.strip().rstrip(",.")
                thoi_gian = phan_thoi_gian.strip().rstrip(",.")
            else:
                thoi_gian = gia_tri.strip().rstrip(",.")

        if not thoi_gian:
            match = re.search(r"\b(?:tối|sáng|chiều|buổi)\s+.*?(?:,|\.|$)", text, flags=re.IGNORECASE)
            if match:
                thoi_gian = match.group(0).strip().rstrip(",.")

        if i + 1 < len(cac_cau):
            text_tiep = cac_cau[i + 1]["sach"]
            if re.search(r"(?:online|Google Meet|tại|ở|phòng|trên|hội trường|room|meeting)\b", text_tiep, flags=re.IGNORECASE):
                dia_diem = text_tiep.strip().rstrip(".")
                dia_diem = re.sub(r"^(?:họp\s+)?", "", dia_diem, flags=re.IGNORECASE)
                dia_diem = dia_diem.strip()

        if thoi_gian or dia_diem:
            return {
                "time": thoi_gian,
                "place": dia_diem,
                "start": cau["start"],
            }
    return None
