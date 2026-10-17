# -*- coding: utf-8 -*-
"""
Đo model chạy bằng thư viện Hugging Face transformers trên bộ đánh giá, ghi kết quả CÙNG ĐỊNH DẠNG với
danh_gia_bo.py để so bằng:  python src/asr/danh_gia_bo.py <bộ> --so-sanh <cấu hình> ...

Vì sao cần (góp ý phản biện 18/10): mới thử họ Whisper qua faster-whisper, chưa đủ để nói "đã chạm giới
hạn model". File này thử thêm:
    - model CTC tiếng Việt (wav2vec2): không sinh chữ tự do nên không bịa câu, chạy CPU nhanh.
      Ra chữ thường, không dấu câu (WER đã bỏ hoa/thường và dấu câu nên vẫn so công bằng).
    - Whisper bản GỐC (vd vinai/PhoWhisper-medium): tự dừng đúng chỗ, xem có chính xác hơn bản CTranslate2.
Cùng tiền xử lý âm thanh như chương trình chính. Đoạn dài hơn 30 giây (file dài) thì cắt theo lượt nói (VAD).

Cần torch + transformers (đã cài khi chạy chuyen_doi_model.py). Lần đầu tải model.
Cách dùng:
    python src/asr/danh_gia_hf.py hop_va_dien_thoai phuong_ngu --so-mau 30 --model nguyenvulebinh/wav2vec2-base-vietnamese-250h
    python src/asr/danh_gia_hf.py hop_va_dien_thoai phuong_ngu --so-mau 30 --model vinai/PhoWhisper-medium
Tên cấu hình kết quả: <tên model>_hf (vd wav2vec2-base-vietnamese-250h_hf).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402
import danh_gia_bo as dg  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def ten_cau_hinh_hf(model):
    return model.rstrip("/").split("/")[-1].lower() + "_hf"


def tai_bo_nghe(model, beam=5):
    """Trả về hàm nghe(song_am) -> chữ, cho model CTC (wav2vec2) hoặc Whisper bản gốc."""
    try:
        import torch
    except ImportError:
        sys.exit("Thiếu torch. Cài: pip install torch --index-url https://download.pytorch.org/whl/cpu ; "
                 "pip install transformers")
    if asr.SO_LUONG_CPU:
        torch.set_num_threads(asr.SO_LUONG_CPU)
    print(f"Đang tải {model} (transformers)...")
    if "wav2vec2" in model.lower():
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        bo_xu_ly = Wav2Vec2Processor.from_pretrained(model)
        mo_hinh = Wav2Vec2ForCTC.from_pretrained(model).eval()

        def nghe(song_am):
            vao = bo_xu_ly(song_am, sampling_rate=asr.TAN_SO_MAU, return_tensors="pt").input_values
            with torch.no_grad():
                ma = mo_hinh(vao).logits.argmax(dim=-1)
            return bo_xu_ly.batch_decode(ma)[0].strip()
        return nghe

    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    bo_xu_ly = WhisperProcessor.from_pretrained(model)
    mo_hinh = WhisperForConditionalGeneration.from_pretrained(model).eval()

    def nghe(song_am):
        vao = bo_xu_ly(song_am, sampling_rate=asr.TAN_SO_MAU, return_tensors="pt").input_features
        with torch.no_grad():
            ma = mo_hinh.generate(vao, language="vi", task="transcribe", num_beams=beam, max_new_tokens=440)
        return bo_xu_ly.batch_decode(ma, skip_special_tokens=True)[0].strip()
    return nghe


def nghe_ca_doan(nghe, song_am):
    """Đoạn <= 30 giây nghe một lần; dài hơn thì cắt theo lượt nói (VAD) rồi nối lại."""
    if len(song_am) <= asr.SO_MAU_CUA_SO:
        return nghe(song_am)
    return " ".join(c for c in (nghe(song_am[a:b]) for a, b in asr.cat_luot_noi(song_am)) if c)


def chay_bo_hf(ten_bo, nghe_hoac_ham_tai, cau_hinh, so_mau=0):
    """Nhận dạng các đoạn chưa có kết quả, lưu sau mỗi đoạn (ngắt giữa chừng chạy lại làm tiếp)."""
    thu_muc = dg.THU_MUC_BO / ten_bo
    cac_muc = dg.doc_json(thu_muc / "nhan.json", [])
    if so_mau:
        cac_muc = cac_muc[:so_mau]
    tep = thu_muc / f"ket_qua__{cau_hinh}.json"
    ket_qua = dg.doc_json(tep, {})
    can_chay = [m for m in cac_muc if m["id"] not in ket_qua]
    print(f"\n=== {ten_bo}: {len(cac_muc)} đoạn, cần nhận dạng {len(can_chay)} ===")
    nghe = None
    for i, muc in enumerate(can_chay, 1):
        if nghe is None:
            nghe = nghe_hoac_ham_tai() if getattr(nghe_hoac_ham_tai, "la_ham_tai", False) else nghe_hoac_ham_tai
        bat_dau = time.time()
        try:
            song_am = asr.doc_am_thanh(thu_muc / muc["tep"])
            song_am, _ = asr.tien_xu_ly_am_thanh(song_am, False)
            chu = nghe_ca_doan(nghe, song_am)
            ket_qua[muc["id"]] = {"du_doan": chu, "bi_loai": [], "do_dai": round(len(song_am) / asr.TAN_SO_MAU, 2),
                                  "thoi_gian": round(time.time() - bat_dau, 2)}
        except asr.LoiDauVao as loi:
            ket_qua[muc["id"]] = {"loi": str(loi)}
        dg.ghi_json(ket_qua, tep)
        kq = ket_qua[muc["id"]]
        print(f"  [{i:>3}/{len(can_chay)}] {muc['id']}: "
              + (f"✗ {kq['loi']}" if "loi" in kq else f"{kq['thoi_gian']:.1f}s | {kq['du_doan'][:60]}"))
    return cac_muc, ket_qua


def main():
    parser = argparse.ArgumentParser(description="Đo model chạy bằng transformers (wav2vec2, Whisper gốc).")
    parser.add_argument("bo", nargs="+", help="Tên bộ trong data/bo_danh_gia/")
    parser.add_argument("--model", required=True, help="Tên model trên Hugging Face")
    parser.add_argument("--so-mau", type=int, default=0, help="Chỉ chạy N đoạn đầu mỗi bộ")
    parser.add_argument("--beam", type=int, default=5, help="Số nhánh dò chữ (chỉ Whisper)")
    args = parser.parse_args()
    cau_hinh = ten_cau_hinh_hf(args.model)

    def ham_tai():
        return tai_bo_nghe(args.model, args.beam)
    ham_tai.la_ham_tai = True

    dg.THU_MUC_BAO_CAO.mkdir(parents=True, exist_ok=True)
    for ten_bo in args.bo:
        cac_muc, ket_qua = chay_bo_hf(ten_bo, ham_tai, cau_hinh, args.so_mau)
        bao_cao = dg.viet_bao_cao(ten_bo, cau_hinh, dg.phan_tich(cac_muc, ket_qua))
        tep = dg.THU_MUC_BAO_CAO / f"{ten_bo}__{cau_hinh}.txt"
        tep.write_text(bao_cao + "\n", encoding="utf-8")
        print("\n" + bao_cao.split("\n\nCÁC CẶP")[0])
        print(f"Đã lưu: {asr.hien_thi(tep)}  |  so sánh: python src/asr/danh_gia_bo.py {ten_bo} --so-sanh ... {cau_hinh}")


if __name__ == "__main__":
    main()
