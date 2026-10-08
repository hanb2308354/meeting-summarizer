# CẦU NỐI sang phần tiền xử lý của Hân (src/tien_xu_ly/tien_xu_ly.py).
#
# Phần tiền xử lý đã chuyển sang Hân phụ trách. File này chỉ giữ lại đúng tên
# và cách gọi cũ, để mọi chỗ trong src/nlp vẫn viết như trước:
#     from tien_xu_ly import tien_xu_ly
#     du_lieu = tien_xu_ly(doc_transcript(duong_dan))
# Đầu ra giữ nguyên format: stt, speaker, start, end, goc, sach, tach_tu, xa_giao.
# Muốn sửa cách làm sạch văn bản thì sửa ở src/tien_xu_ly, KHÔNG sửa file này.
import importlib.util
import sys
from pathlib import Path

from doc_transcript import doc_transcript

_THU_MUC_HAN = Path(__file__).resolve().parents[1] / "tien_xu_ly"

# Thư mục của Hân được thêm vào CUỐI sys.path: file nào trùng tên (vd doc_transcript)
# thì bản trong src/nlp vẫn được ưu tiên, code của phần NLP không bị thay.
if str(_THU_MUC_HAN) not in sys.path:
    sys.path.append(str(_THU_MUC_HAN))

# Nạp file của Hân dưới tên khác, vì nó trùng tên với chính file này
_spec = importlib.util.spec_from_file_location("tien_xu_ly_han", _THU_MUC_HAN / "tien_xu_ly.py")
_tien_xu_ly_han = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tien_xu_ly_han)

tien_xu_ly = _tien_xu_ly_han.tien_xu_ly


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/tien_xu_ly.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    for cau in tien_xu_ly(doc_transcript(duong_dan)):
        danh_dau = "[xã giao] " if cau["xa_giao"] else ""
        print(f"{cau['stt']:2d}. {danh_dau}{cau['sach']}")
