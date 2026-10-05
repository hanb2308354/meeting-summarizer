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

# Động từ bổ sung chỉ dùng để nhận ra mệnh đề giao việc và cắt mô tả việc.
# Không gộp vào DANH_SACH_DONG_TU: danh sách đó còn dùng để lọc tên người
# (nhan_dien_ten.py).
# Chưa bật (cần đi kèm sửa khác để không tăng việc giả): nhận, lập, xếp, lo, rà, gom.
DONG_TU_BO_SUNG = (
    "tổng hợp",
    "đối chiếu",
    "rà soát",
    "chuẩn bị",
    "liên hệ",
    "chỉnh",
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
    # Liên từ, trạng từ nối câu và từ nối: không bao giờ là tên người (C2)
    "thì",
    "mà",
    "nên",
    "rồi",
    "theo",
    "khi",
    "vì",
    "để",
    "và",
    "cũng",
    # "thầy" là danh xưng giảng viên: không nhận là người trong cuộc họp (C2)
    "thầy",
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

# Câu giới thiệu việc chưa có chủ: "(còn) một việc nữa/tiếp theo là <mô tả>".
# Không neo đầu câu (có thể có từ đệm như "À"); neo cuối để mô tả lấy hết
# phần sau "là", dấu câu cuối không thuộc mô tả.
MAU_VIEC_CHO_CHU = (
    r"(?:còn\s+)?"
    r"(?:một\s+việc\s+nữa\s+là|việc\s+nữa\s+là|một\s+việc\s+là|tiếp\s+theo\s+là)"
    r"\s+(?P<mo_ta>\S.*?)(?:\s*[,.;:!?]\s*)?$"
)

# Câu gán chủ cho việc chờ: bắt đầu bằng "việc này/việc đó" kèm cụm gán chủ
# "để (mình|tôi|em) (sẽ) làm/phụ trách" hoặc "<bạn...> Tên (sẽ) làm/phụ trách"
MAU_CAU_GAN_CHU_CHO_VIEC = (
    r"^việc\s+(?:này|đó)\s+"
    r"(?:"
    r"để\s+(?:mình|tôi|em)\s+(?:sẽ\s+)?(?:làm|phụ\s+trách)"
    r"|(?:bạn\s+)?[A-ZÀ-Ỹa-zà-ỹ]+(?:\s+[A-ZÀ-Ỹa-zà-ỹ]+)?\s+(?:sẽ\s+)?(?:làm|phụ\s+trách)"
    r")"
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
