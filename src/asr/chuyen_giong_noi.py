# -*- coding: utf-8 -*-
"""
Chuyển file ghi âm cuộc họp thành transcript JSON cho phần xử lý văn bản (src/nlp).

Luồng xử lý:
    1. Kiểm tra đầu vào  : file có tồn tại, đúng định dạng, đọc được, có tiếng nói
    2. Tiền xử lý âm thanh: bỏ lệch DC, lọc tiếng ù tần số thấp, chuẩn hóa âm lượng,
                            (tùy chọn) giảm tạp âm
    3. Nhận dạng giọng nói: faster-whisper, cắt từng lượt nói bằng VAD; chế độ chính xác dùng
                            PhoWhisper + đệm im lặng (xem CHE_DO), chế độ nhanh dùng Whisper medium
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
import dataclasses
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
from faster_whisper import BatchedInferencePipeline, WhisperModel, decode_audio
from faster_whisper.transcribe import Word, get_compression_ratio
from faster_whisper.vad import VadOptions, get_speech_timestamps

# In tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ======================================================================
# CẤU HÌNH
# ======================================================================
TEN_MODEL = "medium"            # Đã chốt qua thử nghiệm (xem thu_faster_whisper.py)
# Model khác: --model nhận tên model của faster-whisper (vd large-v3-turbo) hoặc thư mục model
# CTranslate2 (vd models/phowhisper-medium-ct2, tạo bằng src/asr/chuyen_doi_model.py)
# Nhận dạng từng lượt nói (nhan_dang tung_luot=True) là MẶC ĐỊNH. Đo trên cùng các đoạn:
#   4 file dài x 5 phút: 36,4% -> 29,9% (mất chữ 841 -> 507 từ), khoảng tin cậy 95% [-13,9; -0,1]
#   30 đoạn ngắn: 25,5% -> 25,4% (bằng nhau, [-0,8; +0,5]); đổi lại chậm hơn ở file dài (1,8x -> 3,0x)
TUNG_LUOT_MAC_DINH = True
# Hai chế độ của chuyen_giong_noi.py (--che-do). Đo 16/10 trên 30 + 30 đoạn, khoảng tin cậy 95% so với medium:
#   chinh_xac: PhoWhisper-medium (VinAI, tinh chỉnh cho tiếng Việt) + đệm im lặng thật + cắt chữ ngoài âm thanh:
#              họp 25,4% -> 20,4% (TỐT HƠN THẬT [-8,6; -1,0]), giọng miền 8,2% -> 5,6%; chậm hơn ~2,7 lần
#   nhanh    : PhoWhisper-small, cùng cách chạy. Đo 19/10 trên bộ kiểm tra GIỮ RIÊNG (100 + 100 đoạn):
#              họp 22,5% / giọng miền 8,5%, 1,4-1,9x độ dài ghi âm; so với chinh_xac (18,1% / 6,8%, 3,5-5,3x)
#              thì lỗi nhiều hơn nhưng nhanh gấp ~2,5 lần; so với Whisper medium (chế độ nhanh cũ: 23,3% / 10,1%,
#              3,5-5,1x) thì lỗi bằng hoặc ít hơn mà nhanh gấp ~2,5 lần, nên thay hẳn medium.
#   nhanh_nhat: tên cũ, giờ giống "nhanh" (Whisper small cũ lỗi nhiều hơn rõ: họp 31,0%, giọng miền 13,7%)
# Model PhoWhisper phải tự chuyển đổi một lần (src/asr/chuyen_doi_model.py); chưa có thì lùi về Whisper
# (medium cho chinh_xac, small cho nhanh) và báo cách tạo.
CHE_DO_MAC_DINH = "chinh_xac"
# Kiểu tính của model trên CPU. int8: nhanh, đủ chính xác. Đã đo: PhoWhisper bản float32 cũng không biết
# dừng y như int8 (lỗi nằm ở cách faster-whisper đệm cửa sổ, đã xử lý bằng đệm im lặng + cắt ngoài âm thanh)
KIEU_TINH = "int8"
# Đệm im lặng thật cho mỗi lượt nói đủ 30 giây trước khi nhận dạng (chế độ từng lượt).
# faster-whisper đệm phần thiếu của cửa sổ 30 giây bằng SỐ 0 trên phổ âm thanh đã tính, mà 0 không phải
# im lặng (im lặng thật là -1,12, tiếng nói ~0,9): Whisper gốc chịu được, nhưng PhoWhisper (huấn luyện với
# cách đệm im lặng thật của thư viện gốc) nghe "tiếng ồn" đó rồi nói tiếp, nối câu bịa sau lời thật.
# Đo: bản gốc transformers dừng đúng chỗ (43 token), faster-whisper sinh 132 token, kể cả khi tính float32.
DEM_IM_LANG = False             # mặc định của nhan_dang(); chế độ "chinh_xac" bật (xem CHE_DO)
# Gộp các lượt nói liền nhau thành nhóm <= 20 giây (gop_luot) ở hai chế độ PhoWhisper. Đo 19/10 trên bộ GIỮ RIÊNG:
#   chinh_xac: họp 18,1% -> 17,8% (-0,3 [-0,7; -0,0] TỐT HƠN THẬT), 3,55x -> 3,32x; giọng miền 6,8% -> 6,7%, 5,3x -> 5,1x;
#              file dài 26,7% -> 26,2%, 3,56x -> 2,98x
#   nhanh    : họp 22,5% -> 22,0% (-0,5 [-1,0; -0,0] TỐT HƠN THẬT), 1,40x -> 1,26x; giọng miền 8,4% -> 8,3%
# Chưa đo với Whisper gốc (medium/small lùi về khi thiếu PhoWhisper) nên ở đó không gộp.
# Đã thử thêm tách lượt ở khoảng ngừng 0,5 giây: một mình thì TỆ HƠN THẬT (họp 19,4%, chậm hơn); kèm gộp 20 giây
# thì bằng (họp 18,1%, giọng miền 6,6%) nhưng file dài tốt hơn (24,8% so với 26,2%, chỉ 4 file) -> chưa đổi,
# để bản ghi họp thật quyết định.
GOP_LUOT_MAC_DINH = 20
BEAM = 5                        # số nhánh dò chữ cùng lúc (beam search); 1 = dò tham lam, nhanh hơn


def so_nhan_that():
    """Số nhân CPU thật (không tính siêu phân luồng). Đo trên máy 2 nhân / 4 luồng: chạy 2 luồng nhanh
    hơn 4 luồng (mặc định của faster-whisper) 16-18%, chữ ra y hệt. 0 = không biết, để thư viện tự chọn."""
    try:
        import psutil
        return psutil.cpu_count(logical=False) or 0
    except Exception:
        return 0


SO_LUONG_CPU = so_nhan_that()   # số luồng CPU cho model = số nhân thật
SO_MAU_CUA_SO = 30 * 16000       # 30 giây ở 16 kHz (cửa sổ của Whisper)
TAN_SO_MAU = 16000              # Whisper làm việc ở 16 kHz, 1 kênh
# Chế độ từng lượt: bỏ chữ có điểm giữa nằm sau cuối âm thanh thật của lượt quá LE_CUOI_LUOT giây.
# Khi đệm im lặng tới 30 giây, chữ bịa (PhoWhisper không biết dừng) luôn nằm trong phần đệm
# (đo lượt 0000101, 0001753); 0,5 giây chừa cho mốc thời gian theo từ bị lệch nhẹ
LE_CUOI_LUOT = 0.5
# Tính theo vị trí file code (src/asr/ -> lên 2 cấp là thư mục project),
# nên chạy từ thư mục nào JSON cũng được lưu đúng chỗ phần NLP đọc.
THU_MUC_GOC = Path(__file__).resolve().parents[2]
THU_MUC_KET_QUA = THU_MUC_GOC / "data" / "transcripts"
MODEL_CHINH_XAC = THU_MUC_GOC / "models" / "phowhisper-medium-ct2"
MODEL_NHANH = THU_MUC_GOC / "models" / "phowhisper-small-ct2"
MODEL_DU_PHONG_NHANH = "small"   # Whisper small: chế độ nhanh khi chưa chuyển đổi PhoWhisper-small
GOI_Y_CHINH_XAC = "khong"


def chon_che_do(che_do, model=None):
    """Trả về (model dùng, có đệm im lặng không, cách gợi ý, cảnh báo hoặc None).

    Chế độ chính xác không dùng câu gợi ý mở đầu: đo bật/tắt trên PhoWhisper (17/10), bỏ gợi ý thì
    giọng miền 5,6% -> 4,5% (TỐT HƠN THẬT), họp 20,3% -> 19,1%, lại nhanh hơn. (Với medium câu gợi ý
    vẫn có ích: 28,2% -> 25,6% lúc chọn cách gợi ý.)"""
    if che_do == "chinh_xac":
        if model:
            return model, True, GOI_Y_CHINH_XAC, None
        if (Path(MODEL_CHINH_XAC) / "model.bin").exists():
            return str(MODEL_CHINH_XAC), True, GOI_Y_CHINH_XAC, None
        return TEN_MODEL, False, GOI_Y_MAC_DINH, (
            f"Chưa có model chính xác ({hien_thi(Path(MODEL_CHINH_XAC))}), tạm dùng Whisper {TEN_MODEL} (lỗi nhiều hơn). "
            "Tạo model một lần: python src/asr/chuyen_doi_model.py")
    # "nhanh" (và tên cũ "nhanh_nhat")
    if model:
        # Họ PhoWhisper cần đệm im lặng và không gợi ý; Whisper gốc thì ngược lại (xem GOI_Y_CHINH_XAC)
        if "phowhisper" in str(model).lower():
            return model, True, GOI_Y_CHINH_XAC, None
        return model, False, GOI_Y_MAC_DINH, None
    if (Path(MODEL_NHANH) / "model.bin").exists():
        return str(MODEL_NHANH), True, GOI_Y_CHINH_XAC, None
    return MODEL_DU_PHONG_NHANH, False, GOI_Y_MAC_DINH, (
        f"Chưa có model nhanh ({hien_thi(Path(MODEL_NHANH))}), tạm dùng Whisper {MODEL_DU_PHONG_NHANH} (lỗi nhiều hơn rõ). "
        "Tạo model một lần: python src/asr/chuyen_doi_model.py vinai/PhoWhisper-small")
DUOI_HO_TRO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma", ".webm", ".mp4"}

# Câu mở đầu (initial_prompt): chỉ có tác dụng ở ~30 giây đầu, giúp model vào đúng
# "giọng văn" cuộc họp. Đo trên bộ đánh giá: tốt nhất cho đoạn họp trực tuyến (23,2% so với
# 27,4% khi không gợi ý) và giữ được câu đầu ("Mày, mày đền đi") mà không gợi ý thì mất.
# Đôi khi model chép lại câu này -> bộ lọc "đọc lại câu mở đầu" bên dưới.
GOI_Y_MAC_DINH = "cau_mo_dau"
# Các mức nhiệt độ model thử lại khi kết quả có vẻ hỏng. Mặc định của faster-whisper thử tới
# 1.0; trên bộ đánh giá các đoạn bị kẹt (81-347 giây cho 4 giây âm thanh) đều ra chữ bịa
# hoặc trống, nên chỉ thử tới 0.4: không đổi WER, nhanh hơn, không còn đoạn kẹt.
NHIET_DO_THU_LAI = (0.0, 0.2, 0.4)
SO_KHUC_MOI_LO = 4   # chế độ theo khúc (chỉ để so sánh, đã bỏ): số khúc nhận dạng cùng lúc
# Thông số VAD (Silero) dùng chung cho mọi chế độ
THONG_SO_VAD = {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,    # bỏ tiếng động ngắn (gõ bàn, ho)
    "min_silence_duration_ms": 1000,  # ngừng 1 giây mới coi là hết đoạn
    "speech_pad_ms": 400,             # chừa lề để không cụt đầu/cuối chữ
}
DO_DAI_LUOT_TOI_DA = 25.0   # chế độ từng lượt: lượt nói dài hơn thì VAD cắt nhỏ (Whisper nghe 30 giây/lần)
# Chế độ từng lượt: lượt dài từ LUOT_XET_MAT_DO giây mà ra ít hơn MAT_DO_TOI_THIEU chữ/giây
# (sau khi bỏ câu bịa) là model đã nghe hỏng cả lượt -> nhận dạng lại. Người Việt nói
# ~4-6 tiếng/giây nên 1 chữ/giây là ngưỡng rất thấp, chỉ bắt lượt hỏng thật.
# Ví dụ đo được (đoạn hop_va_dien_thoai_0000186): lượt 9,7 giây chỉ ra "Cảm ơn các bạn."
LUOT_XET_MAT_DO = 3.0
MAT_DO_TOI_THIEU = 1.0
# Chế độ từng lượt: số token model được sinh tối đa cho một lượt, theo độ dài lượt. Người nói
# nhanh ~8 tiếng/giây, mỗi tiếng Việt ~2-3 token -> 20 token/giây là rộng rãi cho lời thật.
# Không giới hạn thì khi model bịa nó sinh tới ~440 token rồi thử lại ở nhiệt độ khác, lại
# ~440 token: đo được PhoWhisper mất 243 giây cho đoạn 9 giây (12x độ dài, medium 3,7x)
TOKEN_MOI_GIAY = 20
TOKEN_CONG_THEM = 30
TOKEN_TOI_DA = 380              # chừa chỗ cho câu mở đầu trong giới hạn 448 token của Whisper
CAU_MO_DAU = "Cuộc họp nhóm, có dùng một số từ tiếng Anh."
# Cụm 4 từ liền nhau của câu mở đầu, trừ cụm đầu "cuộc họp nhóm có" (người họp nói thật
# "cuộc họp nhóm có ba người"); gặp các cụm còn lại trong đoạn ngắn là model đọc lại gợi ý
_TU_MO_DAU = re.sub(r"\W+", " ", CAU_MO_DAU.lower()).split()
CUM_4_TU_MO_DAU = {" ".join(_TU_MO_DAU[i:i + 4]) for i in range(1, len(_TU_MO_DAU) - 3)}

# Từ khóa gợi ý (hotwords): faster-whisper gắn vào MỌI đoạn 30 giây.
# KHÔNG DÙNG MẶC ĐỊNH NỮA. Đo trên 30 đoạn họp/gọi điện (src/asr/danh_gia_bo.py, cùng tập):
#     câu mở đầu + từ khóa 28,2% | chỉ từ khóa 35,8% | không gợi ý 25,8% | chỉ câu mở đầu 25,6%
# Có từ khóa thì model hay rút câu thành dạng liệt kê ("check customer, check staff, check
# row"), bịa câu kiểu YouTube và bị kẹt hàng trăm giây; từ tiếng Anh (customer, staff) vẫn
# nghe đúng khi không có từ khóa. Giữ danh sách để bộ lọc nhận ra khi model đọc lại nó.
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
# ("Phụ đề được thực hiện bởi cộng đồng Amara.org", "Vietsub by ..." là câu cuối phụ đề
#  Whisper học thuộc. "phụ đề"/"vietsub" vẫn có thể là chuyện thật của team làm video,
#  nên để ở loại NGHI.)
MAU_CAU_BIA_CHAC = re.compile(
    r"ghiền mì gõ|thanks for watching|amara\.org|"
    # Câu kết video large-v3 bịa ra khi tự tin (đo 15/10: 7/30 đoạn họp, lọt bộ lọc vì model không
    # "nghi"). Chỉ bắt dạng kêu gọi kiểu YouTube; câu họp thật "tăng lượt subscribe cho kênh của
    # khách hàng" không khớp
    r"hãy (?:subscribe|đăng k[ýí]) (?:cho )?kênh|ủng hộ kênh của (?:mình|chúng tôi)|"
    r"để không bỏ lỡ (?:những |các )?video",
    re.IGNORECASE)
MAU_CAU_BIA_NGHI = re.compile(
    r"subscribe|like và share|bấm chuông|đăng ký kênh|vietsub|"
    r"phụ đề (?:được thực hiện )?bởi|"
    r"hẹn gặp lại các bạn trong (?:những )?video|"
    r"cảm ơn các bạn đã (?:theo dõi|xem|lắng nghe)",
    re.IGNORECASE,
)
SO_TU_TOI_DA_CAU_BIA = 15
SO_TU_TOI_DA_CAU_BIA_CHAC = 30     # mẫu chắc chắn là bịa: model hay nối 2 câu kết video liền nhau
NGUONG_NGHI_KHONG_CO_TIENG = 0.3   # no_speech_prob trên mức này: model nghi không có người nói
NGUONG_NGHI_DO_TIN_CAY = -1.0      # avg_logprob dưới mức này: model không chắc chữ vừa ra
                                   # (-1.0 là ngưỡng "không chắc" của chính Whisper; để cao hơn
                                   #  sẽ loại oan câu thật trong phòng ồn)

SO_CUM_LUON_LOAI = 5               # chuỗi >= 5 từ khóa gợi ý liền nhau: loại dù model tự tin

# Ngưỡng lọc. (Đoạn "không có tiếng nói" faster-whisper đã tự bỏ qua bên trong,
# với no_speech_prob > 0.6 và avg_logprob <= -1.0, nên ở đây không lọc lại.)
NGUONG_LAP_LAI = 2.4            # compression_ratio cao -> chữ bị lặp vòng
SO_TU_TOI_THIEU_LOC_TRUNG = 4   # câu ngắn lặp lại ("Dạ.", "Ok.") là bình thường, không xóa
# Tốc độ nói bất khả thi: người nói nhanh cũng chỉ ~7-8 tiếng/giây. Câu bịa có mốc thời gian dồn
# vào một khoảnh khắc: đo được "một số khán giả đã tham gia vào đêm thi đấu tại việt nam"
# 12 từ trong 0,08 giây (PhoWhisper), "Cảm ơn các bạn đã theo dõi" 6 từ trong 0,04 giây (medium),
# trong khi lời thật cùng đoạn là 26 từ / 6,6 giây (4 từ/giây)
TOC_DO_NOI_TOI_DA = 12.0        # từ/giây
SO_TU_XET_TOC_DO = 3            # 1-2 từ ("Dạ.", "Ok.") thì mốc thời gian không đủ tin để xét

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


# Chữ rác model sinh ra trong một đoạn nghe được (không phải cả đoạn bịa nên bộ lọc đoạn không bắt):
#   "unk": PhoWhisper in thẳng tên ký hiệu "không biết" của bộ tách từ ("phạm tội unk có..."), tiếng Việt
#          không có từ này; gặp ở đoạn điện thoại khó nghe và file dài
#   một "từ" là một mẩu 1-4 chữ cái lặp >= 4 lần liền nhau, không có khoảng trắng ("vnvnvnvn...", ở đoạn
#          0000119): model kẹt vòng bên trong một từ nên luật "lặp chữ" (tính trên cả đoạn) không bắt được.
#          Âm tiết tiếng Việt không có dạng này; từ tiếng Anh dài thật (orthomyxoviridae) không bị bắt.
# Luật chung, không theo từng từ cụ thể. Thấy trên bộ giữ riêng nên đã ghi rõ trong nhật ký.
MAU_TU_LAP_VONG = re.compile(r"(\w{1,4}?)\1{3,}\w{0,3}")
SO_CHU_TOI_THIEU_TU_LAP_VONG = 8


def la_tu_rac(chu):
    loi = re.sub(r"[\W_]+", "", chu.lower())
    if loi == "unk":
        return True
    return len(loi) >= SO_CHU_TOI_THIEU_TU_LAP_VONG and bool(MAU_TU_LAP_VONG.fullmatch(loi))


def gon_dau_cham(chu):
    """"lại........" -> "lại..." (model kẹt sinh dấu chấm vòng; WER bỏ dấu câu nhưng bên tóm tắt đọc text)."""
    return re.sub(r"\.{4,}", "...", chu)


def lam_sach_van_ban(van_ban):
    """Bỏ chữ rác, gọn dấu chấm lặp. Dùng khi chỉ có chữ của đoạn (chấm lại kết quả cũ, đoạn không có mốc từ)."""
    return " ".join(gon_dau_cham(c) for c in van_ban.split() if not la_tu_rac(c))


def lam_sach_tu(cac_tu):
    """Như lam_sach_van_ban nhưng trên danh sách từ có mốc thời gian (giữ mốc của các từ còn lại)."""
    ket_qua = []
    for t in cac_tu:
        if la_tu_rac(t.word):
            continue
        moi = gon_dau_cham(t.word)
        ket_qua.append(t if moi == t.word else dataclasses.replace(t, word=moi))
    return ket_qua


def ly_do_loai(doan, goi_y="day_du"):
    """Trả về lý do nếu đoạn có dấu hiệu Whisper "bịa chữ", ngược lại trả về None.

    goi_y: cách gợi ý đã dùng khi nhận dạng. Luật "đọc lại từ khóa / câu mở đầu" chỉ bật khi đã
    gợi ý đúng thứ đó: không gợi ý thì model không thể đọc lại, mà luật có thể xóa nhầm câu liệt kê thật
    ("Frontend, backend, database, API, deploy") — góp ý phản biện 18/10."""
    van_ban = doan.text.strip()
    if not van_ban:
        return "rỗng"
    if not lam_sach_van_ban(van_ban):
        return "chữ rác"
    so_tu = len(van_ban.split())
    if so_tu >= SO_TU_XET_TOC_DO and so_tu > TOC_DO_NOI_TOI_DA * max(doan.end - doan.start, 0.0):
        return "tốc độ nói bất khả thi"
    # Chữ bị lặp vòng (vd: "cảm ơn cảm ơn cảm ơn..."). Tính lại tỉ lệ nén trên chữ
    # của RIÊNG đoạn này: doan.compression_ratio của faster-whisper tính cho cả cửa sổ
    # 30 giây, dùng nó sẽ loại oan cả những câu thật nằm chung cửa sổ.
    if len(van_ban) > 20 and get_compression_ratio(van_ban) > NGUONG_LAP_LAI:
        return "lặp chữ"
    model_khong_chac = (doan.no_speech_prob > NGUONG_NGHI_KHONG_CO_TIENG
                        or doan.avg_logprob < NGUONG_NGHI_DO_TIN_CAY)
    # Câu bịa kiểu YouTube (chỉ xét đoạn ngắn)
    if len(van_ban.split()) <= SO_TU_TOI_DA_CAU_BIA_CHAC and MAU_CAU_BIA_CHAC.search(van_ban):
        return "câu bịa kiểu YouTube"
    if len(van_ban.split()) <= SO_TU_TOI_DA_CAU_BIA:
        if MAU_CAU_BIA_NGHI.search(van_ban) and model_khong_chac:
            return "câu bịa kiểu YouTube"
    # Whisper đọc lại danh sách từ khóa gợi ý (hay gặp ở chỗ ồn hoặc im lặng)
    cum = [c.strip().lower().rstrip(".") for c in van_ban.split(",")]
    # Chỉ khi là một chuỗi cụm ngắn gần như toàn từ khóa, tránh loại câu thật như
    # "Hôm nay mình review, test, demo.". Người họp cũng có thể liệt kê thật
    # ("Frontend, backend, database, API."), nên chuỗi 4 cụm chỉ loại khi model
    # không chắc; từ SO_CUM_LUON_LOAI cụm trở lên thì gần như chắc là đọc lại gợi ý.
    if (goi_y in ("day_du", "tu_khoa") and len(cum) >= 4 and all(len(c.split()) <= 2 for c in cum)
            and sum(c in TAP_TU_GOI_Y for c in cum) / len(cum) >= 0.8
            and (model_khong_chac or len(cum) >= SO_CUM_LUON_LOAI)):
        return "đọc lại từ khóa gợi ý"
    # Đọc lại câu mở đầu, kể cả chỉ một phần ("Còn một số từ tiếng Anh."): đo trên bộ
    # đánh giá thấy ở đoạn khó nghe (điện thoại) model chép lại gợi ý thay vì lời thật
    if goi_y not in ("day_du", "cau_mo_dau"):
        return None
    cac_tu = chuan_hoa_so_sanh(van_ban).split()
    if len(cac_tu) <= SO_TU_TOI_DA_CAU_BIA and any(
            " ".join(cac_tu[i:i + 4]) in CUM_4_TU_MO_DAU for i in range(len(cac_tu) - 3)):
        return "đọc lại câu mở đầu"
    if chuan_hoa_so_sanh(van_ban) == chuan_hoa_so_sanh(CAU_MO_DAU):
        return "đọc lại câu mở đầu"
    return None


def loi_thu_muc_model(ten_model):
    """--model là đường dẫn thư mục (vd models/phowhisper-medium-ct2) mà thư mục chưa có hoặc thiếu
    model.bin: báo rõ thay vì để faster-whisper đi tìm trên mạng rồi báo lỗi 401 khó hiểu."""
    if not re.search(r"[\\/]", ten_model):
        return None   # tên model có sẵn của faster-whisper (medium, large-v3-turbo...)
    thu_muc = Path(ten_model)
    if not thu_muc.is_absolute():
        thu_muc = Path.cwd() / thu_muc
    if not (thu_muc / "model.bin").exists():
        return (f"Chưa có model ở {ten_model} (không thấy model.bin). Nếu là model tự chuyển đổi, "
                "chạy trước: python src/asr/chuyen_doi_model.py (xem --help)")
    return None


def cat_luot_noi(song_am, ngung_ms=None):
    """VAD cắt file thành các lượt nói (ngừng >= 1 giây là sang lượt mới), mỗi lượt <= 25 giây.

    ngung_ms: đổi độ dài khoảng ngừng tối thiểu (chỉ để đo, danh_gia_bo.py --vad-ngung).
    Trả về [(mẫu bắt đầu, mẫu kết thúc)].
    """
    thong_so = dict(THONG_SO_VAD, **({"min_silence_duration_ms": ngung_ms} if ngung_ms else {}))
    vad = VadOptions(**thong_so, max_speech_duration_s=DO_DAI_LUOT_TOI_DA)
    return [(d["start"], d["end"]) for d in get_speech_timestamps(song_am, vad, sampling_rate=TAN_SO_MAU)]


def gop_luot(cac_luot, toi_da_giay):
    """Gộp các lượt nói liền nhau thành nhóm dài tối đa toi_da_giay (từ đầu lượt đầu tới cuối lượt cuối,
    giữ nguyên khoảng lặng thật ở giữa). 0 = không gộp.

    Vì sao: mỗi lần nghe tốn trọn một cửa sổ 30 giây (~21 giây trên máy 2 nhân) dù lượt chỉ dài 1 giây
    ("dạ", "ừ"); họp thật có rất nhiều lượt ngắn như vậy. Gộp lại thì ít cửa sổ hơn (góp ý phản biện 18/10).
    Đo 19/10 trên bộ GIỮ RIÊNG (PhoWhisper, đệm im lặng): gộp 20 giây chính xác hơn thật mà nhanh hơn, nên là
    mặc định của hai chế độ PhoWhisper (GOP_LUOT_MAC_DINH)."""
    if toi_da_giay <= 0:
        return list(cac_luot)
    nhom = []
    for bat_dau, ket_thuc in cac_luot:
        if nhom and (ket_thuc - nhom[-1][0]) / TAN_SO_MAU <= toi_da_giay:
            nhom[-1] = (nhom[-1][0], ket_thuc)
        else:
            nhom.append((bat_dau, ket_thuc))
    return nhom


def doi_moc_thoi_gian(doan, lech):
    """Cộng thêm `lech` giây vào mốc thời gian của đoạn và các từ (lượt nói nằm giữa file)."""
    cac_tu = [dataclasses.replace(t, start=t.start + lech, end=t.end + lech) for t in doan.words] \
        if doan.words else doan.words
    return dataclasses.replace(doan, start=doan.start + lech, end=doan.end + lech, words=cac_tu)


def nhan_dang(model, song_am, goi_y=GOI_Y_MAC_DINH, nhiet_do=NHIET_DO_THU_LAI, theo_khuc=False,
              tung_luot=False, nhat_ky=None, khong_moc_thoi_gian=False, dem_im_lang=None, beam=None,
              token_moi_giay=None, token_cong_them=None, nghe_lai=True, cat_ngoai=True, gop=0,
              le_cuoi=None, ngung_ms=None):
    """Nhận dạng giọng nói, trả về danh sách từ (có mốc thời gian) và số đoạn bị loại.

    Các tham số dưới chỉ đổi khi đánh giá so sánh (src/asr/danh_gia_bo.py):
    goi_y    : "cau_mo_dau" (mặc định) = chỉ câu mở đầu; "day_du" = câu mở đầu + từ khóa;
               "tu_khoa" = chỉ từ khóa; "khong" = không gợi ý gì
    nhiet_do : các mức nhiệt độ thử lại; None = mặc định của faster-whisper (thử tới 1.0)
    theo_khuc: True = BatchedInferencePipeline của faster-whisper (gom lời nói thành khúc 30 giây,
               nhận dạng theo lô). Đo trên file dài: TỆ HƠN (36,4% -> 47,0%, mất chữ nhiều hơn)
    tung_luot: True = tự cắt file theo từng lượt nói (cat_luot_noi) rồi nhận dạng từng lượt như
               một file ngắn. Đo trên file dài: 36,4% -> 30,5% (mất chữ 841 -> 568 từ),
               chậm hơn (1,8x -> 2,9x độ dài ghi âm). Lượt ra quá ít chữ (luot_hong) thì nhận
               dạng lại (nghe_lai_luot)
    khong_moc_thoi_gian: True = model không đoán mốc thời gian theo đoạn (without_timestamps; mốc theo
               từ vẫn có). Cần cho model tinh chỉnh không kèm mốc thời gian như PhoWhisper: để
               mặc định thì nó nghe đúng lời nhưng không biết dừng, bịa thêm câu ở cuối
               ("cảm ơn và hẹn gặp lại", "dự án thứ trung quốc...": thừa 151-217 từ / 30 đoạn)
    token_moi_giay, token_cong_them: giới hạn số token model được sinh mỗi lượt
               (= token_moi_giay x số giây + token_cong_them, tối đa TOKEN_TOI_DA); None = mặc định.
               PhoWhisper không biết dừng nên luôn sinh tới giới hạn: giới hạn càng sát càng nhanh
    le_cuoi : lề sau cuối lượt (giây) khi cắt chữ ngoài âm thanh thật; None = LE_CUOI_LUOT
    ngung_ms: khoảng ngừng tối thiểu để VAD tách lượt (ms); None = THONG_SO_VAD (1000)
    gop     : gộp các lượt liền nhau thành nhóm dài tối đa chừng này giây (gop_luot); 0 = không gộp
    nghe_lai, cat_ngoai: chỉ để đo bật/tắt từng thành phần (False = tắt nhận dạng lại lượt hỏng /
               tắt cắt chữ sau cuối âm thanh thật của lượt)
    nhat_ky  : truyền vào một list để ghi chi tiết từng đoạn model trả về (mốc thời gian, độ tin cậy,
               xác suất không có tiếng, nhiệt độ đã dùng, có bị loại không) và các lượt VAD cắt ra.
               Dùng để chẩn đoán vì sao một đoạn bị sai (danh_gia_bo.py --chi-doan)
    """
    if dem_im_lang is None:
        dem_im_lang = DEM_IM_LANG
    le_cuoi = LE_CUOI_LUOT if le_cuoi is None else le_cuoi
    token_moi_giay = TOKEN_MOI_GIAY if token_moi_giay is None else token_moi_giay
    token_cong_them = TOKEN_CONG_THEM if token_cong_them is None else token_cong_them
    if goi_y not in ("day_du", "tu_khoa", "cau_mo_dau", "khong"):
        raise ValueError(f"goi_y không hợp lệ: {goi_y!r}")
    dung_cau_mo_dau = goi_y in ("day_du", "cau_mo_dau")
    dung_tu_khoa = goi_y in ("day_du", "tu_khoa")
    them = {"temperature": list(nhiet_do)} if nhiet_do else {}
    tham_so_chung = dict(language="vi", beam_size=beam or BEAM,
                         initial_prompt=CAU_MO_DAU if dung_cau_mo_dau else None,
                         hotwords=TU_KHOA_GOI_Y if dung_tu_khoa else None,
                         word_timestamps=True, without_timestamps=khong_moc_thoi_gian)
    if tung_luot:
        cac_luot = gop_luot(cat_luot_noi(song_am, ngung_ms) if ngung_ms else cat_luot_noi(song_am), gop)

        def nghe_doan(tu, den, **doi):
            # Không chạy VAD lần nữa trong lượt: đã đo bật VAD ở đây thì TỆ HƠN cả hai bộ
            # (file dài 30,5% -> 31,8%, 30 đoạn ngắn 27,7% -> 29,3%) mà vẫn không hết bịa câu
            so_token = int(token_moi_giay * (den - tu) / TAN_SO_MAU) + token_cong_them
            tham_so = dict(tham_so_chung, **them, condition_on_previous_text=False, vad_filter=False,
                           max_new_tokens=min(so_token, TOKEN_TOI_DA))
            tham_so.update(doi)
            am_thanh = song_am[tu:den]
            if dem_im_lang and len(am_thanh) < SO_MAU_CUA_SO:
                am_thanh = np.pad(am_thanh, (0, SO_MAU_CUA_SO - len(am_thanh)))
            doan, _ = model.transcribe(am_thanh, **tham_so)
            het = (den - tu) / TAN_SO_MAU + le_cuoi
            if not cat_ngoai:
                return [doi_moc_thoi_gian(d, tu / TAN_SO_MAU) for d in doan]
            # Chỗ hết lời = cuối lượt trừ lề VAD. Phản biện lần hai (18/10) lo rằng khi lề bị cụt (lượt cắt cứng,
            # khoảng ngừng ngắn, lượt cuối file) mốc này rơi vào giữa lời và làm mất chữ. Đã đo cả hai cách:
            # chỉ dùng khi chắc có lề -> số từ bị thiếu Y HỆT (63/9 đoạn ngắn, 466 file dài) nhưng chậm lại
            # 4,1x -> 6,2x (đoạn ngắn hầu hết là lượt cuối file). Nên dùng cho mọi lượt; nhật ký vẫn ghi mỗi lần dừng.
            het_loi = (den - tu) / TAN_SO_MAU - THONG_SO_VAD["speech_pad_ms"] / 1000 if dem_im_lang else None
            lay = dung_khi_qua_am_thanh(doan, het, het_loi)
            if nhat_ky is not None and het_loi is not None and lay and het_loi <= lay[-1].end < het:
                nhat_ky.append({"dung_o_cho_het_loi": round(tu / TAN_SO_MAU + lay[-1].end, 2)})
            doan, chu_bo = cat_ngoai_am_thanh(lay, het)
            if chu_bo:
                print(f"  [LOẠI - ngoài âm thanh thật của lượt] {chu_bo}")
                if nhat_ky is not None:
                    nhat_ky.append({"ngoai_am_thanh": chu_bo, "sau_giay": round(den / TAN_SO_MAU, 2)})
            return [doi_moc_thoi_gian(d, tu / TAN_SO_MAU) for d in doan]

        cac_doan = []
        for i, (bat_dau, ket_thuc) in enumerate(cac_luot):
            if nhat_ky is not None:
                nhat_ky.append({"luot": [round(bat_dau / TAN_SO_MAU, 2), round(ket_thuc / TAN_SO_MAU, 2)]})
            doan_luot = nghe_doan(bat_dau, ket_thuc)
            if nghe_lai and luot_hong(doan_luot, bat_dau, ket_thuc, goi_y):
                doan_luot = nghe_lai_luot(nghe_doan, cac_luot, i, doan_luot, nhat_ky, goi_y)
            cac_doan.extend(doan_luot)
        return loc_doan(cac_doan, nhat_ky, goi_y)
    if theo_khuc:
        bo_nhan_dang = BatchedInferencePipeline(model)
        them["batch_size"] = SO_KHUC_MOI_LO
    else:
        bo_nhan_dang = model
        # Không dựa vào chữ của đoạn trước: chặn lỗi lặp vòng ở file dài.
        # (Chế độ theo khúc luôn nhận dạng từng khúc độc lập nên không cần.)
        them["condition_on_previous_text"] = False
    cac_doan, _ = bo_nhan_dang.transcribe(song_am, **tham_so_chung, **them,
                                          vad_filter=True, vad_parameters=dict(THONG_SO_VAD))
    return loc_doan(cac_doan, nhat_ky, goi_y)


def chi_tiet_doan(doan, ly_do):
    """Các chỉ số model tự báo về một đoạn, để biết đoạn sai vì nghe kém, vì bịa hay vì bị loại."""
    return {"start": round(doan.start, 2), "end": round(doan.end, 2), "text": doan.text.strip(),
            "do_tin_cay": round(doan.avg_logprob, 3), "khong_co_tieng": round(doan.no_speech_prob, 3),
            "ty_le_nen": round(doan.compression_ratio, 2), "nhiet_do": getattr(doan, "temperature", None),
            "so_token": len(doan.tokens or []), "loai": ly_do}


def so_chu_that(cac_doan, goi_y="day_du"):
    """Số chữ còn lại sau khi bỏ các đoạn bộ lọc coi là bịa."""
    return sum(len(d.text.split()) for d in cac_doan if not ly_do_loai(d, goi_y))


def luot_hong(cac_doan, bat_dau, ket_thuc, goi_y="day_du"):
    """Lượt nói đủ dài mà ra quá ít chữ thật: model đã nghe hỏng (thường là bịa câu kết video)."""
    giay = (ket_thuc - bat_dau) / TAN_SO_MAU
    return giay >= LUOT_XET_MAT_DO and so_chu_that(cac_doan, goi_y) < MAT_DO_TOI_THIEU * giay


def cat_theo_khoang(cac_doan, tu_giay, den_giay):
    """Chỉ giữ các từ có điểm giữa nằm trong [tu_giay, den_giay), dựng lại đoạn từ các từ đó."""
    ket_qua = []
    for doan in cac_doan:
        cac_tu = [t for t in (doan.words or []) if tu_giay <= (t.start + t.end) / 2 < den_giay]
        if cac_tu:
            ket_qua.append(dataclasses.replace(doan, start=cac_tu[0].start, end=cac_tu[-1].end, words=cac_tu,
                                               text="".join(t.word for t in cac_tu)))
    return ket_qua


def dung_khi_qua_am_thanh(cac_doan, het_giay, het_loi=None):
    """Lấy các đoạn faster-whisper trả về (lần lượt từng cửa sổ 30 giây), dừng ngay sau đoạn đầu tiên
    kéo qua cuối âm thanh thật.

    Khi đệm im lặng, PhoWhisper không biết dừng: faster-whisper thấy câu chưa kết thúc liền mở THÊM cửa
    sổ ngay trong phần đệm, mỗi cửa sổ phải nghe lại 30 giây (đo trên máy 2 nhân: ~21 giây mỗi lần;
    6 lượt nói thành 15 lần nghe, medium chỉ 6). Các đoạn nối tiếp nhau theo thời gian, nên mọi đoạn sau
    một đoạn đã kéo qua cuối âm thanh thật đều nằm hẳn trong phần đệm: ngừng lấy tiếp không mất lời thật
    nào (chữ ở đó đằng nào cũng bị cat_ngoai_am_thanh bỏ). Đoạn kéo qua thì vẫn giữ, cắt theo từ sau.
    Bản đầu chỉ dừng khi đoạn BẮT ĐẦU sau cuối âm thanh: 15 -> 12 lần nghe, vì đoạn dở dang cuối cửa sổ
    đầu (kéo tới hết 30 giây) chưa làm nó dừng.

    het_loi: chỗ hết lời theo VAD (cuối lượt trừ lề VAD tự thêm). Đo 17/10: vẫn 2 cửa sổ mỗi lượt vì
    cửa sổ đầu kết thúc gọn ở cuối lời (mốc < cuối lượt), faster-whisper liền mở cửa sổ mới từ đó, toàn
    phần đệm. Đoạn đã chạm chỗ hết lời thì phần còn lại chỉ là lề im lặng VAD thêm vào: dừng."""
    lay = []
    for doan in cac_doan:
        lay.append(doan)
        if doan.end >= het_giay or (het_loi is not None and doan.end >= het_loi):
            break
    return lay


def cat_ngoai_am_thanh(cac_doan, den_giay):
    """Bỏ các từ BẮT ĐẦU từ den_giay trở đi (nằm trong phần im lặng đệm thêm, không có tiếng thật).

    Xét theo mốc bắt đầu chứ không theo điểm giữa (đổi 18/10): trên bộ giữ riêng, từ thật cuối lượt đôi khi
    bị dò mốc kéo dài sang phần đệm ("...hai trường hợp", "bye bye sếp") nên điểm giữa vượt ngưỡng và bị cắt
    oan; câu bịa thì bắt đầu hẳn trong phần đệm.

    Đoạn không mất từ nào giữ nguyên; đoạn mất hết từ thì bỏ; đoạn không có mốc theo từ thì xét
    theo mốc bắt đầu. Trả về (các đoạn giữ lại, chữ đã bỏ).
    """
    giu, bo = [], []
    for doan in cac_doan:
        if not doan.words:
            if doan.start < den_giay:
                giu.append(doan)
            else:
                bo.append(doan.text.strip())
            continue
        trong = [t for t in doan.words if t.start < den_giay]
        ngoai = [t for t in doan.words if t.start >= den_giay]
        if not ngoai:
            giu.append(doan)
            continue
        bo.append("".join(t.word for t in ngoai).strip())
        if trong:
            giu.append(dataclasses.replace(doan, start=trong[0].start, end=trong[-1].end, words=trong,
                                           text="".join(t.word for t in trong)))
    return giu, " ".join(b for b in bo if b)


def nghe_lai_luot(nghe_doan, cac_luot, i, ban_dau, nhat_ky=None, goi_y="day_du"):
    """Nhận dạng lại một lượt bị hỏng, thử lần lượt:
        1. bỏ câu mở đầu (gợi ý có thể đẩy model sang "giọng" kết video)
        2. nghe cả lượt trước và lượt sau cho đủ ngữ cảnh (giống chế độ mặc định, vốn nghe đúng
           đoạn 0000186), rồi chỉ giữ chữ nằm trong lượt này
    Lấy cách đầu tiên đạt mật độ chữ; không cách nào đạt thì lấy cách ra nhiều chữ thật nhất.
    Không dùng câu mở đầu (chế độ chính xác) thì bỏ cách 1: chạy lại y hệt, tốn thêm một lần nghe.
    """
    bat_dau, ket_thuc = cac_luot[i]
    tu = cac_luot[i - 1][0] if i > 0 else bat_dau
    den = cac_luot[i + 1][1] if i + 1 < len(cac_luot) else ket_thuc
    if (den - tu) / TAN_SO_MAU > DO_DAI_LUOT_TOI_DA:   # quá 25 giây thì chỉ thêm lượt sau hoặc trước
        tu, den = (bat_dau, den) if (den - bat_dau) / TAN_SO_MAU <= DO_DAI_LUOT_TOI_DA else (tu, ket_thuc)
        if (den - tu) / TAN_SO_MAU > DO_DAI_LUOT_TOI_DA:
            tu, den = bat_dau, ket_thuc
    cac_cach = ([("bỏ câu mở đầu", lambda: nghe_doan(bat_dau, ket_thuc, initial_prompt=None))]
                if goi_y in ("day_du", "cau_mo_dau") else [])
    if (tu, den) != (bat_dau, ket_thuc):
        cac_cach.append(("nghe kèm lượt bên cạnh", lambda: cat_theo_khoang(
            nghe_doan(tu, den), bat_dau / TAN_SO_MAU, ket_thuc / TAN_SO_MAU)))
    tot_nhat, ten_tot = ban_dau, "giữ kết quả đầu"
    if nhat_ky is not None:
        nhat_ky.append({"thu_lai": "lần đầu", "so_chu": so_chu_that(ban_dau, goi_y),
                        "chu": " ".join(d.text.strip() for d in ban_dau)[:150]})
    for ten, cach in cac_cach:
        thu = cach()
        if nhat_ky is not None:
            nhat_ky.append({"thu_lai": ten, "so_chu": so_chu_that(thu, goi_y),
                            "chu": " ".join(d.text.strip() for d in thu)[:150]})
        if not luot_hong(thu, bat_dau, ket_thuc, goi_y) or so_chu_that(thu, goi_y) > so_chu_that(tot_nhat, goi_y):
            tot_nhat, ten_tot = thu, ten
        if not luot_hong(thu, bat_dau, ket_thuc, goi_y):
            break
    if nhat_ky is not None:
        nhat_ky.append({"thu_lai": "chọn", "cach": ten_tot})
    return tot_nhat


def loc_doan(cac_doan, nhat_ky=None, goi_y="day_du"):
    """Bỏ các đoạn nghi bịa chữ, trả về danh sách từ (có mốc thời gian) và số đoạn bị loại."""
    cac_tu = []
    so_doan_bi_loai = 0
    hai_doan_truoc = []  # chữ của 2 đoạn được giữ gần nhất
    for doan in cac_doan:
        ly_do = ly_do_loai(doan, goi_y)
        # Đoạn đủ dài mà lặp y hệt 1 trong 2 đoạn ngay trước -> model bị kẹt
        # (bắt cả kiểu A, A và kiểu A, B, A, B). Đoạn bị bỏ giống hệt đoạn đã giữ nên không mất chữ.
        van_ban = chuan_hoa_so_sanh(doan.text)
        du_dai = len(van_ban.split()) >= SO_TU_TOI_THIEU_LOC_TRUNG
        lap_lien_ke = hai_doan_truoc[-1:] == [van_ban]
        # Kiểu A, B, A chỉ tính là kẹt khi B cũng là câu dài; "A, Dạ., A" là người nói
        # nhắc lại câu sau một câu trả lời ngắn, giữ lại để không mất mốc thời gian.
        lap_xen_ke = (len(hai_doan_truoc) == 2 and hai_doan_truoc[0] == van_ban
                      and len(hai_doan_truoc[1].split()) >= SO_TU_TOI_THIEU_LOC_TRUNG)
        if not ly_do and du_dai and (lap_lien_ke or lap_xen_ke):
            ly_do = "lặp lại đoạn trước"
        if nhat_ky is not None:
            nhat_ky.append(chi_tiet_doan(doan, ly_do))
        if ly_do:
            so_doan_bi_loai += 1
            # In ra để tự kiểm tra: nếu thấy câu thật bị loại thì báo lại để chỉnh ngưỡng
            print(f"  [LOẠI - {ly_do}] [{doan.start:7.2f} --> {doan.end:7.2f}] {doan.text.strip()}")
            continue
        hai_doan_truoc = (hai_doan_truoc + [van_ban])[-2:]
        if doan.words:
            cac_tu.extend(lam_sach_tu(doan.words))
        else:
            # Đoạn có chữ nhưng không có mốc thời gian theo từ (hiếm, vd đoạn quá ngắn):
            # coi cả đoạn là một "từ", để câu không bị mất khỏi JSON
            cac_tu.append(Word(start=doan.start, end=doan.end,
                               word=" " + lam_sach_van_ban(doan.text.strip()), probability=1.0))
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
        # Mốc thời gian theo từ của Whisper đôi khi lệch: end không được nhỏ hơn start
        # (src/tien_xu_ly/doc_transcript.py báo lỗi cả file nếu start > end)
        "end": round(max(float(cac_tu[-1].end), float(cac_tu[0].start)), 2),
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
        # Bỏ ngoặc/nháy đóng ở cuối để nhận ra dấu hết câu: 'Lan nói "xong rồi." Tuấn...'
        chu = tu.word.strip().rstrip("\"'”’»)]")
        # Chữ viết tắt không kết thúc câu, TRỪ KHI từ ngay sau viết hoa
        # ("... v.v. Bạn Lan làm slide." vẫn là 2 câu)
        # Bỏ ngoặc/nháy MỞ ở đầu từ sau để xét chữ hoa: 'Thì... "Bạn Lan làm slide."'
        tu_sau = cac_tu[i + 1].word.strip().lstrip("\"'“‘«([") if i + 1 < len(cac_tu) else ""
        la_viet_tat = chu.lower() in TU_VIET_TAT and not (tu_sau[:1].isupper() and chu.lower() in ("v.v.", "đ."))
        # "Thì... mình nghĩ là" : dấu ba chấm là ngập ngừng, chỉ hết câu khi từ sau viết hoa
        # (hoặc là từ cuối cùng). Câu bị nối nhầm vẫn được cắt theo khoảng ngừng ở trên.
        dang_ngap_ngung = chu.endswith(("...", "…")) and tu_sau and not tu_sau[:1].isupper()
        if chu.endswith(DAU_KET_CAU + ("…",)) and not la_viet_tat and not dang_ngap_ngung:
            cac_cau_tho.append(cau_hien_tai)
            cau_hien_tai = []
    if cau_hien_tai:
        cac_cau_tho.append(cau_hien_tai)

    ket_qua = []
    for cau in cac_cau_tho:
        for phan in cat_cau_qua_dai(cau):
            cau_json = tao_cau(phan)
            # Bỏ "câu" chỉ có dấu câu (Whisper đôi khi tách riêng một từ ".")
            if re.search(r"\w", cau_json["text"]):
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
def xu_ly_mot_file(model, duong_dan, loc_nhieu, tien_xu_ly_bat, dem_im_lang=False, goi_y=None):
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
    cac_tu, so_bi_loai = nhan_dang(model, song_am, goi_y=goi_y or GOI_Y_MAC_DINH,
                                   tung_luot=TUNG_LUOT_MAC_DINH, dem_im_lang=dem_im_lang,
                                   gop=GOP_LUOT_MAC_DINH if dem_im_lang else 0)
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
    parser.add_argument("--che-do", choices=["chinh_xac", "nhanh", "nhanh_nhat"], default=CHE_DO_MAC_DINH,
                        help="chinh_xac (mặc định): PhoWhisper-medium, lỗi ít nhất (~3,5x độ dài ghi âm trên máy "
                             "2 nhân); nhanh: PhoWhisper-small, nhanh gấp ~2,5 lần, lỗi nhiều hơn (họp 22,5%% so với "
                             "18,1%%); nhanh_nhat: tên cũ của nhanh")
    parser.add_argument("--model", default=None,
                        help="Đổi model (tên model của faster-whisper hoặc thư mục model CTranslate2)")
    parser.add_argument("--kieu-tinh", default=KIEU_TINH, choices=["int8", "int8_float32", "float32"],
                        help=f"Kiểu tính trên CPU (mặc định {KIEU_TINH})")
    parser.add_argument("--loc-nhieu", action="store_true",
                        help="Bật giảm tạp âm (thử nghiệm, mặc định tắt vì có thể làm méo tiếng)")
    parser.add_argument("--khong-tien-xu-ly", action="store_true",
                        help="Tắt toàn bộ tiền xử lý (chỉ dùng để thử nghiệm so sánh)")
    parser.add_argument("--so-luong", type=int, default=SO_LUONG_CPU,
                        help=f"Số luồng CPU cho model (mặc định = số nhân thật của máy: {SO_LUONG_CPU})")
    parser.add_argument("--ghi-de", action="store_true",
                        help="Khi chạy cả thư mục: chạy lại cả những file đã có JSON")
    args = parser.parse_args()
    args.model, dem_im_lang, goi_y, canh_bao = chon_che_do(args.che_do, args.model)

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
        if so_loi:
            sys.exit("Không có file nào hợp lệ để xử lý.")
        # Mọi file đều đã có JSON (hoặc thư mục trống): không phải lỗi, mã thoát 0
        print("Không có file nào cần xử lý.")
        return

    # hop_01.mp3 và hop_01.wav đều ra hop_01.json -> file sau ghi đè file trước
    ten_da_gap = {}
    for f in hop_le:
        # So không phân biệt hoa/thường: trên Windows Hop.json và hop.json là một file
        if f.stem.lower() in ten_da_gap:
            print(f"  ⚠ {ten_da_gap[f.stem.lower()].name} và {f.name} cùng ra {f.stem}.json, "
                  "file sau sẽ ghi đè file trước. Nên đổi tên một file.")
        ten_da_gap[f.stem.lower()] = f

    # Tải model MỘT lần cho tất cả các file
    if canh_bao:
        print(f"  ⚠ {canh_bao}")
    print(f"Đang tải model {args.model}...")
    bat_dau = time.time()
    if loi_thu_muc_model(args.model):
        sys.exit(loi_thu_muc_model(args.model))
    try:
        model = WhisperModel(args.model, device="cpu", compute_type=args.kieu_tinh, cpu_threads=args.so_luong)
    except Exception as loi:
        sys.exit(
            f"Không tải được model {args.model}: {type(loi).__name__}: {loi}\n"
            "Lần chạy đầu cần internet để tải model (medium khoảng 1,5 GB), "
            "các lần sau dùng bản đã lưu trên máy."
        )
    print(f"Tải model xong ({time.time() - bat_dau:.1f} giây)")

    for duong_dan in hop_le:
        try:
            xu_ly_mot_file(model, duong_dan, args.loc_nhieu, not args.khong_tien_xu_ly, dem_im_lang, goi_y)
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
