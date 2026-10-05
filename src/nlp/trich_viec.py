# Dựng danh sách việc cần làm từ transcript đã làm sạch
import re

from nhan_dien_han import tim_han_chot
from nhan_dien_ten import lay_ten_nguoi_phan_anh
from trich_lich_hop import la_lich_hop
from tu_dien import (
    DANH_SACH_DONG_TU, DONG_TU_BO_SUNG,
    MAU_CAU_GAN_CHU_CHO_VIEC,
    MAU_VIEC_CHO_CHU,
    TIN_HIEU_GIAO_VIEC,
)
from vet import ghi_vet

# Động từ bổ sung (tu_dien.DONG_TU_BO_SUNG), khớp nguyên từ
MAU_DONG_TU_BO_SUNG = re.compile(
    r"\b(?:" + "|".join(re.escape(d) for d in sorted(DONG_TU_BO_SUNG, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Từ mở đầu mệnh đề: không phải lý do để loại, chỉ bỏ ra rồi kiểm động từ trên phần còn lại
MO_DAU_MENH_DE = r"^(?:mình|tôi|em|việc\s+này|còn|thứ(?:\s+\d+)?|phần(?:\s+này)?|bên)\b\s*"

# Cụm gán chủ đứng cuối mệnh đề: không có đối tượng công việc theo sau
# "giao cho (bạn|anh|chị|em|cô|chú)? Tên (phụ trách)?", "Tên phụ trách", "để (mình|tôi|em) làm"
CUM_GAN_CHU_CUOI = (
    r"(?:"
    r"giao\s+cho\s+(?:(?:bạn|anh|chị|em|cô|chú)\s+)?[a-zà-ỹ]+(?:\s+[a-zà-ỹ]+)?(?:\s+phụ\s+trách)?"
    r"|[a-zà-ỹ]+(?:\s+[a-zà-ỹ]+)?\s+phụ\s+trách"
    r"|để\s+(?:mình|tôi|em)\s+làm"
    r")\s*[,.;:!?]*$"
)


def bo_mo_dau(van_ban):
    """Bỏ từ mở đầu (và đại từ chủ ngữ) khỏi mệnh đề."""
    return re.sub(MO_DAU_MENH_DE, "", van_ban, count=1, flags=re.IGNORECASE)


def bo_cum_gan_chu_cuoi(van_ban):
    """Bỏ cụm gán chủ đứng cuối mệnh đề, trả về phần còn lại; không có thì trả None."""
    khop = re.search(CUM_GAN_CHU_CUOI, van_ban, flags=re.IGNORECASE)
    if not khop:
        return None
    return (van_ban[: khop.start()] + van_ban[khop.end() :]).strip()

# Kiểu "<đối tượng> (thì) (tự) làm" / "... phụ trách": đối tượng, rồi động từ nhẹ cuối mệnh đề
MAU_DOI_TUONG_LAM = r"^(?P<dau>.+?)\s+(?:thì\s+)?(?:tự\s+)?(?:làm|phụ\s+trách)\s*[,;:.!?]*$"

# Từ đệm đứng đầu đối tượng: "thì phần", "còn về", "riêng việc"
MAU_TU_DEM_DAU = r"^(?:(?:thì|còn|về|riêng|việc)\s+)+"

# Chủ ngữ "mình/tôi/em" đứng trước động từ ("để thứ 2 mình test chung"); không tính khi là tân ngữ
MAU_CHU_NGU_TU_XUNG = (
    r"(?<!\bcho\s)(?<!\bvới\s)(?<!\bgiúp\s)(?<!\bnhờ\s)(?<!\bbảo\s)"
    r"\b(?:mình|tôi|em)\s+(?:sẽ\s+|tự\s+)?\S"
)

def tach_han_cuoi(van_ban):
    """Cắt cụm hạn đứng cuối mệnh đề; trả (phần còn lại, cụm hạn) hoặc (van_ban, None)."""
    han = tim_han_chot(van_ban)
    if not han:
        return van_ban, None
    khop = re.search(
        rf"\s+(?:(?:chậm\s+nhất|trước|vào|đến)\s+)?{re.escape(han[0])}\s*[,;:.!?]*$",
        van_ban,
        flags=re.IGNORECASE,
    )
    if not khop:
        return van_ban, None
    return van_ban[: khop.start()].rstrip(), han[0]

# Mệnh đề chỉ có động từ ("mình sẽ rà soát lại"), dùng khi mệnh đề liền trước đã nêu đối tượng
MAU_DONG_TU_TRAN = (
    r"^(?:(?:mình|tôi|em)\s+)?(?:(?:sẽ|tự|cũng|rồi|sau\s+đó)\s+)*"
    r"(?P<dt>(?:rà\s+soát|kiểm\s+tra|review|check|test|hoàn\s+thiện|xử\s+lý|làm|sửa|viết|chạy|gửi|nộp|cập\s+nhật|update|fix|thiết\s+kế)"
    r"(?:\s+(?:lại|kỹ|xong|luôn|nốt))?)\s*[,;:.!?]*$"
)


def tach_dong_tu_tran(van_ban):
    """Trả cụm động từ nếu mệnh đề (sau khi cắt hạn cuối) chỉ gồm chủ ngữ tự xưng + động từ; không thì None."""
    phan, _ = tach_han_cuoi(van_ban.strip())
    khop = re.match(MAU_DONG_TU_TRAN, phan.strip(), flags=re.IGNORECASE)
    return khop.group("dt") if khop else None

# Lời gọi tên ngôi hai: "Ngân, em đối chiếu…", "Hiếu, để em lo…" → "Ngân sẽ đối chiếu…"
# Chỉ áp dụng khi chữ trước dấu phẩy là tên đã biết (viết hoa, đứng đầu câu); loại câu hỏi ý kiến ("em thấy…")
TU_NHAN_THUC_SAU_EM = r"(?:thấy|nghĩ|biết|hiểu|muốn|có\s+thể|có\s+ý\s+kiến)"


def chuan_hoa_goi_ten(text, ten_biet):
    """Đổi "<Tên>, (để) em/bạn <việc>" thành "<Tên> sẽ <việc>"; trả (text mới, có đổi không).
    Tên đứng sau dấu chấm của câu trước thì đổi dấu chấm thành dấu phẩy để tên mở một mệnh đề riêng."""
    if not ten_biet:
        return text, False
    nhom_ten = "|".join(re.escape(ten) for ten in ten_biet)
    goi_ten = (
        rf"(?P<ten>{nhom_ten}),\s+(?:để\s+)?(?:em|bạn)\s+(?:sẽ\s+)?"
        rf"(?!{TU_NHAN_THUC_SAU_EM}\b)"
    )
    moi = re.sub(rf"[.!?]\s+{goi_ten}", lambda m: ", " + m.group("ten") + " sẽ ", text)
    moi = re.sub(rf"^{goi_ten}", lambda m: m.group("ten") + " sẽ ", moi)
    return moi, moi != text

def co_dong_tu_trong_danh_sach(phan):
    """Phần còn lại có động từ hành động trong DANH_SACH_DONG_TU không."""
    return any(
        re.search(rf"\b{re.escape(dong_tu)}\b", phan, flags=re.IGNORECASE)
        for dong_tu in DANH_SACH_DONG_TU
    )


def la_de_muc(phan):
    """Nhận diện các câu đề mục không mang việc như 'Đầu tiên là phần API'"""
    phan = phan.strip()
    if not phan:
        ghi_vet("LOAI_DE_MUC", None, phan, "loại")
        return True
    if re.match(r"^(đầu tiên|tiếp theo|cuối cùng|tiếp theo đó)\s+là\b", phan, flags=re.IGNORECASE):
        ghi_vet("LOAI_DE_MUC", None, phan, "loại")
        return True
    if re.match(r"^thứ\s+\d+\s+là\b", phan, flags=re.IGNORECASE):
        ghi_vet("LOAI_DE_MUC", None, phan, "loại")
        return True
    if re.match(r"^(?:phần|mục)\s+.*$", phan, flags=re.IGNORECASE):
        # Câu mở đầu bằng "Phần/Mục" nhưng chứa tín hiệu giao việc thì không phải đề mục
        if not any(
            re.search(rf"\b{re.escape(tin_hieu)}\b", phan, flags=re.IGNORECASE)
            for tin_hieu in TIN_HIEU_GIAO_VIEC
        ):
            ghi_vet("LOAI_DE_MUC", None, phan, "loại")
            return True
    ghi_vet("LOAI_DE_MUC", None, phan, "giữ")
    return False


def co_dong_tu_hanh_dong(van_ban, stt_cau=None, chu=None):
    """Mệnh đề có động từ hành động thì coi là việc cần làm."""
    van_ban_goc = van_ban.strip()
    van_ban = van_ban.lower().strip()
    van_ban = re.sub(
        r"^(?:vì vậy|do đó|ngoài ra|tuy nhiên|nhưng|nên|còn)\b\s*,?\s*",
        "",
        van_ban,
        flags=re.IGNORECASE,
    )
    if not van_ban:
        ghi_vet("LOAI_KHONG_DONG_TU", None, van_ban, "loại")
        return False
    if re.fullmatch(r"(?:để|phụ trách|làm|xong)\s*[,.;]?\s*", van_ban):
        ghi_vet("LOAI_KHONG_DONG_TU", None, van_ban, "loại")
        return False

    # Tập thể đồng ý/thống nhất là quyết định đã chốt, không phải lời giao việc.
    # Có tín hiệu giao việc mạnh trong câu thì giữ nguyên hành vi cũ.
    if MAU_DONG_Y_TAP_THE.search(van_ban) and not MAU_TIN_HIEU_MANH.search(van_ban):
        ghi_vet("LOAI_KHONG_DONG_TU", stt_cau, van_ban_goc, "loại: tập thể đồng ý/thống nhất (quyết định, không phải giao việc)")
        return False
        
    # Cụm gán chủ đứng cuối mệnh đề: áp dụng cho mọi mệnh đề, chỉ loại nếu sau khi bỏ
    # cụm không còn động từ hành động; nếu còn thì giữ rồi kiểm bình thường ở dưới
    phan_gan_chu = bo_cum_gan_chu_cuoi(van_ban)
    if phan_gan_chu is not None and not co_dong_tu_trong_danh_sach(phan_gan_chu):
        ghi_vet(
            "LOAI_KHONG_DONG_TU",
            stt_cau,
            van_ban_goc,
            "loại: chỉ còn cụm gán chủ",
        )
        return False
    if re.match(MO_DAU_MENH_DE, van_ban, flags=re.IGNORECASE):
        # Bỏ từ mở đầu rồi mới kiểm động từ hành động trên phần còn lại
        phan_con = bo_mo_dau(van_ban)
        if not phan_con:
            ghi_vet("LOAI_KHONG_DONG_TU", None, van_ban, "loại: bỏ từ mở đầu xong rỗng")
            return False
    else:
        phan_con = van_ban

        # "chưa/đã/vừa xong" là trạng thái, không phải việc phải làm
    phan_con = re.sub(r"\b(?:chưa|đã|vừa|mới|chẳng)\s+xong\b", " ", phan_con)
        # "làm việc với <ai>" là làm việc cùng, không phải giao việc: bỏ cụm này trước khi kiểm động từ
    phan_con = re.sub(r"\blàm\s+việc\s+với\b", " ", phan_con)

    if re.search(r"\b(?:làm|update|sửa|fix|viết|gửi|upload|cập nhật|phụ trách|chạy|test|thiết kế|hoàn thành|nộp|xong|hỗ trợ|thực hiện|điều|cố gắng)\b", phan_con):
        ghi_vet("LOAI_KHONG_DONG_TU", None, van_ban, "giữ")
        return True
    if MAU_DONG_TU_BO_SUNG.search(phan_con):
        ghi_vet("LOAI_KHONG_DONG_TU", stt_cau, van_ban_goc, "giữ: động từ bổ sung")
        return True
    # Tín hiệu mạnh: "<Tên> sẽ/cần/nhớ <từ>" là giao việc dù động từ chưa có trong danh sách
    # (vd "Khoa sẽ optimize ..."). Chỉ áp dụng cho chủ có tên; "mình/em" chờ xử lý riêng.
    if chu and chu not in ("Người chủ trì", "Mọi người") and re.search(
        rf"\b{re.escape(chu)}\b\s+(?:sẽ|cần|nhớ)\s+(?!(?:là|có|được|bị|đi|gặp|ở)\b)\S+",
        van_ban,
        flags=re.IGNORECASE,
    ):
        ghi_vet("LOAI_KHONG_DONG_TU", stt_cau, van_ban_goc, "giữ: tín hiệu mạnh")
        return True
    ghi_vet("LOAI_KHONG_DONG_TU", None, van_ban, "loại")
    return False


def cat_viec(van_ban, owner):
    """Lấy phần mô tả việc từ động từ hành động trở đi."""
    text = van_ban.strip()
    if not text:
        return text

    text = re.sub(r"^\s*(?:còn\s+)?(?:một\s+việc\s+nữa\s+là|việc\s+nữa\s+là|một\s+việc\s+là)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:tiếp\s+theo\s+là|đầu\s+tiên\s+là|cuối\s+cùng\s+là|thứ\s+\d+\s+là)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*việc\s+(?:này|đó)\s+", "", text, flags=re.IGNORECASE)

    # Chủ có tên đứng ngay trước "sẽ/cần/nhớ": mô tả bắt đầu sau tín hiệu, không cần động từ trong danh sách
    sau_tin_hieu = bool(
        owner
        and owner not in ("Người chủ trì", "Mọi người")
        and re.search(rf"\b{re.escape(owner)}\b\s+(?:sẽ|cần|nhớ)\s+\S", text, flags=re.IGNORECASE)
    )
    # Cụm gán chủ theo tên đã biết: chỉ bỏ đúng tên chủ, không ăn từ đứng sau
    if owner and owner != "Người chủ trì":
        ten = re.escape(owner)
        text = re.sub(
            rf"\b(?:giao\s+cho|chuyển\s+(?:sang\s+)?cho|phụ\s+trách)\s+(?:(?:bạn|anh|chị|em|cô|chú)\s+)?{ten}\b\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

    for mau in [
        r"\b(?:bạn|anh|chị|em)\s+[A-ZÀ-Ỹa-zà-ỹ]+\s+",
        r"\b[A-ZÀ-Ỹa-zà-ỹ]+\s+(?:sẽ|phải|nên|cần|nhớ)\s+",
        r"\b(?:để|việc này\s+để|nên)\s+",
        r"\b(?:mình|tôi|em)\s+(?:sẽ\s+)?",
        r"^(?:bên|trong|ở|tại)\s+[^,;.!?]+?\s+(?:sẽ|phải|nên|cần|nhớ)\s+",
    ]:
        text = re.sub(mau, "", text, flags=re.IGNORECASE)

    if owner == "Người chủ trì":
        text = re.sub(r"^\s*(?:việc này\s+)?(?:để\s+)?(?:mình|tôi|em)\s*(?:sẽ\s+)?", "", text, flags=re.IGNORECASE)

    # Kiểu "<đối tượng> (thì) làm": giữ đối tượng, bỏ động từ nhẹ đứng cuối
    khop_cuoi = None
    giu_dong_tu_dau = False
    khop_cuoi = re.match(MAU_DOI_TUONG_LAM, text, flags=re.IGNORECASE)
    if not khop_cuoi:
        # Có cụm hạn đứng sau "làm" ("... thì để mình tự làm trước ngày 15 tháng 12"): cắt hạn rồi khớp lại
        phan_truoc_han, han_cuoi = tach_han_cuoi(text)
        if han_cuoi:
            giu_dong_tu_dau = False
            khop_cuoi = re.match(MAU_DOI_TUONG_LAM, phan_truoc_han, flags=re.IGNORECASE)
    if khop_cuoi and len(khop_cuoi.group("dau").split()) >= 2:
        text = re.sub(MAU_TU_DEM_DAU, "", khop_cuoi.group("dau").strip(), flags=re.IGNORECASE)
        
        # Kiểu "<đối tượng> phụ trách <việc>" (sau khi đã bỏ cụm "giao cho <chủ>"):
    # đưa việc lên trước, đối tượng ra sau. Chỉ áp dụng khi đối tượng không chứa động từ hành động
    khop_phu_trach = re.match(r"^(?P<dau>.+?)\s+phụ\s+trách\s+(?P<duoi>\S.*)$", text, flags=re.IGNORECASE)
    if khop_phu_trach and len(khop_phu_trach.group("dau").split()) >= 2:
        dau = khop_phu_trach.group("dau").strip()
        co_dong_tu_that = any(
            re.search(rf"\b{re.escape(dong_tu)}\b", dau, flags=re.IGNORECASE)
            for dong_tu in DANH_SACH_DONG_TU
            if dong_tu not in ("làm", "phụ trách", "xong")
        )
        if not co_dong_tu_that:
            dau = re.sub(MAU_TU_DEM_DAU, "", dau, flags=re.IGNORECASE)
            dau = re.sub(r"\s+này$", "", dau, flags=re.IGNORECASE)
            duoi = re.sub(r"[,;:.!?\s]+$", "", khop_phu_trach.group("duoi"))
            if len(dau.split()) >= 2:
                dau = re.sub(r"^(?:Phần|Mục)\b", lambda m: m.group(0).lower(), dau)
                text = f"{duoi} {dau}"
            elif dau.lower() in ("phần", "mục"):
                # Đối tượng chỉ còn chữ đề mục ("Phần này giao cho Lan phụ trách làm ..."): bỏ đề mục
                text = duoi
                giu_dong_tu_dau = True

    if not giu_dong_tu_dau:
        text = re.sub(r"^(?:phụ\s+trách|để|làm(?!\s+lại\b)|nên|cố\s+gắng)\s*[,;:.-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:bên|trong|ở|tại|trên)\s+[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+){0,3}\s*[,;:.-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:trên|tại|ở)\s+", "", text, flags=re.IGNORECASE)

    # Điểm bắt đầu: động từ hành động xuất hiện SỚM NHẤT theo vị trí trong câu
    vi_tri = []
    for dong_tu in DANH_SACH_DONG_TU:
        match = re.search(rf"\b{re.escape(dong_tu)}\b", text, flags=re.IGNORECASE)
        if match:
            vi_tri.append(match.start())
    if sau_tin_hieu:
        text = re.sub(r"^(?:phải|cần|nên|sẽ)\s+", "", text.strip(), flags=re.IGNORECASE)
    elif vi_tri:
        text = text[min(vi_tri):].strip()
    elif MAU_DONG_TU_BO_SUNG.search(text):
        # Không có động từ trong DANH_SACH_DONG_TU: bắt đầu từ động từ bổ sung
        text = text[MAU_DONG_TU_BO_SUNG.search(text).start():].strip()
    text = re.sub(r"^(?:là|đó\s+là)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:,\s*)?(?:còn\s+)?(?:ai\s+có\s+ý\s+kiến\s+gì\s+không\?|có\s+ai\s+.*\bý\s+kiến\b.*\?|cảm\s+ơn.*|để\s+thứ\s+\d+\s+mình\s+test\s+chung.*)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+[,;]$", "", text)
    text = re.sub(r"\s*[,;]\s*(?:để|và|cùng|cũng)\s+.*$", "", text, flags=re.IGNORECASE)
    if not re.search(r"[A-Za-zÀ-Ỹà-ỹ0-9]", text):
        return ""
    return text.strip()

# Từ không mang nội dung khi so hai mô tả việc: động từ nhẹ, từ chức năng, từ chỉ ngày
# (tạm để ở đây; khi dọn kỹ thuật thì chuyển sang tu_dien.py)
TU_KHONG_NOI_DUNG = frozenset("""
làm lại gửi viết nộp sửa chạy test update cập nhật phụ trách hoàn thành thực hiện cố gắng xong
bản phần việc file cái các những từng mỗi mọi
và cùng cũng với cho của để là thì mà nên rồi luôn nhé nha nữa thôi ạ gấp sớm ngay
trước sau vào đến này đó kia thứ tuần tháng ngày hôm nay mai chủ
lúc giờ phút hai ba tư năm sáu bảy nhật
""".split())

# Mệnh đề nói về ý định/phân công cũ: không tạo việc
MAU_Y_DINH_CU = r"\b(?:ban\s+đầu|lúc\s+đầu|dự\s+định\s+giao|định\s+giao|tính\s+giao)\b"


# Câu đổi/gia hạn: việc này cập nhật một việc đã có của cùng chủ
MAU_CAP_NHAT_HAN = r"\b(?:gia\s+hạn|dời\s+hạn|lùi\s+hạn|đổi\s+hạn|hạn\s+mới)\b"

# Mệnh đề không phải lời giao việc: lời kể quá khứ, phủ định/cấm, ước đoán, dẫn lời.
# Có tín hiệu giao việc mạnh trong mệnh đề thì KHÔNG loại ("Nam sẽ làm, không cần ai giúp").
MAU_TIN_HIEU_MANH = re.compile(
    r"(?<!không\s)(?<!chưa\s)\b(?:sẽ|phải|nhớ|phụ\s+trách|giao\s+cho)\b", re.IGNORECASE
)
MAU_KE_QUA_KHU = re.compile(
    r"^(?:(?:mà|còn|nhưng|và)\s+)?(?:hôm\s+qua|hôm\s+trước|bữa\s+trước|bữa\s+nọ|"
    r"(?:tuần|tháng|buổi)\s+trước|(?:tuần|tháng)\s+rồi|lúc\s+nãy|hồi\s+nãy|vừa\s+rồi)\b"
    r"|\b(?:hôm\s+qua|hôm\s+trước|bữa\s+trước|tuần\s+trước|tuần\s+rồi|lúc\s+nãy|hồi\s+nãy)\s+thì\b",
    re.IGNORECASE,
)
MAU_PHU_DINH_CAM = re.compile(
    r"\b(?:đừng(?!\s+quên)|không\s+cần|khỏi\s+phải|chưa\s+cần)\b", re.IGNORECASE
)
MAU_UOC_DOAN = re.compile(
    r"^(?:(?:mà|còn|nhưng|và)\s+)?(?:có\s+thể|có\s+lẽ|hình\s+như|chắc\b(?!\s+chắn))",
    re.IGNORECASE,
)
MAU_DAN_LOI = re.compile(
    r"\b(?:có|đã|vừa|mới)\s+(?:bảo|nói|kể|than|phản\s+ánh)\b", re.IGNORECASE
)

# Tập thể đồng ý/thống nhất/nhất trí: quyết định đã chốt, không phải lời giao việc
# ("Lúc nãy mọi người đồng ý để demo chạy trên máy cục bộ"). Một người nhận việc ("Nam đồng ý làm …") không thuộc luật này.
MAU_DONG_Y_TAP_THE = re.compile(
    r"\b(?:mọi\s+người|cả\s+(?:nhóm|team|lớp)|nhóm(?:\s+mình)?|team(?:\s+mình)?)\s+"
    r"(?:(?:đã|cùng|đều|vừa)\s+)*(?:đồng\s+ý|thống\s+nhất|nhất\s+trí)\b",
    re.IGNORECASE,
)

def ly_do_khong_giao_viec(clause):
    """Trả lý do nếu mệnh đề là lời kể/phủ định/ước đoán/dẫn lời (không phải giao việc); không thì None."""
    if MAU_TIN_HIEU_MANH.search(clause):
        return None
    if MAU_KE_QUA_KHU.search(clause):
        return "lời kể quá khứ"
    if MAU_PHU_DINH_CAM.search(clause):
        return "phủ định/cấm"
    if MAU_UOC_DOAN.search(clause):
        return "ước đoán"
    if MAU_DAN_LOI.search(clause) and not tim_han_chot(clause):
        return "dẫn lời"
    return None

def tu_noi_dung(mo_ta):
    """Tập từ mang nội dung của mô tả việc (bỏ động từ nhẹ, từ chức năng, số)."""
    return {
        tu for tu in re.findall(r"\w+", mo_ta.lower())
        if not tu.isdigit() and tu not in TU_KHONG_NOI_DUNG
    }


def do_trung_noi_dung(mo_ta_a, mo_ta_b):
    """Trả (số từ nội dung chung, tỷ lệ chung so với mô tả ngắn hơn)."""
    a, b = tu_noi_dung(mo_ta_a), tu_noi_dung(mo_ta_b)
    chung = len(a & b)
    nho = min(len(a), len(b))
    return chung, (chung / nho if nho else 0.0)


def tim_viec_trung(tasks, owner, mo_ta, cap_nhat_han):
    """Tìm việc cũ của cùng chủ mà mô tả mới nhắc lại; không có thì trả None."""
    tot_nhat, diem_nhat = None, (0, 0.0)
    for task in tasks:
        if task["owner"] != owner:
            continue
        chung, ti_le = do_trung_noi_dung(task["task"], mo_ta)
        hop_le = chung >= 1 if cap_nhat_han else (chung >= 2 and ti_le >= 0.5)
        if hop_le and (chung, ti_le) >= diem_nhat:
            tot_nhat, diem_nhat = task, (chung, ti_le)
    return tot_nhat

# Mệnh đề không tên nhưng có hạn và nhắc lại nội dung một việc chưa có hạn: gắn hạn cho việc đó
KHOANG_CACH_HAN_THEO_NOI_DUNG = 3   # số đoạn tối đa giữa việc và mệnh đề chứa hạn
SO_TU_CHUNG_HAN_THEO_NOI_DUNG = 3   # số từ nội dung chung tối thiểu


def gan_han_theo_noi_dung(tasks, clause, chi_so, vi_tri_viec, stt_cau):
    """Trả True nếu đã gắn hạn của mệnh đề cho một việc chưa có hạn (khớp theo nội dung)."""
    han = tim_han_chot(clause)
    if not han:
        return False
    tot_nhat, diem_nhat = None, (0, 0.0)
    for task in tasks:
        if task["deadline"] is not None:
            continue
        if chi_so - vi_tri_viec.get(id(task), -99) > KHOANG_CACH_HAN_THEO_NOI_DUNG:
            continue
        chung, ti_le = do_trung_noi_dung(task["task"], clause)
        if chung >= SO_TU_CHUNG_HAN_THEO_NOI_DUNG and ti_le >= 0.5 and (chung, ti_le) > diem_nhat:
            tot_nhat, diem_nhat = task, (chung, ti_le)
    if tot_nhat is None:
        return False
    tot_nhat["deadline"] = han[0]
    ghi_vet("GAN_HAN_THEO_NOI_DUNG", stt_cau, clause, f"gắn {han[0]} cho việc của {tot_nhat['owner']}: {tot_nhat['task']}")
    return True

def ghi_nhan_viec(tasks, owner, task_text, start, clause, chi_so_cau, vi_tri_viec, last_task, stt_cau):
    """Tạo việc mới, hoặc gộp/cập nhật hạn vào việc cũ của cùng chủ; trả về việc đã ghi."""
    han = tim_han_chot(clause)
    han_moi = han[0] if han else None
    cap_nhat_han = re.search(MAU_CAP_NHAT_HAN, clause, flags=re.IGNORECASE) is not None

    viec_cu, kieu = None, "moi"
    if not tu_noi_dung(task_text):
        # Không có đối tượng công việc: chỉ là cập nhật hạn cho việc ngay trước của cùng chủ
        gan = (
            last_task is not None
            and last_task["owner"] == owner
            and chi_so_cau - vi_tri_viec.get(id(last_task), -99) <= 2
        )
        if gan:
            viec_cu, kieu = last_task, "cap_nhat"
    else:
        viec_cu = tim_viec_trung(tasks, owner, task_text, cap_nhat_han)
        if viec_cu is not None:
            kieu = "gop"

    if viec_cu is None:
        task_item = {"task": task_text, "owner": owner, "deadline": None, "start": start}
        tasks.append(task_item)
        ghi_vet("TAO_VIEC", stt_cau, clause, f"giữ {owner}: {task_text}")
        if han_moi:
            ghi_vet("GAN_HAN_TRUC_TIEP", stt_cau, clause, f"gắn {han_moi}")
            task_item["deadline"] = han_moi
    else:
        task_item = viec_cu
        if kieu == "gop":
            task_item["task"] = task_text  # mô tả lấy từ lần nhắc sau cùng
            ghi_vet("GOP_VIEC_TRUNG", stt_cau, clause, f"gộp vào việc của {owner}: {task_text}")
        else:
            ghi_vet("CAP_NHAT_VIEC", stt_cau, clause, f"chỉ cập nhật hạn cho việc của {owner}")
        if han_moi:  # hạn lần sau thay hạn cũ; không có thì giữ hạn cũ
            ghi_vet("GAN_HAN_TRUC_TIEP", stt_cau, clause, f"gắn {han_moi} (thay hạn cũ)")
            task_item["deadline"] = han_moi

    vi_tri_viec[id(task_item)] = chi_so_cau
    return task_item

# Từ nối đứng trước cụm hạn ở cuối mô tả: bỏ cùng với hạn
MAU_NOI_TRUOC_HAN = (
    r"(?:(?:hạn\s+chót|deadline|hoàn\s+thành)\s+là\s+|chậm\s+nhất\s+là\s+|chậm\s+nhất\s+"
    r"|trước\s+|vào\s+|đến\s+|cho\s+|là\s+)*"
)
# Giờ đứng ngay sau hạn ("thứ Năm lúc 21 giờ", "thứ Sáu 18 giờ 30")
MAU_GIO_SAU_HAN = r"(?:\s+(?:lúc\s+)?\d{1,2}(?:\s*giờ|h)(?:\s*\d{1,2})?)?"


def lam_sach_mo_ta(mo_ta, han):
    """Bỏ dấu câu thừa đầu/cuối; bỏ cụm hạn (kèm từ nối, giờ) nếu nó đứng cuối mô tả.
    Chỉ bỏ khi phần còn lại vẫn có từ nội dung; không đổi gì khác."""
    text = re.sub(r"^[\s.,;:!?]+|[\s.,;:!?]+$", "", mo_ta or "")
    if han:
        khop = re.search(
            rf"\s*{MAU_NOI_TRUOC_HAN}{re.escape(han)}{MAU_GIO_SAU_HAN}$",
            text,
            flags=re.IGNORECASE,
        )
        if khop:
            phan = re.sub(r"[\s.,;:!?]+$", "", text[: khop.start()])
            if tu_noi_dung(phan):
                text = phan
    return text

def lay_viec(cac_cau, ten_biet):
    """Dựng danh sách việc cần làm từ các câu đã làm sạch."""
    tasks = []
    last_task = None
    viec_cho_chu = None
    vi_tri_viec = {}  # id(việc) -> chỉ số câu nhắc gần nhất (để giới hạn khoảng cách cập nhật hạn)
    for chi_so, cau in enumerate(cac_cau):
        text = cau["sach"].strip()
        stt_cau = cau.get("stt", None)

        # Việc chờ chủ: chỉ xét câu liền sau; không gán được chủ thì hủy,
        # tuyệt đối không tạo task không có chủ
        if viec_cho_chu is not None:
            if re.match(MAU_CAU_GAN_CHU_CHO_VIEC, text, flags=re.IGNORECASE):
                chu_moi = lay_ten_nguoi_phan_anh(text, ten_biet)
                if chu_moi:
                    task_item = {
                        "task": viec_cho_chu["mo_ta"],
                        "owner": chu_moi,
                        "deadline": None,
                        "start": viec_cho_chu["start"],
                    }
                    tasks.append(task_item)
                    last_task = task_item
                    ghi_vet(
                        "GAN_CHU_CHO_VIEC",
                        viec_cho_chu["stt"],
                        viec_cho_chu["mo_ta"],
                        f"gắn {chu_moi}",
                    )
                else:
                    ghi_vet(
                        "HUY_VIEC_CHO_CHU",
                        viec_cho_chu["stt"],
                        viec_cho_chu["mo_ta"],
                        "hủy: câu gán chủ nhưng không nhận ra người",
                    )
                viec_cho_chu = None
            else:
                ghi_vet(
                    "HUY_VIEC_CHO_CHU",
                    viec_cho_chu["stt"],
                    viec_cho_chu["mo_ta"],
                    "hủy: câu liền sau không gán chủ",
                )
                viec_cho_chu = None

        if not text or cau["xa_giao"]:
            ghi_vet("LOAI_XA_GIAO_RONG", stt_cau, text, "loại")
            continue
        if la_lich_hop(text):
            ghi_vet("LOAI_LICH_HOP", stt_cau, text, "loại")
            continue
                # Whisper hay dính hai câu vào một đoạn: bỏ các câu đề mục ở đầu đoạn, giữ phần còn lại
        cac_phan = [phan for phan in re.split(r"(?<=[.!?])\s+", text) if phan.strip()]
        while len(cac_phan) > 1 and la_de_muc(cac_phan[0]):
            ghi_vet("BO_DE_MUC_DAU_DOAN", stt_cau, cac_phan[0], "bỏ câu đề mục, giữ phần sau")
            cac_phan.pop(0)
        text = " ".join(cac_phan)
        if la_de_muc(text):
            ghi_vet("LOAI_DE_MUC", stt_cau, text, "loại")
            continue
        if re.search(r"\b[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*\s+làm\b.*?,\s*[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*\s+làm\b", text, flags=re.IGNORECASE):
            ghi_vet("LOAI_LIET_KE_NGUOI", stt_cau, text, "loại")
            continue
        if re.match(r"^(?:ok|cảm ơn|vậy thôi|chào)\b", text, flags=re.IGNORECASE):
            ghi_vet("LOAI_CAU_XA_GIAO", stt_cau, text, "loại")
            continue
        if re.fullmatch(r"(?:để|phụ trách|làm)\b.*", text, flags=re.IGNORECASE):
            ghi_vet("LOAI_MANH_CAU", stt_cau, text, "loại")
            continue
        ghi_vet("GIU_CAU", stt_cau, text, "giữ")

        # Một việc nữa chưa có chủ: ghi nhớ việc chờ, chưa tạo task;
        # câu liền sau gán chủ thì tạo, không thì hủy
        khop_viec_moi = re.search(MAU_VIEC_CHO_CHU, text, flags=re.IGNORECASE)
        if khop_viec_moi and lay_ten_nguoi_phan_anh(text, ten_biet) is None:
            mo_ta_cho = khop_viec_moi.group("mo_ta").strip()
            viec_cho_chu = {
                "mo_ta": mo_ta_cho,
                "stt": stt_cau,
                "start": cau["start"],
            }
            ghi_vet("VIEC_CHO_CHU", stt_cau, text, f"ghi nhớ: {mo_ta_cho}")
        text, da_doi = chuan_hoa_goi_ten(text, ten_biet)
        if da_doi:
            ghi_vet("CHUAN_HOA_GOI_TEN", stt_cau, text, "đổi 'Tên, em …' thành 'Tên sẽ …'")
        clauses = [part.strip() for part in re.split(r"\s*,\s*", text) if part.strip()]
        sentence_owner = None
        sau_gan_chu = False  # chỉ bật lại nếu chính mệnh đề này là cụm gán chủ thuần
        doi_tuong_truoc = None
        doi_tuong_cho = None
        viec_liet_ke = None   # việc đang nhận các mảnh liệt kê không tên sau câu gán chủ
        sau_gan_chu = False   # mệnh đề liền trước là cụm gán chủ thuần
        for clause in clauses:
            doi_tuong_truoc, doi_tuong_cho = doi_tuong_cho, None  # chỉ giữ đối tượng cho mệnh đề liền sau
            if not clause:
                ghi_vet("LOAI_MENH_DE_RONG", stt_cau, clause, "loại")
                continue
            if re.match(r"^(?:nếu không|vậy thôi|cảm ơn|ok|chào)\b", clause, flags=re.IGNORECASE):
                ghi_vet("LOAI_MENH_DE_XA_GIAO", stt_cau, clause, "loại")
                continue
            if re.search(r"\bđã\s+.*\bxong\b", clause, flags=re.IGNORECASE):
                ghi_vet("LOAI_DA_XONG", stt_cau, clause, "loại")
                continue
            if re.fullmatch(r"(?:để|phụ trách|làm|xong|test chung|có ai.*|ai.*\?)", clause, flags=re.IGNORECASE):
                ghi_vet("LOAI_MANH_CAU_NGAN", stt_cau, clause, "loại")
                continue

            if re.match(r"^(?:deadline|hạn chót|hạn)\b", clause, flags=re.IGNORECASE):
                han = tim_han_chot(clause)
                if han and last_task and last_task["deadline"] is None:
                    ghi_vet("GAN_HAN_NGUOC", stt_cau, clause, f"gắn {han[0]}")
                    last_task["deadline"] = han[0]
                    # Hạn nói một lần cho cả cụm việc cùng chủ liền trước (chưa có hạn, trong 3 câu)
                    for viec_truoc in reversed(tasks):
                        if viec_truoc is last_task:
                            continue
                        if viec_truoc["owner"] != last_task["owner"] or viec_truoc["deadline"] is not None:
                            break
                        if chi_so - vi_tri_viec.get(id(viec_truoc), -99) > 3:
                            break
                        ghi_vet("GAN_HAN_NGUOC", stt_cau, clause, f"gắn {han[0]} cho cả việc trước của {viec_truoc['owner']}")
                        viec_truoc["deadline"] = han[0]
                else:
                    ghi_vet("GAN_HAN_NGUOC", stt_cau, clause, "loại")
                continue

            if re.search(MAU_Y_DINH_CU, clause, flags=re.IGNORECASE):
                ghi_vet("LOAI_Y_DINH_CU", stt_cau, clause, "loại: ý định/phân công cũ")
                continue

            ly_do = ly_do_khong_giao_viec(clause)
            if ly_do:
                ghi_vet("LOAI_KHONG_GIAO_VIEC", stt_cau, clause, f"loại: {ly_do}")
                continue
            
            owner = lay_ten_nguoi_phan_anh(clause, ten_biet)
            if owner is not None:
                ghi_vet("GAN_CHU_VIEC", stt_cau, clause, f"gắn {owner}")
                sentence_owner = owner
                sau_gan_chu = False  # chỉ bật lại nếu chính mệnh đề này là cụm gán chủ thuần
                # Mệnh đề chỉ có động từ ngay sau mệnh đề gán chủ cùng chủ: việc = động từ + đối tượng trước đó
                dong_tu_tran = None
                if doi_tuong_truoc and doi_tuong_truoc[0] == owner:
                    dong_tu_tran = tach_dong_tu_tran(clause)
                if dong_tu_tran:
                    task_text = f"{dong_tu_tran} {doi_tuong_truoc[1]}"
                    ghi_vet("NOI_DOI_TUONG_CHO", stt_cau, clause, f"nối đối tượng mệnh đề trước: {task_text}")
                    last_task = ghi_nhan_viec(
                        tasks, owner, task_text, cau["start"], clause,
                        chi_so, vi_tri_viec, last_task, stt_cau,
                    )
                    continue
                if not co_dong_tu_hanh_dong(clause, stt_cau, owner):
                    # Mệnh đề chỉ còn cụm gán chủ: nhớ để các mệnh đề không tên liền sau là phần liệt kê của việc này
                    phan_gan_chu = bo_cum_gan_chu_cuoi(clause.strip())
                    if phan_gan_chu is not None:
                        sau_gan_chu = True
                        viec_liet_ke = None
                    if phan_gan_chu:
                        phan_gan_chu = re.sub(MAU_TU_DEM_DAU, "", phan_gan_chu, flags=re.IGNORECASE).strip()
                        if tu_noi_dung(phan_gan_chu):
                            doi_tuong_cho = (owner, phan_gan_chu)
                    ghi_vet("LOAI_KHONG_DONG_TU", stt_cau, clause, "loại")
                    continue

                task_text = cat_viec(clause, owner)
                if not task_text or task_text.lower() in {"họp", "đầu tiên là", "tiếp theo là", "điều này", "theo điều này"}:
                    ghi_vet("LOAI_MO_TA_RONG", stt_cau, clause, "loại")
                    continue

                                # Chủ tự xưng/tập thể mà mô tả chỉ có động từ ("nhóm mình phải update lại"): không có đối tượng nên không là việc,
                # trừ khi đó là câu cập nhật hạn cho việc ngay trước của cùng chủ
                if (
                    owner in ("Người chủ trì", "Mọi người")
                    and not tu_noi_dung(task_text)
                    and not (
                        last_task is not None
                        and last_task["owner"] == owner
                        and chi_so - vi_tri_viec.get(id(last_task), -99) <= 2
                    )
                ):
                    ghi_vet("LOAI_THIEU_DOI_TUONG", stt_cau, clause, f"loại: chỉ có động từ, chủ {owner}")
                    continue

                last_task = ghi_nhan_viec(
                    tasks, owner, task_text, cau["start"], clause,
                    chi_so, vi_tri_viec, last_task, stt_cau,
                )
                continue

            if sentence_owner and co_dong_tu_hanh_dong(clause, stt_cau):
                # Mệnh đề không tên có chủ ngữ "mình/tôi/em": không kế thừa chủ của mệnh đề trước
                chu_menh_de = sentence_owner
                if re.search(MAU_CHU_NGU_TU_XUNG, clause, flags=re.IGNORECASE):
                    chu_menh_de = "Người chủ trì"
                    ghi_vet("DOI_CHU_TU_XUNG", stt_cau, clause, "chủ ngữ tự xưng: Người chủ trì")
                task_text = cat_viec(clause, chu_menh_de)
                if task_text and task_text.lower() not in {"họp", "đầu tiên là", "tiếp theo là", "điều này", "theo điều này"}:
                    if (
                        viec_liet_ke is not None
                        and last_task is viec_liet_ke
                        and chu_menh_de == viec_liet_ke["owner"]
                    ):
                        # Mảnh liệt kê tiếp theo sau câu gán chủ ("giao cho X phụ trách, làm A, sửa B với xóa C"): một việc
                        ghi_vet("GOP_LIET_KE", stt_cau, clause, f"nối vào việc của {chu_menh_de}: {task_text}")
                        viec_liet_ke["task"] = viec_liet_ke["task"].rstrip(" .,;") + ", " + task_text
                    elif last_task and last_task["owner"] == chu_menh_de and last_task["start"] == cau["start"] and re.search(r"\b(?:và|cùng|cũng|đồng thời)\b", clause, flags=re.IGNORECASE):
                        ghi_vet("GOP_VIEC", stt_cau, clause, f"gộp {chu_menh_de}: {task_text}")
                        last_task["task"] = f"{last_task['task']}, {task_text}"
                    else:
                        last_task = ghi_nhan_viec(
                            tasks, chu_menh_de, task_text, cau["start"], clause,
                            chi_so, vi_tri_viec, last_task, stt_cau,
                        )
                        viec_liet_ke = last_task if sau_gan_chu else None
                        sau_gan_chu = False
                    han = tim_han_chot(clause)
                    if han and last_task["deadline"] is None:
                        ghi_vet("GAN_HAN_TRUC_TIEP", stt_cau, clause, f"gắn {han[0]}")
                        last_task["deadline"] = han[0]
                else:
                    ghi_vet("LOAI_MO_TA_RONG", stt_cau, clause, "loại")
                continue
            if not gan_han_theo_noi_dung(tasks, clause, chi_so, vi_tri_viec, stt_cau):
                ghi_vet("LOAI_KHONG_CHU_VIEC", stt_cau, clause, "loại")
    return tasks
