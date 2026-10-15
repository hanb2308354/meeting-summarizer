# -*- coding: utf-8 -*-
"""
Chạy một model Whisper bằng thư viện GỐC (Hugging Face transformers) trên vài đoạn của bộ đánh giá,
để so với cách chạy qua faster-whisper (CTranslate2) của dự án.

Vì sao cần: PhoWhisper chạy qua faster-whisper hay nối câu bịa sau lời thật và chậm ~11x.
Câu hỏi cần trả lời: đó là tính chất của chính model, hay do bản chuyển đổi / cách chạy?
    - Bản gốc cũng bịa và cũng sinh nhiều token  -> giới hạn của model
    - Bản gốc dừng đúng chỗ, ít token            -> lỗi ở bản chuyển đổi hoặc cách chạy, sửa được

Cần torch + transformers (đã cài khi chạy chuyen_doi_model.py). Lần đầu tải model gốc ~3 GB.
Cách dùng:
    python src/asr/thu_model_goc.py hop_va_dien_thoai_0000101 phuong_ngu_0001753
    python src/asr/thu_model_goc.py --model vinai/PhoWhisper-medium hop_va_dien_thoai_0000005
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402
import danh_gia_bo as dg  # noqa: E402


def tim_doan(id_doan):
    for thu_muc in sorted(dg.THU_MUC_BO.iterdir()) if dg.THU_MUC_BO.exists() else []:
        for muc in dg.doc_json(thu_muc / "nhan.json", []):
            if muc["id"] == id_doan:
                return thu_muc, muc
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Chạy model Whisper bằng transformers gốc để so sánh.")
    parser.add_argument("doan", nargs="+", help="Id đoạn trong bộ đánh giá")
    parser.add_argument("--model", default="vinai/PhoWhisper-medium")
    args = parser.parse_args()
    try:
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
    except ImportError as loi:
        sys.exit(f"Thiếu thư viện ({loi.name}). Cài: pip install torch --index-url "
                 "https://download.pytorch.org/whl/cpu ; pip install transformers")

    print(f"Đang tải {args.model} (bản gốc)...")
    bo_xu_ly = WhisperProcessor.from_pretrained(args.model)
    model = WhisperForConditionalGeneration.from_pretrained(args.model).eval()
    for id_doan in args.doan:
        thu_muc, muc = tim_doan(id_doan)
        if not muc:
            print(f"\nKhông tìm thấy đoạn {id_doan}")
            continue
        song_am = asr.doc_am_thanh(thu_muc / muc["tep"])
        dau_vao = bo_xu_ly(song_am, sampling_rate=asr.TAN_SO_MAU, return_tensors="pt").input_features
        bat_dau = time.time()
        with torch.no_grad():
            ma = model.generate(dau_vao, language="vi", task="transcribe", num_beams=5, max_new_tokens=440)
        giay = time.time() - bat_dau
        chu = bo_xu_ly.batch_decode(ma, skip_special_tokens=True)[0].strip()
        dap_an = dg.chuan_hoa_danh_gia(muc["text"])
        du_doan = dg.chuan_hoa_danh_gia(chu)
        so_tu = max(1, len(dap_an.split()))
        print(f"\n=== {id_doan} ({len(song_am) / asr.TAN_SO_MAU:.1f}s âm thanh) ===")
        print(f"Đáp án      : {dap_an}")
        print(f"Bản gốc nghe: {du_doan}")
        print(f"WER {dg.so_loi(dap_an, du_doan) / so_tu:.1%} | {ma.shape[-1]} token | {giay:.1f}s xử lý"
              f" ({giay / (len(song_am) / asr.TAN_SO_MAU):.1f}x)")


if __name__ == "__main__":
    main()
