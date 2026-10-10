# Đọc VĂN BẢN SẠCH do phần tiền xử lý (src/tien_xu_ly, Hân) xuất ra.
# Đây là đầu vào duy nhất của phần NLP: data/processed/<tên>.json
# (tạo bằng: python src/tien_xu_ly/tien_xu_ly.py data/transcripts/<tên>.json)
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GOC_REPO = Path(__file__).resolve().parents[2]
THU_MUC_VAN_BAN_SACH = GOC_REPO / "data" / "processed"
CAC_TRUONG_BAT_BUOC = ("stt", "speaker", "start", "end", "goc", "sach", "tach_tu", "xa_giao")


def doc_van_ban_sach(duong_dan):
    """Đọc file văn bản sạch, kiểm tra đúng format đã chốt, trả về danh sách câu."""
    duong_dan = Path(duong_dan)
    # utf-8-sig: đọc được cả file có BOM (soạn tay trên Windows) lẫn không có BOM
    with open(duong_dan, "r", encoding="utf-8-sig") as f:
        danh_sach_cau = json.load(f)

    if not isinstance(danh_sach_cau, list) or not danh_sach_cau:
        raise ValueError(f"File {duong_dan} phải là danh sách câu và không được rỗng.")

    for i, cau in enumerate(danh_sach_cau):
        if not isinstance(cau, dict):
            raise ValueError(f"Câu số {i} không phải là đối tượng JSON.")
        thieu = [truong for truong in CAC_TRUONG_BAT_BUOC if truong not in cau]
        if thieu:
            raise ValueError(
                f"Câu số {i} thiếu trường: {', '.join(thieu)}. "
                "File này có phải văn bản sạch (data/processed/) không? "
                "Chạy src/tien_xu_ly/tien_xu_ly.py trước."
            )
    return danh_sach_cau
