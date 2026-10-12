# -*- coding: utf-8 -*-
"""
Ghép các đoạn ngắn của một bộ đánh giá thành vài FILE DÀI (mặc định 5 phút) giống cuộc họp:
nhiều lượt nói nối nhau, xen khoảng lặng ngắn/dài và tiếng ồn nền nhẹ.

Vì sao cần: đoạn 5-15 giây không thử được những lỗi chỉ có ở file dài
    - model cắt file thành từng khúc 30 giây, câu mở đầu chỉ có tác dụng ở khúc đầu
    - model hay bịa chữ ở khoảng lặng dài giữa các lượt nói
    - bộ lọc "lặp lại đoạn trước", cách tách câu chỉ thật sự chạy khi file dài
Lời gốc vẫn chính xác: là lời gốc của các đoạn nối lại theo đúng thứ tự.

Kết quả là một bộ đánh giá mới, chạy như mọi bộ khác (không đưa lên git):
    data/bo_danh_gia/<bộ>_dai/audio/<bộ>_dai_01.wav ...
    data/bo_danh_gia/<bộ>_dai/nhan.json   (thêm trường "tu_doan": id các đoạn ngắn đã ghép)

Cách dùng:
    python src/asr/ghep_file_dai.py hop_va_dien_thoai                  (4 file x 5 phút)
    python src/asr/ghep_file_dai.py hop_va_dien_thoai --so-file 2 --phut 10
    python src/asr/danh_gia_bo.py hop_va_dien_thoai_dai
Báo cáo của bộ _dai so luôn với WER khi nghe từng đoạn ngắn của chính các đoạn đó.
"""
import argparse
import json
import random
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

THU_MUC_BO = asr.THU_MUC_GOC / "data" / "bo_danh_gia"
SR = asr.TAN_SO_MAU
# Khoảng lặng giữa hai lượt nói (giây): phần lớn ngắn, đôi khi rất dài (lúc mọi người suy nghĩ,
# chờ chia sẻ màn hình) - chỗ model hay bịa chữ
CAC_KIEU_LANG = [(0.70, 0.3, 1.5), (0.25, 1.5, 4.0), (0.05, 6.0, 10.0)]   # (tỉ lệ, từ, đến)
DO_ON_NEN = 10 ** (-50 / 20)        # tiếng ồn nền rất nhẹ (-50 dBFS), như phòng họp yên tĩnh


def khoang_lang(rd):
    x = rd.random()
    for ti_le, tu, den in CAC_KIEU_LANG:
        if x < ti_le:
            return rd.uniform(tu, den)
        x -= ti_le
    return CAC_KIEU_LANG[-1][2]


def ghi_wav(duong_dan, song_am):
    with wave.open(str(duong_dan), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((np.clip(song_am, -1, 1) * 32767).astype(np.int16).tobytes())


def ghep(ten_bo, so_file, so_phut, hat_giong):
    thu_muc_nguon = THU_MUC_BO / ten_bo
    tep_nhan = thu_muc_nguon / "nhan.json"
    if not tep_nhan.exists():
        sys.exit(f"Chưa có bộ {ten_bo}. Chạy trước:  python src/asr/tai_bo_danh_gia.py {ten_bo}")
    cac_muc = json.loads(tep_nhan.read_text(encoding="utf-8"))
    if any("tu_doan" in m for m in cac_muc):
        sys.exit(f"{ten_bo} đã là bộ ghép, hãy chọn bộ gốc.")

    rd = random.Random(hat_giong)
    rd.shuffle(cac_muc)   # trộn để mỗi file có nhiều kiểu nói / giọng khác nhau, như nhiều người họp
    ten_moi = f"{ten_bo}_dai"
    thu_muc = THU_MUC_BO / ten_moi
    (thu_muc / "audio").mkdir(parents=True, exist_ok=True)

    ket_qua, vi_tri = [], 0
    for so in range(1, so_file + 1):
        phan, cac_id, cac_chu, do_dai = [], [], [], 0.0
        while do_dai < so_phut * 60 and vi_tri < len(cac_muc):
            muc = cac_muc[vi_tri]
            vi_tri += 1
            try:
                song_am = asr.doc_am_thanh(thu_muc_nguon / muc["tep"])
            except asr.LoiDauVao:
                continue   # đoạn hỏng thì bỏ qua, như khi chạy đánh giá
            if phan:
                lang = np.zeros(int(khoang_lang(rd) * SR), dtype=np.float32)
                phan.append(lang)
                do_dai += len(lang) / SR
            phan.append(song_am)
            do_dai += len(song_am) / SR
            cac_id.append(muc["id"])
            cac_chu.append(muc["text"].strip())
        if not phan:
            break
        song_am = np.concatenate(phan)
        song_am = song_am + np.random.default_rng(hat_giong + so).normal(0, DO_ON_NEN, len(song_am)).astype(np.float32)
        tep = Path("audio") / f"{ten_moi}_{so:02d}.wav"
        ghi_wav(thu_muc / tep, song_am)
        ket_qua.append({"id": f"{ten_moi}_{so:02d}", "tep": tep.as_posix(), "text": " ".join(cac_chu),
                        "nhom": "file_dai", "nguon": f"{ten_moi}_{so:02d}", "row_idx": so,
                        "tu_doan": cac_id, "nguon_bo": ten_bo})
        print(f"  {tep.name}: {do_dai / 60:.1f} phút, ghép {len(cac_id)} đoạn")
        if vi_tri >= len(cac_muc) and so < so_file:
            print(f"  ⚠ Hết đoạn ngắn sau {so} file. Tải thêm: "
                  f"python src/asr/tai_bo_danh_gia.py {ten_bo} --so-mau <số lớn hơn>")
            break

    (thu_muc / "nhan.json").write_text(json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nĐã tạo bộ {ten_moi} ({len(ket_qua)} file) trong {asr.hien_thi(thu_muc)}/")
    print(f"Bước tiếp theo:  python src/asr/danh_gia_bo.py {ten_moi}")
    return ket_qua


def main():
    parser = argparse.ArgumentParser(description="Ghép các đoạn ngắn thành file dài giống cuộc họp.")
    parser.add_argument("bo", help="Tên bộ gốc trong data/bo_danh_gia/ (vd: hop_va_dien_thoai)")
    parser.add_argument("--so-file", type=int, default=4, help="Số file dài (mặc định 4)")
    parser.add_argument("--phut", type=float, default=5.0, help="Độ dài mỗi file, phút (mặc định 5)")
    parser.add_argument("--hat-giong", type=int, default=42)
    args = parser.parse_args()
    if args.so_file < 1 or args.phut <= 0:
        sys.exit("--so-file và --phut phải lớn hơn 0.")
    ghep(args.bo, args.so_file, args.phut, args.hat_giong)


if __name__ == "__main__":
    main()
