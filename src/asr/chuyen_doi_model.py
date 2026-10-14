# -*- coding: utf-8 -*-
"""
Chuyển model Whisper trên Hugging Face (định dạng transformers) sang CTranslate2 để faster-whisper dùng.

Vì sao cần: PhoWhisper (VinAI, huấn luyện thêm ~844 giờ tiếng Việt nhiều vùng miền) chỉ có bản
transformers; bản PhoWhisper-medium cho faster-whisper chưa ai đăng. Chỉ cần chạy 1 lần.

Cần thêm (chỉ để chuyển đổi, không đưa vào requirements.txt):
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install transformers

Cách dùng:
    python src/asr/chuyen_doi_model.py                                   (PhoWhisper-medium)
    python src/asr/chuyen_doi_model.py vinai/PhoWhisper-small
Kết quả: models/<tên>-ct2/  (không lên git). Dùng:
    python src/asr/danh_gia_bo.py --model models/phowhisper-medium-ct2
    python src/asr/chuyen_giong_noi.py data/audio/hop.wav --model models/phowhisper-medium-ct2
"""
import argparse
import sys
from pathlib import Path

THU_MUC_GOC = Path(__file__).resolve().parents[2]
# Các file faster-whisper cần đọc kèm: bộ tách từ và thông số trích đặc trưng âm thanh
FILE_KEM = ["tokenizer.json", "preprocessor_config.json"]


def main():
    parser = argparse.ArgumentParser(description="Chuyển model Whisper (transformers) sang CTranslate2.")
    parser.add_argument("model", nargs="?", default="vinai/PhoWhisper-medium",
                        help="Tên model trên Hugging Face (mặc định vinai/PhoWhisper-medium)")
    parser.add_argument("--luong-tu", default="int8", choices=["int8", "float16", "float32"],
                        help="Kiểu lưu trọng số (mặc định int8: nhỏ gọn, chạy CPU nhanh)")
    args = parser.parse_args()
    try:
        import ctranslate2
        import transformers  # noqa: F401  (bộ chuyển đổi cần)
    except ImportError as loi:
        sys.exit(f"Thiếu thư viện ({loi.name}). Cài:\n"
                 "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
                 "  pip install transformers")

    dich = THU_MUC_GOC / "models" / (args.model.split("/")[-1].lower() + "-ct2")
    if (dich / "model.bin").exists():
        sys.exit(f"Đã có {dich}. Xóa thư mục đó nếu muốn chuyển lại.")
    print(f"Đang tải {args.model} và chuyển sang CTranslate2 ({args.luong_tu}). "
          "Lần đầu tải ~3 GB, cần ~8 GB RAM...")
    ctranslate2.converters.TransformersConverter(args.model, copy_files=FILE_KEM).convert(
        str(dich), quantization=args.luong_tu)
    print(f"\nXong: {dich}")
    print(f"Dùng:  python src/asr/danh_gia_bo.py --model models/{dich.name}")


if __name__ == "__main__":
    main()
