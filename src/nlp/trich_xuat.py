# Trích xuất quyết định, việc cần làm, lịch họp tiếp theo từ transcript đã làm sạch
import re
import sys
from pathlib import Path

from doc_van_ban_sach import doc_van_ban_sach
from nhan_dien_ten import tim_ten_biet
from trich_lich_hop import lay_lich_hop
from trich_quyet_dinh import trich_quyet_dinh
from trich_viec import lay_viec, lam_sach_mo_ta
from vet import bat_vet, lay_vet

sys.stdout.reconfigure(encoding="utf-8")


def trich_xuat(cac_cau):
    """Trả về dict chứa quyết định, việc cần làm và lịch họp tiếp theo."""
    ten_biet = tim_ten_biet(cac_cau)
    tasks = lay_viec(cac_cau, ten_biet)

    ket_qua = {
        "decisions": trich_quyet_dinh(cac_cau, ten_biet),
        "tasks": [
            {
                "task": lam_sach_mo_ta(task["task"], task["deadline"]),
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
        sys.exit("Cách dùng: python src/nlp/trich_xuat.py <file văn bản sạch trong data/processed/>")

    che_do_vet = "--vet" in sys.argv[1:]
    if che_do_vet:
        bat_vet()
    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    du_lieu = doc_van_ban_sach(duong_dan)
    ket_qua = trich_xuat(du_lieu)
    if che_do_vet:
        vet_theo_cau = {}
        for dong in lay_vet():
            if dong.get("stt") is None:
                continue
            vet_theo_cau.setdefault(dong["stt"], []).append(dong)
        for cau in du_lieu:
            stt = cau.get("stt")
            print(f"Câu {stt}: {cau['sach']}")
            menh_de = [part.strip() for part in re.split(r"\s*,\s*", cau["sach"]) if part.strip()]
            print(f"Mệnh đề: {' | '.join(menh_de) if menh_de else '(rỗng)'}")
            for dong in vet_theo_cau.get(stt, []):
                print(f"[{dong['ma']}] {dong['noi_dung']} → {dong['ket_qua']}")
    print("Quyết định:")
    for item in ket_qua["decisions"]:
        print(f" - {item['text']} (start={item['start']})")
    print("\nViệc cần làm:")
    for item in ket_qua["tasks"]:
        print(f" - {item['owner']}: {item['task']} | {item['deadline'] or 'không rõ'} | {item['start']}")
    print("\nHọp tiếp theo:")
    print(ket_qua["next_meeting"])
