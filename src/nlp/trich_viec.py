# Dựng danh sách việc cần làm từ transcript đã làm sạch
import re

from nhan_dien_han import tim_han_chot
from nhan_dien_ten import lay_ten_nguoi_phan_anh
from trich_lich_hop import la_lich_hop
from tu_dien import DANH_SACH_DONG_TU


def la_de_muc(phan):
    """Nhận diện các câu đề mục không mang việc như 'Đầu tiên là phần API'"""
    phan = phan.strip()
    if not phan:
        return True
    if re.match(r"^(đầu tiên|tiếp theo|cuối cùng|tiếp theo đó)\s+là\b", phan, flags=re.IGNORECASE):
        return True
    if re.match(r"^thứ\s+\d+\s+là\b", phan, flags=re.IGNORECASE):
        return True
    if re.match(r"^(?:phần|mục)\s+.*$", phan, flags=re.IGNORECASE):
        return True
    return False


def tach_menh_de(cau):
    """Tách câu thành mệnh đề theo dấu phẩy nhưng không tách giữa hai chữ số."""
    ket_qua = []
    tam = []
    i = 0
    while i < len(cau):
        ky_tu = cau[i]
        if ky_tu == ",":
            if i + 1 < len(cau) and cau[i - 1].isdigit() and cau[i + 1].isdigit():
                tam.append(ky_tu)
            else:
                phan = "".join(tam).strip()
                if phan:
                    ket_qua.append(phan)
                tam = []
        else:
            tam.append(ky_tu)
        i += 1
    phan = "".join(tam).strip()
    if phan:
        ket_qua.append(phan)

    ket_qua = [p.strip() for p in ket_qua if p.strip()]
    ket_qua_ban_sau = []
    for p in ket_qua:
        if len(p.split()) <= 2 and ket_qua_ban_sau:
            ket_qua_ban_sau[-1] = f"{ket_qua_ban_sau[-1]}, {p}"
        else:
            ket_qua_ban_sau.append(p)
    return ket_qua_ban_sau


def co_dong_tu_hanh_dong(van_ban):
    """Mệnh đề có động từ hành động thì coi là việc cần làm."""
    van_ban = van_ban.lower().strip()
    van_ban = re.sub(
        r"^(?:vì vậy|do đó|ngoài ra|tuy nhiên|nhưng|nên|còn)\b\s*,?\s*",
        "",
        van_ban,
        flags=re.IGNORECASE,
    )
    if not van_ban:
        return False
    if re.fullmatch(r"(?:để|phụ trách|làm|xong)\s*[,.;]?\s*", van_ban):
        return False
    if re.fullmatch(r"(?:mình|tôi|em|việc này|còn|thứ|phần|bên)\b.*", van_ban):
        return False
    return bool(re.search(r"\b(?:làm|update|sửa|fix|viết|gửi|upload|cập nhật|phụ trách|chạy|test|thiết kế|hoàn thành|nộp|xong|hỗ trợ|thực hiện|điều|cố gắng)\b", van_ban))


def cat_viec(van_ban, owner):
    """Lấy phần mô tả việc từ động từ hành động trở đi."""
    text = van_ban.strip()
    if not text:
        return text

    text = re.sub(r"^\s*(?:còn\s+)?(?:một\s+việc\s+nữa\s+là|việc\s+nữa\s+là|một\s+việc\s+là)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:tiếp\s+theo\s+là|đầu\s+tiên\s+là|cuối\s+cùng\s+là|thứ\s+\d+\s+là)\s*", "", text, flags=re.IGNORECASE)

    for mau in [
        r"\b(?:bạn|anh|chị|em)\s+[A-ZÀ-Ỹa-zà-ỹ]+\s+",
        r"\b[A-ZÀ-Ỹa-zà-ỹ]+\s+(?:sẽ|phải|nên|cần|nhớ)\s+",
        r"\b(?:để|việc này\s+để|nên)\s+",
        r"\b(?:mình|tôi|em)\s+(?:sẽ\s+)?",
        r"\b(?:giao\s+cho|phụ\s+trách)\s+(?:bạn\s+)?[A-ZÀ-Ỹa-zà-ỹ]+\s*",
        r"^(?:bên|trong|ở|tại)\s+[^,;.!?]+?\s+(?:sẽ|phải|nên|cần|nhớ)\s+",
    ]:
        text = re.sub(mau, "", text, flags=re.IGNORECASE)

    if owner == "Người chủ trì":
        text = re.sub(r"^\s*(?:việc này\s+)?(?:để\s+)?(?:mình|tôi|em)\s*(?:sẽ\s+)?", "", text, flags=re.IGNORECASE)

    text = re.sub(r"^(?:phụ\s+trách|để|làm|nên|cố\s+gắng)\s*[,;:.-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:bên|trong|ở|tại|trên)\s+[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+){0,3}\s*[,;:.-]*\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:trên|tại|ở)\s+", "", text, flags=re.IGNORECASE)

    for dong_tu in DANH_SACH_DONG_TU:
        match = re.search(rf"\b{re.escape(dong_tu)}\b", text, flags=re.IGNORECASE)
        if match:
            text = text[match.start():].strip()
            break

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

    for cau in cac_cau:
        text = cau["sach"].strip()
        if not text or cau["xa_giao"]:
            continue
        if la_lich_hop(text):
            continue
        if la_de_muc(text):
            continue
        if re.search(r"\b[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*\s+làm\b.*?,\s*[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ]*\s+làm\b", text, flags=re.IGNORECASE):
            continue
        if re.match(r"^(?:ok|cảm ơn|vậy thôi|chào)\b", text, flags=re.IGNORECASE):
            continue
        if re.fullmatch(r"(?:để|phụ trách|làm)\b.*", text, flags=re.IGNORECASE):
            continue

        clauses = [part.strip() for part in re.split(r"\s*,\s*", text) if part.strip()]
        sentence_owner = None

        for clause in clauses:
            if not clause:
                continue
            if re.match(r"^(?:nếu không|vậy thôi|cảm ơn|ok|chào)\b", clause, flags=re.IGNORECASE):
                continue
            if re.search(r"\bđã\s+.*\bxong\b", clause, flags=re.IGNORECASE):
                continue
            if re.fullmatch(r"(?:để|phụ trách|làm|xong|test chung|có ai.*|ai.*\?)", clause, flags=re.IGNORECASE):
                continue

            if re.match(r"^(?:deadline|hạn chót|hạn)\b", clause, flags=re.IGNORECASE):
                han = tim_han_chot(clause)
                if han and last_task and last_task["deadline"] is None:
                    last_task["deadline"] = han[0]
                continue

            owner = lay_ten_nguoi_phan_anh(clause, ten_biet)
            if owner is not None:
                sentence_owner = owner
                if not co_dong_tu_hanh_dong(clause):
                    continue
                task_text = cat_viec(clause, owner)
                if not task_text or task_text.lower() in {"họp", "đầu tiên là", "tiếp theo là", "điều này", "theo điều này"}:
                    continue
                task_item = {"task": task_text, "owner": owner, "deadline": None, "start": cau["start"]}
                tasks.append(task_item)
                last_task = task_item
                han = tim_han_chot(clause)
                if han and task_item["deadline"] is None:
                    task_item["deadline"] = han[0]
                continue

            if sentence_owner and co_dong_tu_hanh_dong(clause):
                task_text = cat_viec(clause, sentence_owner)
                if task_text and task_text.lower() not in {"họp", "đầu tiên là", "tiếp theo là", "điều này", "theo điều này"}:
                    if last_task and last_task["owner"] == sentence_owner and last_task["start"] == cau["start"] and re.search(r"\b(?:và|cùng|cũng|đồng thời)\b", clause, flags=re.IGNORECASE):
                        last_task["task"] = f"{last_task['task']}, {task_text}"
                    else:
                        task_item = {"task": task_text, "owner": sentence_owner, "deadline": None, "start": cau["start"]}
                        tasks.append(task_item)
                        last_task = task_item
                    han = tim_han_chot(clause)
                    if han and last_task["deadline"] is None:
                        last_task["deadline"] = han[0]
                continue

    return tasks
