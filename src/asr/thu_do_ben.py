# Thử độ bền với file rất dài (điều kiện C2): đọc file, tiền xử lý âm thanh và cắt lượt nói (VAD)
# trên một file N giờ, đo RAM cao nhất và thời gian. Không chạy model nhận dạng: phần đó xử lý từng
# lượt nói (<= 25 giây) nên RAM không tăng theo độ dài file; phần tăng theo độ dài là toàn bộ sóng
# âm được nạp vào bộ nhớ, nên đây là chỗ cần thử.
#
# Cách dùng:  python src/asr/thu_do_ben.py            (2 giờ)
#             python src/asr/thu_do_ben.py --gio 0.5
# File thử được tạo tạm rồi xóa; cần trống ~250 MB mỗi giờ âm thanh.
import argparse
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chuyen_giong_noi as asr  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def tao_file(duong_dan, so_gio):
    """Ghi file WAV 16 kHz giống buổi họp: tiếng nói giả (hài âm 120-220 Hz, bật tắt theo câu) xen
    khoảng lặng, có tiếng ồn nền. Ghi từng phút để không tốn RAM lúc tạo."""
    rng = np.random.default_rng(0)
    sr = asr.TAN_SO_MAU
    with wave.open(str(duong_dan), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        for phut in range(int(round(so_gio * 60))):
            t = np.arange(60 * sr) / sr
            f0 = 120 + 100 * (phut % 7) / 6
            giong = sum(0.08 / k * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 6))
            bat = ((t % 9) < 6) & ((t % 1.3) < 1.0)          # câu 6 giây, nghỉ 3 giây; ngắt quãng theo từ
            x = giong * bat + 0.01 * rng.standard_normal(len(t))
            f.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def main():
    parser = argparse.ArgumentParser(description="Thử RAM và thời gian với file rất dài.")
    parser.add_argument("--gio", type=float, default=2.0, help="Độ dài file thử (giờ), mặc định 2")
    args = parser.parse_args()

    tien_trinh = psutil.Process()
    cao_nhat = [tien_trinh.memory_info().rss]
    dang_do = [True]

    def do_ram():
        while dang_do[0]:
            cao_nhat[0] = max(cao_nhat[0], tien_trinh.memory_info().rss)
            time.sleep(0.2)

    with tempfile.TemporaryDirectory() as tm:
        tep = Path(tm) / "hop_rat_dai.wav"
        print(f"Tạo file thử {args.gio:g} giờ...")
        tao_file(tep, args.gio)
        print(f"  {tep.stat().st_size / 1e6:.0f} MB. RAM lúc đầu: {cao_nhat[0] / 1e6:.0f} MB")
        threading.Thread(target=do_ram, daemon=True).start()
        bat_dau = time.time()
        try:
            song_am = asr.doc_am_thanh(tep)
            t_doc = time.time() - bat_dau
            song_am, buoc = asr.tien_xu_ly_am_thanh(song_am, False)
            t_tien = time.time() - bat_dau - t_doc
            cac_luot = asr.cat_luot_noi(song_am)
            t_vad = time.time() - bat_dau - t_doc - t_tien
        except MemoryError:
            dang_do[0] = False
            sys.exit(f"HẾT RAM khi xử lý file {args.gio:g} giờ (RAM cao nhất {cao_nhat[0] / 1e6:.0f} MB)")
        dang_do[0] = False
        time.sleep(0.3)
    tong_ram = psutil.virtual_memory().total
    print(f"Đọc file {t_doc:.0f}s | tiền xử lý ({', '.join(buoc)}) {t_tien:.0f}s | cắt lượt nói {t_vad:.0f}s "
          f"-> {len(cac_luot)} lượt")
    print(f"RAM cao nhất: {cao_nhat[0] / 1e6:.0f} MB / máy có {tong_ram / 1e9:.1f} GB "
          f"({cao_nhat[0] / tong_ram:.0%}); sóng âm {len(song_am) * 4 / 1e6:.0f} MB")
    print("ĐẠT" if cao_nhat[0] < 0.5 * tong_ram else "CẦN XEM LẠI: dùng quá nửa RAM của máy")


if __name__ == "__main__":
    main()
