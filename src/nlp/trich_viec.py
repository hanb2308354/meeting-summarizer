# Dựng danh sách việc cần làm từ transcript đã làm sạch
import re

from nhan_dien_han import tim_han_chot
from nhan_dien_ten import lay_ten_nguoi_phan_anh
from trich_lich_hop import la_lich_hop
from tu_dien import (
    DANH_SACH_DONG_TU,
    MAU_CAU_GAN_CHU_CHO_VIEC,
    MAU_VIEC_CHO_CHU,
    TIN_HIEU_GIAO_VIEC,
)
from vet import ghi_vet

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


def co_dong_tu_hanh_dong(van_ban, stt_cau=None):
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
    if re.search(r"\b(?:làm|update|sửa|fix|viết|gửi|upload|cập nhật|phụ trách|chạy|test|thiết kế|hoàn thành|nộp|xong|hỗ trợ|thực hiện|điều|cố gắng)\b", phan_con):
        ghi_vet("LOAI_KHONG_DONG_TU", None, van_ban, "giữ")
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
    khop_cuoi = re.match(r"^(?P<dau>.+?)\s+(?:thì\s+)?(?:làm|phụ\s+trách)\s*[,;:.!?]*$", text, flags=re.IGNORECASE)
    if khop_cuoi and len(khop_cuoi.group("dau").split()) >= 2:
        text = re.sub(r"^(?:về|còn|riêng|việc)\s+", "", khop_cuoi.group("dau").strip(), flags=re.IGNORECASE)
        
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
            dau = re.sub(r"\s+này$", "", dau, flags=re.IGNORECASE)
            dau = re.sub(r"^(?:Phần|Mục)\b", lambda m: m.group(0).lower(), dau)
            duoi = re.sub(r"[,;:.!?\s]+$", "", khop_phu_trach.group("duoi"))
            text = f"{duoi} {dau}"

    text = re.sub(r"^(?:phụ\s+trách|để|làm|nên|cố\s+gắng)\s*[,;:.-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:bên|trong|ở|tại|trên)\s+[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+){0,3}\s*[,;:.-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:trên|tại|ở)\s+", "", text, flags=re.IGNORECASE)

    # Điểm bắt đầu: động từ hành động xuất hiện SỚM NHẤT theo vị trí trong câu
    vi_tri = []
    for dong_tu in DANH_SACH_DONG_TU:
        match = re.search(rf"\b{re.escape(dong_tu)}\b", text, flags=re.IGNORECASE)
        if match:
            vi_tri.append(match.start())
    if vi_tri:
        text = text[min(vi_tri):].strip()

    text = re.sub(r"^(?:là|đó\s+là)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:,\s*)?(?:còn\s+)?(?:ai\s+có\s+ý\s+kiến\s+gì\s+không\?|có\s+ai\s+.*\bý\s+kiến\b.*\?|cảm\s+ơn.*|để\s+thứ\s+\d+\s+mình\s+test\s+chung.*)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+[,;]$", "", text)
    text = re.sub(r"\s*[,;]\s*(?:để|và|cùng|cũng)\s+.*$", "", text, flags=re.IGNORECASE)
    if not re.search(r"[A-Za-zÀ-Ỹà-ỹ0-9]", text):
        return ""
    return text.strip()

def lay_viec(cac_cau, ten_biet):
    """Dựng danh sách việc cần làm từ các câu đã làm sạch."""
    tasks = []
    last_task = None
    viec_cho_chu = None

    for cau in cac_cau:
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

        clauses = [part.strip() for part in re.split(r"\s*,\s*", text) if part.strip()]
        sentence_owner = None

        for clause in clauses:
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
                else:
                    ghi_vet("GAN_HAN_NGUOC", stt_cau, clause, "loại")
                continue

            owner = lay_ten_nguoi_phan_anh(clause, ten_biet)
            if owner is not None:
                ghi_vet("GAN_CHU_VIEC", stt_cau, clause, f"gắn {owner}")
                sentence_owner = owner
                if not co_dong_tu_hanh_dong(clause, stt_cau):
                    ghi_vet("LOAI_KHONG_DONG_TU", stt_cau, clause, "loại")
                    continue
                task_text = cat_viec(clause, owner)
                if not task_text or task_text.lower() in {"họp", "đầu tiên là", "tiếp theo là", "điều này", "theo điều này"}:
                    ghi_vet("LOAI_MO_TA_RONG", stt_cau, clause, "loại")
                    continue
                task_item = {"task": task_text, "owner": owner, "deadline": None, "start": cau["start"]}
                tasks.append(task_item)
                last_task = task_item
                ghi_vet("TAO_VIEC", stt_cau, clause, f"giữ {owner}: {task_text}")
                han = tim_han_chot(clause)
                if han and task_item["deadline"] is None:
                    ghi_vet("GAN_HAN_TRUC_TIEP", stt_cau, clause, f"gắn {han[0]}")
                    task_item["deadline"] = han[0]
                continue

            if sentence_owner and co_dong_tu_hanh_dong(clause, stt_cau):
                task_text = cat_viec(clause, sentence_owner)
                if task_text and task_text.lower() not in {"họp", "đầu tiên là", "tiếp theo là", "điều này", "theo điều này"}:
                    if last_task and last_task["owner"] == sentence_owner and last_task["start"] == cau["start"] and re.search(r"\b(?:và|cùng|cũng|đồng thời)\b", clause, flags=re.IGNORECASE):
                        ghi_vet("GOP_VIEC", stt_cau, clause, f"gộp {sentence_owner}: {task_text}")
                        last_task["task"] = f"{last_task['task']}, {task_text}"
                    else:
                        task_item = {"task": task_text, "owner": sentence_owner, "deadline": None, "start": cau["start"]}
                        tasks.append(task_item)
                        last_task = task_item
                        ghi_vet("TAO_VIEC", stt_cau, clause, f"giữ {sentence_owner}: {task_text}")
                    han = tim_han_chot(clause)
                    if han and last_task["deadline"] is None:
                        ghi_vet("GAN_HAN_TRUC_TIEP", stt_cau, clause, f"gắn {han[0]}")
                        last_task["deadline"] = han[0]
                else:
                    ghi_vet("LOAI_MO_TA_RONG", stt_cau, clause, "loại")
                continue
            ghi_vet("LOAI_KHONG_CHU_VIEC", stt_cau, clause, "loại")

    return tasks
