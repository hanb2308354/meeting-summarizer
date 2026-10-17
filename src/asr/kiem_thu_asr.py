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
# Các ca dưới dùng âm thanh giả mà VAD thật không nhận ra là tiếng nói, nên mặc định chạy chế độ
# cả file; chế độ từng lượt có ca kiểm thử riêng (truyền tung_luot=True)
TUNG_LUOT_GOC = asr.TUNG_LUOT_MAC_DINH
asr.TUNG_LUOT_MAC_DINH = False
# Kiểm thử không phụ thuộc máy có sẵn model PhoWhisper hay chưa: coi như chưa có (chế độ chính xác
# tự lùi về medium); ca kiểm thử chế độ tự tạo thư mục model giả
asr.MODEL_CHINH_XAC = Path(tempfile.gettempdir()) / "khong_co_model_phowhisper"
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


def chay_nhan_dang(cac_doan, goi_y=asr.GOI_Y_MAC_DINH):
    cac_tu, so_loai = asr.nhan_dang(ModelGia(cac_doan), np.zeros(SR, dtype=np.float32), goi_y=goi_y)
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
    cau, so_loai = chay_nhan_dang(cac_doan, goi_y="day_du")
    if cau != ["Bạn Lan làm phần slide nha."] or so_loai != 6:
        return f"còn lại {cau}, loại {so_loai}"
    # Không gợi ý gì (chế độ chính xác): model không thể đọc lại gợi ý, nên không loại theo luật đó
    # (câu liệt kê / câu giống câu mở đầu được giữ); các luật khác vẫn chạy
    cau, so_loai = chay_nhan_dang(cac_doan, goi_y="khong")
    if so_loai != 4 or "deadline, hạn chót, project, meeting, slide" not in cau:
        return f"không gợi ý mà vẫn lọc theo gợi ý: còn {cau}, loại {so_loai}"


@ca
def loai_doan_chep_lai_mot_phan_cau_mo_dau():
    # Đo trên bộ đánh giá: đoạn điện thoại khó nghe, model ghi "Còn một số từ tiếng Anh."
    cau, so_loai = chay_nhan_dang([
        doan(chuoi_tu(0.0, "Còn một số từ tiếng Anh.")),
        doan(chuoi_tu(3.0, "Cuộc họp nhóm có ba người, Lan làm slide.")),   # câu thật: giữ
        doan(chuoi_tu(8.0, "Mình dùng một số tool mới cho project.")),       # câu thật: giữ
    ])
    if so_loai != 1 or len(cau) != 2 or "tiếng Anh" in " ".join(cau):
        return f"loại {so_loai}, còn {cau}"


@ca
def che_do_goi_y_truyen_dung_tham_so():
    da_goi = []

    class ModelGhi(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_goi.append((tham_so.get("initial_prompt"), tham_so.get("hotwords")))
            return super().transcribe(am_thanh, **tham_so)

    model = ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))])
    asr.nhan_dang(model, np.zeros(SR, dtype=np.float32))   # mặc định: chỉ câu mở đầu
    for goi_y in ("day_du", "tu_khoa", "cau_mo_dau", "khong"):
        asr.nhan_dang(model, np.zeros(SR, dtype=np.float32), goi_y=goi_y)
    mong_doi = [(True, False), (True, True), (False, True), (True, False), (False, False)]
    thuc_te = [(p is not None, h is not None) for p, h in da_goi]
    if thuc_te != mong_doi:
        return f"(câu mở đầu, từ khóa) = {thuc_te}"
    nhiet_do = []

    class ModelNhietDo(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            nhiet_do.append(tham_so.get("temperature", "mặc định"))
            return super().transcribe(am_thanh, **tham_so)

    m = ModelNhietDo([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))])
    asr.nhan_dang(m, np.zeros(SR, dtype=np.float32))                  # mặc định: giới hạn
    asr.nhan_dang(m, np.zeros(SR, dtype=np.float32), nhiet_do=None)   # như faster-whisper gốc
    if nhiet_do != [[0.0, 0.2, 0.4], "mặc định"]:
        return f"nhiệt độ truyền sai: {nhiet_do}"
    try:
        asr.nhan_dang(m, np.zeros(SR, dtype=np.float32), goi_y=True)
        return "goi_y sai kiểu phải báo lỗi"
    except ValueError:
        pass


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
        cau, so_loai = chay_nhan_dang([doan(chuoi_tu(0, cau_that))], goi_y="day_du")
        if so_loai or cau != [cau_that]:
            return f"loại nhầm câu liệt kê thật {cau_that!r}"
        _, so_loai = chay_nhan_dang([doan(chuoi_tu(0, cau_that), do_tin_cay=-1.5)], goi_y="day_du")
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
                giu_rieng = tb.tai_mot_bo("phuong_ngu", 20, 2026, giu_rieng=True)
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
    trung = {m["row_idx"] for m in giu_rieng} & {m["row_idx"] for m in lan_2}
    if len(giu_rieng) != 20 or trung or len(so_lan_tai) != 1:
        return f"bộ giữ riêng sai: {len(giu_rieng)} đoạn, trùng {sorted(trung)}, tải file gốc {len(so_lan_tai)} lần"
    if not all(m["id"].startswith("phuong_ngu_giu_rieng_") for m in giu_rieng):
        return f"tên đoạn bộ giữ riêng sai: {giu_rieng[0]['id']}"


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
        # Cấu hình mặc định = cấu hình của chuyen_giong_noi.py (chỉ câu mở đầu, giới hạn thử lại)
        bao_cao = (tm / "bao_cao" / f"thu__{asr.TEN_MODEL}_chi_cau_mo_dau_gioi_han_thu_lai.txt"
                   ).read_text(encoding="utf-8")
    if len(so_lan_tai_model) != 1:
        return f"tải model {len(so_lan_tai_model)} lần (lần chạy lại phải dùng kết quả đã lưu)"
    if "WER   0.0%" not in bao_cao:
        return "số viết bằng chữ số vẫn bị tính là sai:\n" + bao_cao[:300]
    if "CẮT BỎ: 2" not in bao_cao or "Ghiền Mì Gõ" not in bao_cao:
        return "báo cáo không liệt kê đoạn bị bộ lọc [LOẠI]"


@ca
def so_sanh_cau_hinh_va_bao_doan_bi_ket():
    import danh_gia_bo as dg
    cac_muc = [{"id": f"d{i}", "tep": f"audio/{i}.wav", "nhom": "Phone Call" if i < 3 else "Meeting",
                "nguon": str(i), "row_idx": i, "text": "anh bị người ta mạo danh số điện thoại"}
               for i in range(6)]
    dung = {"du_doan": "anh bị người ta mạo danh số điện thoại", "bi_loai": [], "do_dai": 5.0, "thoi_gian": 20.0}
    bia = dict(dung, du_doan="cảm ơn mọi người hẹn gặp lại", thoi_gian=300.0)   # bịa + kẹt
    a = {m["id"]: dict(dung) for m in cac_muc}
    a["d0"] = bia
    b = {m["id"]: dict(dung) for m in cac_muc[:5]}   # cấu hình b chưa chạy xong d5
    goc = (dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO)
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        thu_muc = tm / "bo" / "hop"
        thu_muc.mkdir(parents=True)
        (thu_muc / "nhan.json").write_text(json.dumps(cac_muc, ensure_ascii=False), encoding="utf-8")
        (thu_muc / "ket_qua__a.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        (thu_muc / "ket_qua__b.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = tm / "bo", tm / "bao_cao"
            sys.argv = ["danh_gia_bo.py", "--so-sanh", "a", "b", "khong_co"]
            with contextlib.redirect_stdout(io.StringIO()):
                dg.main()
            so_sanh = (tm / "bao_cao" / "hop__so_sanh.txt").read_text(encoding="utf-8")
            bao_cao_a = dg.viet_bao_cao("hop", "a", dg.phan_tich(cac_muc, a))
        finally:
            dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = goc
    if "Trên 5 đoạn" not in so_sanh or "chưa chạy cấu hình khong_co" not in so_sanh:
        return "so sánh phải chỉ tính các đoạn mọi cấu hình đều đã chạy:\n" + so_sanh[:400]
    if "lệch >= 20 điểm): 1" not in so_sanh or "hẹn gặp lại" not in so_sanh:
        return "không chỉ ra đoạn khác biệt:\n" + so_sanh
    if "LÂU BẤT THƯỜNG" not in bao_cao_a or "d0 (Phone Call): 300s" not in bao_cao_a:
        return "không báo đoạn bị kẹt:\n" + bao_cao_a[-500:]


@ca
def kiem_bang_sua_loi_phan_biet_sua_dung_sua_sai():
    import danh_gia_bo as dg
    cac_muc = [
        {"id": "a", "tep": "a.wav", "nhom": "x", "nguon": "a", "row_idx": 0,
         "text": "bạn lan làm phần frontend trước thứ sáu"},
        {"id": "b", "tep": "b.wav", "nhom": "x", "nguon": "b", "row_idx": 1,
         "text": "bạn lan làm phần backend"},
    ]
    kq = {"a": {"du_doan": "Bạn Lan làm phần phôn thên trước thứ sáu.", "bi_loai": [], "do_dai": 3, "thoi_gian": 9},
          "b": {"du_doan": "Bạn Lan làm phần backend.", "bi_loai": [], "do_dai": 3, "thoi_gian": 9}}
    goc = dg.THU_MUC_BO
    with tempfile.TemporaryDirectory() as tm:
        thu_muc = Path(tm) / "bo"
        thu_muc.mkdir()
        (thu_muc / "nhan.json").write_text(json.dumps(cac_muc, ensure_ascii=False), encoding="utf-8")
        (thu_muc / "ket_qua__thu.json").write_text(json.dumps(kq, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO = Path(tm)
            bao_cao = dg.kiem_sua_loi("bo", "thu")
        finally:
            dg.THU_MUC_BO = goc
    if "sửa đúng 1, sửa SAI 0" not in bao_cao or "frontend" not in bao_cao:
        return "không đo đúng tác dụng bảng sửa lỗi:\n" + bao_cao


@ca
def ghep_file_dai_va_so_voi_doan_ngan():
    import danh_gia_bo as dg
    import ghep_file_dai as gh
    cau_hinh = f"{asr.TEN_MODEL}_chi_cau_mo_dau_gioi_han_thu_lai"
    goc = (gh.THU_MUC_BO, dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO)
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        nguon = tm / "bo" / "hop"
        (nguon / "audio").mkdir(parents=True)
        cac_muc, ket_ngan = [], {}
        for i in range(6):
            ghi_wav(nguon / "audio" / f"{i}.wav", tieng_noi_gia(3))
            cac_muc.append({"id": f"hop_{i}", "tep": f"audio/{i}.wav", "nhom": "x", "nguon": str(i),
                            "row_idx": i, "text": "bạn lan làm slide"})
            ket_ngan[f"hop_{i}"] = {"du_doan": "Bạn Lan làm slide.", "bi_loai": [], "do_dai": 3, "thoi_gian": 9}
        (nguon / "nhan.json").write_text(json.dumps(cac_muc, ensure_ascii=False), encoding="utf-8")
        (nguon / f"ket_qua__{cau_hinh}.json").write_text(json.dumps(ket_ngan, ensure_ascii=False), encoding="utf-8")
        try:
            gh.THU_MUC_BO = dg.THU_MUC_BO = tm / "bo"
            dg.THU_MUC_BAO_CAO = tm / "bao_cao"
            with contextlib.redirect_stdout(io.StringIO()):
                ghep = gh.ghep("hop", so_file=2, so_phut=0.12, hat_giong=1)   # ~7 giây mỗi file
                asr.WhisperModel = lambda *a, **k: ModelGia([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))])
                sys.argv = ["danh_gia_bo.py", "hop_dai"]
                dg.main()
            bao_cao = (tm / "bao_cao" / f"hop_dai__{cau_hinh}.txt").read_text(encoding="utf-8")
            with wave.open(str(tm / "bo" / "hop_dai" / ghep[0]["tep"])) as f:
                giay = f.getnframes() / f.getframerate()
        finally:
            gh.THU_MUC_BO, dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = goc
    if len(ghep) != 2 or len(ghep[0]["tu_doan"]) < 2:
        return f"ghép sai: {[(g['id'], g['tu_doan']) for g in ghep]}"
    if ghep[0]["text"] != " ".join(["bạn lan làm slide"] * len(ghep[0]["tu_doan"])):
        return "lời gốc file dài không phải lời các đoạn nối theo thứ tự"
    if not 6.0 <= giay <= 6.0 + 10 * (len(ghep[0]["tu_doan"]) - 1) + 0.1:
        return f"độ dài file dài sai: {giay:.1f} giây"
    if "SO VỚI NGHE TỪNG ĐOẠN NGẮN" not in bao_cao or "nghe từng đoạn ngắn 0.0%" not in bao_cao:
        return "báo cáo không so với đoạn ngắn:\n" + bao_cao[-600:]


@ca
def che_do_theo_khuc_dung_bo_nhan_dang_theo_lo():
    from faster_whisper import BatchedInferencePipeline
    da_goi = []

    class BoTheoLoGia:
        def __init__(self, model):
            self.model = model

        def transcribe(self, am_thanh, **tham_so):
            # Tham số phải hợp lệ với BatchedInferencePipeline thật
            inspect.signature(BatchedInferencePipeline.transcribe).bind(None, am_thanh, **tham_so)
            da_goi.append(tham_so)
            return iter([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))]), None

    goc = asr.BatchedInferencePipeline
    try:
        asr.BatchedInferencePipeline = BoTheoLoGia
        cac_tu, _ = asr.nhan_dang(ModelGia([]), np.zeros(SR, dtype=np.float32), theo_khuc=True)
    finally:
        asr.BatchedInferencePipeline = goc
    if [c["text"] for c in asr.tach_cau(cac_tu)] != ["Bạn Lan làm slide."]:
        return "chế độ theo khúc không ra chữ"
    if not da_goi or da_goi[0].get("batch_size") != asr.SO_KHUC_MOI_LO or not da_goi[0].get("word_timestamps"):
        return f"tham số chế độ theo khúc sai: {da_goi}"


@ca
def che_do_tung_luot_cat_theo_vad_va_doi_moc_thoi_gian():
    da_nghe = []

    cac_cau = iter(["Bạn Lan làm slide.", "Tuấn làm phần API."])

    class ModelGhiLuot(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_nghe.append((len(am_thanh) / SR, tham_so.get("vad_filter")))
            self.cac_doan = [doan(chuoi_tu(0.2, next(cac_cau)))]
            return super().transcribe(am_thanh, **tham_so)

    goc = asr.cat_luot_noi
    try:
        # Hai lượt nói: 0-3 giây và 10-14 giây của file
        asr.cat_luot_noi = lambda song_am: [(0, 3 * SR), (10 * SR, 14 * SR)]
        cac_tu, _ = asr.nhan_dang(ModelGhiLuot([]), np.zeros(20 * SR, dtype=np.float32), tung_luot=True)
    finally:
        asr.cat_luot_noi = goc
    cau = asr.tach_cau(cac_tu)
    if da_nghe != [(3.0, False), (4.0, False)]:
        return f"phải nghe riêng từng lượt, không chạy VAD lần nữa trong lượt: {da_nghe}"
    if [c["start"] for c in cau] != [0.2, 10.2]:
        return f"mốc thời gian lượt sau phải cộng thêm vị trí lượt: {[c['start'] for c in cau]}"
    # VAD thật: file im lặng thì không có lượt nào
    if asr.cat_luot_noi(np.zeros(5 * SR, dtype=np.float32)):
        return "file im lặng mà VAD vẫn cắt ra lượt nói"


@ca
def nhat_ky_ghi_chi_tiet_tung_doan_va_luot():
    nhat_ky = []
    cac_doan = [doan(chuoi_tu(0.0, "Bạn Lan làm slide.")),
                doan(chuoi_tu(3.0, "Cảm ơn các bạn đã theo dõi"), khong_co_tieng=0.9, do_tin_cay=-1.2)]
    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda song_am: [(0, 6 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            asr.nhan_dang(ModelGia(cac_doan), np.zeros(7 * SR, dtype=np.float32), tung_luot=True, nhat_ky=nhat_ky)
    finally:
        asr.cat_luot_noi = goc
    if nhat_ky[0] != {"luot": [0.0, 6.0]}:
        return f"không ghi lượt VAD: {nhat_ky[:1]}"
    doan_ghi = [c for c in nhat_ky if "text" in c]
    if len(doan_ghi) != 2 or doan_ghi[0]["loai"] or not doan_ghi[1]["loai"]:
        return f"không ghi đủ đoạn giữ / đoạn bị loại: {doan_ghi}"
    if doan_ghi[1]["khong_co_tieng"] != 0.9 or doan_ghi[1]["do_tin_cay"] != -1.2:
        return f"không ghi chỉ số model: {doan_ghi[1]}"


@ca
def khoang_tin_cay_phan_biet_that_va_ngau_nhien():
    import danh_gia_bo as dg
    # B ít lỗi hơn A ở mọi đoạn -> tốt hơn thật
    chenh, duoi, tren = dg.khoang_tin_cay([(10, 3, 1)] * 30)
    if not (abs(chenh + 0.2) < 1e-9 and tren < 0):
        return f"B tốt hơn ở mọi đoạn mà khoảng tin cậy không dưới 0: {chenh, duoi, tren}"
    # Hơn ở nửa này, thua ở nửa kia -> chưa chắc
    _, duoi, tren = dg.khoang_tin_cay([(10, 3, 1)] * 15 + [(10, 1, 3)] * 15)
    if not duoi < 0 < tren:
        return f"chênh lệch ngẫu nhiên mà khoảng tin cậy không chứa 0: {duoi, tren}"
    cac_muc = [{"id": f"d{i}", "text": "bạn lan làm slide", "nhom": "x"} for i in range(30)]
    a = {f"d{i}": {"du_doan": "bạn lan làm slai"} for i in range(30)}
    b = {f"d{i}": {"du_doan": "bạn lan làm slide"} for i in range(30)}
    bao_cao = "\n".join(dg.khac_biet_that_hay_ngau_nhien(cac_muc, {"a": a, "b": b}))
    if "TỐT HƠN THẬT" not in bao_cao or "tốt hơn ở 30 đoạn" not in bao_cao:
        return "báo cáo so sánh không kết luận đúng:\n" + bao_cao


@ca
def chi_doan_chay_lai_mot_doan_va_khong_ghi_de_ket_qua():
    import danh_gia_bo as dg
    cau_hinh = f"{asr.TEN_MODEL}_chi_cau_mo_dau_gioi_han_thu_lai"
    goc = (dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO)
    cac_doan = [doan(chuoi_tu(0.0, "Bạn Lan làm slai."), khong_co_tieng=0.8, do_tin_cay=-0.9)]
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        thu_muc = tm / "bo" / "hop"
        (thu_muc / "audio").mkdir(parents=True)
        ghi_wav(thu_muc / "audio" / "0.wav", tieng_noi_gia(3))
        muc = {"id": "hop_0", "tep": "audio/0.wav", "nhom": "x", "nguon": "0", "row_idx": 0,
               "text": "bạn lan làm slide cho nhóm"}
        (thu_muc / "nhan.json").write_text(json.dumps([muc], ensure_ascii=False), encoding="utf-8")
        cu = {"hop_0": {"du_doan": "Bạn Lan làm slide cho nhóm.", "bi_loai": [], "do_dai": 3, "thoi_gian": 9}}
        tep_kq = thu_muc / f"ket_qua__{cau_hinh}.json"
        tep_kq.write_text(json.dumps(cu, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = tm / "bo", tm / "bao_cao"
            asr.WhisperModel = lambda *a, **k: ModelGia(cac_doan)
            sys.argv = ["danh_gia_bo.py", "--chi-doan", "hop_0", "khong_co"]
            with contextlib.redirect_stdout(io.StringIO()) as ra:
                dg.main()
            bao_cao = (tm / "bao_cao" / f"hop_0__{cau_hinh}__chi_tiet.txt").read_text(encoding="utf-8")
            sau = json.loads(tep_kq.read_text(encoding="utf-8"))
        finally:
            dg.THU_MUC_BO, dg.THU_MUC_BAO_CAO = goc
    if sau != cu:
        return "--chi-doan đã ghi đè kết quả đã lưu"
    for can in ("[nghe nhầm] slide  ->  slai", "[bỏ sót]    cho nhóm", "trước đó (cùng cấu hình): WER 0.0%",
                "nghi bịa", "CÁC ĐOẠN MODEL TRẢ VỀ: 1"):
        if can not in bao_cao:
            return f"báo cáo chẩn đoán thiếu '{can}':\n" + bao_cao
    if "Không tìm thấy đoạn: khong_co" not in ra.getvalue():
        return "không báo id không tồn tại"


@ca
def tung_luot_nghe_lai_luot_hong():
    """Lượt 10 giây chỉ ra câu kết video -> nhận dạng lại; lượt bình thường không bị nghe lại."""
    da_goi = []
    cau_that = "Bạn đi ra và bạn làm chuyên viên thì các bạn biết rằng là ở miền tây mình sẽ bị rất nhiều"

    class ModelHongKhiCoGoiY(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            giay = len(am_thanh) / SR
            da_goi.append((giay, tham_so.get("initial_prompt") is not None))
            if giay == 10.0 and tham_so.get("initial_prompt"):
                self.cac_doan = [doan(chuoi_tu(4.0, "Cảm ơn các bạn."), khong_co_tieng=0.62, do_tin_cay=-0.8)]
            elif giay == 10.0:
                self.cac_doan = [doan(chuoi_tu(0.0, cau_that, buoc=0.45))]
            else:
                self.cac_doan = [doan(chuoi_tu(0.0, "Chúng ta sẽ xem một tháng làm bao nhiêu video."))]
            return super().transcribe(am_thanh, **tham_so)

    nhat_ky = []
    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda song_am: [(0, 10 * SR), (11 * SR, 15 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            cac_tu, _ = asr.nhan_dang(ModelHongKhiCoGoiY([]), np.zeros(16 * SR, dtype=np.float32),
                                      tung_luot=True, nhat_ky=nhat_ky)
    finally:
        asr.cat_luot_noi = goc
    van_ban = " ".join(c["text"] for c in asr.tach_cau(cac_tu))
    if "miền tây" not in van_ban or "Cảm ơn các bạn" in van_ban:
        return f"lượt hỏng không được nhận dạng lại: {van_ban}"
    if da_goi != [(10.0, True), (10.0, False), (4.0, True)]:
        return f"phải nghe lại đúng lượt hỏng (bỏ gợi ý), lượt tốt chỉ nghe 1 lần: {da_goi}"
    if {"thu_lai": "chọn", "cach": "bỏ câu mở đầu"} not in nhat_ky:
        return f"nhật ký không ghi lần nghe lại: {nhat_ky}"


@ca
def nghe_kem_luot_ben_canh_chi_giu_chu_trong_luot():
    # Cách 1 (bỏ gợi ý) vẫn hỏng -> cách 2 nghe cả 3 lượt, chỉ giữ chữ của lượt giữa
    def nghe_doan(tu, den, **doi):
        if (tu, den) == (0, 20 * SR):
            return [doan(chuoi_tu(1.0, "lượt một") + chuoi_tu(6.0, "đây là lượt giữa nói khá dài nha")
                         + chuoi_tu(16.0, "lượt ba"))]
        return [doan(chuoi_tu(tu / SR + 1, "Cảm ơn."))]

    cac_luot = [(0, 4 * SR), (5 * SR, 10 * SR), (15 * SR, 20 * SR)]
    ket_qua = asr.nghe_lai_luot(nghe_doan, cac_luot, 1, nghe_doan(5 * SR, 10 * SR))
    chu = " ".join(d.text.strip() for d in ket_qua)
    if chu != "đây là lượt giữa nói khá dài nha":
        return f"phải chỉ giữ chữ nằm trong lượt giữa: {chu!r}"


@ca
def file_dai_chia_loi_ve_tung_doan_ghep():
    import danh_gia_bo as dg
    goc = dg.THU_MUC_BO
    with tempfile.TemporaryDirectory() as tm:
        thu_muc = Path(tm) / "hop"
        thu_muc.mkdir()
        nhan = [{"id": "a", "text": "bạn lan làm slide"}, {"id": "b", "text": "tuấn làm phần api"},
                {"id": "c", "text": "nộp trước thứ sáu"}]
        (thu_muc / "nhan.json").write_text(json.dumps(nhan, ensure_ascii=False), encoding="utf-8")
        muc = {"id": "hop_dai_01", "tu_doan": ["a", "b", "c"], "nguon_bo": "hop",
               "text": "bạn lan làm slide tuấn làm phần api nộp trước thứ sáu", "nhom": "file_dai"}
        try:
            dg.THU_MUC_BO = Path(tm)
            # sai "slide" (đoạn a), mất cả đoạn b, thừa "nha" sau đoạn c
            chia = dg.loi_theo_doan_ghep(muc, "bạn lan làm slai nộp trước thứ sáu nha")
            cac_muc = [dict(muc, id=f"f{i}") for i in range(10)]
            a = {f"f{i}": {"du_doan": "bạn lan làm slai nộp trước thứ sáu nha"} for i in range(10)}
            b = {f"f{i}": {"du_doan": "bạn lan làm slide tuấn làm phần api nộp trước thứ sáu"} for i in range(10)}
            bao_cao = "\n".join(dg.khac_biet_that_hay_ngau_nhien(cac_muc, {"a": a, "b": b}))
        finally:
            dg.THU_MUC_BO = goc
    if chia != [(4, 1), (4, 4), (4, 1)]:
        return f"chia lỗi sai: {chia}"
    if "lấy mẫu trên 30 đoạn ngắn đã ghép thành 10 file" not in bao_cao or "bằng nhau 0" not in bao_cao:
        return "so sánh file dài không lấy mẫu theo đoạn ghép:\n" + bao_cao


@ca
def mac_dinh_la_tung_luot_va_ten_model_tu_thu_muc():
    import danh_gia_bo as dg
    if TUNG_LUOT_GOC is not True:
        return "chế độ mặc định phải là từng lượt (đã đo tốt hơn thật ở file dài)"
    da_goi = []
    goc = (asr.nhan_dang, asr.TUNG_LUOT_MAC_DINH)
    try:
        asr.TUNG_LUOT_MAC_DINH = True
        asr.nhan_dang = lambda model, song_am, **k: (da_goi.append(k), ([], 0))[1]
        with tempfile.TemporaryDirectory() as tm:
            ghi_wav(Path(tm) / "hop.wav", tieng_noi_gia(3))
            with contextlib.redirect_stdout(io.StringIO()):
                chay_main(Path(tm), [], [str(Path(tm) / "hop.wav")])
    finally:
        asr.nhan_dang, asr.TUNG_LUOT_MAC_DINH = goc
    if [k.get("tung_luot") for k in da_goi] != [True]:
        return f"chuyen_giong_noi.py phải nhận dạng từng lượt: {da_goi}"
    for model, ten in (("medium", "medium"), ("models/phowhisper-medium-ct2", "phowhisper-medium-ct2"),
                       ("C:\\x\\models\\PhoWhisper-Medium-ct2", "phowhisper-medium-ct2")):
        if dg.ten_model(model) != ten:
            return f"tên model {model!r} -> {dg.ten_model(model)!r}, cần {ten!r}"


@ca
def khong_moc_thoi_gian_truyen_without_timestamps():
    da_goi = []

    class ModelGhi(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_goi.append(tham_so.get("without_timestamps"))
            return super().transcribe(am_thanh, **tham_so)

    with contextlib.redirect_stdout(io.StringIO()):
        asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))]), np.zeros(SR, dtype=np.float32))
        asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))]), np.zeros(SR, dtype=np.float32),
                      khong_moc_thoi_gian=True)
    if da_goi != [False, True]:
        return f"without_timestamps truyền sai: {da_goi}"


@ca
def loai_cau_bia_toc_do_noi_bat_kha_thi():
    that = doan(chuoi_tu(0.0, "đề nghị các cơ quan soạn thảo cần có giải pháp khắc phục"))
    bia = doan([tu(6.62, w) for w in "một số khán giả đã tham gia vào đêm thi đấu".split()])
    bia = dataclasses.replace(bia, start=6.68, end=6.76)
    da = dataclasses.replace(doan([tu(7.0, "Dạ.")]), start=7.0, end=7.02)   # 1 từ: không xét
    with contextlib.redirect_stdout(io.StringIO()):
        cac_tu, so_loai = asr.nhan_dang(ModelGia([that, bia, da]), np.zeros(SR, dtype=np.float32))
    van_ban = " ".join(c["text"] for c in asr.tach_cau(cac_tu))
    if "khán giả" in van_ban or "soạn thảo" not in van_ban or "Dạ" not in van_ban or so_loai != 1:
        return f"lọc theo tốc độ nói sai: {van_ban!r}, loại {so_loai}"


@ca
def loc_lai_ket_qua_cu_khong_chay_model():
    import danh_gia_bo as dg
    goc = dg.THU_MUC_BO
    chi_tiet = [{"start": 0.0, "end": 6.62, "text": "đề nghị các cơ quan soạn thảo", "do_tin_cay": 0.0,
                 "khong_co_tieng": 0.0, "ty_le_nen": 1.1, "nhiet_do": 0.0, "loai": None},
                {"start": 6.68, "end": 6.76, "text": "một số khán giả đã tham gia", "do_tin_cay": -0.56,
                 "khong_co_tieng": 0.0, "ty_le_nen": 0.9, "nhiet_do": 0.0, "loai": None}]
    kq = {"a": {"du_doan": "đề nghị các cơ quan soạn thảo một số khán giả đã tham gia", "bi_loai": [],
                "do_dai": 6.8, "thoi_gian": 9, "chi_tiet": chi_tiet},
          "b": {"du_doan": "cũ", "bi_loai": [], "do_dai": 3, "thoi_gian": 9}}
    with tempfile.TemporaryDirectory() as tm:
        thu_muc = Path(tm) / "bo"
        thu_muc.mkdir()
        (thu_muc / "ket_qua__x.json").write_text(json.dumps(kq, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO = Path(tm)
            ten, so_bo, thieu = dg.loc_lai("bo", "x")
            moi = json.loads((thu_muc / f"ket_qua__{ten}.json").read_text(encoding="utf-8"))
        finally:
            dg.THU_MUC_BO = goc
    if ten != "x_loc_lai" or so_bo != 1 or thieu != 1:
        return f"đếm sai: {ten}, bỏ {so_bo}, thiếu chi tiết {thieu}"
    if moi["a"]["du_doan"] != "đề nghị các cơ quan soạn thảo" or moi["b"]["du_doan"] != "cũ":
        return f"chấm lại sai: {moi}"


@ca
def tung_luot_gioi_han_so_token_theo_do_dai():
    da_goi = []

    class ModelGhi(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_goi.append(tham_so.get("max_new_tokens"))
            return super().transcribe(am_thanh, **tham_so)

    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda song_am: [(0, 4 * SR), (5 * SR, 30 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide nha mọi người ơi."))]),
                          np.zeros(31 * SR, dtype=np.float32), tung_luot=True)
    finally:
        asr.cat_luot_noi = goc
    if da_goi[:2] != [4 * asr.TOKEN_MOI_GIAY + asr.TOKEN_CONG_THEM, asr.TOKEN_TOI_DA]:
        return f"giới hạn token sai: {da_goi}"
    # Giới hạn tự chọn (đo tốc độ PhoWhisper): 12 x 4 giây + 10
    da_goi.clear()
    try:
        asr.cat_luot_noi = lambda song_am: [(0, 4 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide nha mọi người ơi."))]),
                          np.zeros(5 * SR, dtype=np.float32), tung_luot=True, token_moi_giay=12, token_cong_them=10)
    finally:
        asr.cat_luot_noi = goc
    if da_goi[:1] != [58]:
        return f"giới hạn token tự chọn sai: {da_goi}"


@ca
def kieu_tinh_vao_ten_cau_hinh_va_truyen_cho_model():
    import danh_gia_bo as dg
    from types import SimpleNamespace
    co_ban = dict(model="medium", goi_y="cau_mo_dau", thu_lai="gioi_han", theo_khuc=False, tung_luot=True,
                  khong_moc_thoi_gian=False, dem_im_lang=False, beam=5, khong_tien_xu_ly=False, loc_nhieu=False,
                  token_moi_giay=asr.TOKEN_MOI_GIAY, token_cong_them=asr.TOKEN_CONG_THEM, so_luong=asr.SO_LUONG_CPU,
                  khong_nghe_lai=False, khong_cat_ngoai=False, gop_luot=0)
    ten_int8 = dg.ten_cau_hinh(SimpleNamespace(**co_ban, kieu_tinh="int8"))
    ten_f32 = dg.ten_cau_hinh(SimpleNamespace(**co_ban, kieu_tinh="float32"))
    if ten_int8 != "medium_chi_cau_mo_dau_gioi_han_thu_lai_tung_luot" or ten_f32 != "medium_chi_cau_mo_dau_float32_gioi_han_thu_lai_tung_luot":
        return f"tên cấu hình sai: {ten_int8}, {ten_f32}"
    da_tao = []
    with tempfile.TemporaryDirectory() as tm:
        ghi_wav(Path(tm) / "hop.wav", tieng_noi_gia(2))
        asr.THU_MUC_KET_QUA = Path(tm) / "transcripts"
        asr.WhisperModel = lambda *a, **k: (da_tao.append(k.get("compute_type")), ModelGia([]))[1]
        sys.argv = ["chuyen_giong_noi.py", str(Path(tm) / "hop.wav"), "--kieu-tinh", "float32"]
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                asr.main()
            except SystemExit:
                pass
    if da_tao != ["float32"]:
        return f"kiểu tính không truyền cho model: {da_tao}"


@ca
def bao_ro_khi_thu_muc_model_chua_co():
    if asr.loi_thu_muc_model("medium") is not None:
        return "tên model có sẵn bị coi là thư mục"
    with tempfile.TemporaryDirectory() as tm:
        thieu = asr.loi_thu_muc_model(str(Path(tm) / "models" / "chua-co-ct2"))
        (Path(tm) / "co").mkdir()
        (Path(tm) / "co" / "model.bin").write_bytes(b"x")
        co = asr.loi_thu_muc_model(str(Path(tm) / "co"))
    if not thieu or "chuyen_doi_model.py" not in thieu or co is not None:
        return f"kiểm tra thư mục model sai: {thieu!r}, {co!r}"
    goi, ma = [], None
    asr.WhisperModel = lambda *a, **k: goi.append(1)
    with tempfile.TemporaryDirectory() as tm:
        ghi_wav(Path(tm) / "hop.wav", tieng_noi_gia(2))
        asr.THU_MUC_KET_QUA = Path(tm) / "transcripts"
        sys.argv = ["chuyen_giong_noi.py", str(Path(tm) / "hop.wav"), "--model", "models/chua-co-ct2"]
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                asr.main()
            except SystemExit as thoat:
                ma = thoat.code
    if goi or "chuyen_doi_model.py" not in str(ma):
        return f"không dừng sớm khi thiếu thư mục model: {goi}, {ma!r}"


@ca
def dem_im_lang_that_cho_moi_luot_du_30_giay():
    da_nghe = []

    class ModelGhi(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_nghe.append((len(am_thanh), float(np.abs(am_thanh[SR * 4:]).max()) if len(am_thanh) > SR * 4 else 0.0))
            return super().transcribe(am_thanh, **tham_so)

    song_am = (np.random.default_rng(0).normal(0, 0.1, 10 * SR)).astype(np.float32)
    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda s: [(0, 4 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            for dem in (False, True):
                asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide nha mọi người."))]), song_am,
                              tung_luot=True, dem_im_lang=dem)
    finally:
        asr.cat_luot_noi = goc
    if da_nghe != [(4 * SR, 0.0), (30 * SR, 0.0)]:
        return f"phải đệm im lặng (số 0 trên sóng âm) tới đúng 30 giây khi bật: {da_nghe}"


@ca
def beam_truyen_dung_cho_model():
    da_goi = []

    class ModelGhi(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_goi.append(tham_so.get("beam_size"))
            return super().transcribe(am_thanh, **tham_so)

    with contextlib.redirect_stdout(io.StringIO()):
        asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))]), np.zeros(SR, dtype=np.float32))
        asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.0, "Bạn Lan làm slide."))]), np.zeros(SR, dtype=np.float32), beam=1)
    if da_goi != [asr.BEAM, 1]:
        return f"beam truyền sai: {da_goi}"


@ca
def tung_luot_bo_chu_nam_sau_cuoi_am_thanh_that():
    """Đệm im lặng tới 30 giây: chữ bịa nằm trong phần đệm (sau cuối lượt) phải bị bỏ, chữ thật giữ."""
    that = chuoi_tu(0.2, "Bạn Lan làm slide nha mọi người.")          # 0,2 -> 2,95 s, lượt dài 4 s
    bia = chuoi_tu(6.0, "Cảm ơn các bạn đã theo dõi và hẹn gặp lại.")  # trong phần đệm
    lan_ranh = [tu(3.9, "nhé.")]                                        # điểm giữa 4,075 < 4,5: giữ
    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda s: [(SR, 5 * SR)]
        nhat_ky = []
        with contextlib.redirect_stdout(io.StringIO()):
            cac_tu, _ = asr.nhan_dang(ModelGia([doan(that + lan_ranh), doan(bia)]),
                                      np.zeros(10 * SR, dtype=np.float32), tung_luot=True,
                                      dem_im_lang=True, nhat_ky=nhat_ky)
    finally:
        asr.cat_luot_noi = goc
    chu = asr.ghep_tu(cac_tu)
    if chu != "Bạn Lan làm slide nha mọi người. nhé.":
        return f"giữ/bỏ sai: {chu!r}"
    if abs(cac_tu[0].start - 1.2) > 1e-6:
        return f"mốc thời gian không cộng lệch lượt: {cac_tu[0].start}"
    # Câu bịa trong phần đệm: hoặc không bao giờ được đọc tới (đã dừng ở chỗ hết lời), hoặc bị cắt và ghi nhật ký
    bo = [c for c in nhat_ky if "ngoai_am_thanh" in c]
    if len(bo) > 1 or (bo and not bo[0]["ngoai_am_thanh"].startswith("Cảm ơn")):
        return f"nhật ký ghi chữ đã bỏ sai: {bo}"
    # Một đoạn vắt qua cuối lượt: chỉ cắt phần đuôi, giữ phần đầu
    giu, chu_bo = asr.cat_ngoai_am_thanh([doan(chuoi_tu(3.0, "một hai ba bốn năm"))], 4.5)
    if [asr.ghep_tu(d.words) for d in giu] != ["một hai ba bốn"] or chu_bo != "năm" or giu[0].end != 4.55:
        return f"cắt đoạn vắt qua sai: {[d.text for d in giu]}, {chu_bo!r}"


@ca
def json_dau_ra_qua_duoc_kiem_tra_cua_phan_tom_tat():
    """Hợp đồng với phần tóm tắt (docs/dinh_dang_dau_ra.md): file ASR ghi ra phải đọc được bằng
    src/tien_xu_ly/doc_transcript.py, kể cả khi mốc thời gian theo từ của Whisper bị ngược."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tien_xu_ly"))
    from doc_transcript import doc_transcript
    nguoc = [Word(start=5.0, end=4.8, word=" Xong.", probability=0.9)]
    cac_doan = [doan(chuoi_tu(0, "Bạn Tuấn phụ trách frontend.")), doan(nguoc),
                doan(chuoi_tu(7, "Thứ sáu nhóm nộp báo cáo cho cô, còn bạn Lan gửi slide trước tối thứ năm, "
                                 "bạn Tuấn kiểm tra phần API và sửa lỗi đăng nhập, cuối tuần họp lại."))]
    with tempfile.TemporaryDirectory() as tm:
        tm = Path(tm)
        ghi_wav(tm / "hop.wav", tieng_noi_gia(5))
        ma = chay_main(tm, cac_doan, [str(tm / "hop.wav")])
        tep = tm / "transcripts" / "hop.json"
        if ma != 0 or not tep.exists():
            return f"mã thoát {ma}, có file: {tep.exists()}"
        try:
            cac_cau = doc_transcript(tep)
        except ValueError as loi:
            return f"phần tóm tắt không đọc được: {loi}"
    if len(cac_cau) < 3 or any(c["speaker"] != "SPEAKER_00" or not c["text"].strip() for c in cac_cau):
        return f"nội dung sai: {cac_cau}"
    if any(a["start"] > b["start"] for a, b in zip(cac_cau, cac_cau[1:])):
        return "các câu không theo thứ tự thời gian"


@ca
def loai_cau_ket_video_khi_model_tu_tin_giu_cau_hop_that():
    """large-v3 bịa câu kết video với độ tin cậy cao (lọt bộ lọc cũ), có khi 2 câu nối nhau > 15 từ."""
    bia = ["Hãy subscribe cho kênh La La School để không bỏ lỡ những video hấp dẫn.",
           "Hãy đăng ký kênh để ủng hộ kênh của mình nhé.",
           "Hãy subscribe cho kênh La La School để không bỏ lỡ những video hấp dẫn. "
           "Hãy đăng ký kênh để ủng hộ kênh của mình nhé."]
    for cau in bia:
        if asr.ly_do_loai(doan(chuoi_tu(0, cau, buoc=0.3))) != "câu bịa kiểu YouTube":
            return f"không loại: {cau}"
    that = ["Tháng này mình cần tăng lượt subscribe cho kênh của khách hàng.",
            "Khách hàng muốn người xem đăng ký kênh trước cuối tháng.",
            "Bên mình làm video để không bỏ lỡ khách hàng tiềm năng."]
    for cau in that:
        if asr.ly_do_loai(doan(chuoi_tu(0, cau))):
            return f"loại nhầm câu họp thật: {cau}"


@ca
def so_luong_cpu_truyen_cho_model_va_vao_ten_cau_hinh():
    import danh_gia_bo as dg
    from types import SimpleNamespace
    co_ban = dict(model="models/phowhisper-medium-ct2", goi_y="cau_mo_dau", thu_lai="gioi_han", theo_khuc=False,
                  tung_luot=True, khong_moc_thoi_gian=False, dem_im_lang=True, beam=5, khong_tien_xu_ly=False,
                  loc_nhieu=False, kieu_tinh="int8")
    ten = dg.ten_cau_hinh(SimpleNamespace(**co_ban, token_moi_giay=12, token_cong_them=10, so_luong=8,
                                          khong_nghe_lai=False, khong_cat_ngoai=False, gop_luot=0))
    if ten != "phowhisper-medium-ct2_chi_cau_mo_dau_gioi_han_thu_lai_tung_luot_dem_lang_token12-10_luong8":
        return f"tên cấu hình sai: {ten}"
    da_tao = []
    with tempfile.TemporaryDirectory() as tm:
        ghi_wav(Path(tm) / "hop.wav", tieng_noi_gia(2))
        asr.THU_MUC_KET_QUA = Path(tm) / "transcripts"
        asr.WhisperModel = lambda *a, **k: (da_tao.append(k.get("cpu_threads")), ModelGia([]))[1]
        sys.argv = ["chuyen_giong_noi.py", str(Path(tm) / "hop.wav"), "--so-luong", "6"]
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                asr.main()
            except SystemExit:
                pass
    if da_tao != [6]:
        return f"số luồng không truyền cho model: {da_tao}"


@ca
def thong_ke_token_tim_gioi_han_khong_cat_loi():
    import danh_gia_bo as dg

    class TachGia:   # mỗi từ = 1 token
        def encode(self, chu):
            return type("K", (), {"ids": chu.split()})()

    chi_tiet = [{"luot": [0.0, 4.0]}, {"luot": [5.0, 6.0]},
                {"start": 0.1, "end": 3.9, "text": " ".join(["chữ"] * 47), "loai": None},
                {"start": 4.1, "end": 4.6, "text": "cảm ơn và hẹn gặp lại", "loai": "câu bịa kiểu YouTube"},
                {"start": 5.1, "end": 5.9, "text": "dạ", "loai": None}]
    goc = dg.THU_MUC_BO, dg.tim_tokenizer
    with tempfile.TemporaryDirectory() as tm:
        (Path(tm) / "bo").mkdir()
        (Path(tm) / "bo" / "ket_qua__x.json").write_text(
            json.dumps({"a": {"du_doan": "", "chi_tiet": chi_tiet}}, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO, dg.tim_tokenizer = Path(tm), lambda m: TachGia()
            bao_cao = dg.thong_ke_token(["bo"], "x", "medium")
        finally:
            dg.THU_MUC_BO, dg.tim_tokenizer = goc
    # Lượt 1 (4 giây) cần 47 + 2 + 1 = 50 token: 8 x 4 + 10 = 42 cắt mất lời, 10 x 4 + 10 = 50 vừa đủ;
    # câu bịa bị loại không tính
    dong = {" ".join(l.split("|")[0].split()): l for l in bao_cao.splitlines() if "x giây +" in l and "|" in l}
    if "| 1 lượt" not in " ".join(dong.get("8 x giây + 10", "").split()) \
            or "| 0 lượt" not in " ".join(dong.get("10 x giây + 10", "").split()):
        return f"thống kê sai:\n{bao_cao}"


@ca
def che_do_chinh_xac_dung_phowhisper_dem_im_lang_va_lui_ve_medium():
    goc = asr.MODEL_CHINH_XAC
    try:
        with tempfile.TemporaryDirectory() as tm:
            asr.MODEL_CHINH_XAC = Path(tm) / "phowhisper-medium-ct2"
            thieu = asr.chon_che_do("chinh_xac")
            asr.MODEL_CHINH_XAC.mkdir()
            (asr.MODEL_CHINH_XAC / "model.bin").write_bytes(b"x")
            co = asr.chon_che_do("chinh_xac")
            nhanh = asr.chon_che_do("nhanh")
            tu_chon = asr.chon_che_do("chinh_xac", "models/khac-ct2")
            # main: model chính xác + đệm im lặng truyền tới nhan_dang
            da_tao, da_nghe = [], []
            goc_nhan_dang = asr.nhan_dang
            ghi_wav(Path(tm) / "hop.wav", tieng_noi_gia(2))
            asr.THU_MUC_KET_QUA = Path(tm) / "transcripts"
            asr.WhisperModel = lambda ten, **k: (da_tao.append(ten), ModelGia([]))[1]
            asr.nhan_dang = lambda *a, **k: (da_nghe.append((k.get("dem_im_lang"), k.get("goi_y"))), ([], 0))[1]
            sys.argv = ["chuyen_giong_noi.py", str(Path(tm) / "hop.wav")]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        asr.main()
                    except SystemExit:
                        pass
            finally:
                asr.nhan_dang = goc_nhan_dang
    finally:
        asr.MODEL_CHINH_XAC = goc
    if thieu[:3] != (asr.TEN_MODEL, False, asr.GOI_Y_MAC_DINH) or not thieu[3] or "chuyen_doi_model.py" not in thieu[3]:
        return f"thiếu model chính xác phải lùi về {asr.TEN_MODEL} và báo cách tạo: {thieu}"
    if not co[0].endswith("phowhisper-medium-ct2") or co[1:] != (True, "khong", None):
        return f"có model chính xác mà không dùng: {co}"
    if asr.chon_che_do("nhanh_nhat") != ("small", False, asr.GOI_Y_MAC_DINH, None):
        return f"chế độ nhanh nhất sai: {asr.chon_che_do('nhanh_nhat')}"
    if nhanh != (asr.TEN_MODEL, False, asr.GOI_Y_MAC_DINH, None) or tu_chon != ("models/khac-ct2", True, "khong", None):
        return f"chế độ nhanh / tự chọn model sai: {nhanh}, {tu_chon}"
    if len(da_tao) != 1 or not da_tao[0].endswith("phowhisper-medium-ct2") or da_nghe != [(True, "khong")]:
        return f"main không dùng model chính xác + đệm im lặng: {da_tao}, {da_nghe}"


@ca
def do_thoi_gian_dem_tung_buoc_cua_model():
    import danh_gia_bo as dg

    class KetQua:
        sequences_ids = [[1, 2, 3, 4]]

    class Ct2Gia:
        is_multilingual = True

        def encode(self, x, to_cpu=False):
            return "enc"

        def generate(self, enc, prompt, **k):
            return [KetQua()]

        def align(self, *a, **k):
            return []

    bo = dg.DoThoiGian(Ct2Gia())
    if not bo.is_multilingual or bo.encode(1, to_cpu=True) != "enc":
        return "không chuyển tiếp thuộc tính / lời gọi"
    bo.generate("enc", [[1]])
    bo.generate("enc", [[1]])
    bo.align()
    if (bo.so_lan["encode"], bo.so_lan["generate"], bo.so_lan["align"], bo.so_token) != (1, 2, 1, 8):
        return f"đếm sai: {bo.so_lan}, {bo.so_token}"
    bao_cao = bo.bao_cao(10.0, 5.0, 1)
    if "2.0x" not in bao_cao or "2.00" not in bao_cao:
        return f"báo cáo sai:\n{bao_cao}"


@ca
def khong_nghe_them_cua_so_khi_da_qua_am_thanh_that():
    """PhoWhisper + đệm im lặng: faster-whisper mở thêm cửa sổ trong phần đệm (mỗi lần nghe lại 30 giây).
    Gặp đoạn bắt đầu sau cuối lượt thì phải dừng, không đòi cửa sổ tiếp theo."""
    that = doan(chuoi_tu(0.2, "Bạn Lan làm slide nha mọi người."))      # lượt dài 4 giây
    bia = doan(chuoi_tu(6.0, "cảm ơn và hẹn gặp lại"))

    class ModelNhieuCuaSo(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            inspect.signature(WhisperModel.transcribe).bind(None, am_thanh, **tham_so)

            def cac_cua_so():
                yield that
                yield bia
                raise AssertionError("đã nghe thêm cửa sổ trong phần đệm")
            return cac_cua_so(), None

    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda s: [(0, 4 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            cac_tu, _ = asr.nhan_dang(ModelNhieuCuaSo([]), np.zeros(5 * SR, dtype=np.float32),
                                      tung_luot=True, dem_im_lang=True)
    finally:
        asr.cat_luot_noi = goc
    if asr.ghep_tu(cac_tu) != "Bạn Lan làm slide nha mọi người.":
        return f"chữ sai: {asr.ghep_tu(cac_tu)!r}"
    # Lời thật kéo dài qua nhiều cửa sổ (chưa qua cuối âm thanh) thì vẫn lấy hết
    nhieu = [doan(chuoi_tu(0.0, "một hai")), doan(chuoi_tu(10.0, "ba bốn")), doan(chuoi_tu(20.0, "năm sáu"))]
    if len(asr.dung_khi_qua_am_thanh(iter(nhieu), 25.5)) != 3:
        return "dừng sớm khi lời thật còn tiếp"
    # Đoạn dở dang cuối cửa sổ đầu: bắt đầu trong lượt, kéo tới hết 30 giây -> không mở cửa sổ sau
    do_dang = doan(chuoi_tu(3.0, "nha cảm ơn và hẹn gặp lại"))
    do_dang = dataclasses.replace(do_dang, end=30.0)

    def cua_so():
        yield doan(chuoi_tu(0.2, "Bạn Lan làm slide"))
        yield do_dang
        raise AssertionError("đã nghe thêm cửa sổ sau đoạn dở dang")
    lay = asr.dung_khi_qua_am_thanh(cua_so(), 4.5)
    # Cửa sổ đầu kết thúc gọn ở chỗ hết lời (theo VAD): không mở cửa sổ mới vào phần lề / đệm

    def gon():
        yield doan(chuoi_tu(0.2, "Bạn Lan làm slide nha"))   # hết lúc 2,15 giây; hết lời theo VAD: 2,1 giây
        raise AssertionError("đã mở cửa sổ mới sau chỗ hết lời")
    if len(asr.dung_khi_qua_am_thanh(gon(), 3.1, 2.1)) != 1:
        return "không dừng ở chỗ hết lời"
    giu, _ = asr.cat_ngoai_am_thanh(lay, 4.5)
    if asr.ghep_tu([t for d in giu for t in d.words]) != "Bạn Lan làm slide nha cảm ơn và":
        return f"giữ chữ trong lượt sai: {[d.text for d in giu]}"


@ca
def doc_file_stereo_44100hz_va_mp3():
    """Ghi âm điện thoại / máy tính hay là stereo 44,1 kHz hoặc mp3: phải đọc thành 16 kHz, 1 kênh, đúng độ dài."""
    import av
    t = np.arange(int(3.0 * 44100)) / 44100
    trai = 0.2 * np.sin(2 * np.pi * 200 * t)
    phai = 0.2 * np.sin(2 * np.pi * 300 * t)
    with tempfile.TemporaryDirectory() as tm:
        tep = Path(tm) / "stereo.wav"
        with wave.open(str(tep), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(44100)
            f.writeframes((np.stack([trai, phai], axis=1) * 32767).astype(np.int16).tobytes())
        x = asr.doc_am_thanh(tep)
        if x.ndim != 1 or abs(len(x) - 3 * SR) > SR // 50:
            return f"stereo 44,1 kHz đọc sai: {x.shape}"
        # mp3 (tạo bằng chính thư viện đọc file của faster-whisper)
        mp3 = Path(tm) / "hop.mp3"
        with av.open(str(mp3), "w") as ra:
            luong = ra.add_stream("mp3", rate=44100)
            luong.layout = "stereo"
            khung = av.AudioFrame.from_ndarray(
                (np.stack([trai, phai]) * 32767).astype(np.int16).reshape(1, -1), format="s16", layout="stereo")
            khung.sample_rate = 44100
            for goi in luong.encode(khung):
                ra.mux(goi)
            for goi in luong.encode(None):
                ra.mux(goi)
        y = asr.doc_am_thanh(mp3)
        if y.ndim != 1 or abs(len(y) - 3 * SR) > SR // 5:
            return f"mp3 stereo đọc sai: {y.shape}"


@ca
def tat_tung_thanh_phan_de_do_co_ich_khong():
    """A2: tắt nghe lại lượt hỏng / tắt cắt ngoài âm thanh / giữ đoạn bộ lọc bỏ (chấm lại không chạy model)."""
    import danh_gia_bo as dg
    goi = []

    class ModelHong(ModelGia):   # lượt 5 giây chỉ ra 1 chữ: lượt hỏng
        def transcribe(self, am_thanh, **tham_so):
            goi.append(1)
            return super().transcribe(am_thanh, **tham_so)

    bia = doan(chuoi_tu(6.0, "cảm ơn và hẹn gặp lại"))
    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda s: [(0, 5 * SR)]
        with contextlib.redirect_stdout(io.StringIO()):
            asr.nhan_dang(ModelHong([doan([tu(0.1, "dạ")])]), np.zeros(6 * SR, dtype=np.float32),
                          tung_luot=True, nghe_lai=False)
            co_cat, _ = asr.nhan_dang(ModelGia([doan(chuoi_tu(0.1, "Bạn Lan làm slide.")), bia]),
                                      np.zeros(6 * SR, dtype=np.float32), tung_luot=True, dem_im_lang=True)
            khong_cat, _ = asr.nhan_dang(ModelGia([doan(chuoi_tu(0.1, "Bạn Lan làm slide.")), bia]),
                                         np.zeros(6 * SR, dtype=np.float32), tung_luot=True, dem_im_lang=True,
                                         cat_ngoai=False)
    finally:
        asr.cat_luot_noi = goc
    if goi != [1]:
        return f"tắt nghe lại mà vẫn nhận dạng lại: {len(goi)} lần"
    if "hẹn gặp lại" in asr.ghep_tu(co_cat) or "hẹn gặp lại" not in asr.ghep_tu(khong_cat):
        return f"tắt cắt ngoài âm thanh sai: {asr.ghep_tu(co_cat)!r} / {asr.ghep_tu(khong_cat)!r}"
    chi_tiet = [{"start": 0, "end": 1, "text": "bạn lan làm slide", "loai": None},
                {"start": 2, "end": 3, "text": "hãy đăng ký kênh", "loai": "câu bịa kiểu YouTube"}]
    goc_bo = dg.THU_MUC_BO
    with tempfile.TemporaryDirectory() as tm:
        (Path(tm) / "bo").mkdir()
        (Path(tm) / "bo" / "ket_qua__x.json").write_text(json.dumps(
            {"a": {"du_doan": "bạn lan làm slide", "chi_tiet": chi_tiet}}, ensure_ascii=False), encoding="utf-8")
        try:
            dg.THU_MUC_BO = Path(tm)
            ten, so = dg.khong_loc("bo", "x")
            moi = json.loads((Path(tm) / "bo" / f"ket_qua__{ten}.json").read_text(encoding="utf-8"))
        finally:
            dg.THU_MUC_BO = goc_bo
    if ten != "x_khong_loc" or so != 1 or moi["a"]["du_doan"] != "bạn lan làm slide hãy đăng ký kênh":
        return f"chấm lại không lọc sai: {ten}, {so}, {moi}"


@ca
def gop_luot_ngan_lien_nhau_de_bot_cua_so():
    luot = [(0, 2 * SR), (3 * SR, 4 * SR), (5 * SR, 9 * SR), (30 * SR, 31 * SR), (32 * SR, 55 * SR)]
    if asr.gop_luot(luot, 0) != luot:
        return "0 phải là không gộp"
    gop = asr.gop_luot(luot, 20)
    if gop != [(0, 9 * SR), (30 * SR, 31 * SR), (32 * SR, 55 * SR)]:
        return f"gộp sai: {[(a / SR, b / SR) for a, b in gop]}"
    da_nghe = []

    class ModelGhi(ModelGia):
        def transcribe(self, am_thanh, **tham_so):
            da_nghe.append(len(am_thanh) / SR)
            return super().transcribe(am_thanh, **tham_so)

    goc = asr.cat_luot_noi
    try:
        asr.cat_luot_noi = lambda s: luot[:3]
        with contextlib.redirect_stdout(io.StringIO()):
            asr.nhan_dang(ModelGhi([doan(chuoi_tu(0.2, "Bạn Lan làm slide nha mọi người ơi nhé."))]),
                          np.zeros(10 * SR, dtype=np.float32), tung_luot=True, gop=20)
    finally:
        asr.cat_luot_noi = goc
    if da_nghe != [9.0]:
        return f"3 lượt liền nhau phải nghe 1 lần: {da_nghe}"


@ca
def danh_gia_hf_ghi_ket_qua_dung_dinh_dang_va_lam_tiep():
    """danh_gia_hf.py (wav2vec2, Whisper gốc): kết quả cùng định dạng danh_gia_bo để --so-sanh được;
    chạy lại thì bỏ qua đoạn đã có; đoạn > 30 giây cắt theo lượt nói."""
    import danh_gia_bo as dg
    import danh_gia_hf as hf
    goc = (dg.THU_MUC_BO, asr.cat_luot_noi)
    da_nghe = []

    def nghe(song_am):
        da_nghe.append(round(len(song_am) / SR))
        return "bạn lan làm slide"
    try:
        with tempfile.TemporaryDirectory() as tm:
            thu_muc = Path(tm) / "bo"
            (thu_muc / "audio").mkdir(parents=True)
            ghi_wav(thu_muc / "audio" / "a.wav", tieng_noi_gia(3))
            ghi_wav(thu_muc / "audio" / "b.wav", tieng_noi_gia(40))
            (thu_muc / "nhan.json").write_text(json.dumps([
                {"id": "a", "tep": "audio/a.wav", "text": "bạn lan làm slide", "nhom": "x"},
                {"id": "b", "tep": "audio/b.wav", "text": "bạn lan làm slide", "nhom": "x"}]), encoding="utf-8")
            dg.THU_MUC_BO = Path(tm)
            asr.cat_luot_noi = lambda s: [(0, 10 * SR), (20 * SR, 30 * SR)]
            with contextlib.redirect_stdout(io.StringIO()):
                _, kq = hf.chay_bo_hf("bo", nghe, "x_hf")
                hf.chay_bo_hf("bo", lambda s: 1 / 0, "x_hf")      # chạy lại: không nghe lại đoạn nào
            luu = json.loads((thu_muc / "ket_qua__x_hf.json").read_text(encoding="utf-8"))
    finally:
        dg.THU_MUC_BO, asr.cat_luot_noi = goc
    if da_nghe != [3, 10, 10]:
        return f"cách nghe sai (đoạn ngắn 1 lần, đoạn dài theo lượt): {da_nghe}"
    if set(luu) != {"a", "b"} or luu["b"]["du_doan"] != "bạn lan làm slide bạn lan làm slide" \
            or not {"du_doan", "do_dai", "thoi_gian"} <= set(luu["a"]):
        return f"kết quả sai định dạng: {luu}"
    if hf.ten_cau_hinh_hf("nguyenvulebinh/wav2vec2-base-vietnamese-250h") != "wav2vec2-base-vietnamese-250h_hf":
        return "tên cấu hình sai"


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
