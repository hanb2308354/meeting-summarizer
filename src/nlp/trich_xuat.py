# Trích xuất quyết định, việc cần làm, lịch họp tiếp theo từ transcript đã làm sạch
import re
import sys
from pathlib import Path

from doc_transcript import doc_transcript
from nhan_dien_ten import lay_ten_nguoi_phan_anh, tim_ten_biet
from tien_xu_ly import tien_xu_ly
from tu_dien import (
    DANH_SACH_DONG_TU,
    DANH_SACH_HAN_CHOT,
    DANH_SACH_TU_CHUC_NANG,
    THU_MUC_CAU,
)

sys.stdout.reconfigure(encoding="utf-8")


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


def tim_han_chot(van_ban):
    """Trích xuất hạn chót từ mệnh đề hoặc câu, có thể trả về nhiều giá trị trong cùng câu."""
    van_ban = van_ban.strip()
    if not van_ban:
        return []
    van_ban = re.sub(r"(?:,\s*)?(?:còn\s+)?(?:ai\s+có\s+ý\s+kiến\s+gì\s+không\?|có\s+ai\s+.*\bý\s+kiến\b.*\?|cảm\s+ơn.*)$", "", van_ban, flags=re.IGNORECASE)
    if re.match(r"^thứ\s+\d+\s+là\b", van_ban, flags=re.IGNORECASE):
        return []

    ket_qua = []
    for mau in [
        r"(?:deadline|hạn chót|chậm nhất|hạn)\s*(?:là|:)\s*([^,.]+?)(?:,|\.|$)",
        r"\b(?:trước|sớm hơn)\s+([^,.]+?)(?:,|\.|$)",
        r"\b(?:ngày\s+\d+\s+tháng\s+\d+|thứ\s+\d+\s+(?:tuần\s+(?:này|sau)|\w+)|thứ\s+\d+\s+tuần\s+(?:này|sau)|chủ nhật|cuối\s+tuần)\b([^,.]*?)(?:,|\.|$)",
    ]:
        for match in re.finditer(mau, van_ban, flags=re.IGNORECASE):
            if match.lastindex:
                gia_tri = match.group(1).strip()
            else:
                gia_tri = match.group(0).strip()
            gia_tri = re.sub(r"^(?:là|đó\s+là|đây\s+là)\s*", "", gia_tri, flags=re.IGNORECASE)
            gia_tri = gia_tri.replace(".", "").strip()
            if not gia_tri or gia_tri.lower() in {"là", "đây", "đó"}:
                continue
            if re.search(r"\b(?:điều này|ý kiến|có ai|đến|gặp|lúc)\b", gia_tri, flags=re.IGNORECASE):
                continue
            ket_qua.append(gia_tri)

    ket_qua = list(dict.fromkeys(ket_qua))
    return ket_qua


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


def trich_xuat(cac_cau):
    """Trả về dict chứa quyết định, việc cần làm và lịch họp tiếp theo."""
    ten_biet = tim_ten_biet(cac_cau)
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

    ket_qua = {
        "decisions": [],
        "tasks": [
            {
                "task": task["task"],
                "owner": task["owner"],
                "deadline": task["deadline"],
                "start": task["start"],
            }
            for task in tasks
        ],
        "next_meeting": lay_lich_hop(cac_cau),
    }

    for cau in cac_cau:
        text = cau["sach"]
        if la_lich_hop(text) or la_de_muc(text) or cau["xa_giao"]:
            continue
        if not la_quyet_dinh(text):
            continue
        if lay_ten_nguoi_phan_anh(text, ten_biet) is not None and co_dong_tu_hanh_dong(text):
            continue
        phan = text
        if len(ket_qua["decisions"]) and re.match(r"^(kèm|và|cùng|cuối cùng là|từ tháng này|mỗi)\b", text, flags=re.IGNORECASE):
            phan = f"{ket_qua['decisions'][-1]['text']}, {text}"
            ket_qua["decisions"][-1]["text"] = phan.strip()
            continue
        ket_qua["decisions"].append({"text": phan.strip(), "start": cau["start"]})

    return ket_qua


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/trich_xuat.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    du_lieu = tien_xu_ly(doc_transcript(duong_dan))
    ket_qua = trich_xuat(du_lieu)
    print("Quyết định:")
    for item in ket_qua["decisions"]:
        print(f" - {item['text']} (start={item['start']})")
    print("\nViệc cần làm:")
    for item in ket_qua["tasks"]:
        print(f" - {item['owner']}: {item['task']} | {item['deadline'] or 'không rõ'} | {item['start']}")
    print("\nHọp tiếp theo:")
    print(ket_qua["next_meeting"])
