# Chuyển file ghi âm cuộc họp thành transcript JSON cho phần xử lý văn bản
import json
import sys
import time
from pathlib import Path
from faster_whisper import WhisperModel

# In tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
sys.stdout.reconfigure(encoding="utf-8")

# Cấu hình đã chốt qua thử nghiệm
TEN_MODEL = "medium"
GOI_Y = ("Cuộc họp nhóm. Các từ thường gặp: deadline, hạn chót, project, slide, "
         "file, check, demo, test, support, group Zalo, Google Meet, Whisper.")
THU_MUC_KET_QUA = Path("data/transcripts")
DAU_KET_CAU = (".", "?", "!")  # Gặp các dấu này thì cắt thành một câu


def tao_cau(danh_sach_tu):
    """Gộp các từ thành một câu theo format đã chốt."""
    return {
        "speaker": "SPEAKER_00",  # Chưa tách người nói, tạm gán một người
        "start": round(danh_sach_tu[0].start, 2),
        "end": round(danh_sach_tu[-1].end, 2),
        "text": "".join(tu.word for tu in danh_sach_tu).strip(),
    }


def chuyen_giong_noi(duong_dan_am_thanh):
    """Nhận dạng giọng nói, trả về danh sách các câu theo format đã chốt."""
    model = WhisperModel(TEN_MODEL, device="cpu", compute_type="int8")
    cac_doan, _ = model.transcribe(
        str(duong_dan_am_thanh),
        language="vi",
        initial_prompt=GOI_Y,
        beam_size=5,
        word_timestamps=True,  # Lấy mốc thời gian cho từng từ để tách câu
        vad_filter=True,       # Bỏ qua các đoạn im lặng
    )

    ket_qua = []
    cau_hien_tai = []
    for doan in cac_doan:
        for tu in doan.words:
            cau_hien_tai.append(tu)
            # Từ kết thúc bằng dấu chấm, hỏi, than thì chốt câu
            if tu.word.strip().endswith(DAU_KET_CAU):
                ket_qua.append(tao_cau(cau_hien_tai))
                cau_hien_tai = []

    # Phần còn lại cuối file (nếu không kết thúc bằng dấu câu)
    if cau_hien_tai:
        ket_qua.append(tao_cau(cau_hien_tai))

    for cau in ket_qua:
        print(f"[{cau['start']:6.2f} --> {cau['end']:6.2f}] {cau['text']}")
    return ket_qua


def luu_json(ket_qua, duong_dan_am_thanh):
    """Lưu kết quả ra data/transcripts/<tên file ghi âm>.json"""
    THU_MUC_KET_QUA.mkdir(parents=True, exist_ok=True)
    tep_json = THU_MUC_KET_QUA / (Path(duong_dan_am_thanh).stem + ".json")
    with open(tep_json, "w", encoding="utf-8") as f:
        # ensure_ascii=False để tiếng Việt hiện đúng chữ, không thành \u1ed3...
        json.dump(ket_qua, f, ensure_ascii=False, indent=2)
    return tep_json


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/asr/chuyen_giong_noi.py <đường dẫn file ghi âm>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    print("Đang nhận dạng giọng nói, vui lòng chờ...")
    bat_dau = time.time()
    ket_qua = chuyen_giong_noi(duong_dan)
    tep_json = luu_json(ket_qua, duong_dan)
    print(f"\nĐã lưu {len(ket_qua)} câu vào {tep_json}")
    print(f"Tổng thời gian: {time.time() - bat_dau:.1f} giây")