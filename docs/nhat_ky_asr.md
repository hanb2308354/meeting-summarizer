# Nhật ký kỹ thuật phần ASR (Tô Tiểu Hân)

Ghi lại mọi thay đổi của phần nhận dạng giọng nói và tiền xử lý văn bản: đổi gì, vì sao,
số liệu trước/sau, quyết định gì. Dùng làm nguồn cho báo cáo tiến độ và chương báo cáo phần ASR.
Mỗi lần có thay đổi mới thì ghi thêm vào mục "Nhật ký theo thời gian" và cập nhật "Trạng thái hiện tại".

**Quy ước số liệu**
- WER (tỉ lệ lỗi từ) càng thấp càng tốt. Trước khi so, chữ được đưa về cùng cách viết
  (số "20" = "hai mươi", "km" = "ki lô mét", "kì" = "kỳ", dấu thanh kiểu cũ/mới...), nên WER chỉ tính lỗi nghe sai thật.
- `hop_va_dien_thoai`: đoạn họp trực tuyến, hội nghị, tranh luận, thuyết trình, phỏng vấn, gọi điện
  (DataStudio/Vietnamese_ASR_TestingData). `phuong_ngu`: giọng Bắc, Trung, Nam, Tây Nguyên (LSVSC, CC BY 4.0).
  `..._dai`: 4 file × 5 phút ghép từ đoạn ngắn, xen khoảng lặng 0,3–10 giây và ồn nền, mô phỏng cuộc họp.
- "Tốt hơn thật / tệ hơn thật / chưa chắc": khoảng tin cậy 95% (bootstrap ghép cặp theo đoạn) không chứa 0 / chứa 0.
- Tốc độ "3,7x" = thời gian xử lý gấp 3,7 lần độ dài ghi âm, trên máy của Hân (CPU 4 luồng, không GPU).

---

## Tóm tắt các quyết định quan trọng

| # | Quyết định | Bằng chứng | Ngày |
|---|---|---|---|
| 1 | Dùng faster-whisper `medium` int8 trên CPU | Thử nghiệm ban đầu các cỡ model (thu_faster_whisper.py) | 30/09 |
| 2 | Bỏ phân biệt người nói (pyannote), bỏ giao diện demo | Thu hẹp phạm vi; giảng viên không yêu cầu | trước 08/10 |
| 3 | Đo bằng bộ dữ liệu công khai thay vì tự thu âm | Phần ASR chỉ cần tiếng Việt tự nhiên bất kỳ; thu âm tốn thời gian và cần đồng ý người nói | 10/10 |
| 4 | Bỏ từ khóa gợi ý (hotwords), chỉ giữ câu mở đầu | WER 28,2% → 25,6%; từ khóa làm model liệt kê, bịa câu, kẹt | 11/10 |
| 5 | Chỉ thử lại tới nhiệt độ 0,4 | Đoạn bị kẹt 1 → 0, nhanh hơn ~25%, WER không đổi | 11/10 |
| 6 | Nhận dạng từng lượt nói làm mặc định | File dài 36,4% → 29,9%, tốt hơn thật [−13,9; −0,1]; đoạn ngắn bằng nhau | 14/10 |
| 7 | Lượt ra quá ít chữ thì nhận dạng lại | Đoạn bị bịa câu 88% → 42%; đoạn ngắn về lại 25,4% | 14/10 |
| 8 | Loại câu có tốc độ nói bất khả thi (> 12 từ/giây) | Câu bịa có mốc thời gian dồn vào 0,04–0,18 giây; luật bỏ 0 đoạn lời thật của medium/turbo | 15/10 |
| 9 | Không dùng `large-v3-turbo` | Không tốt hơn thật ở bộ nào, chậm hơn medium trên máy Hân (5,1x so với 3,7x) | 14/10 |
| 10 | PhoWhisper là ứng viên thay medium (đang xác nhận) | Sau khi lọc: 21,2% / 5,2% so với medium 25,4% / 8,2% (ước tính, chưa chắc về thống kê) | 15/10 |

---

## Nhật ký theo thời gian

### 30/09 — Dựng nền tảng
- Thử nghiệm faster-whisper, chốt `medium` int8 chạy CPU.
- Viết `chuyen_giong_noi.py`: đọc file âm thanh, nhận dạng, tách câu theo dấu câu, xuất JSON cho phần tóm tắt.

### 08/10 – 09/10 — Hoàn thiện luồng âm thanh → văn bản sạch
- Tiền xử lý âm thanh: lọc tiếng ù 50 Hz, chuẩn hóa âm lượng, giảm tạp âm (tùy chọn).
- Bộ lọc câu bịa `[LOẠI]`: câu kiểu YouTube ("Cảm ơn các bạn đã theo dõi", "Hãy subscribe..."), lặp chữ,
  đọc lại từ khóa gợi ý, lặp lại đoạn trước (kể cả kiểu A, B, A, B). Sửa các trường hợp loại oan lời thật
  (câu liệt kê, câu nhắc lại sau "Dạ.").
- Tách câu theo dấu câu và khoảng ngừng; không cắt ở "...", "v.v.", chữ viết tắt.
- Nhận phần tiền xử lý văn bản từ Anh, tách riêng thành `src/tien_xu_ly` (làm sạch, sửa lỗi nhận dạng, từ đệm,
  câu xã giao); phần NLP của Anh đọc văn bản sạch từ `data/processed`. Kèm kiểm thử.

### 10/10 — Bộ đánh giá trên dữ liệu thật
- Tải mẫu từ Hugging Face (tải thẳng file parquet, chờ và thử lại khi bị giới hạn 429/500), chia đều mẫu
  theo nhóm và giới hạn số đoạn cùng người nói.
- Bỏ VietSuperSpeech khỏi mặc định: lời gốc do máy tạo, không tin được.
- Sửa cách tính WER cho công bằng (số, đơn vị, i/y, vị trí dấu thanh).

### 10/10 – 11/10 — Thử nghiệm cách gợi ý cho model (30 đoạn họp/gọi điện)

| Cấu hình | WER | Tốc độ | Đoạn kẹt |
|---|---|---|---|
| Câu mở đầu + từ khóa (cấu hình cũ) | 28,2% | 5,4x | 1 |
| Chỉ từ khóa | 35,8% | 5,6x | 2 |
| Không gợi ý | 25,8% | 4,0x | 0 |
| Chỉ câu mở đầu | 25,6% | 4,2x | 1 |
| **Chỉ câu mở đầu + thử lại tới 0,4** | **25,6%** | **4,0x** | **0** |

- Kết luận: từ khóa gợi ý có hại → bỏ. Đoạn kẹt mất 81–347 giây cho 4 giây âm thanh và đều ra chữ bịa → giới hạn thử lại.
- Thêm luật loại đoạn chép lại một phần câu mở đầu ("Còn một số từ tiếng Anh.").
- Bộ phương ngữ: 8,3% → 8,2% (không đổi).
- Đo bảng sửa lỗi của tiền xử lý văn bản trên chữ ASR thật: 0 chỗ sửa sai / 2.100 từ.

### 12/10 — Số liệu 100 đoạn và thử file dài
- 100 đoạn mỗi bộ (7.150 từ): họp/gọi điện **25,6%** (tranh luận 8,8%, hội nghị 12,9%, thuyết trình 16,3%,
  họp trực tuyến 24,4%, gọi điện 58,1%); phương ngữ **10,2%** (Bắc 8,4%, Trung 10,4%, Nam 12,6%, Tây Nguyên 12,6%).
- Ghép 4 file × 5 phút: **file dài 36,4%** trong khi nghe từng đoạn ngắn của chính lời đó **27,0%**.
  Lỗi tăng chủ yếu do **mất chữ** (thiếu 841 từ): cửa sổ 30 giây trượt trên cả file bỏ qua cả khúc lời.

### 14/10 — Sửa lỗi mất chữ ở file dài

| Cách nhận dạng | File dài | Thiếu từ | 30 đoạn ngắn | Quyết định |
|---|---|---|---|---|
| Trượt cửa sổ cả file (cũ) | 36,4% | 841 | 25,5% | — |
| Theo lô của faster-whisper | 47,0% | 1.486 | 26,8% | Bỏ |
| Từng lượt nói, lần 1 | 30,5% | 568 | 27,7% | Giữ hướng, còn 1 đoạn bị bịa |
| + gộp lượt quá ngắn | 30,4% | — | 27,8% | Bỏ (không tác dụng; chẩn đoán sai) |
| + bật VAD lần nữa trong lượt | 31,8% | 649 | 29,3% | Bỏ (tệ hơn cả hai bộ) |
| **+ nhận dạng lại lượt ra quá ít chữ** | **29,9%** | **507** | **25,4%** | **Mặc định** |

- Hai lần chẩn đoán sai liên tiếp (đoán do lượt quá ngắn, rồi do VAD) → thêm công cụ chẩn đoán:
  lưu chi tiết từng đoạn model trả về (mốc thời gian, độ tin cậy, xác suất im lặng, nhiệt độ),
  `--chi-doan` chạy lại 1 đoạn và in lỗi theo vị trí, khoảng tin cậy trong `--so-sanh`.
- Nguyên nhân thật (đoạn 0000186): lượt 9,7 giây chỉ ra "Cảm ơn các bạn." → luật mật độ chữ
  (lượt ≥ 3 giây mà < 1 chữ/giây là hỏng) rồi nhận dạng lại (bỏ gợi ý, sau đó nghe kèm lượt bên cạnh).
  Đoạn 0000186: 88% → 42%.
- Khoảng tin cậy file dài tính theo 91 đoạn ngắn đã ghép (thay vì 4 file): −6,5 điểm [−13,9; −0,1] → tốt hơn thật.
- Dời dự án và bộ nhớ đệm model sang ổ D (ổ C chỉ còn 1,6 GB trống).

### 14/10 – 15/10 — So sánh model (cùng 30 + 30 đoạn)

| Model | Họp/gọi điện | Phương ngữ | Tốc độ | Kết luận |
|---|---|---|---|---|
| medium (mặc định) | 25,4% | 8,2% | 3,7x | mốc so sánh |
| large-v3-turbo | 29,1% | 7,1% | 5,1x | chưa chắc cả hai bộ, chậm hơn → không dùng |
| PhoWhisper-medium (chuyển sang CTranslate2) | 37,1% | 25,3% | 11,8x | tệ hơn thật |
| PhoWhisper, không đoán mốc thời gian | 50,0% | — | 10,1x | tệ hơn nữa → bỏ hướng này |
| **PhoWhisper + lọc tốc độ nói (ước tính)** | **21,2%** | **5,2%** | 11,8x | chưa chắc (−4,2 [−9,2; +1,3] và −3,0 [−7,4; +0,6]), thắng 21/30 và 16/30 đoạn |

- PhoWhisper (VinAI, huấn luyện thêm ~844 giờ tiếng Việt) nghe đúng hơn rõ (nghe sai 95–134 từ so với 168 của medium;
  Tây Nguyên 13,9% → 2,4%: medium nghe "lục" thay "luật"), nhưng nối câu bịa sau lời thật.
- Giả thuyết "do model không được dạy đoán mốc thời gian" đã thử và **sai** (bịa nhiều hơn: thừa 200 → 434 từ).
- Dấu hiệu thật, tìm được từ nhật ký chi tiết: lời thật 26 từ / 6,62 giây (độ tin cậy −0,00), câu bịa 12 từ / 0,08 giây.
  → Luật "tốc độ nói bất khả thi". Kiểm chứng: bỏ 0 đoạn của medium và turbo (không xóa nhầm), bỏ 16–23 đoạn bịa của PhoWhisper.
- Câu mở đầu có ích cho PhoWhisper ở cuộc gọi điện (81% → 43%).
- Thêm `--loc-lai`: chấm lại kết quả đã lưu với bộ lọc mới trong vài giây (ước tính, không chạy lại model).

### 15/10 — Giới hạn số token mỗi lượt (đang đo)
- PhoWhisper chậm 11,8x vì khi bịa nó sinh tới ~440 token rồi thử lại ở nhiệt độ khác.
  Giới hạn 20 token/giây + 30 (tối đa 380). Đang chạy thật medium + PhoWhisper để kiểm:
  medium phải giữ nguyên WER, PhoWhisper phải nhanh ngang medium và giữ WER ước tính.

---

## Hướng đã thử và bỏ (kết quả âm, vẫn có giá trị cho báo cáo)

| Hướng | Kết quả | Lý do bỏ |
|---|---|---|
| Từ khóa gợi ý (hotwords) | 25,6% → 35,8% khi chỉ dùng từ khóa | Model liệt kê từ khóa, bịa câu, kẹt |
| Nhận dạng theo lô (BatchedInferencePipeline) | File dài 47,0% | Mất chữ nhiều hơn (1.486 từ) |
| Gộp lượt nói quá ngắn | Không đổi (30,4% / 27,8%) | Chẩn đoán sai nguyên nhân |
| Bật VAD lần nữa trong từng lượt | Tệ hơn ở cả hai bộ | Không chữa được câu bịa |
| PhoWhisper không đoán mốc thời gian | Thừa 200 → 434 từ | Bịa nhiều hơn |
| large-v3-turbo | Không tốt hơn thật, chậm hơn | Không đáng đổi |
| VietSuperSpeech làm bộ đánh giá | Lời gốc do máy tạo | Không tin được |

---

## Trạng thái hiện tại (15/10)

- Giai đoạn 7/13 (chọn model). Điểm 7,5/10, hoàn thiện khoảng 55% theo 16 điều kiện của kế hoạch.
- Kiểm thử tự động: 58 ca ASR + 9 nhóm tiền xử lý, đều đạt.
- Việc tiếp theo: xác nhận PhoWhisper bằng chạy thật; thử model lớn (large-v3, PhoWhisper-large);
  tạo bộ kiểm tra giữ riêng (≥ 100 đoạn mỗi bộ + họp thật tự ghi).
