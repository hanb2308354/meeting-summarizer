# -*- coding: utf-8 -*-
"""
Kiểm tra (và nếu cần thì sửa) "alignment heads" của model PhoWhisper đã chuyển đổi.

Vì sao (phản biện 18/10): mốc thời gian THEO TỪ của faster-whisper được tính từ một số "đầu chú ý" (attention
heads) chọn sẵn của Whisper. Bộ chuyển đổi CTranslate2 lấy danh sách này từ generation_config của model gốc;
nếu model gốc không ghi thì dùng MẶC ĐỊNH là mọi đầu của nửa sau các lớp, thường kém chính xác hơn. Luật cắt
câu bịa và luật dừng sớm của dự án dựa vào mốc thời gian theo từ, nên cần biết bản PhoWhisper đang dùng loại nào.

PhoWhisper-medium được tinh chỉnh từ Whisper medium, nên khi thiếu thì thử dùng danh sách của Whisper medium.
Tạo bản sửa ở thư mục mới (model.bin được liên kết cứng, không tốn thêm dung lượng nếu cùng ổ đĩa), không đụng
bản gốc. Rồi đo bản sửa bằng danh_gia_bo.py --model <thư mục mới> để biết có tốt hơn không.

Cách dùng:
    python src/asr/sua_alignment_heads.py                      (models/phowhisper-medium-ct2)
    python src/asr/sua_alignment_heads.py models/phowhisper-small-ct2 --mau small
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

THU_MUC_GOC = Path(__file__).resolve().parents[2]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def doc_heads(thu_muc):
    tep = Path(thu_muc) / "config.json"
    if not tep.exists():
        return None
    return json.loads(tep.read_text(encoding="utf-8")).get("alignment_heads")


def heads_mac_dinh(so_lop, so_dau):
    """Mặc định của bộ chuyển đổi CTranslate2 khi model gốc không ghi: mọi đầu của nửa sau các lớp."""
    return [[lop, dau] for lop in range(so_lop // 2, so_lop) for dau in range(so_dau)]


def thu_muc_mau(ten):
    """Thư mục model Whisper chuẩn (faster-whisper) đã tải trong bộ nhớ đệm, không tải mới."""
    from faster_whisper.utils import download_model
    return download_model(ten, local_files_only=True)


def tao_ban_sua(goc, dich, heads):
    dich.mkdir(parents=True, exist_ok=True)
    for tep in goc.iterdir():
        if tep.is_file() and tep.name != "config.json":
            dich_tep = dich / tep.name
            if dich_tep.exists():
                dich_tep.unlink()
            try:
                os.link(tep, dich_tep)          # liên kết cứng: không tốn thêm dung lượng
            except OSError:
                shutil.copy2(tep, dich_tep)
    cau_hinh = json.loads((goc / "config.json").read_text(encoding="utf-8"))
    cau_hinh["alignment_heads"] = heads
    (dich / "config.json").write_text(json.dumps(cau_hinh, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra / sửa alignment heads của model PhoWhisper đã chuyển đổi.")
    parser.add_argument("model", nargs="?", default="models/phowhisper-medium-ct2")
    parser.add_argument("--mau", default="medium", help="Model Whisper chuẩn để lấy danh sách (mặc định medium)")
    parser.add_argument("--so-lop", type=int, default=24, help="Số lớp decoder (medium 24, small 12)")
    parser.add_argument("--so-dau", type=int, default=16, help="Số đầu chú ý mỗi lớp (medium 16, small 12)")
    args = parser.parse_args()
    goc = Path(args.model)
    if not goc.is_absolute():
        goc = THU_MUC_GOC / goc
    heads = doc_heads(goc)
    if heads is None:
        sys.exit(f"Không thấy {goc / 'config.json'}. Chạy chuyen_doi_model.py trước.")
    mac_dinh = heads_mac_dinh(args.so_lop, args.so_dau)
    print(f"{goc.name}: {len(heads)} alignment heads"
          + (" = MẶC ĐỊNH của bộ chuyển đổi (model gốc không ghi)" if sorted(heads) == mac_dinh else " (có sẵn từ model gốc)"))
    try:
        heads_mau = doc_heads(thu_muc_mau(args.mau))
    except Exception as loi:
        sys.exit(f"Không tìm thấy Whisper {args.mau} trong bộ nhớ đệm ({loi}). Chạy medium một lần trước.")
    print(f"Whisper {args.mau}: {len(heads_mau or [])} alignment heads")
    if not heads_mau or sorted(heads) == sorted(heads_mau):
        print("Không cần sửa.")
        return
    dich = goc.with_name(goc.name + "-ah")
    tao_ban_sua(goc, dich, heads_mau)
    print(f"Đã tạo bản dùng alignment heads của Whisper {args.mau}: {dich}")
    print(f"Đo: python src/asr/danh_gia_bo.py <bộ> --model models/{dich.name} ...")


if __name__ == "__main__":
    main()
