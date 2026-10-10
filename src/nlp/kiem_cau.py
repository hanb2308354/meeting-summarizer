# Kiểm thử mức câu cho pipeline NLP: mỗi ca dựng transcript trong bộ nhớ rồi
# chạy lõi đường xử lý mà kiem_thu.py dùng cho một file (tách phần ghi,
# không đụng outputs/), so việc thực tế với mong_doi.
import sys
from pathlib import Path

# Ca kiểm thử dựng câu THÔ trong bộ nhớ (chưa có file văn bản sạch), nên riêng file
# kiểm thử này gọi thẳng phần làm sạch của Hân để có văn bản sạch, giống hệt khi chạy
# src/tien_xu_ly/tien_xu_ly.py. Code chính của NLP chỉ đọc file data/processed/.
sys.path.append(str(Path(__file__).resolve().parents[1] / "tien_xu_ly"))
from doc_transcript import CAC_TRUONG_BAT_BUOC  # noqa: E402
from lam_sach import tien_xu_ly  # noqa: E402
from tom_tat import tom_tat
from trich_xuat import trich_xuat

# Khoảng cách (giây) giữa hai câu liên tiếp trong transcript dựng trong bộ nhớ
KHOANG_CACH_CAU = 4.0

# Mỗi ca: ten (tên hiển thị), cau (một hoặc vài câu liền nhau), mong_doi
# ("không có việc" hoặc danh sách (chủ, từ khóa nội dung, hạn; hạn so khớp
# bằng hoặc None)), dang_loi_da_biet (True nếu ca KHÔNG ĐẠT do chức năng
# chưa làm; thiếu trường này nghĩa là lỗi lạ).
DANH_SACH_CA = (
    {
        "ten": "Góp ý 'nên' không phải giao việc",
        "cau": ["Theo anh thì nên gửi báo giá sớm hơn."],
        "mong_doi": "không có việc",
    },
    {
        "ten": "Câu điều kiện 'nếu làm theo cách cũ'",
        "cau": ["Nếu làm theo cách cũ thì sẽ mất thêm thời gian."],
        "mong_doi": "không có việc",
        "dang_loi_da_biet": False,
    },
    {
        "ten": "Việc đã làm trong quá khứ",
        "cau": ["Tuần trước bạn Hùng đã gửi báo cáo rồi."],
        "mong_doi": "không có việc",
        "dang_loi_da_biet": True,
    },
    {
        "ten": "Đề mục 'Phần tiếp theo'",
        "cau": ["Phần tiếp theo sẽ là phần API."],
        "mong_doi": "không có việc",
        "dang_loi_da_biet": False,
    },
    {
        "ten": "Giao việc kèm hạn 'trước thứ 6'",
        "cau": ["Chị Lan sẽ gửi báo cáo trước thứ 6."],
        "mong_doi": [("Lan", "báo cáo", "thứ 6")],
        "dang_loi_da_biet": False,
    },
    {
        "ten": "Hai việc liệt kê, hạn nói một lần ở cuối",
        "cau": ["Bạn Hùng làm phần đăng nhập, bạn Lan làm phần thanh toán, hạn là thứ 6."],
        "mong_doi": [
            ("Hùng", "đăng nhập", "thứ 6"),
            ("Lan", "thanh toán", "thứ 6"),
        ],
        "dang_loi_da_biet": True,
    },
    {
        "ten": "Hạn 'ngày mai'",
        "cau": ["Bạn Nam sẽ nộp báo cáo vào ngày mai."],
        "mong_doi": [("Nam", "báo cáo", "ngày mai")],
        "dang_loi_da_biet": True,
    },
    {
        "ten": "Chủ trì giao qua từ 'lo'",
        "cau": ["Em lo phần báo cáo nhé, hạn là thứ 6."],
        "mong_doi": [("Người chủ trì", "báo cáo", "thứ 6")],
        "dang_loi_da_biet": True,
    },
    {
        "ten": "Việc chờ chủ nối câu gán chủ",
        "cau": [
            "Còn một việc nữa là viết slide giới thiệu.",
            "Việc này bạn Lan làm.",
        ],
        "mong_doi": [("Lan", "slide", None)],
        "dang_loi_da_biet": True,
    },
    {
        "ten": "Phụ trách không hạn",
        "cau": ["Bạn Hùng phụ trách phần đăng nhập."],
        "mong_doi": [("Hùng", "đăng nhập", None)],
        "dang_loi_da_biet": False,
    },
    {
        "ten": "Đề mục nối câu xã giao",
        "cau": [
            "Tiếp theo là phần giao diện.",
            "Hôm nay trời đẹp quá.",
        ],
        "mong_doi": "không có việc",
        "dang_loi_da_biet": False,
    },
    {
        "ten": "Tên hai chữ 'Thanh Hà'",
        "cau": ["Chị Thanh Hà sẽ gửi báo cáo trước thứ 6."],
        "mong_doi": [("Thanh Hà", "báo cáo", "thứ 6")],
        "dang_loi_da_biet": False,
    },
    {
        "ten": "Câu điều kiện 'nếu ... thì sẽ'",
        "cau": ["Nếu mọi người đồng ý thì sẽ chốt luôn."],
        "mong_doi": "không có việc",
        "dang_loi_da_biet": False,
    },
    {
        # Đỏ do trich_viec.cat_viec (ngoài C2, không được sửa): cụm
        # "\b(?:bạn|anh|chị|em)\s+<tên>" bỏ "anh Bảo " trước, rồi cụm
        # "giao cho <từ>" nuốt luôn động từ "nộp" → mô tả thiếu "nộp".
        # Chứng minh độc lập: thay "chú giải" bằng "biên soạn" cũng mất "nộp".
        "ten": "Chú giải giao cho anh Bảo",
        "cau": ["Phần chú giải giao cho anh Bảo nộp trước chủ nhật."],
        "mong_doi": [("Bảo", "nộp", "chủ nhật")],
        "dang_loi_da_biet": True,
    },
)


def tao_transcript(cac_cau):
    """Dựng transcript trong bộ nhớ đúng format mà doc_transcript trả về."""
    if not cac_cau:
        raise ValueError("Ca phải có ít nhất một câu.")
    danh_sach = []
    for chi_so, van_ban in enumerate(cac_cau):
        bat_dau = chi_so * KHOANG_CACH_CAU
        danh_sach.append(
            {
                "speaker": "SPEAKER_00",
                "start": bat_dau,
                "end": bat_dau + KHOANG_CACH_CAU - 1.0,
                "text": van_ban,
            }
        )
    for chi_so, cau in enumerate(danh_sach):
        thieu_truong = [truong for truong in CAC_TRUONG_BAT_BUOC if truong not in cau]
        if thieu_truong:
            raise ValueError(f"Câu số {chi_so} thiếu trường: {', '.join(thieu_truong)}.")
    return danh_sach


def chay_loi(danh_sach_cau):
    """Câu thô -> làm sạch -> lõi NLP (dùng cho ca dựng trong bộ nhớ)."""
    return chay_loi_sach(tien_xu_ly(danh_sach_cau))


def chay_loi_sach(du_lieu):
    """Chạy lõi pipeline trên văn bản sạch như chay_nlp nhưng không đụng outputs/."""
    trich = trich_xuat(du_lieu)
    tong_ket = tom_tat(du_lieu, [muc["text"] for muc in trich["decisions"]])
    return {
        "summary": tong_ket,
        "decisions": trich["decisions"],
        "tasks": trich["tasks"],
        "next_meeting": trich["next_meeting"],
    }


def chuan_hoa(gia_tri):
    """Chuẩn hóa chuỗi khi so chủ việc, không phân biệt hoa/thường và khoảng trắng."""
    if gia_tri is None:
        return ""
    return str(gia_tri).strip().lower()


def khop_chu(thuc_te, mong_doi):
    return chuan_hoa(thuc_te) == chuan_hoa(mong_doi)


def khop_tu_khoa(thuc_te, mong_doi):
    return chuan_hoa(mong_doi) in chuan_hoa(thuc_te)


def khop_han(thuc_te, mong_doi):
    if mong_doi is None:
        return thuc_te is None
    return thuc_te == mong_doi


def so_viec(tasks):
    """Danh sách (chủ, mô tả, hạn) để in việc thực tế khi ca KHÔNG ĐẠT."""
    return [
        (task.get("owner"), task.get("task"), task.get("deadline"))
        for task in tasks
    ]


def kiem_tra_ca(ca):
    """Chạy một ca; trả về (đạt, danh sách việc thiếu, danh sách việc thực tế)."""
    ket_qua = chay_loi(tao_transcript(ca["cau"]))
    tasks = ket_qua["tasks"]
    mong_doi = ca["mong_doi"]
    if mong_doi == "không có việc":
        return len(tasks) == 0, [], tasks
    da_dung = set()
    thieu = []
    for chu, tu_khoa, han in mong_doi:
        chi_so = next(
            (
                i
                for i, task in enumerate(tasks)
                if i not in da_dung
                and khop_chu(task.get("owner"), chu)
                and khop_tu_khoa(task.get("task"), tu_khoa)
                and khop_han(task.get("deadline"), han)
            ),
            None,
        )
        if chi_so is None:
            thieu.append((chu, tu_khoa, han))
        else:
            da_dung.add(chi_so)
    dat = len(tasks) == len(mong_doi) and not thieu
    return dat, thieu, tasks


def chay_kiem_cau():
    """Chạy tất cả ca, in kết quả từng ca và tổng kết; trả về mã thoát."""
    so_dat = 0
    loi_da_biet = 0
    loi_la = 0
    for chi_so, ca in enumerate(DANH_SACH_CA, start=1):
        dat, thieu, tasks = kiem_tra_ca(ca)
        if dat:
            so_dat += 1
            print(f"ĐẠT | ca {chi_so}: {ca['ten']}")
            continue
        if ca.get("dang_loi_da_biet", False):
            loi_da_biet += 1
        else:
            loi_la += 1
        print(f"KHÔNG ĐẠT | ca {chi_so}: {ca['ten']}")
        print(f"  Việc thực tế ({len(tasks)}): {so_viec(tasks)!r}")
        if thieu:
            print(f"  Việc thiếu ({len(thieu)}): {thieu!r}")
        if ca.get("dang_loi_da_biet", False):
            print("  Đang lỗi đã biết (dang_loi_da_biet=True)")
    tong = len(DANH_SACH_CA)
    print(
        f"Tổng kết: {so_dat}/{tong} ca ĐẠT, {tong - so_dat} ca KHÔNG ĐẠT "
        f"(lỗi đã biết: {loi_da_biet}, lỗi lạ: {loi_la})."
    )
    if loi_la:
        print("KẾT LUẬN: KHÔNG ĐẠT (có ca KHÔNG ĐẠT không thuộc dang_loi_da_biet)")
        return 1
    print("KẾT LUẬN: ĐẠT (mọi ca KHÔNG ĐẠT đều thuộc dang_loi_da_biet)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(chay_kiem_cau())

