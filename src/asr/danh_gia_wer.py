# Đánh giá độ chính xác nhận dạng giọng nói bằng tỷ lệ lỗi từ (WER)
# Cách dùng: python src/asr/danh_gia_wer.py thu_nghiem
#   so data/transcripts/thu_nghiem.json với đáp án data/dap_an/thu_nghiem.txt
# Quy ước viết đáp án: số viết bằng chữ số (thứ 4, 20 tháng 10) như Whisper hay ra.
import json
import re
import sys
import unicodedata
from pathlib import Path

import jiwer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THU_MUC_GOC = Path(__file__).resolve().parents[2]


def chuan_hoa(van_ban):
    """Đưa về cùng một dạng để so sánh công bằng: chữ thường, bỏ dấu câu.

    Chỉ tính lỗi NGHE SAI, không tính lỗi cách viết (hoa/thường, dấu phẩy).
    """
    # NFC: thống nhất cách mã hóa dấu tiếng Việt (có 2 cách gõ cùng một chữ)
    van_ban = unicodedata.normalize("NFC", van_ban.lower())
    # Gạch nối giữa hai chữ cái: front-end -> frontend (giữ "2-3 ngày" không thành "23")
    van_ban = re.sub(r"(?<=[^\W\d_])-(?=[^\W\d_])", "", van_ban)
    # Cùng một cách đọc, chỉ khác cách viết: 9h30 -> 9 giờ 30, 10% -> 10 phần trăm
    van_ban = re.sub(r"(\d+)\s*h\s*(\d+)?\b", lambda m: f"{m[1]} giờ {m[2] or ''}", van_ban)
    van_ban = van_ban.replace("%", " phần trăm ")
    van_ban = re.sub(r"[^\w\s]", " ", van_ban)    # bỏ dấu câu
    return re.sub(r"\s+", " ", van_ban).strip()   # gộp khoảng trắng thừa


def do_mot_file(ten):
    """Trả về (đáp án đã chuẩn hóa, kết quả jiwer) cho một file."""
    tep_json = THU_MUC_GOC / "data" / "transcripts" / f"{ten}.json"
    tep_dap_an = THU_MUC_GOC / "data" / "dap_an" / f"{ten}.txt"
    for tep in (tep_json, tep_dap_an):
        if not tep.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {tep}")
    cac_cau = json.loads(tep_json.read_text(encoding="utf-8-sig"))
    du_doan = chuan_hoa(" ".join(cau["text"] for cau in cac_cau))
    dap_an = chuan_hoa(tep_dap_an.read_text(encoding="utf-8-sig"))
    if not dap_an:
        raise ValueError(f"Đáp án rỗng: {tep_dap_an}")
    return dap_an, jiwer.process_words(dap_an, du_doan)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/asr/danh_gia_wer.py <tên file> [tên file ...]\n"
                 "Ví dụ:     python src/asr/danh_gia_wer.py thu_nghiem hop_01 hop_02")

    chi_tiet = len(sys.argv) == 2
    tong = {"tu": 0, "sai": 0, "thieu": 0, "thua": 0}
    bo_qua = []
    for ten in sys.argv[1:]:
        try:
            dap_an, kq = do_mot_file(ten)
        except (FileNotFoundError, ValueError) as loi:
            # Nhiều file mà thiếu một file: bỏ qua file đó, vẫn tính WER gộp các file còn lại
            print(f"{ten:<20} BỎ QUA: {loi}")
            bo_qua.append(ten)
            continue
        so_tu = len(dap_an.split())
        tong["tu"] += so_tu
        tong["sai"] += kq.substitutions
        tong["thieu"] += kq.deletions
        tong["thua"] += kq.insertions
        print(f"{ten:<20} {so_tu:>5} từ | sai {kq.substitutions:>3} | thiếu {kq.deletions:>3} "
              f"| thừa {kq.insertions:>3} | WER {kq.wer:6.1%}")
        if chi_tiet:
            print("\nChi tiết từng chỗ sai:")
            print(jiwer.visualize_alignment(kq))

    # WER gộp = tổng lỗi / tổng số từ (không lấy trung bình WER từng file,
    # vì file ngắn sẽ bị tính nặng ngang file dài)
    so_file = len(sys.argv) - 1 - len(bo_qua)
    if not so_file:
        sys.exit("Không đo được file nào.")
    wer_gop = (tong["sai"] + tong["thieu"] + tong["thua"]) / tong["tu"]
    print(f"\nTỔNG: {so_file} file, {tong['tu']} từ, WER gộp = {wer_gop:.1%}")
    if tong["tu"] < 300:
        print("(Lưu ý: dưới 300 từ thì WER dao động mạnh, nên đo thêm nhiều file)")
    if bo_qua:
        # Mã thoát 1 để người chạy biết WER gộp chưa tính đủ các file đã yêu cầu
        sys.exit(f"Đã bỏ qua {len(bo_qua)} file: {', '.join(bo_qua)}")
