# Bảng cấu hình dùng chung cho phần NLP (chỉ hằng số mức module, không import gì)

# --- Hằng số của phần trích xuất (nguồn: trich_xuat.py) ---
DANH_SACH_DONG_TU = (
    "làm",
    "update",
    "sửa",
    "fix",
    "viết",
    "gửi",
    "upload",
    "cập nhật",
    "phụ trách",
    "chạy",
    "test",
    "thiết kế",
    "hoàn thành",
    "nộp",
    "điều",
    "xong",
    "hỗ trợ",
    "nhớ",
    "thực hiện",
)

DANH_SACH_TU_CHUC_NANG = {
    "nào",
    "nữa",
    "bên",
    "trước",
    "sau",
    "là",
    "sẽ",
    "phải",
    "làm",
    "gửi",
    "có",
    "cần",
    "ơi",
    "ấy",
    "kia",
    "đó",
    "tuần",
    "tháng",
    "mình",
    "mọi",
    "ai",
    "này",
    "nơi",
    "tiếp",
    "còn",
    "về",
    "đầu",
    "nếu",
    "vậy",
    "hôm",
    "ok",
}

# Tín hiệu cho thấy câu đang giao việc (không phải đề mục dù mở đầu bằng
# "Phần/Mục"). Dùng trong la_de_muc (trich_viec.py).
TIN_HIEU_GIAO_VIEC = (
    "giao cho",
    "phụ trách",
    "sẽ",
    "phải",
    "cần",
)

# --- Hằng số của phần tiền xử lý (nguồn: tien_xu_ly.py) ---
# Lỗi Whisper hay nhận sai (mẫu -> sửa lại). Thêm dần khi gặp lỗi mới
SUA_LOI = [
    (r"\bSpring\b", "Sprint"),
    (r"\bshopping\b", "Shopee"),
    (r"\breact\b", "React"),
    (r"\b(dùng|không dùng)\s+view\b", r"\1 Vue"),
    (r"\bview\b", "Vue"),
    (r"\bFacebook\b", "Facebook"),
    (r"\bTikTok\b", "TikTok"),
    (r"\bGoogle Drive\b", "Google Drive"),
    (r"\bGoogle Meet\b", "Google Meet"),
    (r"\bMessenger\b", "Messenger"),
    (r"\bAPI\b", "API"),
    (r"\bSprint\b", "Sprint"),
]

TU_DEM = r"\b(?:ờ|ừm|à|ạ|nha|nhé|á|ok)\b"

MAU_XA_GIAO = [
    r"cảm ơn",
    r"có ai.*(câu hỏi|ý kiến)",
    r"bắt đầu.*(họp|meeting)",
    r"vào đủ rồi",
]

SO_TU_TOI_DA_XA_GIAO = 15

# --- Hằng số của phần tóm tắt (nguồn: tom_tat.py) ---
SO_CAU_TOI_THIEU = 2
SO_CAU_TOI_DA = 5

DIEM_BO_SUNG = {
    "chốt": 0.35,
    "thống nhất": 0.35,
    "quyết định": 0.4,
    "đồng ý": 0.3,
    "%": 0.15,
    "tỷ": 0.15,
    "hôm nay": 0.1,
    "mục tiêu": 0.15,
    "tối thiểu": 0.15,
}
