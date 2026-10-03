# Script kiểm tra nhanh pipeline NLP trên 3 file mẫu
import re
import sys
from pathlib import Path

from chay_nlp import chay_nlp

sys.stdout.reconfigure(encoding="utf-8")

DAP_AN = {
    "thu_nghiem.json": {
        "tasks": [
            ("Tuấn", "thứ 4 tuần sau"),
            ("Ngọc", "ngày 20 tháng 10"),
            ("Mọi người", None),
        ],
        "next_meeting_time": "chủ nhật",
        "decision_count": 0,
    },
    "thu_nghiem1.json": {
        "tasks": [
            ("Khoa", "thứ 3 tuần sau"),
            ("Vi", "ngày 25 tháng 10"),
            ("Phúc", "chủ nhật"),
            ("Người chủ trì", "thứ 6"),
        ],
        "decision_count": 1,
        "next_meeting_time": "thứ 4",
    },
    "thu_nghiem2.json": {
        "tasks": [
            ("Hạnh", "thứ 4 tuần này"),
            ("Dũng", "ngày 10 tháng 10"),
            ("Thảo", "thứ 6"),
        ],
        "decision_count": 1,
        "next_meeting_time": "thứ 2",
    },
}

TUONG_DONG = {"người chủ trì": "người chủ trì", "mình": "người chủ trì", "tôi": "người chủ trì", "em": "người chủ trì"}
DONG_TU_HANH_DONG = (
    "làm", "update", "sửa", "fix", "viết", "gửi", "upload", "cập nhật",
    "phụ trách", "chạy", "test", "thiết kế", "hoàn thành", "nộp", "điều",
    "xong", "hỗ trợ", "nhớ", "thực hiện", "cố gắng", "gửi"
)
TU_MANG_Y_NGIA = ("làm", "update", "sửa", "fix", "viết", "gửi", "upload", "cập nhật", "chạy", "xong", "test", "giao")
TU_REJECT = {"làm", "để", "phụ trách", "xong", "test chung", "ai", "hôm", "nếu"}


def chuan_hoa(text):
    """Chuẩn hóa chuỗi để so sánh không phân biệt hoa/thường, bỏ khoảng trắng thừa."""
    if text is None:
        return ""
    text = re.sub(r"\s+", " ", str(text).strip())
    return text.lower().strip()


def co_tu_hanh_dong(text):
    """Mệnh đề có ít nhất một động từ hành động, không chỉ là mảnh câu."""
    text = chuan_hoa(text)
    if not text:
        return False
    if len(text.split()) <= 2:
        return False
    return any(tu in text for tu in TU_MANG_Y_NGIA)


def task_hop_le(task_item):
    """Task hợp lệ phải mang nghĩa hành động, không phải tiêu đề hoặc từ đệm."""
    if not task_item:
        return False
    owner = chuan_hoa(task_item.get("owner"))
    task = chuan_hoa(task_item.get("task") or "")
    deadline = chuan_hoa(task_item.get("deadline") or "")
    if not owner or not task:
        return False
    if owner in {"", "mình", "tôi", "em", "để", "ok"}:
        return False
    if task in TU_REJECT or task.split()[:2] == ["để"]:
        return False
    if len(task.split()) < 3:
        return False
    if not co_tu_hanh_dong(task):
        return False
    if deadline and re.fullmatch(r"(?:thứ\s+\d+|chủ nhật|ngày\s+\d+\s+tháng\s+\d+|tháng\s+\d+|cả\s+tuần)", deadline) is None and not re.search(r"(tuần|tháng|ngày|thứ|chủ nhật)", deadline):
        return False
    return True


def kiem_tra_file(ten_file):
    """Kiểm tra một file transcript theo đáp án mẫu."""
    duong_dan = Path("data/transcripts") / ten_file
    ket_qua, _, _ = chay_nlp(duong_dan)
    dap_an = DAP_AN[ten_file]

    tasks = ket_qua.get("tasks", [])
    tasks_hop_le = [task for task in tasks if task_hop_le(task)]
    ket_qua_task = {}
    for item in tasks_hop_le:
        owner = chuan_hoa(item.get("owner"))
        deadline = chuan_hoa(item.get("deadline"))
        ket_qua_task.setdefault(owner, []).append(deadline)

    ket_qua_metric = []
    for owner, han_mong_muon in dap_an["tasks"]:
        owner_key = chuan_hoa(owner)
        if owner_key not in ket_qua_task:
            ket_qua_metric.append(False)
            continue
        if han_mong_muon is None:
            ket_qua_metric.append(True)
            continue
        hop_le = any(chuan_hoa(han_mong_muon) in item for item in ket_qua_task[owner_key] if item)
        ket_qua_metric.append(hop_le)

    so_quyet_dinh = len(ket_qua.get("decisions", []))
    quyet_dinh_dat = so_quyet_dinh >= dap_an["decision_count"]

    next_time = chuan_hoa(ket_qua.get("next_meeting", {}).get("time")) if ket_qua.get("next_meeting") else ""
    lich_hop_dat = bool(next_time) and re.search(r"(?:thứ\s+\d+|chủ nhật|sáng|chiều|tối|giờ|tuần|ngày)", next_time)
    return {
        "task": len(tasks_hop_le) >= 1 and all(ket_qua_metric),
        "decision": quyet_dinh_dat,
        "next_meeting": lich_hop_dat,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        files = [sys.argv[1]]
    else:
        files = ["thu_nghiem.json", "thu_nghiem1.json", "thu_nghiem2.json"]

    for ten_file in files:
        ket_qua = kiem_tra_file(ten_file)
        print(f"{ten_file}:")
        print(f"  - Người phụ trách + hạn chót: {'ĐẠT' if ket_qua['task'] else 'KHÔNG ĐẠT'}")
        print(f"  - Quyết định: {'ĐẠT' if ket_qua['decision'] else 'KHÔNG ĐẠT'}")
        print(f"  - Lịch họp tiếp theo: {'ĐẠT' if ket_qua['next_meeting'] else 'KHÔNG ĐẠT'}")
