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
