# Trích xuất quyết định của cuộc họp từ transcript đã làm sạch
import re

from nhan_dien_ten import lay_ten_nguoi_phan_anh
from trich_lich_hop import la_lich_hop
from trich_viec import co_dong_tu_hanh_dong, la_de_muc


def la_quyet_dinh(van_ban):
    """Nhận diện mệnh đề quyết định của cuộc họp."""
    if re.search(r"\b(chốt|thống nhất|quyết định|đồng ý|kpi|không dùng|tối thiểu|miễn phí vận chuyển|kèm)\b", van_ban, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(từ tháng này|mỗi.*phải đạt|chỉ giảm|kèm miễn phí vận chuyển|giảm\s+10%|giảm\s+20%)\b", van_ban, flags=re.IGNORECASE):
        return True
    return False


def trich_quyet_dinh(cac_cau, ten_biet):
    """Dựng danh sách quyết định của cuộc họp từ các câu đã làm sạch."""
    decisions = []

    for cau in cac_cau:
        text = cau["sach"]
        if la_lich_hop(text) or la_de_muc(text) or cau["xa_giao"]:
            continue
        if not la_quyet_dinh(text):
            continue
        if lay_ten_nguoi_phan_anh(text, ten_biet) is not None and co_dong_tu_hanh_dong(text):
            continue
        phan = text
        if len(decisions) and re.match(r"^(kèm|và|cùng|cuối cùng là|từ tháng này|mỗi)\b", text, flags=re.IGNORECASE):
            phan = f"{decisions[-1]['text']}, {text}"
            decisions[-1]["text"] = phan.strip()
            continue
        decisions.append({"text": phan.strip(), "start": cau["start"]})

    return decisions
