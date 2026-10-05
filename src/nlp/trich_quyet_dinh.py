# Trích xuất quyết định của cuộc họp từ transcript đã làm sạch
import re

from nhan_dien_ten import lay_ten_nguoi_phan_anh
from trich_lich_hop import la_lich_hop
from trich_viec import co_dong_tu_hanh_dong, la_de_muc
from vet import ghi_vet


# Đuôi ", cuối cùng là KPI." là lời dẫn sang mục kế tiếp, không thuộc quyết định hiện tại
MAU_DUOI_CHU_DE = re.compile(
    r",\s*(?:cuối\s+cùng|tiếp\s+theo|còn\s+lại)\s+là\s+(?P<chu_de>[^\s.,;]+(?:\s+[^\s.,;]+){0,2})\s*\.?\s*$",
    flags=re.IGNORECASE,
)

# Câu bắt đầu bằng từ nối thì bổ sung cho quyết định liền trước
MAU_NOI_TIEP = re.compile(r"^(?:kèm|và|cùng)\b", flags=re.IGNORECASE)


def la_quyet_dinh(van_ban):
    """Nhận diện mệnh đề quyết định của cuộc họp."""
    if re.search(r"\b(chốt|thống nhất|quyết định|đồng ý|kpi|không dùng|tối thiểu|miễn phí vận chuyển)\b", van_ban, flags=re.IGNORECASE):
        ghi_vet("GIU_QUYET_DINH", None, van_ban, "giữ")
        return True
    if re.search(r"\b(từ tháng này|mỗi.*phải đạt|chỉ giảm|giảm\s+10%|giảm\s+20%)\b", van_ban, flags=re.IGNORECASE):
        ghi_vet("GIU_QUYET_DINH", None, van_ban, "giữ")
        return True
    ghi_vet("LOAI_KHONG_QUYET_DINH", None, van_ban, "loại")
    return False


def tach_duoi_chu_de(van_ban):
    """Cắt đuôi ', cuối cùng là X.' khỏi câu; trả (câu đã cắt, chủ đề X hoặc None)."""
    khop = MAU_DUOI_CHU_DE.search(van_ban)
    if not khop:
        return van_ban, None
    return van_ban[:khop.start()].rstrip(" ,;") + ".", khop.group("chu_de").strip()


def noi_quyet_dinh(truoc, sau):
    """Nối câu bổ sung vào quyết định trước, không để lại '.,' ở chỗ nối."""
    truoc = truoc.rstrip(" .,;")
    sau = sau.strip()
    if sau and not sau[:2].isupper():  # giữ nguyên chữ viết tắt như KPI
        sau = sau[0].lower() + sau[1:]
    return f"{truoc}, {sau}"


def trich_quyet_dinh(cac_cau, ten_biet):
    """Dựng danh sách quyết định của cuộc họp từ các câu đã làm sạch."""
    decisions = []
    chu_de_cho = None  # chủ đề từ đuôi câu trước, chỉ áp dụng cho câu liền sau

    for cau in cac_cau:
        text = cau["sach"]
        stt_cau = cau.get("stt", None)
        chu_de_truoc, chu_de_cho = chu_de_cho, None
        if la_lich_hop(text) or la_de_muc(text) or cau["xa_giao"]:
            ghi_vet("LOAI_QUYET_DINH_NEN", stt_cau, text, "loại")
            continue
        if not la_quyet_dinh(text):
            ghi_vet("LOAI_QUYET_DINH_NEN", stt_cau, text, "loại")
            continue
        if lay_ten_nguoi_phan_anh(text, ten_biet) is not None and co_dong_tu_hanh_dong(text):
            ghi_vet("LOAI_QUYET_DINH_LA_VIEC", stt_cau, text, "loại")
            continue

        phan, chu_de_moi = tach_duoi_chu_de(text)
        if chu_de_moi:
            ghi_vet("CAT_DUOI_CHU_DE", stt_cau, text, f"chuyển '{chu_de_moi}' sang câu sau")

        if len(decisions) and not chu_de_truoc and MAU_NOI_TIEP.match(phan):
            decisions[-1]["text"] = noi_quyet_dinh(decisions[-1]["text"], phan)
            ghi_vet("GOP_QUYET_DINH", stt_cau, text, "gộp")
        else:
            if chu_de_truoc and chu_de_truoc.lower() not in phan.lower():
                phan = f"{chu_de_truoc}: {phan}"
                ghi_vet("GAN_CHU_DE_QUYET_DINH", stt_cau, text, f"đặt tiêu đề '{chu_de_truoc}'")
            decisions.append({"text": phan.strip(), "start": cau["start"]})
            ghi_vet("TAO_QUYET_DINH", stt_cau, text, "giữ")
        chu_de_cho = chu_de_moi

    return decisions