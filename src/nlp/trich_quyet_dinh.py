# Trích xuất quyết định của cuộc họp từ transcript đã làm sạch
import re

from nhan_dien_ten import lay_ten_nguoi_phan_anh, tim_ten_biet
from trich_lich_hop import la_lich_hop
from trich_viec import co_dong_tu_hanh_dong, la_de_muc


def la_quyet_dinh(van_ban):
    """Nhận diện mệnh đề quyết định của cuộc họp."""
    if re.search(r"\b(chốt|thống nhất|quyết định|đồng ý|kpi|không dùng|tối thiểu|miễn phí vận chuyển|kèm)\b", van_ban, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(từ tháng này|mỗi.*phải đạt|chỉ giảm|kèm miễn phí vận chuyển|giảm\s+10%|giảm\s+20%)\b", van_ban, flags=re.IGNORECASE):
        return True
    return False


def lay_quyet_dinh(cac_cau):
    """Trích xuất các quyết định nhớ và nối mệnh đề tiếp theo nếu cần."""
    ket_qua = []
    i = 0
    while i < len(cac_cau):
        text = cac_cau[i]["sach"]
        if la_quyet_dinh(text):
            if lay_ten_nguoi_phan_anh(text, tim_ten_biet(cac_cau)) is not None and co_dong_tu_hanh_dong(text):
                i += 1
                continue
            phan = text
            if i + 1 < len(cac_cau):
                text_tiep = cac_cau[i + 1]["sach"]
                if re.match(r"^(kèm|và|cùng|cuối cùng là|từ tháng này|mỗi)\b", text_tiep, flags=re.IGNORECASE):
                    phan = f"{phan}, {text_tiep}"
                    i += 1
            ket_qua.append({"text": phan.strip(), "start": cac_cau[i]["start"]})
        i += 1
    return ket_qua


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
