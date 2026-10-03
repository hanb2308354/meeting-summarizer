# Chạy toàn bộ pipeline NLP và lưu kết quả ra outputs/
import json
import sys
import time
from pathlib import Path

from doc_transcript import doc_transcript
from tien_xu_ly import tien_xu_ly
from tom_tat import tom_tat
from trich_xuat import trich_xuat

sys.stdout.reconfigure(encoding="utf-8")

THU_MUC_KET_QUA = Path("outputs")


def luu_json(ket_qua, ten_file):
    """Lưu dict vào outputs/<tên>.json theo chuẩn UTF-8 và indent 2."""
    THU_MUC_KET_QUA.mkdir(parents=True, exist_ok=True)
    duong_dan = THU_MUC_KET_QUA / (Path(ten_file).stem + ".json")
    with open(duong_dan, "w", encoding="utf-8") as f:
        json.dump(ket_qua, f, ensure_ascii=False, indent=2)
    return duong_dan


def tao_markdown(ket_qua):
    """Sinh file Markdown từ dict JSON đã lưu, chuẩn như đề xuất."""
    ten = Path(ket_qua["source"]).stem
    lines = [f"# Tóm tắt cuộc họp: {ten}", "", "## Nội dung chính", ""]
    lines.append(ket_qua["summary"].strip())
    lines.append("")
    lines.append("## Quyết định")
    if ket_qua["decisions"]:
        for item in ket_qua["decisions"]:
            lines.append(f"- {item['text']}")
    else:
        lines.append("Không có")
    lines.append("")
    lines.append("## Việc cần làm")
    if ket_qua["tasks"]:
        lines.append("| Việc | Người phụ trách | Hạn chót |")
        lines.append("|---|---|---|")
        for item in ket_qua["tasks"]:
            viec = item.get("task") or "Chưa rõ"
            nguoi = item.get("owner") or "Chưa rõ"
            han = item.get("deadline") or "Chưa rõ"
            lines.append(f"| {viec} | {nguoi} | {han} |")
    else:
        lines.append("Không có")
    lines.append("")
    lines.append("## Cuộc họp tiếp theo")
    next_meeting = ket_qua.get("next_meeting")
    if next_meeting:
        time_value = next_meeting.get("time") or "Chưa rõ"
        place_value = next_meeting.get("place") or "Chưa rõ"
        lines.append(f"- Thời gian: {time_value}")
        lines.append(f"- Địa điểm: {place_value}")
    else:
        lines.append("Không có")
    return "\n".join(lines) + "\n"


def chay_nlp(duong_dan):
    """Chạy đầy đủ pipeline NLP cho một transcript và trả về dict kết quả."""
    bai_doc = doc_transcript(duong_dan)
    du_lieu = tien_xu_ly(bai_doc)
    trich = trich_xuat(du_lieu)
    tong_ket = tom_tat(du_lieu)

    ket_qua = {
        "source": Path(duong_dan).name,
        "summary": tong_ket,
        "decisions": trich["decisions"],
        "tasks": trich["tasks"],
        "next_meeting": trich["next_meeting"],
    }
    tep_json = luu_json(ket_qua, duong_dan)
    tep_md = THU_MUC_KET_QUA / (Path(duong_dan).stem + ".md")
    with open(tep_md, "w", encoding="utf-8") as f:
        f.write(tao_markdown(ket_qua))
    return ket_qua, tep_json, tep_md


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/chay_nlp.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    bat_dau = time.time()
    print("Bước 1: đọc transcript...")
    print("Bước 2: tiền xử lý văn bản...")
    print("Bước 3: trích xuất thông tin...")
    print("Bước 4: tóm tắt...")
    ket_qua, tep_json, tep_md = chay_nlp(duong_dan)
    print(f"Đã lưu JSON: {tep_json}")
    print(f"Đã lưu Markdown: {tep_md}")
    print(f"Tổng thời gian: {time.time() - bat_dau:.2f} giây")
    print(f"Số quyết định: {len(ket_qua['decisions'])}")
    print(f"Số việc cần làm: {len(ket_qua['tasks'])}")
