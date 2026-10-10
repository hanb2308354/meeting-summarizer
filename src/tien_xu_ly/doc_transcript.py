# Đọc file transcript JSON do phần ASR xuất ra (đầu vào của tiền xử lý)
# Người phụ trách: Hân (chuyển từ src/nlp sang, giữ nguyên logic).
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CAC_TRUONG_BAT_BUOC = ("speaker", "start", "end", "text")


def doc_transcript(duong_dan):
    """Đọc file JSON, kiểm tra đúng format đã chốt, trả về danh sách câu."""
    duong_dan = Path(duong_dan)
    # utf-8-sig: đọc được cả file soạn tay bằng Notepad (có BOM) lẫn file không có BOM
    with open(duong_dan, "r", encoding="utf-8-sig") as f:
        danh_sach_cau = json.load(f)

    if not isinstance(danh_sach_cau, list) or not danh_sach_cau:
        raise ValueError(f"File {duong_dan} phải là danh sách câu và không được rỗng.")

    for i, cau in enumerate(danh_sach_cau):
        if not isinstance(cau, dict):
            raise ValueError(f"Câu số {i} không phải là đối tượng JSON.")
        thieu = [truong for truong in CAC_TRUONG_BAT_BUOC if truong not in cau]
        if thieu:
            raise ValueError(f"Câu số {i} thiếu trường: {', '.join(thieu)}.")
        # Kiểm tra kiểu dữ liệu ngay ở đầu vào, để lỗi không trôi xuống phần NLP
        so = (int, float)
        if not isinstance(cau["start"], so) or not isinstance(cau["end"], so) \
                or isinstance(cau["start"], bool) or isinstance(cau["end"], bool):
            raise ValueError(f"Câu số {i}: start/end phải là số (giây).")
        if cau["start"] != cau["start"] or cau["end"] != cau["end"]:
            raise ValueError(f"Câu số {i}: start/end không hợp lệ (NaN).")
        if cau["start"] > cau["end"]:
            raise ValueError(f"Câu số {i}: start lớn hơn end.")
        if not isinstance(cau["speaker"], str) or not isinstance(cau["text"], str):
            raise ValueError(f"Câu số {i}: speaker và text phải là chuỗi.")

    return danh_sach_cau


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/tien_xu_ly/doc_transcript.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    try:
        danh_sach_cau = doc_transcript(duong_dan)
        print(f"Đọc thành công {len(danh_sach_cau)} câu từ {duong_dan}")
    except Exception as loi:
        sys.exit(f"Lỗi khi đọc transcript: {loi}")
