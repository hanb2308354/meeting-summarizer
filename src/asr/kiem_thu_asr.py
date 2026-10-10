# Kiểm thử tự động cho phần nhận dạng giọng nói (chuyen_giong_noi.py).
# Không cần tải model: dùng âm thanh tổng hợp và một "model giả" trả về các đoạn
# dựng sẵn, nên chạy được trên mọi máy trong vài giây.
#
# Cách dùng:  python src/asr/kiem_thu_asr.py
# Mỗi ca in ĐẠT / KHÔNG ĐẠT; mã thoát 0 khi tất cả đều ĐẠT.
import contextlib
import dataclasses
import inspect
import io
import json
import subprocess
import sys
import tempfile
import unicodedata
import wave
from collections import Counter
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment, Word

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402
import danh_gia_wer  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SR = asr.TAN_SO_MAU
CAC_CA = []


def ca(ham):
    """Đánh dấu một hàm là ca kiểm thử."""
    CAC_CA.append(ham)
    return ham


# ----------------------------------------------------------------------
# Công cụ dựng dữ liệu giả
# ----------------------------------------------------------------------
def tu(bat_dau, chu):
    return Word(start=bat_dau, end=bat_dau + 0.35, word=" " + chu, probability=0.9)


def chuoi_tu(bat_dau, cau, buoc=0.4):
    return [tu(bat_dau + i * buoc, w) for i, w in enumerate(cau.split())]


def doan(cac_tu, ty_le_nen=1.5, khong_co_tieng=0.1, do_tin_cay=-0.3):
    return Segment(
        id=0, seek=0, start=cac_tu[0].start, end=cac_tu[-1].end,
        text="".join(w.word for w in cac_tu), tokens=[], avg_logprob=do_tin_cay,
        compression_ratio=ty_le_nen, no_speech_prob=khong_co_tieng, words=cac_tu, temperature=0.0,
    )


class ModelGia:
    """Trả về các đoạn dựng sẵn; kiểm tra tham số truyền vào có hợp lệ với faster-whisper thật."""

    def __init__(self, cac_doan):
        self.cac_doan = cac_doan

    def transcribe(self, am_thanh, **tham_so):
        inspect.signature(WhisperModel.transcribe).bind(None, am_thanh, **tham_so)
        assert isinstance(am_thanh, np.ndarray) and am_thanh.dtype == np.float32
        return iter(self.cac_doan), None


def ghi_wav(duong_dan, song_am):
    with wave.open(str(duong_dan), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((np.clip(song_am, -1, 1) * 32767).astype(np.int16).tobytes())


def tieng_noi_gia(giay, co_lang=True):
    """Hài âm 200 Hz (giống giọng nói), bật/tắt mỗi giây nếu co_lang."""
    t = np.arange(int(giay * SR)) / SR
    giong = sum(0.1 / k * np.sin(2 * np.pi * 200 * k * t) for k in range(1, 8))
    if co_lang:
        giong = giong * ((t % 2) < 1.2)
    return giong.astype(np.float32)


def bien_do_tai(song_am, tan_so):
    pho = np.abs(np.fft.rfft(song_am))
    return pho[np.argmin(np.abs(np.fft.rfftfreq(len(song_am), 1 / SR) - tan_so))]


def chay_nhan_dang(cac_doan):
    cac_tu, so_loai = asr.nhan_dang(ModelGia(cac_doan), np.zeros(SR, dtype=np.float32))
    return [c["text"] for c in asr.tach_cau(cac_tu)], so_loai


# ----------------------------------------------------------------------
# 1. Đọc file đầu vào
# ----------------------------------------------------------------------
@ca
def doc_file_loi_bao_ro_rang():
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        (tm / "rong.mp3").write_bytes(b"")
        (tm / "hong.mp3").write_bytes(b"khong phai mp3" * 50)
        (tm / "ghi_chu.txt").write_text("x")
        ghi_wav(tm / "ngan.wav", tieng_noi_gia(0.5))
        ghi_wav(tm / "im_lang.wav", np.zeros(SR * 3))
        for ten in ("khong_co.mp3", "rong.mp3", "hong.mp3", "ghi_chu.txt", "ngan.wav", "im_lang.wav"):
            try:
                asr.doc_am_thanh(tm / ten)
                return f"{ten}: lẽ ra phải báo lỗi"
            except asr.LoiDauVao:
                pass


# ----------------------------------------------------------------------
# 2. Tiền xử lý âm thanh
# ----------------------------------------------------------------------
@ca
def loc_tieng_u_bo_50hz_giu_giong():
    t = np.arange(SR * 5) / SR
    x = (0.05 * np.sin(2 * np.pi * 50 * t) + 0.1 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    y = asr.loc_tieng_u(x)
    if len(y) != len(x):
        return "độ dài thay đổi (mốc thời gian sẽ lệch)"
    giam_50 = 20 * np.log10(bien_do_tai(y, 50) / bien_do_tai(x, 50))
    giu_200 = 20 * np.log10(bien_do_tai(y, 200) / bien_do_tai(x, 200))
    if giam_50 > -30 or abs(giu_200) > 0.1:
        return f"50 Hz {giam_50:.1f} dB, 200 Hz {giu_200:.2f} dB"


@ca
def chuan_hoa_am_luong_khong_qua_tay():
    x = np.zeros(SR * 60, dtype=np.float32)
    x[: SR * 3] = 0.001 * tieng_noi_gia(3, co_lang=False)  # 95% im lặng, tiếng rất nhỏ
    y, tang_db = asr.chuan_hoa_am_luong(x)
    if tang_db > asr.TANG_TOI_DA_DB + 1e-6:
        return f"khuếch đại {tang_db:.1f} dB, vượt giới hạn"
    if np.max(np.abs(y)) > asr.DINH_TOI_DA + 1e-6:
        return "bị cắt đỉnh"


@ca
def giam_tap_am_bo_qua_khi_khong_co_khoang_lang():
    rng = np.random.default_rng(0)
    x = tieng_noi_gia(10, co_lang=False) + 0.01 * rng.standard_normal(SR * 10).astype(np.float32)
    y, da_ap_dung = asr.giam_tap_am(x)
    if da_ap_dung or not np.allclose(x, y):
        return "vẫn giảm nhiễu dù không có khoảng lặng (sẽ xóa mất giọng)"


@ca
def giam_tap_am_giam_on_giu_giong():
    rng = np.random.default_rng(0)
    t = np.arange(SR * 20) / SR
    co_giong = (t % 2) < 1.2
    x = tieng_noi_gia(20) + 0.01 * rng.standard_normal(len(t)).astype(np.float32)
    y, da_ap_dung = asr.giam_tap_am(x)
    giam_on = 20 * np.log10(np.std(y[~co_giong]) / np.std(x[~co_giong]))
    giu_giong = np.std(y[co_giong]) / np.std(x[co_giong])
    if not da_ap_dung or giam_on > -6 or giu_giong < 0.9 or len(y) != len(x):
        return f"áp dụng={da_ap_dung}, ồn {giam_on:.1f} dB, giọng giữ {giu_giong:.2f}"


# ----------------------------------------------------------------------
# 3. Lọc lỗi nhận dạng: giữ câu thật, loại câu bịa
# ----------------------------------------------------------------------
@ca
def giu_cau_tra_loi_ngan_lap_lai():
    cau, _ = chay_nhan_dang([doan(chuoi_tu(0, "Dạ.")), doan(chuoi_tu(1.5, "Dạ."))])
    if cau != ["Dạ.", "Dạ."]:
        return f"ra {cau}"


@ca
def loai_doan_lap_xen_ke_a_b_a_b():
    # Model kẹt lặp 2 câu xen kẽ: chỉ giữ lần đầu của mỗi câu
    a, b = "Bạn Tuấn làm phần API.", "Mọi người nhớ nộp trước thứ sáu."
    cau, so_loai = chay_nhan_dang([doan(chuoi_tu(0, a)), doan(chuoi_tu(3, b)),
                                   doan(chuoi_tu(7, a)), doan(chuoi_tu(10, b))])
    if cau != [a, b] or so_loai != 2:
        return f"ra {cau}, loại {so_loai}"
    # Câu ngắn ("Dạ.", "Ok.") lặp xen kẽ là bình thường, giữ hết
    cau, _ = chay_nhan_dang([doan(chuoi_tu(0, "Dạ.")), doan(chuoi_tu(1.5, "Ok.")),
                             doan(chuoi_tu(3, "Dạ.")), doan(chuoi_tu(4.5, "Ok."))])
    if cau != ["Dạ.", "Ok.", "Dạ.", "Ok."]:
        return f"câu ngắn bị loại: {cau}"
    # Câu dài nhắc lại sau 2 câu khác thì giữ (chỉ xét 2 đoạn gần nhất)
    c = "Còn phần giao diện thì sao."
    cau, _ = chay_nhan_dang([doan(chuoi_tu(0, a)), doan(chuoi_tu(3, b)),
                             doan(chuoi_tu(7, c)), doan(chuoi_tu(10, a))])
    if cau != [a, b, c, a]:
        return f"câu nhắc lại xa bị loại: {cau}"


@ca
def giu_cau_hop_that_co_chu_video():
    cau, _ = chay_nhan_dang([doan(chuoi_tu(0, "Video tiếp theo mình làm về sản phẩm mới, deadline thứ sáu."))])
    if len(cau) != 1:
        return "câu họp thật bị loại"


@ca
def giu_cau_liet_ke_cong_viec():
    cau, _ = chay_nhan_dang([doan(chuoi_tu(0, "Hôm nay mình review, test, demo."))])
    if len(cau) != 1:
        return "câu 'review, test, demo' bị coi là đọc lại từ khóa"


@ca
def giu_cau_that_chung_cua_so_voi_doan_lap():
    # compression_ratio của cả cửa sổ cao, nhưng chữ của riêng câu này bình thường
    cau, _ = chay_nhan_dang([doan(chuoi_tu(0, "Bình làm slide thứ sáu."), ty_le_nen=3.0)])
    if len(cau) != 1:
        return "câu thật bị loại theo cả cửa sổ 30 giây"


@ca
def loai_cac_kieu_cau_bia():
    cac_doan = [
        doan(chuoi_tu(0, "cảm ơn cảm ơn cảm ơn cảm ơn cảm ơn cảm ơn cảm ơn")),
        doan(chuoi_tu(10, "Hãy subscribe cho kênh Ghiền Mì Gõ")),
        doan(chuoi_tu(15, "Cảm ơn các bạn đã theo dõi."), khong_co_tieng=0.5),
        doan(chuoi_tu(20, "deadline, hạn chót, project, meeting, slide")),
        doan(chuoi_tu(30, asr.CAU_MO_DAU)),
        doan(chuoi_tu(40, "Bạn Lan làm phần slide nha.")),
        doan(chuoi_tu(45, "Bạn Lan làm phần slide nha.")),
    ]
    cau, so_loai = chay_nhan_dang(cac_doan)
    if cau != ["Bạn Lan làm phần slide nha."] or so_loai != 6:
        return f"còn lại {cau}, loại {so_loai}"


@ca
def loai_cau_bia_cuoi_phu_de():
    cac_doan = [
        doan(chuoi_tu(0, "Phụ đề được thực hiện bởi cộng đồng Amara.org")),   # chắc chắn bịa
        doan(chuoi_tu(5, "Vietsub by Mì Gõ Team"), khong_co_tieng=0.5),        # nghi + model không chắc
    ]
    cau, so_loai = chay_nhan_dang(cac_doan)
    if cau or so_loai != 2:
        return f"còn lại {cau}, loại {so_loai}"
    # Team làm video nói thật, model nói rõ -> giữ
    cau, so_loai = chay_nhan_dang([doan(chuoi_tu(0, "Lan làm vietsub cho video khách hàng."))])
    if so_loai:
        return "loại nhầm câu họp thật có chữ vietsub"


@ca
def giu_doan_khong_co_moc_thoi_gian_theo_tu():
    # Đoạn có chữ nhưng words=None: trước đây in ra như được giữ mà không vào JSON
    khong_co_tu = dataclasses.replace(doan(chuoi_tu(3, "Bạn Lan làm slide.")), words=None)
    cau, so_loai = chay_nhan_dang([doan(chuoi_tu(0, "Bắt đầu nhé.")), khong_co_tu])
    if cau != ["Bắt đầu nhé.", "Bạn Lan làm slide."] or so_loai:
        return f"ra {cau}"


@ca
def giu_cau_nhac_lai_sau_cau_tra_loi_ngan():
    # "A", "Dạ.", "A": người nói nhắc lại câu sau một câu trả lời ngắn, không phải model kẹt
    a = "Bạn Tuấn làm slide trước thứ sáu."
    cau, so_loai = chay_nhan_dang([doan(chuoi_tu(0, a)), doan(chuoi_tu(4, "Dạ.")), doan(chuoi_tu(6, a))])
    if so_loai or len(cau) != 3:
        return f"loại {so_loai} đoạn, còn {cau}"


@ca
def giu_cau_hop_marketing_that():
    # Nói rõ (model tự tin), nhắc tới subscribe/like/bấm chuông là chuyện công việc
    cau, so_loai = chay_nhan_dang([
        doan(chuoi_tu(0, "Tháng này mình cần tăng lượt subscribe cho kênh của khách hàng.")),
        doan(chuoi_tu(6, "Bài đăng tuần trước được like và share khá nhiều.")),
        doan(chuoi_tu(12, "Video mới nhớ kêu gọi người xem bấm chuông thông báo.")),
    ])
    if so_loai:
        return f"loại nhầm {so_loai} câu họp thật"


@ca
def giu_cau_liet_ke_tu_khoa_khi_model_tu_tin():
    # Người họp liệt kê thật, model nói rõ -> giữ; cùng câu đó mà model không chắc -> loại
    for cau_that in ("Frontend, backend, database, API.", "Update, fix, test, demo."):
        cau, so_loai = chay_nhan_dang([doan(chuoi_tu(0, cau_that))])
        if so_loai or cau != [cau_that]:
            return f"loại nhầm câu liệt kê thật {cau_that!r}"
        _, so_loai = chay_nhan_dang([doan(chuoi_tu(0, cau_that), do_tin_cay=-1.5)])
        if so_loai != 1:
            return f"không loại {cau_that!r} khi model không chắc"


# ----------------------------------------------------------------------
# 4. Tách câu
# ----------------------------------------------------------------------
@ca
def khong_cat_khi_chi_ngap_ngung():
    cac_tu = chuoi_tu(0, "Deadline phần backend là") + chuoi_tu(3.0, "thứ sáu nha Nam.")
    cau = [c["text"] for c in asr.tach_cau(cac_tu)]
    if len(cau) != 1:
        return f"bị cắt thành {cau}"


@ca
def cat_khi_ngung_rat_lau():
    cac_tu = chuoi_tu(0, "Ok") + chuoi_tu(10, "Bình làm slide.")
    cau = asr.tach_cau(cac_tu)
    if len(cau) != 2 or cau[1]["start"] != 10.0:
        return f"ra {[(c['start'], c['text']) for c in cau]}"


@ca
def khong_cat_o_chu_viet_tat():
    cau = asr.tach_cau(chuoi_tu(0, "Gặp ở TP. Cần Thơ lúc 9h."))
    if len(cau) != 1:
        return f"bị cắt thành {[c['text'] for c in cau]}"


@ca
def van_tach_cau_sau_v_v_khi_cau_moi_viet_hoa():
    cau = asr.tach_cau(chuoi_tu(0, "Làm báo cáo, slide, v.v. Bạn Lan làm demo."))
    if len(cau) != 2:
        return f"ra {[c['text'] for c in cau]}"


@ca
def khong_cat_o_dau_ba_cham_khi_dang_ngap_ngung():
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, "Thì... mình nghĩ là xong rồi."))]
    if len(cau) != 1:
        return f"bị cắt thành {cau}"
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, "Vậy thôi… Bạn Lan làm slide."))]
    if len(cau) != 2:
        return f"không tách khi câu sau viết hoa: {cau}"


@ca
def tach_cau_sau_dau_cham_trong_ngoac_kep():
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, 'Lan nói "xong rồi." Tuấn làm slide.'))]
    if cau != ['Lan nói "xong rồi."', "Tuấn làm slide."]:
        return f"ra {cau}"


@ca
def tach_cau_khi_cau_sau_mo_ngoac_kep_viet_hoa():
    # Từ sau bắt đầu bằng nháy/ngoặc mở: phải xét chữ cái ngay sau nháy, không phải chính dấu nháy
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, 'Thì... "Bạn Lan làm slide."'))]
    if cau != ["Thì...", '"Bạn Lan làm slide."']:
        return f"ra {cau}"
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, 'Làm báo cáo, v.v. "Bạn Lan" làm demo.'))]
    if len(cau) != 2:
        return f"ra {cau}"
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, 'Thì... "mình" nghĩ là xong rồi.'))]
    if len(cau) != 1:
        return f"ngập ngừng mà vẫn bị cắt: {cau}"


@ca
def bo_cau_chi_co_dau_cau():
    cau = [c["text"] for c in asr.tach_cau(chuoi_tu(0, "Xong rồi. . Tuấn làm."))]
    if cau != ["Xong rồi.", "Tuấn làm."]:
        return f"ra {cau}"


@ca
def end_khong_nho_hon_start():
    # Mốc thời gian theo từ bị lệch: từ cuối kết thúc trước khi từ đầu bắt đầu
    cau = asr.tach_cau([Word(start=5.0, end=4.9, word=" Ok.", probability=0.9)])
    if cau[0]["end"] < cau[0]["start"]:
        return f"start {cau[0]['start']} > end {cau[0]['end']}"


@ca
def cat_cau_qua_dai_o_dau_phay():
    cac_tu = [tu(i * 1.0, f"từ{i}" + ("," if i == 12 else "")) for i in range(30)]
    cau = asr.tach_cau(cac_tu)
    if len(cau) != 2 or not cau[0]["text"].endswith("từ12,"):
        return f"ra {[c['text'][-8:] for c in cau]}"


# ----------------------------------------------------------------------
# 5. Chạy cả chương trình: đúng format, không ghi file rỗng
# ----------------------------------------------------------------------
def chay_main(thu_muc, cac_doan, tham_so):
    asr.THU_MUC_KET_QUA = thu_muc / "transcripts"
    asr.WhisperModel = lambda *a, **k: ModelGia(cac_doan)
    sys.argv = ["chuyen_giong_noi.py", *tham_so]
    try:
        asr.main()
        return 0
    except SystemExit as thoat:
        return thoat.code


@ca
def ghi_json_dung_format():
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        ghi_wav(tm / "hop.wav", tieng_noi_gia(5))
        ma = chay_main(tm, [doan(chuoi_tu(0, "Bạn Tuấn phụ trách frontend."))], [str(tm / "hop.wav")])
        tep = tm / "transcripts" / "hop.json"
        if ma != 0 or not tep.exists():
            return f"mã thoát {ma}, có file: {tep.exists()}"
        du_lieu = json.loads(tep.read_text(encoding="utf-8"))
        for cau in du_lieu:
            if set(cau) != {"speaker", "start", "end", "text"}:
                return f"sai trường: {sorted(cau)}"
            if not (isinstance(cau["start"], float) and isinstance(cau["text"], str) and cau["text"]):
                return f"sai kiểu dữ liệu: {cau}"


@ca
def bao_loi_file_hong_truoc_khi_tai_model():
    def khong_duoc_tai(*a, **k):
        raise AssertionError("đã tải model dù không có file hợp lệ")
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        (tm / "rong.MP3").write_bytes(b"")
        asr.THU_MUC_KET_QUA = tm / "transcripts"
        asr.WhisperModel = khong_duoc_tai
        sys.argv = ["chuyen_giong_noi.py", str(tm / "rong.MP3")]
        dau_ra = io.StringIO()
        with contextlib.redirect_stdout(dau_ra):
            try:
                asr.main()
                return "không báo lỗi"
            except SystemExit as thoat:
                if not thoat.code:
                    return "mã thoát 0 dù file rỗng"
        if "File rỗng" not in dau_ra.getvalue():
            return "không báo 'File rỗng' rõ ràng"


@ca
def thu_muc_bo_qua_file_da_co_va_canh_bao_trung_ten():
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        (tm / "audio").mkdir()
        for ten in ("Hop.mp3", "hop.wav", "cu.mp3"):
            (tm / "audio" / ten).write_bytes(b"x")
        asr.THU_MUC_KET_QUA = tm / "transcripts"
        asr.THU_MUC_KET_QUA.mkdir()
        (asr.THU_MUC_KET_QUA / "cu.json").write_text("[]")
        dau_ra = io.StringIO()
        with contextlib.redirect_stdout(dau_ra):
            cac_file = asr.liet_ke_file([str(tm / "audio")], ghi_de=False)
            asr.WhisperModel = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dừng"))
            sys.argv = ["chuyen_giong_noi.py", str(tm / "audio")]
            try:
                asr.main()
            except SystemExit:
                pass
        if any(f.name == "cu.mp3" for f in cac_file):
            return "không bỏ qua file đã có JSON"
        if "cùng ra" not in dau_ra.getvalue():
            return "không cảnh báo Hop.mp3 và hop.wav trùng tên"


@ca
def thu_muc_da_xu_ly_het_thi_ma_thoat_0():
    # Chạy lại cả thư mục khi mọi file đã có JSON: không phải lỗi, không tải model
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        (tm / "audio").mkdir()
        (tm / "audio" / "cu.mp3").write_bytes(b"x")
        (tm / "transcripts").mkdir()
        (tm / "transcripts" / "cu.json").write_text("[]")

        def khong_duoc_tai(*a, **k):
            raise AssertionError("đã tải model dù không có file cần xử lý")
        asr.WhisperModel = khong_duoc_tai
        asr.THU_MUC_KET_QUA = tm / "transcripts"
        sys.argv = ["chuyen_giong_noi.py", str(tm / "audio")]
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                asr.main()
            except SystemExit as thoat:
                if thoat.code:
                    return f"mã thoát {thoat.code!r} dù không có lỗi"


@ca
def canh_bao_on_khong_bao_oan_khi_noi_lien_tuc():
    lien_tuc = tieng_noi_gia(10, co_lang=False)
    if any("Tạp âm" in c for c in asr.canh_bao_chat_luong(lien_tuc)):
        return "cảnh báo tạp âm oan khi nói liên tục"
    rng = np.random.default_rng(0)
    on = tieng_noi_gia(10) + 0.03 * rng.standard_normal(SR * 10).astype(np.float32)
    if not any("Tạp âm" in c for c in asr.canh_bao_chat_luong(on)):
        return "không cảnh báo khi ồn thật"


@ca
def khong_ghi_file_khi_khong_nghe_duoc_gi():
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        ghi_wav(tm / "on.wav", tieng_noi_gia(5))
        ma = chay_main(tm, [], [str(tm / "on.wav")])
        if ma == 0 or (tm / "transcripts" / "on.json").exists():
            return "vẫn ghi file JSON rỗng"


# ----------------------------------------------------------------------
# 6. Chuẩn hóa văn bản khi đo WER (danh_gia_wer.py)
# ----------------------------------------------------------------------
@ca
def chuan_hoa_wer_cung_cach_doc_thi_giong_nhau():
    cac_ca = [
        ("Họp lúc 9h30, thứ 4.", "họp lúc 9 giờ 30 thứ 4"),
        ("9h", "9 giờ"),
        ("Tăng 10% doanh số", "tăng 10 phần trăm doanh số"),
        ("Mất 2-3 ngày", "mất 2 3 ngày"),             # không dính thành "23"
        ("Phần Front-end và back-end", "phần frontend và backend"),
        ("Thứ 4 họp nhé", "thứ 4 họp nhé"),           # "4 họp" không bị coi là "4h"
        (unicodedata.normalize("NFD", "Hạn chót"), "hạn chót"),
    ]
    for vao, mong_doi in cac_ca:
        ra = danh_gia_wer.chuan_hoa(vao)
        if ra != mong_doi:
            return f"{vao!r} -> {ra!r}, mong đợi {mong_doi!r}"


@ca
def wer_nhieu_file_thieu_mot_van_tinh_gop():
    tep = Path(danh_gia_wer.__file__)
    kq = subprocess.run([sys.executable, str(tep), "thu_nghiem", "khong_co_file_nay"],
                        capture_output=True, text=True, encoding="utf-8")
    if "TỔNG: 1 file" not in kq.stdout or "BỎ QUA" not in kq.stdout:
        return f"không tính WER gộp khi thiếu một file: {kq.stdout[-200:]} {kq.stderr[-200:]}"
    if kq.returncode == 0:
        return "mã thoát 0 dù có file bị bỏ qua"


# ----------------------------------------------------------------------
# 8. Đánh giá trên bộ dữ liệu tải về (tai_bo_danh_gia.py, danh_gia_bo.py)
# ----------------------------------------------------------------------
@ca
def doc_so_va_chuan_hoa_so_cong_bang():
    import danh_gia_bo as dg
    mong_doi = {"21": "hai mươi mốt", "105": "một trăm linh năm", "1005": "một nghìn không trăm linh năm",
                "2024": "hai nghìn không trăm hai mươi bốn", "20500": "hai mươi nghìn năm trăm",
                "15": "mười lăm", "0901": "không chín không một"}
    for so, chu in mong_doi.items():
        if dg.doc_so(so) != chu:
            return f"{so} -> {dg.doc_so(so)!r}, mong đợi {chu!r}"
    # Máy viết số, đáp án viết chữ (mỗi vùng đọc một kiểu): phải coi là giống nhau
    cung_nghia = [("20 tháng 10", "hai mươi tháng mười"), ("24 người", "hai mươi tư người"),
                  ("2,5%", "hai phẩy năm phần trăm"), ("1.000.000 đồng", "một triệu đồng"),
                  ("năm 2024", "năm hai ngàn không trăm hai mươi bốn"), ("105", "một trăm lẻ năm"),
                  ("35", "ba mươi lăm"), ("9h30", "chín giờ ba mươi"),
                  ("trên 10km", "trên mười ki lô mét"), ("nặng 5 kg", "nặng năm ki-lô-gam"),
                  ("đừng tưởng kỳ kèo", "đừng tưởng kì kèo"), ("hòa thuận thủy lợi", "hoà thuận thuỷ lợi"),
                  ("lý do", "lí do")]
    for a, b in cung_nghia:
        if dg.chuan_hoa_danh_gia(a) != dg.chuan_hoa_danh_gia(b):
            return f"{a!r} và {b!r} lẽ ra phải giống nhau sau chuẩn hóa"
    # Từ thường không được bị đổi nhầm ("năm" là năm học, "tư" là tư duy)
    if dg.chuan_hoa_danh_gia("năm nay tư duy tốt") != "năm nay tư duy tốt":
        return "chuẩn hóa số làm đổi nhầm chữ thường"
    # Nghe sai thật thì vẫn phải khác nhau
    for a, b in [("bất động sản", "cộng sản"), ("bả đi chợ", "bà đi chợ"), ("tầm nhìn", "tâm nhìn"),
                 ("cái km", "cái ki lô mét")]:   # "km" không đứng sau số thì không đổi
        if dg.chuan_hoa_danh_gia(a) == dg.chuan_hoa_danh_gia(b):
            return f"{a!r} và {b!r} khác nhau thật mà bị coi là giống"


@ca
def chon_mau_chia_deu_nhom_va_gioi_han_nguoi_noi():
    import tai_bo_danh_gia as tb
    cau_hinh = tb.CAC_BO["vimd"]
    cac_dong = []
    for i in range(60):
        mien = ["North", "Central", "South"][i % 3] if i < 45 else "North"
        cac_dong.append((i, {"region": mien, "speakerID": f"spk_{i // 4}", "text": "một hai ba bốn"}))
    cac_dong.append((99, {"region": "South", "speakerID": "x", "text": "ngắn"}))   # dưới 3 từ: bỏ
    chon = tb.chon_dong(cac_dong, cau_hinh, 9, [])
    dem_mien, dem_nguoi = Counter(d["region"] for _, d in chon), Counter(d["speakerID"] for _, d in chon)
    if len(chon) != 9 or max(dem_mien.values()) > 3 or max(dem_nguoi.values()) > 2:
        return f"chọn {len(chon)} đoạn, theo miền {dict(dem_mien)}, theo người {dict(dem_nguoi)}"
    if any(r == 99 for r, _ in chon):
        return "lấy cả đoạn quá ngắn"
    # Đã có sẵn 9 đoạn -> tăng lên 12 chỉ lấy thêm 3, không trùng đoạn cũ
    da_co = [{"row_idx": r, "nhom": d["region"], "nguon": d["speakerID"]} for r, d in chon]
    them = tb.chon_dong(cac_dong, cau_hinh, 12, da_co)
    if len(them) != 3 or {r for r, _ in them} & {r for r, _ in chon}:
        return f"tải bù sai: thêm {len(them)} đoạn"


@ca
def tai_bo_parquet_chia_deu_tach_am_thanh_va_tai_bu():
    import pyarrow as pa
    import pyarrow.parquet as pq
    import tai_bo_danh_gia as tb
    phuong_ngu = ["northern dialect", "central dialect", "southern dialect", "highland central", "minority"]
    so_dong = 60
    am_thanh = [b"RIFF" + bytes([i]) * 20 if i % 2 else b"ID3" + bytes([i]) * 20 for i in range(so_dong)]
    bang = pa.table({
        "transcription": [f"câu số {i} có đủ chữ" if i != 7 else "ngắn" for i in range(so_dong)],
        # Toàn bộ "minority" chỉ có 2 dòng: thiếu nhóm thì lượt 2 phải lấy bù từ nhóm khác
        "dialect": [phuong_ngu[i % 4] if i not in (3, 33) else phuong_ngu[4] for i in range(so_dong)],
        "audio": [{"bytes": am_thanh[i], "path": None} for i in range(so_dong)],
    })
    so_lan_tai = []
    goc = (tb.THU_MUC_BO, tb.tai_file)
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        tep_goc = tm / "goc.parquet"
        pq.write_table(bang, tep_goc, row_group_size=16)   # nhiều row group: đọc đúng nhóm

        def tai_gia(url, duong_dan, bao_tien_do=False):
            so_lan_tai.append(url)
            duong_dan.write_bytes(tep_goc.read_bytes())

        try:
            tb.THU_MUC_BO, tb.tai_file = tm / "bo", tai_gia
            tb._bo_nho_parquet.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                lan_1 = tb.tai_mot_bo("phuong_ngu", 20, 42)
                lan_2 = tb.tai_mot_bo("phuong_ngu", 25, 42)   # tải bù: không tải lại file gốc
        finally:
            tb.THU_MUC_BO, tb.tai_file = goc
            tb._bo_nho_parquet.clear()
        thu_muc = tm / "bo" / "phuong_ngu"
        sai_am_thanh = [m["id"] for m in lan_2
                        if (thu_muc / m["tep"]).read_bytes() != am_thanh[m["row_idx"]]
                        or Path(m["tep"]).suffix != (".wav" if m["row_idx"] % 2 else ".mp3")]
    dem = Counter(m["nhom"] for m in lan_1)
    if len(lan_1) != 20 or dem["minority"] != 2 or max(dem.values()) > 6:
        return f"chia theo phương ngữ sai: {dict(dem)}"
    if any(m["row_idx"] == 7 for m in lan_2):
        return "lấy cả đoạn quá ngắn"
    if len(so_lan_tai) != 1 or len(lan_2) != 25 or lan_2[:20] != lan_1:
        return f"tải bù sai: tải file gốc {len(so_lan_tai)} lần, {len(lan_2)} đoạn"
    if sai_am_thanh:
        return f"âm thanh tách ra không khớp dòng: {sai_am_thanh[:3]}"


@ca
def tai_bo_qua_danh_sach_chia_deu_theo_kenh():
    import tai_bo_danh_gia as tb
    kenh = ["vietcetera", "nguoitrongmuonnghe", "nguoiviethaingoai", "trinhlieu"]
    thu_muc_kenh = ["asr_segments_vietcetera_part06", "asr_segments_nguoitrongmuonnghe_part00",
                    "asr_dataset_nguoiviethaingoai", "asr_dataset_trinhlieu_part01"]
    danh_sach = [{"audio": f"audio/{thu_muc_kenh[i % 4]}/video{i // 3} ab_seg{i:03d}.wav",
                  "text": f"câu nói tự nhiên số {i}", "duration": 12.0, "source": f"video{i // 3}"}
                 for i in range(80)]
    cac_url = []

    def tai_gia(url, duong_dan, bao_tien_do=False):
        cac_url.append(url)
        noi_dung = json.dumps(danh_sach) if url.endswith("dev.json") else "RIFF"
        duong_dan.write_text(noi_dung, encoding="utf-8")

    goc = (tb.THU_MUC_BO, tb.tai_file)
    with tempfile.TemporaryDirectory() as tm:
        try:
            tb.THU_MUC_BO, tb.tai_file = Path(tm), tai_gia
            with contextlib.redirect_stdout(io.StringIO()):
                cac_muc = tb.tai_mot_bo("tu_nhien", 8, 42)
                tb.tai_mot_bo("tu_nhien", 10, 42)   # tải bù: không tải lại danh sách
        finally:
            tb.THU_MUC_BO, tb.tai_file = goc
    dem_kenh = Counter(m["nhom"] for m in cac_muc)
    if len(cac_muc) != 8 or set(dem_kenh) != set(kenh) or max(dem_kenh.values()) > 2:
        return f"chia theo kênh sai: {dict(dem_kenh)}"
    if max(Counter(m["nguon"] for m in cac_muc).values()) > 2:
        return "lấy quá 2 đoạn của cùng một video"
    if sum(u.endswith("dev.json") for u in cac_url) != 1:
        return "tải danh sách nhiều lần"
    link_am = [u for u in cac_url if u.endswith(".wav")]
    if not all(u.startswith("https://huggingface.co/datasets/thanhnew2001/VietSuperSpeech/resolve/main/audio/")
               and " " not in u for u in link_am):
        return f"link tải âm thanh sai: {link_am[:1]}"


@ca
def mang_cho_va_thu_lai_khi_bi_gioi_han():
    import urllib.error
    import tai_bo_danh_gia as tb

    def loi(ma, cho=None):
        return urllib.error.HTTPError("http://x", ma, "loi", {"Retry-After": cho} if cho else {}, None)

    def chay(cac_ket_qua):
        """Giả lập urlopen trả lần lượt các kết quả; trả (kết quả, các lần chờ, số lần gọi)."""
        con_lai, da_cho = list(cac_ket_qua), []
        goc = (tb.urllib.request.urlopen, tb.time.sleep)

        def urlopen_gia(yeu_cau, timeout):
            kq = con_lai.pop(0)
            if isinstance(kq, Exception):
                raise kq
            return kq
        try:
            tb.urllib.request.urlopen, tb.time.sleep = urlopen_gia, da_cho.append
            with contextlib.redirect_stdout(io.StringIO()):
                return tb.mo_url("http://x"), da_cho, len(cac_ket_qua) - len(con_lai)
        except tb.LoiTai as e:
            return e, da_cho, len(cac_ket_qua) - len(con_lai)
        finally:
            tb.urllib.request.urlopen, tb.time.sleep = goc

    kq, cho, _ = chay([loi(429, "7"), loi(503), "ok"])
    if kq != "ok" or cho != [7, tb.CHO_KHI_LOI[1]]:
        return f"429/503 phải chờ rồi thử lại (theo Retry-After): {kq}, chờ {cho}"
    kq, cho, so_lan = chay([loi(404), "ok"])
    if not isinstance(kq, tb.LoiTai) or so_lan != 1:
        return "lỗi 404 không được thử lại"
    kq, _, so_lan = chay([loi(403), "ok"])
    if not isinstance(kq, tb.LoiTai) or "HF_TOKEN" not in str(kq):
        return "lỗi 403 phải nhắc kiểm tra token"
    kq, cho, so_lan = chay([loi(429)] * (len(tb.CHO_KHI_LOI) + 1))
    if not isinstance(kq, tb.LoiTai) or len(cho) != len(tb.CHO_KHI_LOI):
        return "thử lại mãi không dừng"


@ca
def danh_gia_bo_do_wer_bao_cao_va_lam_tiep():
    import danh_gia_bo as dg
    cac_doan = [doan(chuoi_tu(0.0, "Bạn Lan làm 20 slide.")),
                doan(chuoi_tu(3.0, "Hãy subscribe cho kênh Ghiền Mì Gõ"))]   # bị [LOẠI]
    so_lan_tai_model = []

    def model_gia(*a, **k):
        so_lan_tai_model.append(1)
        return ModelGia(cac_doan)

    goc = (dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO)
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        thu_muc = tm / "bo" / "thu"
        (thu_muc / "audio").mkdir(parents=True)
        cac_muc = []
        for i in range(2):
            ghi_wav(thu_muc / "audio" / f"{i}.wav", tieng_noi_gia(4))
            cac_muc.append({"id": f"thu_{i}", "tep": f"audio/{i}.wav", "nhom": "North", "nguon": "a",
                            "row_idx": i, "text": "bạn lan làm hai mươi slide"})
        (thu_muc / "nhan.json").write_text(json.dumps(cac_muc, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = tm / "bo", tm / "bao_cao"
            asr.WhisperModel = model_gia
            for _ in range(2):   # lần 2: đã có kết quả, không được tải model lại
                sys.argv = ["danh_gia_bo.py"]
                with contextlib.redirect_stdout(io.StringIO()):
                    dg.main()
        finally:
            dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = goc
        bao_cao = (tm / "bao_cao" / f"thu__{asr.TEN_MODEL}.txt").read_text(encoding="utf-8")
    if len(so_lan_tai_model) != 1:
        return f"tải model {len(so_lan_tai_model)} lần (lần chạy lại phải dùng kết quả đã lưu)"
    if "WER   0.0%" not in bao_cao:
        return "số viết bằng chữ số vẫn bị tính là sai:\n" + bao_cao[:300]
    if "CẮT BỎ: 2" not in bao_cao or "Ghiền Mì Gõ" not in bao_cao:
        return "báo cáo không liệt kê đoạn bị bộ lọc [LOẠI]"


if __name__ == "__main__":
    so_dat = 0
    goc = (asr.THU_MUC_KET_QUA, asr.WhisperModel, list(sys.argv))
    for ham in CAC_CA:
        try:
            loi = ham()
        except Exception as e:  # ca lỗi bất ngờ cũng tính là KHÔNG ĐẠT
            loi = f"{type(e).__name__}: {e}"
        finally:
            asr.THU_MUC_KET_QUA, asr.WhisperModel, sys.argv = goc[0], goc[1], list(goc[2])
        if loi:
            print(f"KHÔNG ĐẠT | {ham.__name__}: {loi}")
        else:
            so_dat += 1
            print(f"ĐẠT       | {ham.__name__}")
    print(f"\nTổng kết: {so_dat}/{len(CAC_CA)} ca ĐẠT")
    sys.exit(0 if so_dat == len(CAC_CA) else 1)
