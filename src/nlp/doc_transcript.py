# Đọc file transcript JSON do phần ASR xuất ra
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CAC_TRUONG_BAT_BUOC = ("speaker", "start", "end", "text")


def doc_transcript(duong_dan):
    """Đọc file JSON, kiểm tra đúng format đã chốt, trả về danh sách câu."""
    duong_dan = Path(duong_dan)
    with open(duong_dan, "r", encoding="utf-8") as f:
        danh_sach_cau = json.load(f)

    if not isinstance(danh_sach_cau, list) or not danh_sach_cau:
        raise ValueError(f"File {duong_dan} phải là danh sách câu và không được rỗng.")

    for i, cau in enumerate(danh_sach_cau):
        if not isinstance(cau, dict):
            raise ValueError(f"Câu số {i} không phải là đối tượng JSON.")
        thieu = [truong for truong in CAC_TRUONG_BAT_BUOC if truong not in cau]
        if thieu:
            raise ValueError(f"Câu số {i} thiếu trường: {', '.join(thieu)}.")

    return danh_sach_cau


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/doc_transcript.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    try:
        danh_sach_cau = doc_transcript(duong_dan)
        print(f"Đọc thành công {len(danh_sach_cau)} câu từ {duong_dan}")
    except Exception as loi:
        sys.exit(f"Lỗi khi đọc transcript: {loi}")
