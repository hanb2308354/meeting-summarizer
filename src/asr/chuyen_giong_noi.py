# -*- coding: utf-8 -*-
"""
Chuyển file ghi âm cuộc họp thành transcript JSON cho phần xử lý văn bản (src/nlp).

Luồng xử lý:
    1. Kiểm tra đầu vào  : file có tồn tại, đúng định dạng, đọc được, có tiếng nói
    2. Tiền xử lý âm thanh: bỏ lệch DC, lọc tiếng ù tần số thấp, chuẩn hóa âm lượng,
                            (tùy chọn) giảm tạp âm
    3. Nhận dạng giọng nói: faster-whisper + VAD + từ khóa gợi ý cho MỌI đoạn
    4. Lọc lỗi nhận dạng  : bỏ đoạn "bịa chữ" ở chỗ im lặng/nhiễu, bỏ câu bị lặp
    5. Tách câu           : theo dấu câu, theo khoảng ngừng, và cắt câu quá dài
    6. Ghi JSON           : ghi an toàn, đúng format đã thống nhất với phần NLP

RANH GIỚI VỚI BƯỚC SAU:
    File này chỉ lo "nghe đúng nhất có thể" và giữ NGUYÊN VĂN chữ Whisper nghe được.
    Mọi xử lý văn bản (sửa lỗi nghe nhầm, bỏ từ đệm, tách từ...) nằm ở bước
    tiền xử lý (src/tien_xu_ly), để mỗi bước làm đúng một việc.

FORMAT ĐẦU RA (đầu vào của src/tien_xu_ly, KHÔNG ĐƯỢC ĐỔI):
    data/transcripts/<tên file ghi âm>.json
    [{"speaker": "SPEAKER_00", "start": 0.0, "end": 2.14, "text": "..."}]

Cách dùng:
    python src/asr/chuyen_giong_noi.py data/audio/hop_01.mp3
    python src/asr/chuyen_giong_noi.py data/audio/            (chạy cả thư mục, bỏ qua file đã có JSON)
    python src/asr/chuyen_giong_noi.py data/audio/ --ghi-de   (chạy lại cả thư mục)
    python src/asr/chuyen_giong_noi.py data/audio/hop_01.mp3 --loc-nhieu
    python src/asr/chuyen_giong_noi.py data/audio/hop_01.mp3 --khong-tien-xu-ly
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel, decode_audio
from faster_whisper.transcribe import get_compression_ratio

# In tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ======================================================================
# CẤU HÌNH
# ======================================================================
TEN_MODEL = "medium"            # Đã chốt qua thử nghiệm (xem thu_faster_whisper.py)
TAN_SO_MAU = 16000              # Whisper làm việc ở 16 kHz, 1 kênh
# Tính theo vị trí file code (src/asr/ -> lên 2 cấp là thư mục project),
# nên chạy từ thư mục nào JSON cũng được lưu đúng chỗ phần NLP đọc.
THU_MUC_GOC = Path(__file__).resolve().parents[2]
THU_MUC_KET_QUA = THU_MUC_GOC / "data" / "transcripts"
DUOI_HO_TRO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma", ".webm", ".mp4"}

# Câu mở đầu: chỉ có tác dụng ở ~30 giây đầu, giúp model vào đúng "giọng văn" cuộc họp
CAU_MO_DAU = "Cuộc họp nhóm, có dùng một số từ tiếng Anh."

# Từ khóa gợi ý: faster-whisper gắn vào MỌI đoạn 30 giây (khác initial_prompt chỉ
# tác dụng ở đầu file), nên cuộc họp dài vẫn nhận đúng thuật ngữ đến cuối.
TU_KHOA_GOI_Y = (
    "deadline, hạn chót, project, meeting, slide, file, check, demo, test, review, "
    "update, fix, bug, feedback, support, frontend, backend, database, API, "
    "upload, link, email, KPI, sale, marketing, budget, target, deal, "
    "group Zalo, Messenger, Google Meet, Google Drive"
)

TAP_TU_GOI_Y = {tu.strip().lower() for tu in TU_KHOA_GOI_Y.split(",")}

# Câu "bịa" kinh điển của Whisper tiếng Việt (học từ phụ đề YouTube),
# hay xuất hiện ở chỗ im lặng hoặc cuối file.
# Chỉ áp dụng cho đoạn ngắn, để câu họp thật có nhắc "video", "đăng ký" không bị xóa.
# Câu bịa học từ phụ đề YouTube, chia 2 loại:
# - CHẮC CHẮN bịa (không ai nói trong cuộc họp): loại luôn.
# - NGHI bịa: cuộc họp marketing có thể nói thật ("tăng lượt subscribe cho kênh"),
#   nên chỉ loại khi model cũng không tự tin về đoạn đó.
MAU_CAU_BIA_CHAC = re.compile(r"ghiền mì gõ|thanks for watching", re.IGNORECASE)
MAU_CAU_BIA_NGHI = re.compile(
    r"subscribe|like và share|bấm chuông|đăng ký kênh|"
    r"hẹn gặp lại các bạn trong (?:những )?video|"
    r"cảm ơn các bạn đã (?:theo dõi|xem|lắng nghe)",
    re.IGNORECASE,
)
SO_TU_TOI_DA_CAU_BIA = 15
NGUONG_NGHI_KHONG_CO_TIENG = 0.3   # no_speech_prob trên mức này: model nghi không có người nói
NGUONG_NGHI_DO_TIN_CAY = -1.0      # avg_logprob dưới mức này: model không chắc chữ vừa ra
                                   # (-1.0 là ngưỡng "không chắc" của chính Whisper; để cao hơn
                                   #  sẽ loại oan câu thật trong phòng ồn)

# Ngưỡng lọc. (Đoạn "không có tiếng nói" faster-whisper đã tự bỏ qua bên trong,
# với no_speech_prob > 0.6 và avg_logprob <= -1.0, nên ở đây không lọc lại.)
NGUONG_LAP_LAI = 2.4            # compression_ratio cao -> chữ bị lặp vòng
SO_TU_TOI_THIEU_LOC_TRUNG = 4   # câu ngắn lặp lại ("Dạ.", "Ok.") là bình thường, không xóa

# Tách câu
DAU_KET_CAU = (".", "?", "!")
# Chữ viết tắt có dấu chấm: KHÔNG phải hết câu ("Gặp ở TP. Cần Thơ lúc 9h.")
TU_VIET_TAT = {"tp.", "tt.", "q.", "p.", "ts.", "ths.", "pgs.", "gs.", "bs.", "ks.",
               "st.", "vd.", "v.v.", "đ.", "tr.", "ct.", "cty.", "mr.", "ms.", "dr."}
KHOANG_NGUNG_TACH_CAU = 2.0     # ngừng nói >= 2 giây thì coi là sang câu mới...
DO_DAI_CAU_TOI_THIEU = 3.0      # ...nhưng chỉ khi câu đang dở đã dài >= 3 giây
KHOANG_NGUNG_LUON_TACH = 5.0    # ngừng >= 5 giây thì luôn tách ("Ok." ... im lặng ... câu mới)
                                # (tránh cắt "Deadline phần backend là ... thứ sáu")
DO_DAI_CAU_TOI_DA = 20.0        # câu dài hơn 20 giây thì cắt ở dấu phẩy gần nhất

# Âm lượng mục tiêu khi chuẩn hóa (dBFS, tính trên các đoạn có tiếng)
AM_LUONG_MUC_TIEU = -20.0
TANG_TOI_DA_DB = 15.0           # không khuếch đại quá +15 dB (file gần như toàn im lặng)
DINH_TOI_DA = 0.95              # không để biên độ vượt mức này (tránh méo tiếng)


# ======================================================================
# 1. KIỂM TRA VÀ ĐỌC FILE GHI ÂM
# ======================================================================
class LoiDauVao(Exception):
    """Lỗi do file đầu vào: báo cho người dùng biết, không in traceback."""


def kiem_tra_file(duong_dan):
    """Kiểm tra nhanh (không đọc nội dung): có tồn tại, đúng đuôi, không rỗng."""
    if not duong_dan.exists():
        raise LoiDauVao(f"Không tìm thấy file: {duong_dan}")
    if duong_dan.suffix.lower() not in DUOI_HO_TRO:
        raise LoiDauVao(
            f"Định dạng {duong_dan.suffix} chưa hỗ trợ. Dùng một trong: "
            + ", ".join(sorted(DUOI_HO_TRO))
        )
    if duong_dan.stat().st_size == 0:
        raise LoiDauVao(f"File rỗng (0 byte): {duong_dan}")


def doc_am_thanh(duong_dan):
    """Đọc file ghi âm thành sóng âm 16 kHz, 1 kênh (numpy float32)."""
    kiem_tra_file(duong_dan)

    try:
        song_am = decode_audio(str(duong_dan), sampling_rate=TAN_SO_MAU)
    except Exception as loi:
        raise LoiDauVao(f"Không đọc được file (có thể bị hỏng): {duong_dan}\n  Chi tiết: {loi}")

    do_dai = len(song_am) / TAN_SO_MAU
    if do_dai < 1.0:
        raise LoiDauVao(f"File quá ngắn ({do_dai:.1f} giây), không đủ để nhận dạng.")
    if np.max(np.abs(song_am)) < 1e-4:
        raise LoiDauVao("File gần như không có âm thanh (toàn im lặng).")
    return song_am.astype(np.float32, copy=False)


# ======================================================================
# 2. TIỀN XỬ LÝ ÂM THANH
# ======================================================================
def cat_khung(song_am, n_fft, buoc):
    """Chia sóng âm thành các khung chồng nhau (dạng "view", không tốn thêm RAM)."""
    x = np.pad(song_am, (n_fft, n_fft + buoc), mode="constant")
    return np.lib.stride_tricks.sliding_window_view(x, n_fft)[::buoc]


def xu_ly_pho(song_am, ham_he_so, n_fft, buoc, lo=2048):
    """Biến đổi Fourier từng khung, nhân phổ với hệ số, rồi ghép lại (overlap-add).

    ham_he_so(pho) trả về hệ số (0..1) cho từng tần số của từng khung.
    Xử lý theo lô khung nên file dài hàng giờ vẫn không tốn nhiều RAM.
    Độ dài đầu ra bằng đúng đầu vào nên mốc thời gian không bị lệch.
    """
    so_mau_goc = len(song_am)
    cua_so = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    cac_khung = cat_khung(song_am, n_fft, buoc)
    so_khung = len(cac_khung)
    so_phan = n_fft // buoc

    dau_ra = np.zeros(((so_khung + so_phan) * buoc,), dtype=np.float32)
    dau_ra_khoi = dau_ra.reshape(-1, buoc)
    for i in range(0, so_khung, lo):
        pho = np.fft.rfft(cac_khung[i:i + lo] * cua_so, axis=1)
        khung_moi = np.fft.irfft(pho * ham_he_so(pho), n=n_fft, axis=1)
        khung_moi = khung_moi.astype(np.float32) * cua_so
        so = len(khung_moi)
        for p in range(so_phan):
            dau_ra_khoi[i + p:i + p + so] += khung_moi[:, p * buoc:(p + 1) * buoc]

    # Cửa sổ Hann chồng 75% có tổng bình phương = 1,5 -> chia lại để đúng biên độ
    dau_ra /= 1.5
    return dau_ra[n_fft:n_fft + so_mau_goc]


def loc_tieng_u(song_am, tu_hz=50.0, den_hz=90.0):
    """Bỏ lệch DC và lọc tiếng ù tần số thấp (quạt, xe, tiếng điện 50 Hz).

    Tắt hẳn mọi tần số dưới 50 Hz, giữ nguyên từ 90 Hz trở lên, ở giữa giảm dần.
    Giọng nói (kể cả giọng nam trầm) chủ yếu nằm trên 90 Hz nên không bị ảnh hưởng.
    Hạn chế: chỉ bỏ tần số gốc 50 Hz, các hài 100/150 Hz của tiếng điện vẫn còn;
    mic điện thoại thường đã tự lọc tần số thấp nên tác dụng thực tế có thể nhỏ.
    """
    n_fft, buoc = 2048, 512                     # 2048 mẫu -> phân giải ~8 Hz
    tan_so = np.fft.rfftfreq(n_fft, 1 / TAN_SO_MAU)
    t = np.clip((tan_so - tu_hz) / (den_hz - tu_hz), 0.0, 1.0)
    he_so = (0.5 - 0.5 * np.cos(np.pi * t)).astype(np.float32)   # chuyển mượt từ 0 lên 1
    return xu_ly_pho(song_am - np.mean(song_am), lambda pho: he_so, n_fft, buoc)


def nang_luong_theo_khung(song_am, khung=0.03):
    """Tính độ lớn (RMS) của từng khung 30 ms."""
    n = int(khung * TAN_SO_MAU)
    so_khung = len(song_am) // n
    if so_khung == 0:
        return np.array([np.sqrt(np.mean(song_am ** 2))])
    khung_am = song_am[: so_khung * n].reshape(so_khung, n)
    return np.sqrt(np.mean(khung_am ** 2, axis=1) + 1e-12)


def chuan_hoa_am_luong(song_am):
    """Đưa âm lượng giọng nói về mức chuẩn, để người nói nhỏ hay để máy xa vẫn rõ.

    Whisper gần như không bị ảnh hưởng bởi âm lượng, nhưng bộ dò tiếng nói (VAD)
    thì có: ghi âm quá nhỏ dễ bị VAD bỏ sót câu. Bước này giúp VAD không bỏ sót.

    Đo âm lượng trên các khung TO NHẤT (phần có tiếng nói), không đo trung bình
    cả file, vì đoạn im lặng dài sẽ kéo con số xuống và làm khuếch đại quá tay.
    """
    rms = nang_luong_theo_khung(song_am)
    rms_tieng_noi = np.percentile(rms, 90)
    if rms_tieng_noi < 1e-6:
        return song_am, 0.0

    db_hien_tai = 20 * np.log10(rms_tieng_noi)
    tang_db = min(AM_LUONG_MUC_TIEU - db_hien_tai, TANG_TOI_DA_DB)
    he_so = 10 ** (tang_db / 20)

    # Không khuếch đại đến mức các đỉnh bị cắt (méo tiếng)
    dinh = np.max(np.abs(song_am))
    if dinh * he_so > DINH_TOI_DA:
        he_so = DINH_TOI_DA / dinh
    return (song_am * he_so).astype(np.float32), 20 * np.log10(he_so)


def giam_tap_am(song_am, n_fft=512, buoc=128, giam_toi_da=0.15, he_so_tru=1.5):
    """Giảm tạp âm nền đều (quạt, máy lạnh, ồn phòng) bằng phương pháp spectral gating.

    - Ước lượng "phổ của tiếng ồn" từ 10% khung yên tĩnh nhất trong file.
    - Ở mỗi khung, tần số nào gần mức ồn thì giảm xuống, tần số nào vượt xa
      mức ồn (giọng nói) thì giữ nguyên.
    - Không bao giờ giảm quá 85% (giam_toi_da=0.15) để tránh tiếng bị "rè kim loại",
      vì âm bị méo còn làm Whisper nhận dạng TỆ HƠN cả âm có nhiễu.
    - File không có khoảng lặng thì 10% khung "yên tĩnh nhất" vẫn là tiếng nói,
      ước lượng nhiễu sẽ sai và xóa luôn giọng -> phát hiện và bỏ qua bước này.

    Trả về (sóng âm, đã áp dụng hay chưa).
    """
    lo = 2048
    cua_so = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    cac_khung = cat_khung(song_am, n_fft, buoc)

    # Chỉ xét khung nằm trọn trong file thật (bỏ phần đệm số 0 ở hai đầu)
    khung_hop_le = np.arange(n_fft // buoc, max(n_fft // buoc + 1, len(song_am) // buoc))
    nang_luong = np.concatenate([np.sum(cac_khung[khung_hop_le[i:i + lo]] ** 2, axis=1)
                                 for i in range(0, len(khung_hop_le), lo)])
    thu_tu = np.argsort(nang_luong)
    chi_so_yen_tinh = khung_hop_le[thu_tu[: max(1, len(khung_hop_le) // 10)]]

    # Khung yên tĩnh nhất mà chỉ nhỏ hơn mức trung vị chưa tới 10 dB -> không có khoảng lặng thật
    nang_luong_yen_tinh = np.mean(nang_luong[thu_tu[: max(1, len(thu_tu) // 10)]])
    if nang_luong_yen_tinh > 0.1 * np.median(nang_luong):
        return song_am, False

    pho_on = np.zeros(n_fft // 2 + 1, dtype=np.float32)
    for i in range(0, len(chi_so_yen_tinh), lo):
        idx = chi_so_yen_tinh[i:i + lo]
        pho_on += np.abs(np.fft.rfft(cac_khung[idx] * cua_so, axis=1)).sum(axis=0)
    pho_on /= len(chi_so_yen_tinh)

    def he_so(pho):
        return np.clip(1.0 - he_so_tru * pho_on / (np.abs(pho) + 1e-10), giam_toi_da, 1.0)

    return xu_ly_pho(song_am, he_so, n_fft, buoc), True


def tien_xu_ly_am_thanh(song_am, loc_nhieu=False):
    """Chạy các bước tiền xử lý. Độ dài sóng âm giữ nguyên nên mốc thời gian không lệch."""
    thong_tin = []
    song_am = loc_tieng_u(song_am)
    thong_tin.append("lọc tiếng ù")

    if loc_nhieu:
        song_am, da_ap_dung = giam_tap_am(song_am)
        thong_tin.append("giảm tạp âm" if da_ap_dung
                         else "bỏ qua giảm tạp âm (không có khoảng lặng để ước lượng nhiễu)")

    song_am, tang_db = chuan_hoa_am_luong(song_am)
    thong_tin.append(f"chuẩn hóa âm lượng ({tang_db:+.1f} dB)")
    return song_am, thong_tin


def canh_bao_chat_luong(song_am):
    """Cảnh báo sớm các lỗi ghi âm hay gặp (không dừng chương trình)."""
    canh_bao = []
    dinh = np.max(np.abs(song_am))
    ti_le_cat = np.mean(np.abs(song_am) > 0.99)
    if ti_le_cat > 0.001:
        canh_bao.append("Ghi âm bị rè do quá to (clipping), nên để điện thoại xa miệng hơn.")
    if dinh < 0.05:
        canh_bao.append("Ghi âm rất nhỏ, nên để điện thoại gần người nói hơn.")
    rms = nang_luong_theo_khung(song_am)
    on_nen = np.percentile(rms, 10)
    tieng_noi = np.percentile(rms, 90)
    snr = 20 * np.log10((tieng_noi + 1e-9) / (on_nen + 1e-9))
    # Nói liên tục không có khoảng lặng thì không đo được tiếng ồn nền: không cảnh báo oan
    co_khoang_lang = on_nen < 0.5 * np.median(rms)
    if co_khoang_lang and snr < 15:
        canh_bao.append(
            f"Tạp âm nền khá lớn (tiếng nói chỉ to hơn tiếng ồn ~{snr:.0f} dB), "
            "kết quả có thể kém hơn. Nên ghi âm ở nơi yên tĩnh hơn."
        )
    return canh_bao


# ======================================================================
# 3 + 4. NHẬN DẠNG GIỌNG NÓI VÀ LỌC LỖI
# ======================================================================
def chuan_hoa_so_sanh(van_ban):
    return re.sub(r"\W+", " ", van_ban.lower()).strip()


def ly_do_loai(doan):
    """Trả về lý do nếu đoạn có dấu hiệu Whisper "bịa chữ", ngược lại trả về None."""
    van_ban = doan.text.strip()
    if not van_ban:
        return "rỗng"
    # Chữ bị lặp vòng (vd: "cảm ơn cảm ơn cảm ơn..."). Tính lại tỉ lệ nén trên chữ
    # của RIÊNG đoạn này: doan.compression_ratio của faster-whisper tính cho cả cửa sổ
    # 30 giây, dùng nó sẽ loại oan cả những câu thật nằm chung cửa sổ.
    if len(van_ban) > 20 and get_compression_ratio(van_ban) > NGUONG_LAP_LAI:
        return "lặp chữ"
    # Câu bịa kiểu YouTube (chỉ xét đoạn ngắn)
    if len(van_ban.split()) <= SO_TU_TOI_DA_CAU_BIA:
        if MAU_CAU_BIA_CHAC.search(van_ban):
            return "câu bịa kiểu YouTube"
        model_khong_chac = (doan.no_speech_prob > NGUONG_NGHI_KHONG_CO_TIENG
                            or doan.avg_logprob < NGUONG_NGHI_DO_TIN_CAY)
        if MAU_CAU_BIA_NGHI.search(van_ban) and model_khong_chac:
            return "câu bịa kiểu YouTube"
    # Whisper đọc lại danh sách từ khóa gợi ý (hay gặp ở chỗ ồn hoặc im lặng)
    cum = [c.strip().lower().rstrip(".") for c in van_ban.split(",")]
    # (chỉ khi là một chuỗi cụm ngắn gần như toàn từ khóa, tránh loại câu thật như
    #  "Hôm nay mình review, test, demo.")
    if (len(cum) >= 4 and all(len(c.split()) <= 2 for c in cum)
            and sum(c in TAP_TU_GOI_Y for c in cum) / len(cum) >= 0.8):
        return "đọc lại từ khóa gợi ý"
    if chuan_hoa_so_sanh(van_ban) == chuan_hoa_so_sanh(CAU_MO_DAU):
        return "đọc lại câu mở đầu"
    return None


def nhan_dang(model, song_am):
    """Nhận dạng giọng nói, trả về danh sách từ (có mốc thời gian) và số đoạn bị loại."""
    cac_doan, _ = model.transcribe(
        song_am,
        language="vi",
        beam_size=5,
        initial_prompt=CAU_MO_DAU,
        hotwords=TU_KHOA_GOI_Y,
        # Không dựa vào chữ của đoạn trước: chặn lỗi lặp vòng ở file dài.
        # Thuật ngữ vẫn được giữ nhờ hotwords gắn vào mọi đoạn.
        condition_on_previous_text=False,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={
            "threshold": 0.5,
            "min_speech_duration_ms": 250,    # bỏ tiếng động ngắn (gõ bàn, ho)
            "min_silence_duration_ms": 1000,  # ngừng 1 giây mới coi là hết đoạn
            "speech_pad_ms": 400,             # chừa lề để không cụt đầu/cuối chữ
        },
    )

    cac_tu = []
    so_doan_bi_loai = 0
    van_ban_truoc = None
    for doan in cac_doan:
        ly_do = ly_do_loai(doan)
        # Đoạn đủ dài mà lặp y hệt đoạn ngay trước -> model bị kẹt
        van_ban = chuan_hoa_so_sanh(doan.text)
        if not ly_do and van_ban == van_ban_truoc and len(van_ban.split()) >= SO_TU_TOI_THIEU_LOC_TRUNG:
            ly_do = "lặp lại đoạn trước"
        if ly_do:
            so_doan_bi_loai += 1
            # In ra để tự kiểm tra: nếu thấy câu thật bị loại thì báo lại để chỉnh ngưỡng
            print(f"  [LOẠI - {ly_do}] [{doan.start:7.2f} --> {doan.end:7.2f}] {doan.text.strip()}")
            continue
        van_ban_truoc = van_ban
        cac_tu.extend(doan.words or [])
        print(f"  [{doan.start:7.2f} --> {doan.end:7.2f}] {doan.text.strip()}")
    return cac_tu, so_doan_bi_loai


# ======================================================================
# 5. TÁCH CÂU
# ======================================================================
def ghep_tu(cac_tu):
    """Ghép các từ thành câu, giữ nguyên văn Whisper (chỉ bỏ khoảng trắng thừa)."""
    return re.sub(r"\s+", " ", "".join(tu.word for tu in cac_tu)).strip()


def tao_cau(cac_tu):
    return {
        "speaker": "SPEAKER_00",  # Chưa tách người nói, tạm gán một người
        "start": round(float(cac_tu[0].start), 2),
        "end": round(float(cac_tu[-1].end), 2),
        "text": ghep_tu(cac_tu),
    }


def cat_cau_qua_dai(cac_tu):
    """Câu dài quá DO_DAI_CAU_TOI_DA giây: cắt ở dấu phẩy gần giữa nhất."""
    if cac_tu[-1].end - cac_tu[0].start <= DO_DAI_CAU_TOI_DA or len(cac_tu) < 4:
        return [cac_tu]
    giua = len(cac_tu) // 2
    vi_tri_phay = [i for i, tu in enumerate(cac_tu[:-1]) if tu.word.strip().endswith(",")]
    vi_tri = min(vi_tri_phay, key=lambda i: abs(i - giua)) + 1 if vi_tri_phay else giua
    return cat_cau_qua_dai(cac_tu[:vi_tri]) + cat_cau_qua_dai(cac_tu[vi_tri:])


def tach_cau(cac_tu):
    """Gom từ thành câu: theo dấu câu, theo khoảng ngừng dài, rồi cắt câu quá dài."""
    cac_cau_tho = []
    cau_hien_tai = []
    for i, tu in enumerate(cac_tu):
        # Ngừng nói lâu trước từ này VÀ câu đang dở đã đủ dài -> chốt câu cũ
        # (cho trường hợp Whisper quên dấu chấm, nhưng không cắt khi chỉ ngập ngừng).
        # Ngừng rất lâu thì luôn chốt, để câu sau không bị lệch mốc thời gian.
        khoang_ngung = tu.start - cau_hien_tai[-1].end if cau_hien_tai else 0.0
        if cau_hien_tai and (
                khoang_ngung >= KHOANG_NGUNG_LUON_TACH
                or (khoang_ngung >= KHOANG_NGUNG_TACH_CAU
                    and cau_hien_tai[-1].end - cau_hien_tai[0].start >= DO_DAI_CAU_TOI_THIEU)):
            cac_cau_tho.append(cau_hien_tai)
            cau_hien_tai = []
        cau_hien_tai.append(tu)
        chu = tu.word.strip()
        # Chữ viết tắt không kết thúc câu, TRỪ KHI từ ngay sau viết hoa
        # ("... v.v. Bạn Lan làm slide." vẫn là 2 câu)
        tu_sau = cac_tu[i + 1].word.strip() if i + 1 < len(cac_tu) else ""
        la_viet_tat = chu.lower() in TU_VIET_TAT and not (tu_sau[:1].isupper() and chu.lower() in ("v.v.", "đ."))
        if chu.endswith(DAU_KET_CAU) and not la_viet_tat:
            cac_cau_tho.append(cau_hien_tai)
            cau_hien_tai = []
    if cau_hien_tai:
        cac_cau_tho.append(cau_hien_tai)

    ket_qua = []
    for cau in cac_cau_tho:
        for phan in cat_cau_qua_dai(cau):
            cau_json = tao_cau(phan)
            if cau_json["text"]:
                ket_qua.append(cau_json)
    return ket_qua


# ======================================================================
# 6. GHI KẾT QUẢ
# ======================================================================
def hien_thi(duong_dan):
    """Đường dẫn gọn để in ra: tương đối với thư mục dự án nếu được."""
    try:
        return duong_dan.relative_to(THU_MUC_GOC)
    except ValueError:
        return duong_dan


def luu_json(ket_qua, duong_dan_am_thanh):
    """Ghi ra file tạm rồi mới đổi tên: phần NLP không bao giờ đọc phải file ghi dở."""
    THU_MUC_KET_QUA.mkdir(parents=True, exist_ok=True)
    tep_json = THU_MUC_KET_QUA / (duong_dan_am_thanh.stem + ".json")
    tep_tam = tep_json.with_suffix(".json.tmp")
    with open(tep_tam, "w", encoding="utf-8") as f:
        # ensure_ascii=False để tiếng Việt hiện đúng chữ, không thành ồ...
        json.dump(ket_qua, f, ensure_ascii=False, indent=2)
    os.replace(tep_tam, tep_json)
    return tep_json


# ======================================================================
# CHƯƠNG TRÌNH CHÍNH
# ======================================================================
def xu_ly_mot_file(model, duong_dan, loc_nhieu, tien_xu_ly_bat):
    print(f"\n=== {duong_dan.name} ===")
    bat_dau = time.time()

    song_am = doc_am_thanh(duong_dan)
    do_dai = len(song_am) / TAN_SO_MAU
    print(f"Độ dài: {do_dai / 60:.1f} phút")
    for cb in canh_bao_chat_luong(song_am):
        print(f"  ⚠ {cb}")

    if tien_xu_ly_bat:
        song_am, buoc = tien_xu_ly_am_thanh(song_am, loc_nhieu)
        print("Tiền xử lý: " + ", ".join(buoc))
    else:
        print("Tiền xử lý: tắt")

    print("Đang nhận dạng giọng nói, vui lòng chờ...")
    cac_tu, so_bi_loai = nhan_dang(model, song_am)
    ket_qua = tach_cau(cac_tu)
    if not ket_qua:
        # Không ghi file rỗng: src/tien_xu_ly/doc_transcript.py coi danh sách rỗng là lỗi
        raise LoiDauVao("Không nhận dạng được câu nào (file có thể không có tiếng nói), "
                        "không tạo file JSON.")
    tep_json = luu_json(ket_qua, duong_dan)

    thoi_gian = time.time() - bat_dau
    print(f"Đã lưu {len(ket_qua)} câu vào {hien_thi(tep_json)}")
    if so_bi_loai:
        print(f"Đã loại {so_bi_loai} đoạn nghi bị nhận dạng sai (xem các dòng [LOẠI] ở trên)")
    print(f"Thời gian xử lý: {thoi_gian:.1f} giây (gấp {thoi_gian / do_dai:.1f} lần độ dài file)")


def da_co_json(duong_dan):
    return (THU_MUC_KET_QUA / (duong_dan.stem + ".json")).exists()


def liet_ke_file(cac_duong_dan, ghi_de):
    """Nhận cả file lẻ lẫn thư mục.

    - File chỉ định trực tiếp: luôn chạy (kể cả khi đã có JSON).
    - Thư mục: lấy mọi file âm thanh bên trong, bỏ qua file đã có JSON
      (trừ khi có --ghi-de), để chạy cả thư mục nhiều lần không tốn thời gian.
    """
    danh_sach = []
    for p in map(Path, cac_duong_dan):
        if not p.is_dir():
            danh_sach.append(p)
            continue
        for f in sorted(p.iterdir()):
            if f.suffix.lower() not in DUOI_HO_TRO:
                continue
            if da_co_json(f) and not ghi_de:
                print(f"Bỏ qua {f.name} (đã có JSON, thêm --ghi-de để chạy lại)")
                continue
            danh_sach.append(f)
    return danh_sach


def main():
    parser = argparse.ArgumentParser(
        description="Chuyển file ghi âm cuộc họp thành transcript JSON."
    )
    parser.add_argument("duong_dan", nargs="+", help="File ghi âm hoặc thư mục chứa file ghi âm")
    parser.add_argument("--model", default=TEN_MODEL, help=f"Model Whisper (mặc định: {TEN_MODEL})")
    parser.add_argument("--loc-nhieu", action="store_true",
                        help="Bật giảm tạp âm (thử nghiệm, mặc định tắt vì có thể làm méo tiếng)")
    parser.add_argument("--khong-tien-xu-ly", action="store_true",
                        help="Tắt toàn bộ tiền xử lý (chỉ dùng để thử nghiệm so sánh)")
    parser.add_argument("--ghi-de", action="store_true",
                        help="Khi chạy cả thư mục: chạy lại cả những file đã có JSON")
    args = parser.parse_args()

    cac_file = liet_ke_file(args.duong_dan, args.ghi_de)

    # Loại file hỏng rõ ràng TRƯỚC khi tải model (tải model mất thời gian, lần đầu cần mạng)
    so_loi = 0
    hop_le = []
    for f in cac_file:
        try:
            kiem_tra_file(f)
            hop_le.append(f)
        except LoiDauVao as loi:
            so_loi += 1
            print(f"  ✗ {loi}")
    if not hop_le:
        sys.exit("Không có file nào cần xử lý.")

    # hop_01.mp3 và hop_01.wav đều ra hop_01.json -> file sau ghi đè file trước
    ten_da_gap = {}
    for f in hop_le:
        # So không phân biệt hoa/thường: trên Windows Hop.json và hop.json là một file
        if f.stem.lower() in ten_da_gap:
            print(f"  ⚠ {ten_da_gap[f.stem.lower()].name} và {f.name} cùng ra {f.stem}.json, "
                  "file sau sẽ ghi đè file trước. Nên đổi tên một file.")
        ten_da_gap[f.stem.lower()] = f

    # Tải model MỘT lần cho tất cả các file
    print(f"Đang tải model {args.model}...")
    bat_dau = time.time()
    try:
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
    except Exception as loi:
        sys.exit(
            f"Không tải được model {args.model}: {type(loi).__name__}: {loi}\n"
            "Lần chạy đầu cần internet để tải model (medium khoảng 1,5 GB), "
            "các lần sau dùng bản đã lưu trên máy."
        )
    print(f"Tải model xong ({time.time() - bat_dau:.1f} giây)")

    for duong_dan in hop_le:
        try:
            xu_ly_mot_file(model, duong_dan, args.loc_nhieu, not args.khong_tien_xu_ly)
        except LoiDauVao as loi:
            so_loi += 1
            print(f"  ✗ {loi}")
        except Exception as loi:
            # Lỗi bất ngờ (hết RAM, file JSON đang bị mở...): báo lỗi rồi chạy file tiếp theo
            so_loi += 1
            print(f"  ✗ Lỗi khi xử lý {duong_dan.name}: {type(loi).__name__}: {loi}")
            tep_tam = THU_MUC_KET_QUA / (duong_dan.stem + ".json.tmp")
            if tep_tam.exists():
                tep_tam.unlink()

    print(f"\nHoàn tất: {len(cac_file) - so_loi}/{len(cac_file)} file thành công.")
    if so_loi:
        sys.exit(1)


if __name__ == "__main__":
    main()
