# Thử nghiệm faster-whisper: đo tốc độ và độ chính xác để chọn model
import sys
import time
from faster_whisper import WhisperModel

# Bắt Python in tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
sys.stdout.reconfigure(encoding="utf-8")

TEP_AM_THANH = "data/audio/thu_nghiem.mp3"
GOI_Y = ("Cuộc họp nhóm. Các từ thường gặp: deadline, hạn chót, project, slide, "
         "file, check, demo, test, support, group Zalo, Google Meet, Whisper.")

# Tên model lấy từ dòng lệnh, mặc định là medium
ten_model = sys.argv[1] if len(sys.argv) > 1 else "medium"

# Tải model, dùng int8 để chạy nhanh hơn trên CPU
bat_dau = time.time()
model = WhisperModel(ten_model, device="cpu", compute_type="int8")
thoi_gian_tai = time.time() - bat_dau

# Nhận dạng giọng nói
bat_dau = time.time()
cac_doan, thong_tin = model.transcribe(
    TEP_AM_THANH, language="vi", initial_prompt=GOI_Y, beam_size=5
)
for doan in cac_doan:
    print(f"[{doan.start:6.2f} --> {doan.end:6.2f}] {doan.text.strip()}")
thoi_gian_nhan_dang = time.time() - bat_dau

print(f"\nModel: {ten_model}")
print(f"Độ dài file ghi âm: {thong_tin.duration:.1f} giây")
print(f"Thời gian tải model: {thoi_gian_tai:.1f} giây")
print(f"Thời gian nhận dạng: {thoi_gian_nhan_dang:.1f} giây")