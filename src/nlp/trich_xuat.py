# Trích xuất quyết định, việc cần làm, lịch họp tiếp theo từ transcript đã làm sạch
import sys
from pathlib import Path

from doc_transcript import doc_transcript
from nhan_dien_ten import tim_ten_biet
from tien_xu_ly import tien_xu_ly
from trich_lich_hop import lay_lich_hop
from trich_quyet_dinh import trich_quyet_dinh
from trich_viec import lay_viec

sys.stdout.reconfigure(encoding="utf-8")


def trich_xuat(cac_cau):
    """Trả về dict chứa quyết định, việc cần làm và lịch họp tiếp theo."""
    ten_biet = tim_ten_biet(cac_cau)
    tasks = lay_viec(cac_cau, ten_biet)

    ket_qua = {
        "decisions": trich_quyet_dinh(cac_cau, ten_biet),
        "tasks": [
            {
                "task": task["task"],
                "owner": task["owner"],
                "deadline": task["deadline"],
                "start": task["start"],
            }
            for task in tasks
        ],
        "next_meeting": lay_lich_hop(cac_cau),
    }

    return ket_qua


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/trich_xuat.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    du_lieu = tien_xu_ly(doc_transcript(duong_dan))
    ket_qua = trich_xuat(du_lieu)
    print("Quyết định:")
    for item in ket_qua["decisions"]:
        print(f" - {item['text']} (start={item['start']})")
    print("\nViệc cần làm:")
    for item in ket_qua["tasks"]:
        print(f" - {item['owner']}: {item['task']} | {item['deadline'] or 'không rõ'} | {item['start']}")
    print("\nHọp tiếp theo:")
    print(ket_qua["next_meeting"])
