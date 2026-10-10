# Chạy tiền xử lý từ dòng lệnh: data/transcripts/<tên>.json -> data/processed/<tên>.json
# Người phụ trách: Hân.
#
# VỊ TRÍ TRONG HỆ THỐNG:
#   src/asr         -> data/transcripts/<tên>.json   (Hân: âm thanh -> chữ)
#   src/tien_xu_ly  -> văn bản sạch                  (Hân: chữ -> văn bản sạch)  <- THƯ MỤC NÀY
#   src/nlp         -> outputs/<tên>.json, .md        (Anh: văn bản sạch -> tóm tắt, trích xuất)
#
# Logic làm sạch nằm trong lam_sach.py. Phần NLP KHÔNG đọc data/processed: nó gọi
# thẳng hàm tien_xu_ly() (qua cầu nối src/nlp/tien_xu_ly.py) trên data/transcripts.
# data/processed chỉ để người xem/kiểm tra; kiem_thu_tien_xu_ly.py báo lỗi nếu nó
# lệch với code hiện tại (sửa từ điển xong thì chạy lại lệnh dưới đây).
#
# Cách dùng:
#   python src/tien_xu_ly/tien_xu_ly.py data/transcripts/thu_nghiem.json
#   python src/tien_xu_ly/tien_xu_ly.py data/transcripts/      (cả thư mục)
#
# ĐẦU RA data/processed/<tên>.json (giống hệt đầu ra hàm tien_xu_ly()):
#   [{"stt", "speaker", "start", "end", "goc", "sach", "tach_tu", "xa_giao"}]
import json
import os
import sys
from pathlib import Path

from doc_transcript import doc_transcript
from lam_sach import tien_xu_ly

# In tiếng Việt bằng UTF-8, tránh lỗi bảng mã trên PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Đường dẫn tính theo vị trí file code, chạy từ thư mục nào cũng đúng
THU_MUC_GOC = Path(__file__).resolve().parents[2]
THU_MUC_RA = THU_MUC_GOC / "data" / "processed"


def hien_thi(duong_dan):
    """Đường dẫn gọn để in ra: tương đối với thư mục dự án nếu được."""
    try:
        return duong_dan.relative_to(THU_MUC_GOC)
    except ValueError:
        return duong_dan


def luu_json(ket_qua, ten):
    """Ghi ra file tạm rồi mới đổi tên: không bao giờ để lại file ghi dở."""
    THU_MUC_RA.mkdir(parents=True, exist_ok=True)
    tep_json = THU_MUC_RA / f"{ten}.json"
    tep_tam = tep_json.with_suffix(".json.tmp")
    try:
        with open(tep_tam, "w", encoding="utf-8") as f:
            json.dump(ket_qua, f, ensure_ascii=False, indent=2)
        os.replace(tep_tam, tep_json)
    finally:
        if tep_tam.exists():
            tep_tam.unlink()  # Lỗi giữa chừng thì không để lại file tạm
    return tep_json


def xu_ly_mot_file(duong_dan):
    """Đọc transcript, làm sạch, in ra màn hình và lưu vào data/processed/."""
    ket_qua = tien_xu_ly(doc_transcript(duong_dan))
    if not ket_qua:
        # Phần NLP coi danh sách rỗng là lỗi, nên không ghi file
        raise ValueError("bỏ từ đệm xong không còn câu nào, không ghi file.")
    for cau in ket_qua:
        danh_dau = "[xã giao] " if cau["xa_giao"] else ""
        print(f"{cau['stt']:2d}. {danh_dau}{cau['sach']}")
    return luu_json(ket_qua, duong_dan.stem)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/tien_xu_ly/tien_xu_ly.py <file transcript JSON hoặc thư mục>")

    cac_file = []
    for p in map(Path, sys.argv[1:]):
        cac_file += sorted(p.glob("*.json")) if p.is_dir() else [p]
    if not cac_file:
        sys.exit("Không có file transcript nào để xử lý.")

    so_loi = 0
    for duong_dan in cac_file:
        if len(cac_file) > 1:
            print(f"\n=== {duong_dan.name} ===")
        try:
            if not duong_dan.exists():
                raise FileNotFoundError("không tìm thấy file")
            tep_json = xu_ly_mot_file(duong_dan)
            print(f"Đã lưu vào {hien_thi(tep_json)}")
        except Exception as loi:
            so_loi += 1
            print(f"  ✗ Lỗi khi xử lý {duong_dan}: {loi}")
    if so_loi:
        sys.exit(1)
