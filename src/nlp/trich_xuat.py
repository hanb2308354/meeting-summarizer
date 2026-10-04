# Trích xuất quyết định, việc cần làm, lịch họp tiếp theo từ transcript đã làm sạch
import re
import sys
from pathlib import Path

from doc_transcript import doc_transcript
from nhan_dien_han import tim_han_chot
from nhan_dien_ten import lay_ten_nguoi_phan_anh, tim_ten_biet
from tien_xu_ly import tien_xu_ly
from trich_lich_hop import la_lich_hop, lay_lich_hop
from trich_viec import co_dong_tu_hanh_dong, la_de_muc, lay_viec
from tu_dien import (
    DANH_SACH_DONG_TU,
    DANH_SACH_HAN_CHOT,
    DANH_SACH_TU_CHUC_NANG,
    THU_MUC_CAU,
)

sys.stdout.reconfigure(encoding="utf-8")


def la_quyet_dinh(van_ban):
    """Nhận diện mệnh đề quyết định của cuộc họp."""
    if re.search(r"\b(chốt|thống nhất|quyết định|đồng ý|kpi|không dùng|tối thiểu|miễn phí vận chuyển|kèm)\b", van_ban, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(từ tháng này|mỗi.*phải đạt|chỉ giảm|kèm miễn phí vận chuyển|giảm\s+10%|giảm\s+20%)\b", van_ban, flags=re.IGNORECASE):
        return True
    return False


def lay_quyet_dinh(cac_cau):
    """Trích xuất các quyết định nhớ và nối mệnh đề tiếp theo nếu cần."""
    ket_qua = []
    i = 0
    while i < len(cac_cau):
        text = cac_cau[i]["sach"]
        if la_quyet_dinh(text):
            if lay_ten_nguoi_phan_anh(text, tim_ten_biet(cac_cau)) is not None and co_dong_tu_hanh_dong(text):
                i += 1
                continue
            phan = text
            if i + 1 < len(cac_cau):
                text_tiep = cac_cau[i + 1]["sach"]
                if re.match(r"^(kèm|và|cùng|cuối cùng là|từ tháng này|mỗi)\b", text_tiep, flags=re.IGNORECASE):
                    phan = f"{phan}, {text_tiep}"
                    i += 1
            ket_qua.append({"text": phan.strip(), "start": cac_cau[i]["start"]})
        i += 1
    return ket_qua


def trich_xuat(cac_cau):
    """Trả về dict chứa quyết định, việc cần làm và lịch họp tiếp theo."""
    ten_biet = tim_ten_biet(cac_cau)
    tasks = lay_viec(cac_cau, ten_biet)

    ket_qua = {
        "decisions": [],
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

    for cau in cac_cau:
        text = cau["sach"]
        if la_lich_hop(text) or la_de_muc(text) or cau["xa_giao"]:
            continue
        if not la_quyet_dinh(text):
            continue
        if lay_ten_nguoi_phan_anh(text, ten_biet) is not None and co_dong_tu_hanh_dong(text):
            continue
        phan = text
        if len(ket_qua["decisions"]) and re.match(r"^(kèm|và|cùng|cuối cùng là|từ tháng này|mỗi)\b", text, flags=re.IGNORECASE):
            phan = f"{ket_qua['decisions'][-1]['text']}, {text}"
            ket_qua["decisions"][-1]["text"] = phan.strip()
            continue
        ket_qua["decisions"].append({"text": phan.strip(), "start": cau["start"]})

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
