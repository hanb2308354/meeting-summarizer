# Kiểm thử tự động cho phần tiền xử lý văn bản (lam_sach.py, tien_xu_ly.py và cầu nối
# src/nlp/tien_xu_ly.py).
# Mỗi ca là một câu thô (như ASR xuất ra) và kết quả mong đợi, gồm cả các lỗi
# đã từng gặp, để sửa từ điển sau này không làm hỏng lại.
#
# Cách dùng:  python src/tien_xu_ly/kiem_thu_tien_xu_ly.py
# Mã thoát 0 khi tất cả đều ĐẠT.
import json
import pickle
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

THU_MUC_NAY = Path(__file__).resolve().parent
THU_MUC_GOC = THU_MUC_NAY.parents[1]
sys.path.insert(0, str(THU_MUC_NAY))
import lam_sach as txl  # noqa: E402
import tien_xu_ly as cli  # noqa: E402
from doc_transcript import doc_transcript  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# (câu thô, câu sạch mong đợi, có phải câu xã giao không)
CA_LAM_SACH = [
    ("Mình bắt đầu thảo luận phần họp báo.", "Mình bắt đầu thảo luận phần họp báo.", False),
    ("(ờ) Tuấn sửa hàm login() nhé.", "Tuấn sửa hàm login().", False),
    ("Bích Linh là thứ 6 tuần này, nhớ gửi file cho cả nhóm.",
     "deadline là thứ 6 tuần này, nhớ gửi file cho cả nhóm.", False),
    # --- Sửa lỗi nghe nhầm ---
    ("Bích link là thứ 6 tuần này.", "deadline là thứ 6 tuần này.", False),
    ("Phần phôn thên thì giao cho bạn Tuấn.", "Phần frontend thì giao cho bạn Tuấn.", False),
    ("Phần bắt kênh thì bạn Ngọc sẽ fix lỗi.", "Phần backend thì bạn Ngọc sẽ fix lỗi.", False),
    ("Phần front-end và back-end.", "Phần frontend và backend.", False),
    ("Nhắn lên rút dalo nhé.", "Nhắn lên group Zalo.", False),
    ("Bạn Lan sẽ tết thử trên 5 file.", "Bạn Lan sẽ test thử trên 5 file.", False),
    # --- Không sửa nhầm từ có thật ---
    ("Dùng Spring Boot cho backend.", "Dùng Spring Boot cho backend.", False),
    ("Sprint 4, spring mới.", "Sprint 4, Sprint mới.", False),
    ("Tạo view trong database.", "Tạo view trong database.", False),
    ("Giao diện thì team mình dùng view rồi.", "Giao diện thì team mình dùng Vue rồi.", False),
    ("Frontend dùng view thay vì React.", "Frontend dùng Vue thay vì React.", False),
    ("Bích Linh là thứ 6 tuần này.", "deadline là thứ 6 tuần này.", False),
    ("Thầy có phép bắt là phần giao diện còn rối.", "Thầy có feedback là phần giao diện còn rối.", False),
    ("Chuyển qua Misco cho dễ quản lý.", "Chuyển qua MySQL cho dễ quản lý.", False),
    ("Ngày 5, à không, ngày 6.", "Ngày 5, à không, ngày 6.", False),
    ("Họp tiếp theo là tối chủ nhật lúc 9h, ok.", "Họp tiếp theo là tối chủ nhật lúc 9h.", False),
    ("Họp tiếp theo là tối chủ nhật lúc 9h ok.", "Họp tiếp theo là tối chủ nhật lúc 9h.", False),
    ("Lúc 10 giờ ok nhé.", "Lúc 10 giờ.", False),
    ("Bạn Phúc xem view sản phẩm.", "Bạn Phúc xem view sản phẩm.", False),
    ("Mình đi shopping với khách hàng.", "Mình đi shopping với khách hàng.", False),
    ("Doanh số trên shopping giảm.", "Doanh số trên Shopee giảm.", False),
    ("Bích Linh là thứ 6 nhé.", "deadline là thứ 6.", False),
    ("Họp xong. Bích Linh là ngày 20 tháng 10.", "Họp xong. deadline là ngày 20 tháng 10.", False),
    ("Team mình chốt là dùng react chứ không dùng view nữa.",
     "Team mình chốt là dùng React chứ không dùng Vue nữa.", False),
    ("Frontend dùng view hay React?", "Frontend dùng Vue hay React?", False),
    ("Hôm nay chia việc cho spring tiếp theo.", "Hôm nay chia việc cho Sprint tiếp theo.", False),
    ("Bắt đầu cuộc họp spring 4.", "Bắt đầu cuộc họp Sprint 4.", True),
    # --- Từ đệm: bỏ khi là đệm, giữ khi có nghĩa ---
    ("Rồi, à, hôm nay mình review nha.", "Rồi, hôm nay mình review.", False),
    ("À, nhóm mình đã chốt rồi à.", "nhóm mình đã chốt rồi.", False),
    # (trước đây mong đợi "Tuấn— hôm nay", tức là chốt luôn khoảng trắng thừa sau khi bỏ "à")
    ("Tuấn—à hôm nay không có Tuấn.", "Tuấn—hôm nay không có Tuấn.", False),
    ("File này ok chưa em?", "File này ok chưa em?", False),
    ("Thị trường châu Á tăng mạnh.", "Thị trường châu Á tăng mạnh.", False),
    ("Anh Á phụ trách viết báo cáo.", "Anh Á phụ trách viết báo cáo.", False),
    ("Ừm, ờ, bạn Khoa làm database ạ.", "bạn Khoa làm database.", False),
    # "ok" đầu câu không có dấu phẩy (Whisper hay bỏ dấu phẩy) vẫn là từ đệm
    ("ok phần database để mình làm.", "phần database để mình làm.", False),
    ("Ok chốt lại phân công: Hạnh chạy ads.", "chốt lại phân công: Hạnh chạy ads.", False),
    # "ok?"/"à?" là từ để hỏi: giữ, chỉ bỏ "nhé"
    ("Hạn là thứ 6 nhé, ok?", "Hạn là thứ 6, ok?", False),
    ("Deadline à? Thứ 6.", "Deadline à? Thứ 6.", False),
    # --- Câu xã giao: chỉ khi CẢ câu là xã giao ---
    ("Ok, mình bắt đầu meeting nha.", "mình bắt đầu meeting.", True),
    ("Ok, vậy thôi, cảm ơn mọi người.", "vậy thôi, cảm ơn mọi người.", True),
    ("Có ai có câu hỏi gì không?", "Có ai có câu hỏi gì không?", True),
    ("Có ai ý kiến không, anh Bình phụ trách báo cáo trước thứ sáu.",
     "Có ai ý kiến không, anh Bình phụ trách báo cáo trước thứ sáu.", False),
    ("Anh Bình bắt đầu phụ trách đặt phòng họp trước thứ sáu.",
     "Anh Bình bắt đầu phụ trách đặt phòng họp trước thứ sáu.", False),
    ("Cảm ơn Lan, Tuấn làm slide.", "Cảm ơn Lan, Tuấn làm slide.", False),
    ("Mình bắt đầu họp lúc 9h thứ hai tuần sau.", "Mình bắt đầu họp lúc 9h thứ hai tuần sau.", False),
    ("Rồi, cảm ơn mọi người.", "Rồi, cảm ơn mọi người.", True),
    ("Chào mọi người, mình bắt đầu buổi họp giao ban.", "Chào mọi người, mình bắt đầu buổi họp giao ban.", True),
    ("Xin chào mọi người.", "Xin chào mọi người.", True),
    ("Chào cả nhà.", "Chào cả nhà.", True),
    ("Hello mọi người, mình bắt đầu nhé.", "Hello mọi người, mình bắt đầu.", True),
    ("Thanks mọi người.", "Thanks mọi người.", True),
    ("Chào hàng là việc của Lan.", "Chào hàng là việc của Lan.", False),
    ("Hello mọi người, Tuấn làm slide.", "Hello mọi người, Tuấn làm slide.", False),
    ("Mình bắt đầu làm phần đăng nhập.", "Mình bắt đầu làm phần đăng nhập.", False),
    ("Hi vọng Lan xong phần slide.", "Hi vọng Lan xong phần slide.", False),
    # Cụm xã giao nằm GIỮA câu giao việc: không phải xã giao (phần NLP bỏ câu xã giao -> mất việc)
    ("Tuấn chuẩn bị slide trước khi bắt đầu họp.", "Tuấn chuẩn bị slide trước khi bắt đầu họp.", False),
    ("Lan viết thư cảm ơn nhà tài trợ.", "Lan viết thư cảm ơn nhà tài trợ.", False),
    ("Bạn Nam tổng hợp xem có ai có câu hỏi không.",
     "Bạn Nam tổng hợp xem có ai có câu hỏi không.", False),
    ("Tuấn làm slide thì mình bắt đầu họp.", "Tuấn làm slide thì mình bắt đầu họp.", False),
    ("Hẹn gặp lại khách hàng để chốt hợp đồng.", "Hẹn gặp lại khách hàng để chốt hợp đồng.", False),
    # Câu xã giao thật, kể cả cách viết khác và câu chào kết thúc
    ("Mọi người vào đông đủ rồi thì mình bắt đầu cuộc họp Sprint 4.",
     "Mọi người vào đông đủ rồi thì mình bắt đầu cuộc họp Sprint 4.", True),
    ("Mình xin phép bắt đầu cuộc họp.", "Mình xin phép bắt đầu cuộc họp.", True),
    ("Vậy mọi người có ai ý kiến gì không?", "Vậy mọi người có ai ý kiến gì không?", True),
    ("Xin cám ơn mọi người.", "Xin cám ơn mọi người.", True),
    ("Cảm ơn mọi người, hẹn gặp lại.", "Cảm ơn mọi người, hẹn gặp lại.", True),
    ("Tạm biệt mọi người.", "Tạm biệt mọi người.", True),
    ("Bye mọi người.", "Bye mọi người.", True),
    # --- Dọn khoảng trắng/dấu câu sau khi bỏ từ đệm ---
    ("Dùng .NET và C# nhé.", "Dùng .NET và C#.", False),     # dấu chấm dính chữ không phải dấu câu
    ("Ờ, .NET chạy ổn rồi.", ".NET chạy ổn rồi.", False),
    ("Thì... ờ... mình nghĩ là xong rồi.", "Thì... mình nghĩ là xong rồi.", False),
    ("(ờ) Tuấn làm slide.", "Tuấn làm slide.", False),        # không để lại "()"
    ("Ừ ừ, à à à, bạn Lan làm slide.", "bạn Lan làm slide.", False),
    ("Lan sửa nha trang chủ.", "Lan sửa trang chủ.", False),  # "nha" vẫn là đệm trước "trang chủ"
    ("Học kỳ Spring 2025 xong, sang spring 5.", "Học kỳ Spring 2025 xong, sang Sprint 5.", False),
]

# Câu ĐÚNG, có tên người, địa danh, cụm từ thường gặp: tiền xử lý KHÔNG được đổi gì.
# Mỗi khi thêm luật sửa lỗi mới vào tu_dien_tien_xu_ly.py, bộ này phải vẫn ĐẠT.
CAU_KHONG_DUOC_DOI = [
    "Tuấn sửa hàm login() trước thứ sáu.",
    "Trả về mảng [] khi rỗng.",
    "Spring 3.0 ra rồi.",
    "Mình bắt đầu thảo luận phần họp báo.",
    "Bích Linh là thứ hai, Lan là thứ ba.",
    "Ok lắm, cứ thế làm.",
    "Ok luôn, Tuấn làm.",
    "Dùng Spring cuối cùng là Spring Boot.",
    "Chị Bích Linh phụ trách làm slide, hạn chót thứ sáu.",
    "Em Bích Linh gửi báo cáo trước ngày 20.",
    "Bạn Bích Link bên marketing sẽ liên hệ khách hàng.",
    "Thầy cho phép bắt đầu từ tuần sau.",
    "Đây là phần bắt buộc, ai cũng phải làm.",
    "Buổi họp tiếp theo ở Nha Trang vào thứ hai tuần sau.",
    "Chiều nay mình đi nha khoa nên về sớm.",
    "Anh Á phụ trách viết báo cáo trước thứ sáu.",
    "Thị trường châu Á đang tăng trưởng tốt.",
    "Dùng Spring Boot cho phần backend.",
    "Dùng Spring Security cho chức năng đăng nhập.",
    "Dữ liệu lấy qua Spring Data.",
    "Dùng view cho báo cáo doanh thu.",
    "Tạo view trong database để thống kê.",
    "Bạn Phúc xem view sản phẩm trên trang chủ.",
    "Mình đi shopping với khách hàng chiều nay.",
    "File này ok chưa em?",
    "Mọi thứ đều ok.",
    "Bản thiết kế này ok.",
    "Tết thử nghiệm món mới cho quán.",
    "Mình xin phép bắt đầu phần báo cáo.",
    "Bạn Kênh phụ trách quay video.",
    "Bạn Ngọc sẽ fix lỗi đăng ký tài khoản.",
    "Deadline là thứ 4 tuần sau.",
    "Hạn chót là ngày 20 tháng 10.",
    "Khoa update lại database trước thứ ba.",
    "Vi làm các API thêm sách, sửa sách với xóa sách.",
    "Họp tiếp theo ở phòng họp tầng 3 lúc 9 giờ.",
    "Chị Hạnh chạy campaign quảng cáo trên Facebook và TikTok.",
    "Anh Dũng gửi báo giá cho công ty Minh Phát.",
    "Cô Nha dạy môn cơ sở dữ liệu.",
    "Frontend dùng React, còn báo cáo thì dùng view trong database.",
    "Còn Bích Linh vào thứ sáu nộp báo cáo.",
    "Slide ok.",
    "Bạn Tuấn ok.",
    "Phần backend ok.",
    "Hạn thứ 6 ok.",
    "Sprint 4 ok.",
    "Bích Linh là thứ hai trong danh sách.",
    # "Bích Linh" là tên người khi đứng giữa câu hoặc sau mốc ngày còn động từ
    "Lan với Bích Linh là thứ 6 nộp báo cáo.",
    "Còn Bích Linh là thứ sáu nộp.",
    "Bích Linh là thứ 6 nộp báo cáo.",
    # "ok" đầu câu mang nội dung
    "Ok là chốt phương án A.",
    "OK button bị lỗi, Tuấn fix.",
    # "ok"/"à" trước dấu hỏi là từ để hỏi
    "Bạn làm lúc 9 giờ ok?",
    "Mình chọn phương án B à?",
    "Thế à?",
    # "view" là danh từ ("view biển") dù câu có nói tới frontend
    "Nhóm frontend họp với khách, khách thích view đẹp hay view biển?",
    # "Spring" có thật, "kênh shopping" có thật
    "Dùng Spring JPA cho phần backend.",
    "Spring Festival năm nay tổ chức ở Cần Thơ.",
    "Mở thêm kênh shopping online cho khách.",
    # Dấu chấm dính chữ (".NET") không bị nối vào từ trước
    "Chuyển sang: .NET cho phần backend.",
    ".NET là framework mới của nhóm.",
    # "Spring 2025" là học kỳ/năm; "shopping mall/online" là cụm tiếng Anh có thật
    "Học kỳ Spring 2025 nhóm mình đăng ký.",
    "Đi qua shopping mall gần trường.",
    "Bán trên shopping online cho khách.",
    "Họp ở nha trang vào thứ hai tuần sau.",
    # Cụm xã giao nằm giữa câu giao việc: không được đổi chữ (xa_giao kiểm ở CA_LAM_SACH)
    "Lan viết thư cảm ơn nhà tài trợ.",
]

# (câu đã sạch, kết quả tách từ mong đợi phải CHỨA các cụm này)
CA_TACH_TU = [
    ("Hạn chót là thứ 6.", ["Hạn_chót"]),
    ("Họp ở phòng họp với ban giám đốc.", ["phòng_họp", "ban_giám_đốc"]),
    ("Gửi lên Google Drive trong group Zalo.", ["Google_Drive", "group_Zalo"]),
    ("Cuộc họp sau bạn Tuấn phụ trách.", ["Cuộc_họp", "phụ_trách"]),
]

TRUONG_DAU_RA = {"stt", "speaker", "start", "end", "goc", "sach", "tach_tu", "xa_giao"}


def cau_tho(cac_van_ban):
    return [{"speaker": "SPEAKER_00", "start": float(i), "end": i + 0.9, "text": t}
            for i, t in enumerate(cac_van_ban)]


def kiem_lam_sach():
    loi = []
    for tho, mong_sach, mong_xa_giao in CA_LAM_SACH:
        kq = txl.tien_xu_ly(cau_tho([tho]))
        if not kq:
            loi.append(f"{tho!r}: bị bỏ mất cả câu")
            continue
        if kq[0]["sach"] != mong_sach:
            loi.append(f"{tho!r} -> {kq[0]['sach']!r}, mong đợi {mong_sach!r}")
        if kq[0]["xa_giao"] != mong_xa_giao:
            loi.append(f"{tho!r}: xa_giao={kq[0]['xa_giao']}, mong đợi {mong_xa_giao}")
    return loi


def kiem_cau_khong_duoc_doi():
    loi = []
    for cau in CAU_KHONG_DUOC_DOI:
        kq = txl.tien_xu_ly(cau_tho([cau]))
        if not kq or kq[0]["sach"] != cau:
            loi.append(f"{cau!r} bị đổi thành {kq[0]['sach'] if kq else '(mất câu)'!r}")
    return loi


def kiem_tach_tu():
    loi = []
    for cau, cac_cum in CA_TACH_TU:
        kq = txl.tach_tu(cau)
        for cum in cac_cum:
            if cum not in kq.split():
                loi.append(f"{cau!r} -> {kq!r}, thiếu {cum!r}")
    return loi


def kiem_dinh_dang_va_stt():
    kq = txl.tien_xu_ly(cau_tho(["Ừm.", "Bạn Tuấn làm slide.", "Ok.", "À.", "Bạn Lan test."]))
    loi = []
    if [c["stt"] for c in kq] != list(range(len(kq))):
        loi.append(f"stt không liên tục: {[c['stt'] for c in kq]}")
    if [c["sach"] for c in kq] != ["Bạn Tuấn làm slide.", "Bạn Lan test."]:
        loi.append(f"câu chỉ có từ đệm chưa bị bỏ: {[c['sach'] for c in kq]}")
    for c in kq:
        if set(c) != TRUONG_DAU_RA:
            loi.append(f"sai trường: {sorted(c)}")
    if [c["start"] for c in kq] != [1.0, 4.0]:
        loi.append(f"mốc thời gian bị lệch: {[c['start'] for c in kq]}")
    return loi


def kiem_tu_dem_lap_dai_chay_nhanh():
    # Whisper đôi khi ra "à à à ..." hàng nghìn lần; trước đây mất ~5 giây cho 5000 chữ
    bat_dau = time.time()
    loi = []
    # Cùng một từ lặp, từ đệm xen kẽ, và "ok" lặp
    for chuoi in (["à"] * 5000, ["à", "ờ"] * 2500, ["ok"] * 3000):
        kq = txl.bo_tu_dem(" ".join(chuoi) + " bạn Lan làm slide.")
        if kq.strip() != "bạn Lan làm slide.":
            loi.append(f"{chuoi[:2]}...: ra {kq.strip()[:40]!r}")
    if time.time() - bat_dau > 1.5:
        loi.append(f"chạy mất {time.time() - bat_dau:.1f} giây")
    return loi


def kiem_unicode_to_hop():
    # Cùng câu nhưng dấu được mã hóa kiểu tổ hợp (NFD), hay gặp khi copy từ macOS
    kq = txl.tien_xu_ly(cau_tho([unicodedata.normalize("NFD", "Ờ, bích link thứ 6 nhé.")]))
    return [] if kq and kq[0]["sach"] == "deadline thứ 6." else [f"ra {kq[0]['sach'] if kq else kq!r}"]


def kiem_doc_ghi_file():
    loi = []
    goc = cli.THU_MUC_RA
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        cli.THU_MUC_RA = tm / "processed"
        try:
            # File có BOM (soạn bằng Notepad) vẫn đọc được
            co_bom = tm / "co_bom.json"
            co_bom.write_text(json.dumps(cau_tho(["Bạn Tuấn làm slide."]), ensure_ascii=False),
                              encoding="utf-8-sig")
            cli.xu_ly_mot_file(co_bom)
            du_lieu = json.loads((tm / "processed" / "co_bom.json").read_text(encoding="utf-8"))
            if len(du_lieu) != 1:
                loi.append("đọc file có BOM sai")
            # Chỉ có từ đệm -> báo lỗi, KHÔNG ghi file rỗng
            rong = tm / "rong.json"
            rong.write_text(json.dumps(cau_tho(["Ừm.", "Ok."])), encoding="utf-8")
            try:
                cli.xu_ly_mot_file(rong)
                loi.append("không báo lỗi khi bỏ hết câu")
            except ValueError:
                pass
            if (tm / "processed" / "rong.json").exists():
                loi.append("vẫn ghi file rỗng")
            # text không phải chuỗi -> lỗi rõ ràng
            try:
                txl.tien_xu_ly([{"speaker": "S", "start": 0, "end": 1, "text": None}])
                loi.append("text=None không báo lỗi")
            except ValueError:
                pass
            if list((tm / "processed").glob("*.tmp")):
                loi.append("còn sót file tạm")
        finally:
            cli.THU_MUC_RA = goc
    return loi


# Đoạn mã chạy như một file trong src/nlp: thư mục src/nlp đứng đầu sys.path
# (giống khi chạy "python src/nlp/chay_nlp.py"), rồi gọi đúng câu lệnh của Anh.
MA_GOI_CAU_NOI = """
import pickle, sys
sys.path.insert(0, sys.argv[1])
from tien_xu_ly import tien_xu_ly
import doc_transcript
pickle.dumps(tien_xu_ly)
print(tien_xu_ly.__module__)
print(sys.modules[tien_xu_ly.__module__].__file__)
print(doc_transcript.__file__)
print(tien_xu_ly([{"speaker": "S", "start": 0, "end": 1, "text": "Ờ, bích link thứ 6 nhé."}])[0]["sach"])
"""


def kiem_cau_noi():
    """Cầu nối src/nlp/tien_xu_ly.py: gọi được từ mọi thư mục, ra đúng hàm của Hân,
    không thay doc_transcript của phần NLP, và pickle được (multiprocessing trên Windows)."""
    loi = []
    thu_muc_nlp = THU_MUC_GOC / "src" / "nlp"
    for cwd in (THU_MUC_GOC, thu_muc_nlp, Path(THU_MUC_GOC.anchor)):
        kq = subprocess.run([sys.executable, "-c", MA_GOI_CAU_NOI, str(thu_muc_nlp)],
                            cwd=cwd, capture_output=True, text=True, encoding="utf-8")
        if kq.returncode != 0:
            loi.append(f"chạy từ {cwd}: lỗi {kq.stderr.strip().splitlines()[-1:]}")
            continue
        dong = kq.stdout.splitlines()
        mong_doi = ["lam_sach", str(THU_MUC_NAY / "lam_sach.py"),
                    str(thu_muc_nlp / "doc_transcript.py"), "deadline thứ 6."]
        if [d.strip() for d in dong] != mong_doi:
            loi.append(f"chạy từ {cwd}: ra {dong}, mong đợi {mong_doi}")
    # Chạy chính file cầu nối từ thư mục khác (đường dẫn tuyệt đối)
    tep = THU_MUC_GOC / "data" / "transcripts" / "thu_nghiem.json"
    kq = subprocess.run([sys.executable, str(thu_muc_nlp / "tien_xu_ly.py"), str(tep)],
                        cwd=THU_MUC_GOC.anchor, capture_output=True, text=True, encoding="utf-8")
    if kq.returncode != 0 or "0." not in kq.stdout:
        loi.append(f"python src/nlp/tien_xu_ly.py chạy từ / lỗi: {kq.stderr.strip()[-200:]}")
    # Trong cùng tiến trình: hàm pickle được (tên module đăng ký đúng trong sys.modules)
    try:
        pickle.loads(pickle.dumps(txl.tien_xu_ly))
    except Exception as e:
        loi.append(f"không pickle được: {e}")
    return loi


def kiem_data_processed_khop_code():
    """data/processed/*.json phải giống hệt tien_xu_ly() trên data/transcripts/*.json.

    Phần NLP không đọc data/processed (nó gọi thẳng tien_xu_ly()), nên nếu sửa từ điển
    mà quên chạy lại thì file trong data/processed sẽ cũ mà không ai biết.
    """
    loi = []
    cac_file = sorted((THU_MUC_GOC / "data" / "transcripts").glob("*.json"))
    for tep in cac_file:
        tep_ra = THU_MUC_GOC / "data" / "processed" / tep.name
        if not tep_ra.exists():
            loi.append(f"thiếu data/processed/{tep.name}")
            continue
        if txl.tien_xu_ly(doc_transcript(tep)) != json.loads(tep_ra.read_text(encoding="utf-8")):
            loi.append(f"data/processed/{tep.name} đã cũ, chạy lại: "
                       "python src/tien_xu_ly/tien_xu_ly.py data/transcripts/")
    if not cac_file:
        loi.append("không có file nào trong data/transcripts")
    return loi


if __name__ == "__main__":
    cac_nhom = [
        (f"Làm sạch ({len(CA_LAM_SACH)} câu)", kiem_lam_sach),
        (f"Câu đúng không được đổi ({len(CAU_KHONG_DUOC_DOI)} câu)", kiem_cau_khong_duoc_doi),
        (f"Tách từ ({len(CA_TACH_TU)} câu)", kiem_tach_tu),
        ("Định dạng đầu ra và stt", kiem_dinh_dang_va_stt),
        ("Từ đệm lặp rất dài vẫn chạy nhanh", kiem_tu_dem_lap_dai_chay_nhanh),
        ("Unicode tổ hợp (NFD)", kiem_unicode_to_hop),
        ("Đọc/ghi file (BOM, file rỗng, file tạm)", kiem_doc_ghi_file),
        ("Cầu nối src/nlp/tien_xu_ly.py (3 thư mục chạy, pickle)", kiem_cau_noi),
        ("data/processed khớp với code hiện tại", kiem_data_processed_khop_code),
    ]
    so_dat = 0
    for ten, ham in cac_nhom:
        loi = ham()
        if loi:
            print(f"KHÔNG ĐẠT | {ten}")
            for dong in loi:
                print(f"    - {dong}")
        else:
            so_dat += 1
            print(f"ĐẠT       | {ten}")
    print(f"\nTổng kết: {so_dat}/{len(cac_nhom)} nhóm ĐẠT")
    sys.exit(0 if so_dat == len(cac_nhom) else 1)
