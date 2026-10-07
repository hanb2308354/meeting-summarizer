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


# Từ khóa động từ của quyết định; chỉ tính khi không bị phủ định/mục đích đứng trước
TU_KHOA_DONG_TU = re.compile(r"\b(?:chốt|thống\s+nhất|quyết\s+định|đồng\s+ý)\b", flags=re.IGNORECASE)
TU_KHOA_PHU = re.compile(
    r"\b(?:kpi|không\s+dùng|tối\s+thiểu|miễn\s+phí\s+vận\s+chuyển)\b", flags=re.IGNORECASE
)

# Phủ định đứng trước từ khóa trong cùng mệnh đề (dấu phẩy/chấm chặn lại):
# "Đừng hiểu là mình vừa chốt tên mới" (đừng + tới 6 từ), "chưa chốt", "không thể chốt" (tối đa 2 từ chen giữa)
MAU_PHU_DINH_TRUOC = re.compile(
    r"\b(?:đừng(?:\s+[^\s,.;:]+){0,6}|(?:chưa|không|chẳng|chả)(?:\s+[^\s,.;:]+){0,2})\s*$",
    flags=re.IGNORECASE,
)
# "để thống nhất cách hiểu", "nhằm chốt kế hoạch": nêu mục đích, chưa phải quyết định
MAU_MUC_DICH_TRUOC = re.compile(r"\b(?:để|nhằm)\s+(?:cùng\s+)?$", flags=re.IGNORECASE)

# Quyết định dạng quy định/thể lệ, không cần chữ "chốt": "Từ tuần này, ...", "Từ nay, ...",
# "... phải được anh duyệt trước khi ..."; "từ giờ đến thứ 6" là khoảng thời gian của một việc nên loại
MAU_QUY_DINH = re.compile(
    r"\btừ\s+(?:tuần|tháng)\s+(?:này|sau|tới)\b(?!\s+(?:đến|tới|cho\s+đến))"
    r"|\btừ\s+(?:hôm\s+nay|nay|giờ|bây\s+giờ|buổi\s+(?:sau|tới)|lần\s+(?:sau|tới))\b(?!\s+(?:đến|tới|cho\s+đến))"
    r"|\b(?:phải|bắt\s+buộc)\s+được\b[^.]{0,60}?\btrước\s+khi\b"
    r"|\bmỗi\b.*\bphải\s+đạt\b",
    flags=re.IGNORECASE,
)

# Tên mà `lay_ten_nguoi_phan_anh` trả về khi chủ ngữ là người họp tự xưng (mình/tôi/em),
# không phải một người cụ thể được giao việc
NGUOI_CHU_TRI = "Người chủ trì"


def co_tu_khoa_quyet_dinh(van_ban):
    """Có từ khóa quyết định không bị phủ định hoặc nêu mục đích đứng trước."""
    for khop in TU_KHOA_DONG_TU.finditer(van_ban):
        truoc = van_ban[:khop.start()]
        if MAU_PHU_DINH_TRUOC.search(truoc):
            ghi_vet("BO_TU_KHOA_PHU_DINH", None, van_ban, f"bỏ '{khop.group(0)}': có phủ định đứng trước")
            continue
        if MAU_MUC_DICH_TRUOC.search(truoc):
            ghi_vet("BO_TU_KHOA_MUC_DICH", None, van_ban, f"bỏ '{khop.group(0)}': nêu mục đích")
            continue
        return True
    return bool(TU_KHOA_PHU.search(van_ban))


def la_quy_dinh(van_ban):
    """Câu dạng quy định/thể lệ áp dụng từ một mốc ('Từ nay, ...', 'phải được ... trước khi ...')."""
    return bool(MAU_QUY_DINH.search(van_ban))


def la_quyet_dinh(van_ban):
    """Nhận diện mệnh đề quyết định của cuộc họp."""
    if co_tu_khoa_quyet_dinh(van_ban):
        ghi_vet("GIU_QUYET_DINH", None, van_ban, "giữ")
        return True
    if la_quy_dinh(van_ban):
        ghi_vet("GIU_QUYET_DINH", None, van_ban, "giữ: dạng quy định")
        return True
    if re.search(r"\b(chỉ giảm|giảm\s+10%|giảm\s+20%)\b", van_ban, flags=re.IGNORECASE):
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
        ten_chu = lay_ten_nguoi_phan_anh(text, ten_biet)
        if ten_chu is not None and co_dong_tu_hanh_dong(text):
            # Quy định áp dụng từ một mốc do người chủ trì tự nêu ("Từ tuần này, mình kiểm quầy
            # hai lượt") là quyết định chứ không phải việc giao cho một người cụ thể
            if la_quy_dinh(text) and ten_chu == NGUOI_CHU_TRI:
                ghi_vet("GIU_QUY_DINH_DU_CO_CHU", stt_cau, text, "giữ: quy định của người chủ trì")
            else:
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