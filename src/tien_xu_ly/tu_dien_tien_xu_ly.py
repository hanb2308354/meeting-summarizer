# Bảng cấu hình của phần TIỀN XỬ LÝ VĂN BẢN (Hân phụ trách)
# Chuyển nguyên văn từ src/nlp/tu_dien.py sang. Chỉ chứa hằng số, không import gì.

# Lỗi Whisper hay nhận sai (mẫu -> sửa lại). Thêm dần khi gặp lỗi mới.
#
# NGUYÊN TẮC (vì sửa sai còn tệ hơn không sửa):
# - Chỉ sửa chữ NGHE NHẦM, không dịch tiếng Anh sang tiếng Việt (phần NLP đang
#   nhận cả từ tiếng Anh như fix, update, deadline).
# - Cụm nghe nhầm mà cũng là tiếng Việt có thật (tên người, cụm thường gặp) thì
#   PHẢI kèm ngữ cảnh. Ví dụ "Bích Linh" là tên người, "cho phép bắt đầu" là câu đúng.
# - Mỗi luật mới phải thêm ca vào kiem_thu_tien_xu_ly.py, gồm cả ca "câu đúng không được đổi".
# - (?-i:...) = phần đó phân biệt hoa/thường (mặc định các luật không phân biệt).
DANH_XUNG = r"(?<!chị )(?<!em )(?<!bạn )(?<!cô )(?<!anh )(?<!bà )(?<!ông )(?<!thầy )"

SUA_LOI = [
    # --- Thuật ngữ tiếng Anh bị nghe thành tiếng Việt (gặp khi chạy thử ASR) ---
    # "bích link" không phải tiếng Việt; "Bích Linh" là tên người nên chỉ sửa khi
    # CẢ câu chỉ nói về hạn: đứng đầu câu, ngay sau là "là <mốc ngày>" rồi hết câu
    # ("Bích Linh là thứ 6 tuần này."). Giữ tên khi đứng giữa câu ("Lan với Bích Linh
    # là thứ 6 nộp", "Còn Bích Linh là thứ sáu nộp") hoặc sau mốc ngày còn động từ.
    (DANH_XUNG + r"\bbích\s+link\b", "deadline"),
    (r"(?:^|(?<=[.?!]\s))bích\s+linh\b(?=\s+là\s+"
     r"(?:thứ\s+(?:\d|hai|ba|tư|năm|sáu|bảy)|chủ\s+nhật|ngày\s+\d+(?:\s+tháng\s+\d+)?|cuối\s+tuần)"
     r"(?:\s+(?:tuần|tháng)\s+(?:này|sau|tới))?(?:\s+(?:nhé|nha|nhá))?\s*(?:[.,!?]|$))", "deadline"),
    (r"\bphôn\s+th[eê]n\b|\bfront\s*-\s*end\b", "frontend"),
    (r"\b(phần|bên|team|code)\s+bắt\s+kênh\b", r"\1 backend"),
    (r"\bbackgnd\b|\bback\s*-\s*end\b", "backend"),
    (r"\bdead\s*-\s*line\b", "deadline"),
    (r"\bup\s*-\s*load\b|\bupo\s+lát\b", "upload"),
    (r"\bp\s+ra\s+chất\b", "project"),
    (r"\bmeet\s+thinh\b", "meeting"),
    # "cho phép bắt đầu", "phép bắt buộc" là câu đúng; chỉ sửa "có phép bắt là ..."
    (r"(?<!cho )(?<!được )(?<!xin )\bphép\s+bắt\b(?=\s+(?:là|về))", "feedback"),
    # "Tết thử nghiệm" là câu đúng; Whisper ra "tết" viết thường
    (r"\b(?-i:tết)\s+thử\b(?!\s+nghiệm)", "test thử"),
    (r"\brút\s+(?:dalo|da\s+lô|giá\s+lô)\b", "group Zalo"),
    (r"\b(qua|dùng|sang|bằng)\s+misco\b", r"\1 MySQL"),
    (r"\bdọng\s+nói\b", "giọng nói"),

    # --- Anh đã thêm trước đó (giữ lại, kèm ngữ cảnh cho từ có thật) ---
    # Spring Boot/JPA/Security..., "Spring Festival", "mùa Spring" là từ có thật:
    # chỉ sửa khi sau đó là số hoặc từ hay đi với Sprint ("spring 4", "spring mới",
    # "Spring tiếp theo", "spring planning")
    (r"\bSpring\b(?=\s*\d|\s+(?:tiếp|mới|này|sau|trước|tới|kế|đầu|cuối|hiện|planning|review|backlog|goal)\b)",
     "Sprint"),
    # Không có "kênh": "kênh shopping online" (kênh mua sắm) là cụm có thật
    (r"\b(trên|qua|sàn)\s+shopping\b", r"\1 Shopee"),
    (r"\breact\b", "React"),
    # "view" là từ có thật (view của database, "view biển", "view sản phẩm"):
    # chỉ sửa thành Vue khi câu đang nói về frontend (có React, Angular, giao diện...)
    # VÀ sau "view" là hết vế hoặc từ nối ("dùng view rồi", "view thay vì React").
    # "view đẹp", "view biển", "view trong database": sau view là danh/tính từ -> giữ.
    (r"^(?=.*\b(?:react|angular|frontend|giao\s+diện|component|javascript|framework)\b)"
     r"(.*?\b(?:dùng|không\s+dùng|qua|với|hay|thay\s+vì|bằng)\s+)view\b"
     r"(?=\s*(?:[,.!?;:]|$)|\s+(?:nữa|rồi|thay\s+vì|chứ|hay|hoặc|với|và|vì|nhé|nha|thì|luôn)\b)",
     r"\1Vue"),
    (r"\bFacebook\b", "Facebook"),
    (r"\bTikTok\b", "TikTok"),
    (r"\blazada\b", "Lazada"),
    (r"\bGoogle Drive\b", "Google Drive"),
    (r"\bGoogle Meet\b", "Google Meet"),
    (r"\bMessenger\b", "Messenger"),
    (r"\bAPI\b", "API"),
    (r"\bSprint\b", "Sprint"),
]

# Từ đệm, bỏ đi khi:
# - ờ, ờm, ừ, ừm, ơ, ạ, nhé: luôn là đệm khi đứng riêng.
# - "nha" viết thường, trừ "nha khoa", "nha sĩ"... ("Nha Trang" viết hoa nên không bị đụng).
# - "à": ở đầu câu, sau dấu câu, hoặc cuối câu; nhưng giữ "à không", "à quên", "à mà"
#   (người nói đang tự sửa lời, bỏ đi sẽ đổi nghĩa).
# - "ok": chỉ bỏ ở đầu câu, khi là một vế riêng ("..., ok."), hoặc ngay sau mốc giờ
#   ("lúc 9h ok."). Các trường hợp khác "ok" thường mang nghĩa đồng ý
#   ("Slide ok.", "Bạn Tuấn ok.") nên giữ lại.
#   Đầu câu vẫn giữ "Ok là ..." ("Ok là chốt phương án A") và "OK button".
#   (Không đòi dấu phẩy sau "ok" đầu câu: Whisper hay bỏ dấu phẩy, vd
#    "ok phần database để mình làm" thì "ok" vẫn là từ đệm.)
# - "à"/"ok" ngay trước dấu "?" là từ để HỎI, giữ lại: "Thế à?", "Hạn thứ 6, ok?"
#   (bỏ đi thì "Hạn là thứ 6, ok?" thành "Hạn là thứ 6?", nghĩa khác).
# - Không có "á": dễ trùng "châu Á", tên người "Á".
TU_DEM = (
    r"\b(?:ờ|ờm|ừ|ừm|ơ|ạ|nhé)\b"
    r"|\b(?-i:nha)\b(?!\s+(?:khoa|sĩ|thuốc|bè))"
    r"|(?:^\s*|(?<=[.?!,;:…—–])\s*)à\b(?!\s+(?:không|quên|mà|đúng))(?!\s*\?)"
    r"|\bà(?=\s*(?:[.!]|$))"
    r"|^\s*ok\b(?!\s+(?:là|button)\b)(?!\s*\?)"
    r"|(?<=[.?!,;:…—–])\s*ok(?=\s*(?:[,.!]|$))"
    # "... lúc 9h ok." / "... 9 giờ ok.": "ok" chốt câu sau mốc giờ, không phải nội dung
    r"|(?:(?<=\dh )|(?<=giờ )|(?<=phút ))ok(?=\s*[.!]?\s*$)"
)

MAU_XA_GIAO = [
    r"cảm ơn",
    # Chào: chỉ khi "chào" đứng đầu vế và theo sau là người nghe, để "Chào hàng là
    # việc của Lan" (chào hàng = mời mua) không bị coi là xã giao
    r"^(?:xin\s+)?chào(?:\s+(?:mọi\s+người|cả\s+nhà|các\s+bạn|cả\s+nhóm|team|anh|chị|em|thầy|cô)\b|$)",
    r"^hello\b",   # không có "hi": trùng "hi vọng" (cách viết khác của "hy vọng")
    r"^(?:thanks?|thank\s+you)\b",
    r"có ai.*(câu hỏi|ý kiến)",
    # "bắt đầu (cuộc) họp", không khớp "bắt đầu phụ trách đặt phòng họp"
    r"bắt đầu\s+(?:\S+\s+){0,3}?(?<!phòng )(?:họp|meeting)\b",
    r"vào đủ rồi",
]

SO_TU_TOI_DA_XA_GIAO = 15

# Vế ngắn được phép đi kèm câu xã giao mà không làm mất tính "xã giao"
# ("Rồi, cảm ơn mọi người", "Vậy thôi, cảm ơn"). Dùng danh sách cố định thay vì
# "vế ngắn bất kỳ", vì "Cảm ơn Lan, Tuấn làm slide" có vế "Tuấn làm slide" là giao việc.
VE_KET_XA_GIAO = (
    # (không cần "vậy nhé", "thế nhé": chữ "nhé" đã bị bỏ ở bước từ đệm trước đó)
    r"^(?:ok|rồi|vậy|vậy thôi|thế thôi|hết rồi|xong rồi|"
    r"chào mọi người|chào cả nhà|chào các bạn|mọi người|các bạn|cả nhà|"
    # "Hello mọi người, mình bắt đầu nhé" (chữ "nhé" đã bị bỏ trước đó)
    r"(?:mình\s+|chúng\s+ta\s+)?bắt đầu(?:\s+thôi)?)$"
)

# Câu có mốc thời gian thì không phải xã giao ("Mình bắt đầu họp lúc 9h thứ hai tuần sau")
MAU_THOI_GIAN = (
    r"\blúc\b|\d+\s*(?:h|giờ)\b|\bthứ\s+(?:\d|hai|ba|tư|năm|sáu|bảy)\b|\bchủ\s+nhật\b|"
    r"\bngày\s+(?:\d|mai|kia)|\btuần\s+(?:sau|tới)\b|\btháng\s+(?:sau|tới|\d)"
)

# Cụm từ PyVi không tự nối (đã chạy thử), nối lại sau khi tách từ
TU_GHEP = [
    "hạn chót",
    "cuộc họp",
    "phòng họp",
    "ban giám đốc",
    "group Zalo",
    "Google Drive",
    "Google Meet",
]
