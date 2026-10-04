# Đáp án mong đợi cho bộ kiểm thử NLP (chỉ dữ liệu, không logic).
# Quy ước: mỗi việc là (chủ việc, hạn chót). Đáp án Vi đã chốt với sinh
# viên: Vi gộp chung 1 việc duy nhất (làm API + viết document), hạn
# "ngày 25 tháng 10" áp cho cả cụm đó, tuyệt đối không tách làm 2 việc.
DAP_AN = {
    "thu_nghiem.json": {
        "tasks": [
            ("Tuấn", "thứ 4 tuần sau"),
            ("Ngọc", "ngày 20 tháng 10"),
            ("Mọi người", None),
        ],
        "required_task_deadlines": [
            ("Tuấn", "trang chủ", "thứ 4 tuần sau"),
            ("Ngọc", "lỗi đăng ký", "ngày 20 tháng 10"),
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
        "required_task_deadlines": [
            ("Khoa", "database", "thứ 3 tuần sau"),
            ("Vi", "xóa sách", "ngày 25 tháng 10"),
            ("Vi", "document", "ngày 25 tháng 10"),
            ("Phúc", "trang tìm kiếm", "chủ nhật"),
            ("Người chủ trì", "bản draft", "thứ 6"),
        ],
        "next_meeting_time": "thứ 4",
        "next_meeting_place": "online trên Google Meet",
        "decision_count": 1,
    },
    "thu_nghiem2.json": {
        "tasks": [
            ("Hạnh", None),
            ("Hạnh", "thứ 4 tuần này"),
            ("Dũng", "ngày 10 tháng 10"),
            ("Thảo", "thứ 6"),
        ],
        "required_task_deadlines": [
            ("Hạnh", "kế hoạch", "thứ 4 tuần này"),
            ("Dũng", "báo giá", "ngày 10 tháng 10"),
        ],
        "required_task_descriptions": [
            ("Hạnh", "campaign"),
            ("Hạnh", "kế hoạch"),
        ],
        "forbidden_task_phrases": [
            "giảm giá 20%",
        ],
        "next_meeting_time": "thứ 2",
        "next_meeting_place": "phòng họp tầng 3",
        "decision_count": 2,
    },
    "phat_trien.json": {
        "tasks": [
            ("Lam", "thứ 5 tuần sau"),
            ("Người chủ trì", "ngày 18 tháng 11"),
            ("Người chủ trì", "thứ 6"),
            ("Bảo", "chủ nhật"),
            ("Mai", "thứ 4 tuần sau"),
        ],
        "required_task_deadlines": [
            ("Lam", "ánh xạ", "thứ 5 tuần sau"),
            ("Người chủ trì", "checklist", "ngày 18 tháng 11"),
            ("Người chủ trì", "bản tổng hợp", "thứ 6"),
            ("Bảo", "trích dẫn", "chủ nhật"),
            ("Mai", "phụ lục", "thứ 4 tuần sau"),
        ],
        "required_task_descriptions": [
            ("Lam", "ánh xạ"),
            ("Người chủ trì", "checklist"),
            ("Người chủ trì", "bản tổng hợp"),
            ("Bảo", "trích dẫn"),
            ("Mai", "phụ lục"),
        ],
        "next_meeting_time": None,
        "next_meeting_place": "",
        "decision_count": 0,
    },
}
