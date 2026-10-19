# Nhật ký phần nhận dạng giọng nói (ASR) — Tô Tiểu Hân

## 1. Tóm tắt

**Phần của Hân làm gì:** nhận file ghi âm cuộc họp → chuyển thành chữ → làm sạch chữ → giao văn bản sạch
cho phần tóm tắt của Anh.

```
File ghi âm → Làm sạch âm thanh → Nhận dạng giọng nói (Whisper) → Lọc câu bịa → Tách câu → JSON
           → Làm sạch văn bản (sửa lỗi nhận dạng, bỏ từ đệm, câu xã giao) → Văn bản sạch cho phần tóm tắt
```

**Kết quả hiện tại** (WER = tỉ lệ lỗi theo **âm tiết** — tiếng Việt viết tách âm tiết nên "từ" ở đây là âm tiết;
không so thẳng với WER tiếng Anh. Càng thấp càng tốt. Số trên bộ dùng để chỉnh 30 + 30 đoạn; số chính thức sẽ lấy
từ bộ kiểm tra giữ riêng 100 + 100 đoạn):

| Loại âm thanh | Lúc bắt đầu (medium) | Medium sau chỉnh | Chế độ chính xác (PhoWhisper) |
|---|---|---|---|
| Họp, hội nghị, gọi điện (đoạn ngắn) | 28,2% | 25,4% | 18,5% (bộ giữ riêng: **18,1%**) |
| Cuộc họp dài 5 phút (ghép nhân tạo) | 36,4% | 29,9% | 26,7% |
| Giọng các miền | 8,3% | 8,2% | 4,5% (bộ giữ riêng: **6,8%**) |
| Tốc độ trên máy 2 nhân (lần độ dài ghi âm) | — | 3,3–3,8x | 3,5–5,3x (chế độ nhanh PhoWhisper-small: 1,4–1,9x, lỗi 22,5% / 8,5%) |
| Model bị kẹt | có | 0 | 0 |

**Cấu hình đang dùng:** chế độ chính xác = PhoWhisper-medium + đệm im lặng, không gợi ý (chế độ nhanh =
PhoWhisper-small, cùng cách chạy), CPU, số luồng = số nhân thật · nhận dạng từng lượt nói · lượt nào ra quá ít chữ thì nhận dạng lại · lọc câu bịa (kể cả câu có tốc độ nói bất khả thi).

**Đã xong:** chọn model (PhoWhisper-medium, đã chạm giới hạn model chạy được trên máy này), tốc độ ngang Whisper
medium, kết quả chính thức trên bộ giữ riêng. **Còn lại:** chốt gộp lượt, chẩn đoán phần chênh của file dài, bỏ chữ
rác, ghi âm một cuộc họp thật 15–20 phút để kiểm lần cuối, báo cáo tiến độ.

**Cách đo dùng xuyên suốt:**
- Không tự thu âm mà dùng bộ dữ liệu công khai có sẵn lời gốc: 30–100 đoạn họp/hội nghị/gọi điện, 30–100 đoạn giọng
  Bắc/Trung/Nam/Tây Nguyên, và 4 file 5 phút ghép từ các đoạn đó để giả lập cuộc họp dài.
- Mọi thay đổi đều đo trên **cùng một bộ đoạn** trước và sau.
- Chỉ đổi cấu hình mặc định khi chênh lệch là **thật** (khoảng tin cậy 95% không chứa 0), không phải do may rủi.

---

## 2. Các vấn đề đã giải quyết

### 2.1. Chọn công cụ và model nền
**Mục đích:** chạy được trên laptop sinh viên không có card đồ họa.
**Đã làm:** viết script đo tốc độ và độ chính xác của faster-whisper (bản Whisper chạy nhanh trên CPU)
trên một file thử, chạy được với từng cỡ model.
**Chọn:** `medium`, nén int8 để chạy nhanh hơn trên CPU.
**Lưu ý:** số liệu của lần thử này không được lưu lại. Việc so sánh model có số liệu đầy đủ đang làm ở mục 3.

### 2.2. Làm sạch âm thanh đầu vào
**Mục đích:** giảm lỗi do âm thanh xấu (tiếng ù điện, ghi âm quá nhỏ hoặc quá to).
**Đã làm:** lọc tiếng ù 50 Hz, chuẩn hóa âm lượng; giảm tạp âm để ở dạng tùy chọn.
**Lý do giảm tạp âm chỉ là tùy chọn:** giảm tạp âm mạnh có thể làm méo giọng; sẽ đo bật/tắt ở giai đoạn sau.

### 2.3. Chống "bịa chữ"
**Vấn đề:** Whisper học từ phụ đề YouTube nên ở chỗ im lặng hoặc khó nghe hay tự bịa câu như
"Cảm ơn các bạn đã theo dõi", "Hãy subscribe cho kênh...", hoặc lặp một chữ nhiều lần.

| Đã thử | Kết quả | Quyết định |
|---|---|---|
| Lọc câu kiểu YouTube, lặp chữ, lặp lại đoạn trước | Chặn được phần lớn | Giữ |
| Lọc mọi câu "lặp lại đoạn trước" | Xóa nhầm câu thật như "Dạ.", câu người nói nhắc lại | Sửa: chỉ xét câu từ 4 từ, cho phép kiểu "A, Dạ., A" |
| Lọc câu chép lại câu gợi ý ("Còn một số từ tiếng Anh.") | Model hay chép gợi ý ở chỗ khó nghe | Giữ |
| Lọc theo **tốc độ nói bất khả thi** (> 12 từ/giây) | Câu bịa có thời gian dồn vào 0,04–0,18 giây (vd 12 từ trong 0,08 giây), lời thật ~4 từ/giây. Không xóa nhầm đoạn nào của model medium | Giữ (15/10) |

### 2.4. Cách "gợi ý" cho model
**Mục đích:** giúp model nghe đúng từ chuyên môn trong cuộc họp (deadline, frontend, slide...).
**Đã làm:** so 4 cách trên cùng 30 đoạn họp/gọi điện.

| Cách | WER | Tốc độ | Model bị kẹt | Quyết định |
|---|---|---|---|---|
| Câu mở đầu + danh sách từ khóa (cách cũ) | 28,2% | 5,4x | 1 | Bỏ |
| Chỉ danh sách từ khóa | 35,8% | 5,6x | 2 | Bỏ: model đọc lại danh sách, bịa câu |
| Không gợi ý gì | 25,8% | 4,0x | 0 | — |
| **Chỉ câu mở đầu** + giới hạn số lần thử lại | **25,6%** | **4,0x** | **0** | **Chọn** |

**Bài học:** gợi ý càng nhiều chưa chắc càng tốt. Danh sách từ khóa làm model "nghe ra" từ khóa ở chỗ không có.
"Giới hạn số lần thử lại" (nhiệt độ tới 0,4): các lần model bị kẹt 81–347 giây cho 4 giây âm thanh đều ra chữ bịa,
nên không cần cho nó thử tiếp.

### 2.5. Cuộc họp dài bị mất chữ
**Vấn đề phát hiện được:** cùng một lời nói, nghe từng đoạn ngắn thì sai 27,0%, nhưng ghép thành file 5 phút
thì sai 36,4%. Phần lỗi tăng thêm chủ yếu là **mất chữ** (841 từ): model bỏ qua cả khúc lời.

| Cách đã thử | File dài | Đoạn ngắn | Quyết định |
|---|---|---|---|
| Đọc cả file theo cửa sổ 30 giây (cách cũ) | 36,4% | 25,5% | Bỏ |
| Xử lý theo lô (có sẵn trong faster-whisper) | 47,0% | 26,8% | Bỏ: mất chữ nhiều hơn |
| Cắt theo từng lượt nói rồi nhận dạng từng lượt | 30,5% | 27,7% | Giữ hướng, nhưng 1 đoạn bị bịa cả câu |
| + gộp các lượt quá ngắn | 30,4% | 27,8% | Bỏ: không tác dụng (đoán sai nguyên nhân) |
| + cắt lại thêm một lần trong mỗi lượt | 31,8% | 29,3% | Bỏ: tệ hơn |
| **+ lượt nào ra quá ít chữ thì nhận dạng lại** | **29,9%** | **25,4%** | **Chọn** (tốt hơn thật) |

**Quá trình:** sau hai lần đoán sai nguyên nhân, đã làm thêm công cụ xem chi tiết từng đoạn model trả về.
Nhờ đó thấy nguyên nhân thật: một lượt nói 9,7 giây mà model chỉ ra "Cảm ơn các bạn." (4 chữ, trong khi
bình thường phải 30–40 chữ). Từ đó thêm luật "lượt dài mà quá ít chữ là hỏng → nhận dạng lại".

### 2.6. Làm sạch văn bản (nhận lại từ Anh)
**Mục đích:** văn bản giao cho phần tóm tắt phải sạch: sửa từ nghe nhầm hay gặp (vd "phôn thên" → "frontend"),
bỏ từ đệm ("ờ", "à"), đánh dấu câu xã giao.
**Đã làm:** tách thành thư mục riêng `src/tien_xu_ly` để không lẫn với code của Anh; viết kiểm thử.
**Kết quả:** đo trên chữ máy nghe thật: 0 chỗ sửa sai trên 2.100 từ.
**Chưa làm:** thêm luật sửa lỗi từ danh sách "các cặp hay nghe nhầm". Cố ý để sau khi chốt model, vì mỗi model
nghe nhầm theo kiểu khác nhau, và chỉ thêm luật cho lỗi lặp lại nhiều lần.

### 2.7. Xây dựng cách đo
**Mục đích:** biết chính xác sai ở đâu, sửa có hiệu quả không, thay vì đoán.

| Đã làm | Vì sao |
|---|---|
| Tải bộ dữ liệu họp/gọi điện và bộ giọng miền từ Hugging Face | Có lời gốc chính xác để so; đủ đa dạng |
| Bỏ bộ VietSuperSpeech | Lời gốc do máy tạo ra, không tin được |
| Chuẩn hóa trước khi so ("20" = "hai mươi", "kì" = "kỳ"...) | Không tính oan cách viết khác là lỗi |
| Ghép đoạn ngắn thành file 5 phút | Thử được lỗi chỉ có ở cuộc họp dài mà không cần thu âm |
| Khoảng tin cậy 95% khi so sánh | Phân biệt cải thiện thật với may rủi |
| Công cụ xem chi tiết 1 đoạn (`--chi-doan`) | Tìm đúng nguyên nhân trước khi sửa |
| Chấm lại kết quả cũ với bộ lọc mới (`--loc-lai`) | Thử ý tưởng trong vài giây thay vì chạy lại 1 tiếng |

---

## 3. Đang làm: chọn model

**Mục đích:** biết `medium` có phải là tốt nhất chưa. Nếu model khác tốt hơn thì đổi; nếu không thì đã chạm giới hạn.

| Model | Họp/gọi điện | Giọng miền | Tốc độ | Nhận xét |
|---|---|---|---|---|
| medium (đang dùng) | 25,4% | 8,2% | 3,7x | Mốc so sánh |
| large-v3-turbo | 29,1% | 7,1% | 5,1x | Không tốt hơn thật, lại chậm hơn → **bỏ** |
| PhoWhisper-medium (VinAI) | 37,1% | 25,3% | 11,8x | Nghe đúng hơn nhưng nối câu bịa sau lời thật |
| PhoWhisper, tắt đoán mốc thời gian | 50,0% | — | 10,1x | Thử chữa bịa câu, **sai hướng**, bịa nhiều hơn → **bỏ** |
| PhoWhisper + lọc tốc độ nói (ước tính) | **21,2%** | **5,2%** | 11,8x | Tốt nhất, thắng medium ở 21/30 và 16/30 đoạn, chưa chắc về thống kê |
| PhoWhisper + lọc + giới hạn số chữ mỗi lượt (chạy thật, 15/10) | **21,2%** | **5,2%** | 11,0x / 13,3x | Xác nhận đúng số ước tính; tốc độ gần như không đổi |

- Điểm mạnh của PhoWhisper: nghe đúng giọng miền, ví dụ medium nghe "**lục** ban hành văn bản",
  PhoWhisper nghe đúng "**luật**"; giọng Tây Nguyên 13,9% → 2,4%.
- Điểm yếu: hay nối câu bịa sau lời thật, nên chậm. Đã thêm giới hạn số chữ model được sinh mỗi lượt
  (theo độ dài lượt): WER giữ đúng như ước tính nhưng tốc độ chỉ 11,8x → 11,0x, tức chậm không chủ yếu vì câu bịa dài.
- Đếm token (15/10): PhoWhisper dành 50–67% số token cho câu bịa nối sau lời thật (vd đoạn 6,8 giây: 48 token lời thật,
  99 token bịa), medium thì 0. Câu bịa là một phần lý do chậm.
- **Phép thử phân định (15/10):** chạy PhoWhisper bằng thư viện gốc của VinAI (transformers, số thực đầy đủ) trên cùng
  đoạn: **dừng đúng chỗ, không có câu bịa** (43 token, đúng 100%). → Lỗi không nằm ở model mà ở bản chuyển đổi/cách chạy.
  Nghi vấn chính: lúc chuyển đã nén trọng số xuống int8, làm model tinh chỉnh mất khả năng "biết dừng".
- Giả thuyết "nén int8 làm model không biết dừng": **sai**. Bản giữ số thực, tính float32 vẫn bịa y hệt
  (đoạn 6,8 giây: 48 token lời thật + 84 token "cảm ơn và hẹn gặp lại......").
- Nguyên nhân tìm được bằng cách đọc mã nguồn faster-whisper: phần thiếu của cửa sổ 30 giây được đệm bằng
  **số 0 trên phổ âm thanh**, mà 0 không phải im lặng (im lặng thật = −1,12, tiếng nói ≈ 0,9). Thư viện gốc đệm
  im lặng thật vào âm thanh. Câu bịa luôn nằm đúng ở vùng đệm này (6,62 → 6,72 giây, ngay sau lời thật).
- Đệm im lặng thật (`--dem-im-lang`): với PhoWhisper **không chữa được**, còn tệ hơn: câu bịa rải vào khoảng im lặng
  (17–30 giây) với tốc độ bình thường nên lọt bộ lọc (đoạn 1753: 0% → 127%). Với medium trên 1 đoạn: 5,6% → 0%,
  nhanh hơn 29% (77 → 55 giây) — cần đo trên cả bộ.
- Vòng thử cuối cho PhoWhisper (gom mọi khác biệt còn lại với bản gốc trong 1 lượt, đoạn 0001753): cả 4 cách vẫn bịa.
  | Cách chạy | Token model sinh | Thời gian | Ghi chú |
  |---|---|---|---|
  | Đủ điều kiện như bản gốc (không gợi ý, không mốc, đệm im lặng, không tiền xử lý) | 75 | 90 s | vẫn bịa |
  | Chỉ bỏ tiền xử lý âm thanh | 147 | 126 s | vẫn bịa |
  | Dò 1 nhánh (beam 1) | 85 | 82 s | WER 0% sau lọc, nhanh hơn 35% |
  | Như bản gốc + beam 1 | 84 | — | vẫn bịa |
- **Kết luận (dừng tìm nguyên nhân):** đã loại int8, đệm phổ bằng 0, mốc thời gian, gợi ý, tiền xử lý âm thanh, số nhánh dò.
  Bản gốc (transformers) dừng đúng, bản faster-whisper không bao giờ sinh token kết thúc ở model này. Ghi là giới hạn
  của faster-whisper với PhoWhisper; không vá tiếp vào bên trong thư viện.
- Hai điều rút ra dùng được: (1) beam 1 cùng WER mà nhanh hơn → đưa vào bước tăng tốc (C1); (2) khi đệm im lặng,
  câu bịa **luôn** nằm sau cuối âm thanh thật của lượt → có thể cắt bằng mốc thời gian thay vì đoán theo nội dung.
- **Luật mới (bundle 28): bỏ chữ nằm sau cuối âm thanh thật của lượt.** Trong chế độ từng lượt, từ có điểm giữa
  sau (độ dài lượt + 0,5 giây) bị bỏ, in `[LOẠI - ngoài âm thanh thật của lượt]`, ghi vào chi tiết để `--chi-doan` hiện ra.
  Không đệm thì model không thể ra từ sau cuối âm thanh, nên luật chỉ có tác dụng khi bật `--dem-im-lang`; mặc định
  không đổi kết quả. Cần đo: medium và PhoWhisper với `--dem-im-lang` (và beam 1) trên 30 + 30 đoạn, so bằng khoảng tin cậy.
- Sự cố: dời bộ nhớ đệm Hugging Face sang ổ D bằng cách chép file làm hỏng các file "lối tắt" bên trong
  (thành file rỗng): `medium` không tải được (đã tải lại, chạy bình thường), bản gốc PhoWhisper cũng hỏng.
  Bài học: không chép tay bộ nhớ đệm model; xóa rồi để chương trình tự tải lại vào chỗ mới.
  Đã thêm báo lỗi rõ ràng khi thiếu thư mục model hoặc bộ nhớ đệm hỏng.

- **Kết quả bundle 28 (đo 15–16/10, 30 + 30 đoạn và 4 file dài 5 phút, khoảng tin cậy 95% so với medium):**

  | Cấu hình | Họp/gọi điện | Giọng miền | File dài | Tốc độ (đoạn ngắn) | Kết luận |
  |---|---|---|---|---|---|
  | medium (mặc định) | 25,4% | 8,2% | 29,9% | 3,7x / 4,6x | mốc so sánh |
  | medium + đệm im lặng | 25,6% | 8,4% | 32,1% | 3,8x / 4,7x | không có ích → **bỏ** (1 đoạn thử trước đó là may) |
  | medium + beam 1 | 27,4% (TỆ HƠN THẬT) | 9,3% (TỆ HƠN THẬT) | — | 3,6x / 4,1x | nhanh hơn rất ít mà tệ hơn → **bỏ** |
  | PhoWhisper | 21,2% | 5,2% | — | 11,0x / 13,3x | |
  | **PhoWhisper + đệm im lặng + luật cắt** | **20,4% (TỐT HƠN THẬT, −5,0 [−8,6; −1,0])** | 5,6% (−2,5, chưa chắc) | — | 10,2x / 12,6x | **chính xác nhất** |
  | PhoWhisper + đệm + beam 1 | 21,7% | 6,0% | 28,1% (−1,8, tốt hơn ở 4/4 file) | 10,0x / 10,0x | tệ hơn chút, nhanh hơn ít → không dùng beam 1 |
  | large-v3 | 32,7% | 6,7% | — | 8,0x / 9,0x | bịa câu kết video rất tự tin (7/30 đoạn) → **bỏ** |
  | PhoWhisper-large | 22,6% | 7,8% | — | 12,1x / 17,1x | không hơn bản medium, chậm hơn → **bỏ** |

- Luật cắt chữ ngoài âm thanh thật: bỏ 200 khúc trên mọi lần chạy; các khúc xem được đều là câu bịa (câu kết video,
  "cảm ơn và hẹn gặp lại", chuỗi lặp "a b b b..."). Với medium chỉ cắt 2 khúc ở đoạn ngắn ("mọi người.",
  "đã theo dõi.") — cũng là câu bịa. Chưa thấy cắt nhầm lời thật.
- **Kết luận chọn model (điều kiện A1 đạt):** đã thử đủ 5 model; PhoWhisper-medium + đệm im lặng là bản duy nhất
  TỐT HƠN THẬT medium, không model nào hơn nó. Model lớn hơn không giúp gì trên tiếng Việt ở đây.
- **Còn vướng: tốc độ.** PhoWhisper không bao giờ tự dừng nên lượt nào cũng sinh tới giới hạn token
  (20 token/giây + 30), phần lớn là chữ bịa rồi bị cắt. File họp 5 phút mất khoảng 38 phút. Chưa đổi mặc định
  cho tới khi đo xong cách tăng tốc (bundle 29): giới hạn token sát hơn và dùng nhiều luồng CPU hơn.
- Bổ sung bộ lọc (bundle 29): các câu kêu gọi kiểu YouTube ("Hãy subscribe cho kênh...", "ủng hộ kênh của mình",
  "để không bỏ lỡ những video") luôn bị loại kể cả khi model tự tin, nối 2 câu tới 30 từ vẫn bắt được; câu họp thật
  "tăng lượt subscribe cho kênh của khách hàng" vẫn giữ (có ca kiểm thử).

- **Kết quả bundle 29 (16/10) — tăng tốc PhoWhisper:**

  | Thử | Họp/gọi điện | Giọng miền | Tốc độ | Kết luận |
  |---|---|---|---|---|
  | PhoWhisper + đệm, giới hạn token cũ (20/giây + 30) | 20,4% | 5,6% | 10,2x / 12,6x | mốc |
  | giới hạn 14/giây + 15 | 20,9% | 7,5% | 10,2x / 12,7x | không nhanh hơn, tệ hơn |
  | giới hạn 12/giây + 10 | 25,2% | 12,3% | 10,1x / 12,2x | cắt mất lời → **bỏ** |
  | giới hạn 10/giây + 10 | 26,8% | 18,3% | 10,0x / 12,9x | cắt mất lời → **bỏ** |
  | 2 luồng CPU thay vì 4 (máy Hân: 2 nhân thật, 4 luồng) — 10 + 10 đoạn | y hệt | y hệt | medium 3,9x → 3,3x; PhoWhisper 11,8x → 9,7x | **nhanh hơn 16–18%, giữ** |

  - Giả thuyết "PhoWhisper chậm vì luôn sinh chữ tới giới hạn token" **sai**: siết giới hạn không nhanh hơn chút nào,
    lại cắt mất lời (dù thống kê token lời thật — trung vị 8,1, cao nhất 12,8 token/giây — cho thấy giới hạn 12 lẽ ra đủ;
    cơ chế chưa rõ, không theo đuổi vì không có lợi về tốc độ). Giữ giới hạn cũ.
  - Số luồng: đặt bằng số nhân thật (tự đếm bằng psutil) là mặc định mới.
  - Bộ lọc câu kết video mới, chấm lại trên kết quả cũ: large-v3 bỏ thêm 7 đoạn bịa (32,7% → 32,2%), medium và
    PhoWhisper bỏ thêm 0 đoạn → không loại nhầm lời thật.
  - Máy chỉ có 2 nhân: ngay cả medium cũng mất ~3,3 lần độ dài ghi âm. Điều kiện tốc độ C1 (≤ 1,5x) có thể là giới
    hạn phần cứng; cần đo chỗ tốn thời gian thật (bundle 30: đo thời gian từng bước) và một model nhỏ làm chế độ nhanh.
- **Đổi mặc định (bundle 30):** `chuyen_giong_noi.py` có 2 chế độ: `chinh_xac` (mặc định, PhoWhisper + đệm im lặng)
  và `nhanh` (medium). Căn cứ: PhoWhisper + đệm TỐT HƠN THẬT medium ở bộ họp, không bộ nào tệ hơn thật (đúng quy
  tắc đổi mặc định). Chưa có model PhoWhisper đã chuyển đổi thì tự lùi về medium và báo cách tạo. Còn phải xác nhận
  trên file dài 5 phút với đúng cấu hình mặc định (bundle 30); nếu tệ hơn thì quay lại medium.

- **Kết quả bundle 30 (16–17/10):**
  - **Tìm ra chỗ chậm thật (đo thời gian từng bước, 6 đoạn, 62 giây âm thanh, máy 2 nhân):**

    | | Gọi nhận dạng | Lần nghe cửa sổ 30 giây | Nghe | Sinh chữ | Dò mốc thời gian | Tổng |
    |---|---|---|---|---|---|---|
    | medium | 6 | 6 | 129s (49%) | 112s (42%) | 22s | 266s (4,3x) |
    | PhoWhisper + đệm | 6 | **15** | 265s (52%) | 195s (39%) | 44s | 505s (8,1x) |

    Mỗi lần nghe một cửa sổ mất ~21 giây trên máy này. PhoWhisper không biết dừng nên faster-whisper mở thêm cửa
    sổ ngay trong phần im lặng đệm (2,5 cửa sổ mỗi lượt), chữ ra ở đó đằng nào cũng bị cắt. Đây mới là lý do chậm,
    không phải số token (bundle 29) hay thử lại nhiệt độ (không có lần thử lại nào).
    **Sửa (bundle 31):** đọc kết quả từng cửa sổ và dừng ngay khi gặp đoạn bắt đầu sau cuối âm thanh thật — các
    cửa sổ sau chỉ còn phần đệm nên không mất lời thật; chữ ra phải giống hệt, chỉ nhanh hơn. Đang đo.
  - **Chế độ chính xác trên file dài 5 phút (xác nhận đổi mặc định):** 27,7% so với medium 29,9% (−2,2 điểm,
    tốt hơn ở 3/4 file, chưa chắc) → không tệ hơn, **giữ mặc định**.
  - **Model `small` cho chế độ nhanh:** họp 31,0% (medium 25,4%), giọng miền 13,7% (8,2%), tốc độ 1,3x / 1,5x
    (đạt mức ≤ 1,5x). Nhanh gấp ~2,8 lần medium nhưng lỗi nhiều hơn rõ. Ghi nhận làm phương án cho máy yếu,
    chưa thay chế độ nhanh.
- **Độ bền file rất dài (C2, `src/asr/thu_do_ben.py`):** đo trên máy phát triển: file 1 giờ dùng tối đa ~1,1 GB RAM
  cho đọc + tiền xử lý + cắt lượt nói (khoảng 4–5 lần dung lượng sóng âm); file 2 giờ ước ~2 GB. Đo trên máy Hân ở bundle 31.

- **Kết quả bundle 31 (17/10):**
  - Bản sửa thứ nhất (dừng khi đoạn BẮT ĐẦU sau cuối âm thanh): chữ ra **giống hệt** (20,4% / 5,6%, file dài 27,7%),
    lần nghe cửa sổ 15 → 12, thời gian 6 đoạn 505s → 421s (−17%). So với lần đo cũ (còn 4 luồng CPU): 10,2x → 7,5x,
    12,6x → 9,4x, file dài 9,2x → 6,9x.
  - Vẫn 2 cửa sổ mỗi lượt: đoạn dở dang cuối cửa sổ đầu kéo tới hết 30 giây nên chưa làm dừng.
    **Sửa lần hai (bundle 32):** dừng khi đoạn KÉO QUA cuối âm thanh thật. Các đoạn nối tiếp nhau theo thời gian
    nên mọi đoạn sau nó đều nằm trong phần đệm: vẫn không mất lời. Đang đo.
  - **File 2 giờ (C2):** đọc + tiền xử lý + cắt lượt nói chạy hết trong 48 giây, RAM cao nhất 2,0 GB / 8,5 GB (23%).
    Nhận dạng xử lý từng lượt ≤ 25 giây nên RAM phần đó không tăng theo độ dài file → **đạt**.
- **Bổ sung bundle 32:** chế độ `nhanh_nhat` (Whisper small) cho máy yếu (C1: phần chậm do máy — mỗi cửa sổ ~21 giây
  trên 2 nhân — và có cấu hình ≤ 1,5x thay thế); tải bộ kiểm tra giữ riêng (`--giu-rieng`, không trùng đoạn nào của
  bộ dùng để chỉnh, hạt giống khác); cờ tắt từng thành phần để đo A2.

- **Kết quả bundle 32 (17–18/10):**
  - Sửa tốc độ lần hai: chữ vẫn **giống hệt** (họp 20,3%, giọng miền 5,6%, file dài 27,6%), nhanh thêm:
    đoạn ngắn 7,5x → 7,0x, 9,4x → 9,0x; **file dài 6,9x → 5,8x**. Tổng cộng so với trước khi sửa:
    10,2x → 7,0x và file dài 9,2x → 5,8x (nhanh hơn 31–37%) mà không mất chữ nào.
    Vẫn còn 2 cửa sổ mỗi lượt ở 6 đoạn đo: cửa sổ đầu kết thúc gọn đúng chỗ hết lời, faster-whisper mở cửa sổ
    mới từ đó (toàn phần đệm). **Sửa lần ba (bundle 33):** dừng khi đoạn đã chạm chỗ hết lời theo VAD (cuối lượt
    trừ 0,4 giây lề VAD tự thêm).
  - **Đo bật/tắt từng thành phần trên PhoWhisper (A2), 30 + 30 đoạn, so với cấu hình đang dùng (20,3% / 5,6%):**

    | Tắt thành phần | Họp | Giọng miền | Tốc độ | Kết luận |
    |---|---|---|---|---|
    | cắt chữ ngoài âm thanh thật | 69,4% | 74,5% | 10,2x | **TỆ HƠN THẬT (+49 / +69)** → bắt buộc giữ |
    | câu gợi ý mở đầu (bỏ gợi ý) | **19,1%** | **4,5% (TỐT HƠN THẬT)** | 6,3x / 8,6x | gợi ý **có hại** với PhoWhisper → **bỏ** |
    | đệm im lặng | 21,2% | 5,2% | 11,0x / 13,3x | chữ ngang nhau, nhưng đệm nhanh hơn ~35% → giữ |
    | nhận dạng từng lượt (nghe cả file) | 21,0% | 5,2% | 10,9x / 14,2x | ngang nhau, từng lượt nhanh hơn và tốt hơn ở file dài → giữ |
    | tiền xử lý âm thanh | 19,9% | 6,0% | 6,5x / 8,9x | ngang nhau (bộ dữ liệu ít tiếng ù) → giữ, kiểm lại trên họp thật |
    | giới hạn thử lại nhiệt độ | 20,0% | 5,6% | 7,0x / 8,8x | ngang nhau; giữ vì chống kẹt ở medium |
    | nhận dạng lại lượt hỏng | 20,3% | 5,6% | 6,9x / 9,0x | không lượt nào hỏng với PhoWhisper; giữ (có ích với medium, không tốn gì khi không dùng) |
    | bộ lọc [LOẠI] | 20,4% | 5,6% | — | chỉ 1 đoạn bị loại, không loại nhầm; giữ để chặn câu bịa |

    → **Đổi chế độ chính xác sang không gợi ý** (đúng quy tắc: tốt hơn thật ở một bộ, không bộ nào tệ hơn).
  - **Bộ kiểm tra giữ riêng đã tải (D1):** 100 đoạn họp/gọi điện + 100 đoạn giọng miền, không trùng đoạn nào của bộ
    dùng để chỉnh. Chạy lần đầu ở bundle 33 cho cả medium và cấu hình cuối.

- **Phản biện độc lập (18/10)** — một người review đọc code và nhật ký, chấm 8,5/10 như đồ án sinh viên, 6/10 so với
  chuẩn "hoàn hảo". Đã xử lý:
  - Bộ lọc "đọc lại câu mở đầu / từ khóa" chỉ bật khi thật sự gợi ý thứ đó (trước đây vẫn chạy ở chế độ chính xác
    không gợi ý, có thể xóa nhầm câu liệt kê thật); bỏ lần nghe lại "bỏ câu mở đầu" vô ích khi không có câu mở đầu.
  - Đo thêm (bundle 34): model ngoài họ Whisper (wav2vec2 tiếng Việt, `danh_gia_hf.py`), PhoWhisper bản gốc
    (transformers), PhoWhisper-small cho chế độ nhanh, large-v3 với đệm + cắt + không gợi ý (lần trước thử chưa công
    bằng), gộp lượt ngắn liền nhau vào một cửa sổ (`--gop-luot`) để bớt số lần nghe.
  - Không dùng số theo nhóm nhỏ (3–6 đoạn mỗi nhóm) để kết luận; báo cáo chỉ dùng số tổng.
  - Dữ liệu huấn luyện PhoWhisper (theo bài báo): CMV-Vi 14, VIVOS, VLSP 2020 Task-1 và 586 giờ dữ liệu riêng; không
    có LSVSC hay DataStudio, nhưng phần dữ liệu riêng không kiểm được → WER giọng miền thấp có thể bị lạc quan; họp
    thật tự ghi là phép thử không thể trùng.
  - Hạn chế ghi nhận, chưa sửa: file dài ghép nhân tạo có khoảng lặng sạch (dễ cho VAD hơn họp thật); bộ họp không có
    thông tin người nói nên không giới hạn được số đoạn mỗi người ở bộ giữ riêng; nhiều quyết định chọn trên 30 đoạn
    (đã so hơn 20 cấu hình) nên số trên bộ chỉnh lạc quan — số chính thức lấy từ bộ giữ riêng.

- **Phản biện lần hai (18/10)** — người review thứ hai kiểm lại từng ý của lần một trên code và mã nguồn
  faster-whisper / CTranslate2; chấm 8,5/10 (đồ án) và 5,5/10 (chuẩn "hoàn hảo"). Kết luận chính và cách xử lý:
  - **Luật dừng ở chỗ hết lời (bundle 33) vào mặc định trước khi đo**, và giả định "cuối lượt = hết lời + 0,4 giây"
    sai khi lề VAD bị cụt: lượt bị cắt cứng ở 25 giây, lượt tách ở khoảng ngừng ngắn (lề chỉ bằng nửa khoảng
    ngừng), lượt cuối file. → Chỉ dùng luật này khi lượt chắc chắn có đủ lề (còn khoảng trống tới lượt sau / chưa
    chạm cuối file); ghi nhật ký mỗi lần dừng; đo lại so với bản trước (bundle 35). Bộ giữ riêng ở bundle 33 chạy với
    bản chưa sửa: nếu bản sửa cho chữ giống hệt trên bộ chỉnh thì giữ số bộ giữ riêng; nếu khác thì chạy lại và
    ghi rõ lý do (sửa lỗi, không phải chỉnh tham số).
  - **Khoảng tin cậy của file dài sai** (bốc lẻ ~100 đoạn con trong chỉ 4 file, các đoạn con không độc lập) →
    bốc theo cụm file. Với 4 file, khoảng tin cậy chỉ để tham khảo; con số [−13,9; −0,1] cũ (từng lượt so với cả
    file) không còn được coi là "tốt hơn thật".
  - **Mốc thời gian theo từ:** CTranslate2 dùng "alignment heads" mặc định nếu model gốc không ghi → kiểm bằng
    `sua_alignment_heads.py`, nếu đúng là mặc định thì tạo bản dùng danh sách của Whisper medium và đo so sánh.
  - Ý "cắt cứng 25 giây hay làm đứt chữ" và "mốc <|30.00|> giữa lượt" bị đánh giá là phóng đại (VAD chỉ cắt cứng
    khi không có khoảng ngừng ≥ 98 ms; faster-whisper ghi đè mốc cuối đoạn bằng mốc từ cuối).
  - Ghi nhận thêm: bộ dữ liệu bỏ đoạn dưới 3 từ nên lượt rất ngắn ("dạ", "ừ") gần như không được đo; so sánh
    wav2vec2 không có mô hình ngôn ngữ và không có dấu câu nên chưa hoàn toàn công bằng; câu "cảm ơn các bạn đã
    lắng nghe" (kết họp thật) có thể bị bộ lọc loại khi đệm im lặng làm model "không chắc" — cần kiểm trên họp thật;
    chế độ nhanh giữ câu gợi ý dựa trên chênh lệch không có ý nghĩa thống kê (25,6% so với 25,8%).

- **KẾT QUẢ CHÍNH THỨC — bộ kiểm tra giữ riêng (bundle 33, 18/10), 100 + 100 đoạn chưa từng dùng để chỉnh,
  chạy một lần:**

  | | Whisper medium (mặc định cũ) | Chế độ chính xác (PhoWhisper + đệm + không gợi ý) | Chênh lệch (khoảng tin cậy 95%) |
  |---|---|---|---|
  | Họp / gọi điện | 23,3% | **18,1%** | −5,1 điểm [−7,4; −3,2] **TỐT HƠN THẬT**, tốt hơn ở 58 đoạn, tệ hơn ở 24 |
  | Giọng các miền | 10,1% | **6,8%** | −3,3 điểm [−5,4; −1,2] **TỐT HƠN THẬT**, tốt hơn ở 53 đoạn, tệ hơn ở 18 |
  | Tốc độ | 3,45x / 5,1x | 3,53x / 5,3x | **ngang nhau** |

  → Các lựa chọn trên bộ chỉnh giữ nguyên trên dữ liệu mới, không phải "khớp riêng" 30 đoạn. Từ thừa của
  PhoWhisper (225 so với 107) chủ yếu là từ đệm có thật trong lời nói ("là", "ờ", "cái", "thì") mà đáp án không ghi.
- **Bundle 33/35 — các phép đo khác (bộ chỉnh 30 + 30 đoạn):**

  | Cấu hình | Họp | Giọng miền | Tốc độ | Kết luận |
  |---|---|---|---|---|
  | Chế độ chính xác, dừng ở chỗ hết lời mọi lượt (sửa lần 3) | **18,6%** | 4,5% | **4,1x / 4,6x**; file dài 26,6%, **3,5x** | lỗi thiếu Y HỆT bản trước (63 / 9 / 466 từ) → không mất chữ; nhanh ngang medium |
  | Như trên nhưng chỉ dừng khi lượt chắc có lề (theo phản biện lần hai) | 19,1% | 4,5% | 6,2x / 8,6x; file dài 3,9x | không cứu thêm chữ nào, chậm hơn nhiều → **quay lại dừng mọi lượt** |
  | Gộp lượt ngắn ≤ 20 giây | 18,5% | 4,5% | file dài **3,3x** (26,3%) | nhanh hơn ở file dài, chữ ngang → đo tiếp với bản dừng mọi lượt |
  | PhoWhisper bản gốc (transformers, float32) | 18,1% | 4,4% | 12,3x / 15,2x | chính xác ngang bản đang dùng (18,6% / 4,5%), chậm gấp 3 → **cách chạy của dự án không làm mất độ chính xác của model** |
  | PhoWhisper-small | 27,4% | 8,7% | 2,3x / 3,0x | ứng viên chế độ nhanh |
  | wav2vec2 tiếng Việt (CTC, ngoài họ Whisper) | 30,5% | 8,2% | **0,3x** | rất nhanh, nhưng thua PhoWhisper rõ và không có dấu câu |
  | large-v3 có đệm + cắt + không gợi ý (thử lại cho công bằng) | 26,7% | 8,3% | 7,3x / 9,1x | không hơn → **bỏ hẳn** |
  | Whisper small | 31,0% | 13,7% | 1,3x / 1,5x | thua wav2vec2 và PhoWhisper-small ở mọi mặt trừ tốc độ |

  - **Alignment heads:** bản PhoWhisper đã chuyển đổi có sẵn 6 heads từ model gốc, giống Whisper medium → mốc thời gian
    theo từ không bị dùng danh sách mặc định; lo ngại của phản biện không xảy ra.
  - **Giới hạn model:** đã thử 10 cách (medium, small, turbo, large-v3 ×2, PhoWhisper small/medium/large, PhoWhisper bản
    gốc, wav2vec2). PhoWhisper-medium tốt nhất; bản gốc của nó chỉ hơn bản đang dùng 0,5 điểm ở họp (trong mức ngẫu
    nhiên) và bằng ở giọng miền → **đã chạm giới hạn của model tốt nhất có thể chạy trên máy này**. Chưa thử (tên chưa
    xác minh / cần thư viện khác): Zipformer, Chunkformer, EraX-WoW-Turbo — ghi vào hướng phát triển.
  - **Chế độ nhanh cần chọn lại:** medium giờ không nhanh hơn chế độ chính xác (3,45x so với 3,53x) mà lỗi nhiều hơn.
    Ứng viên: PhoWhisper-small (đo lại với bản dừng mọi lượt ở bundle 36).
  - **Bộ lọc cắt oan từ thật (B2) phát hiện trên bộ giữ riêng:** luật cắt chữ ngoài âm thanh xét theo điểm giữa của từ;
    từ thật cuối lượt bị dò mốc kéo dài sang phần đệm nên bị cắt ("...hai trường hợp" mất "hợp", "bye bye sếp", khoảng
    8 từ / 7.500). **Sửa (bundle 36):** xét theo mốc BẮT ĐẦU của từ; đo thêm lề 1,0 giây. Bộ giữ riêng sẽ chạy lại
    với bản sửa — ghi rõ: lần chạy thứ hai là để kiểm một lỗi tìm thấy, không phải chỉnh tham số theo bộ giữ riêng.

- **Bundle 36 (19/10) — kết quả và quyết định:**

  | Phép đo | Kết quả | Quyết định |
  |---|---|---|
  | Bộ giữ riêng chạy lại với bản sửa B2 (cắt theo mốc bắt đầu) | họp 18,1% (thiếu 238 → 234 từ), giọng miền 6,8% (thiếu 26 → 24) | **B2 đạt**: từ thật cuối lượt không còn bị cắt, không lỗi nào tăng. Đây là lần chạy thứ hai trên bộ giữ riêng, để kiểm một lỗi, đã ghi rõ |
  | Lề cuối lượt 0,5 → 1,0 giây | đoạn ngắn y hệt (18,5% / 4,5%), file dài 26,7% → 26,6% | không khác → **giữ 0,5** |
  | Gộp lượt ≤ 20 giây | đoạn ngắn 18,5% → 17,9%, 4,05x → **3,63x**; giọng miền bằng; file dài 26,7% → 26,2%, 3,56x → **2,98x** | tốt hơn hoặc bằng ở cả 3 bộ, nhanh hơn 10–16% → đo trên bộ giữ riêng ở bundle 37 rồi mới đổi mặc định (không đổi mặc định khi chưa đo, rút kinh nghiệm lần trước) |
  | **PhoWhisper-small trên bộ giữ riêng** | họp **22,5%**, giọng miền **8,5%**, **1,40x / 1,88x** | so với Whisper medium (chế độ nhanh cũ, 23,3% / 10,1%, 3,45x / 5,1x): lỗi bằng (−0,7 [−2,9; +1,2]; −1,6 [−3,4; +0,3], chưa chắc là tốt hơn) mà **nhanh gấp ~2,5 lần** → **chế độ `nhanh` = PhoWhisper-small**, Whisper medium bị loại khỏi các chế độ. Gộp lượt 20 giây cho small: 27,1% → 26,5%, 1,49x → 1,40x (bộ chỉnh) |
  | 100 đoạn họp (bộ chỉnh, 70 đoạn mới) | 20,6%, 3,81x | khớp với bộ giữ riêng (18,1%), không có dấu hiệu "khớp riêng" 30 đoạn |
  | File dài so với chính các đoạn đó nghe riêng (B1) | file dài 26,7% / nghe riêng 22,0% (gộp 20 giây: 26,2%) | còn chênh 4,7 điểm, chủ yếu là **thiếu chữ** (461 từ) → bundle 37 chia lỗi theo vị trí (biên / giữa mỗi đoạn ghép) và thử VAD tách lượt ở khoảng ngừng 0,5 giây |

  - **Phân loại 15 đoạn sai nhiều nhất trên bộ giữ riêng (B5):** nói tiếng Anh 3 đoạn (0173, 0174, 0035: model
    phiên âm sang tiếng Việt); gọi điện chất lượng thấp 5 đoạn (0007 ra trống, 0008 ra "unk" lặp, 0011, 0022, 0199) —
    nhóm gọi điện 43,7% lỗi, 109/364 từ bị thiếu; câu cảm thán lặp ngắn 2 (0051, 0070); câu xã giao ngắn bị thêm chữ 2
    (0081, 0134); thuật ngữ chuyên ngành 1 (0119); phỏng vấn đường phố ồn 1 (0086); đọc số 1 (0062). Gần như tất cả là
    giới hạn của model (giọng điện thoại băng hẹp, tiếng Anh, ồn), không phải lỗi luồng xử lý — trừ 2 loại chữ rác dưới.
  - **Chữ rác lọt bộ lọc (B3), sửa ở bundle 37:** PhoWhisper đôi khi in "unk" (tên ký hiệu "không biết" của bộ tách từ)
    lẫn trong câu thật, và kẹt vòng bên trong một từ ("nguyên vụ sợi đờn âm phòng hậu cơm vnvnvnvn..."), luật "lặp
    chữ" xét cả đoạn nên không bắt. Thêm luật bỏ từng từ rác (`la_tu_rac`): "unk", và mẩu 1–4 chữ cái lặp ≥ 4 lần
    không có khoảng trắng (từ ≥ 8 chữ cái); gọn "........" thành "...". Luật chung, không theo từ cụ thể, nhưng có
    thấy trên bộ giữ riêng → ghi rõ ở đây; con số bộ giữ riêng sau sửa chỉ là ước tính chấm lại (`--loc-lai`).
  - **Cặp nghe nhầm (B6):** nhiều nhất là từ tiếng Anh bị phiên âm (mic → mích, zoom → giun, link → linh, learning →
    ninh, fanpage → pết) và trợ từ vùng miền (nhá → nhé). **Không thêm luật sửa:** cặp lấy từ bộ giữ riêng, thêm luật
    theo chúng là chỉnh theo bộ kiểm tra; mà "linh", "giun" là từ tiếng Việt thật, sửa máy móc sẽ sai ở chỗ khác.
    Để dành cho bản ghi họp thật (nếu một cặp lặp lại nhiều ở đó thì mới thêm vào bảng sửa của bước làm sạch văn bản).
  - **Cài mới từ đầu (C4) — đạt:** trên máy Windows của Hân, thư mục trống `D:\thu_cai_moi`: `git clone` nhánh
    han-danh-gia-asr → tạo venv Python 3.11 → `pip install -r requirements.txt` (faster-whisper 1.2.1, ctranslate2 4.8.3)
    → cài torch 2.14 (CPU) + transformers 5.20 → `chuyen_doi_model.py` tạo `models/phowhisper-medium-ct2` → kiểm thử
    76/76 ĐẠT → nhận dạng một đoạn thật bằng chế độ mặc định, ra JSON đúng định dạng (3,0x độ dài ghi âm). Không cần
    bước nào ngoài README. Các dòng "NativeCommandError" trong nhật ký chạy chỉ là PowerShell bọc chữ in ra stderr
    (thanh tiến trình, thông báo pip), không phải lỗi.

---

## 4. Phạm vi đã thu hẹp

| Bỏ | Lý do |
|---|---|
| Phân biệt ai nói câu nào (pyannote) | Ngoài yêu cầu của giảng viên, tốn công |
| Giao diện demo | Tập trung vào chất lượng nhận dạng |

---

## 5. Việc tiếp theo
1. Xác nhận chế độ chính xác trên file dài; đo thời gian từng bước để biết PhoWhisper chậm ở đâu; thử model nhỏ
   (small) làm chế độ nhanh cho máy yếu.
2. Tạo bộ kiểm tra giữ riêng (≥ 100 đoạn mỗi bộ, chưa từng dùng để chỉnh) + 15–20 phút họp thật tự ghi.
3. Bật/tắt từng thành phần để chắc thành phần nào cũng có ích.
4. Tăng tốc độ, thử file 2 giờ, thêm luật sửa lỗi từ các cặp hay nghe nhầm.
5. Chương báo cáo phần ASR và demo.

**Đã xong ở bundle 28 (không cần chạy model):**
- Tài liệu định dạng đầu ra cho phần tóm tắt `docs/dinh_dang_dau_ra.md` + ca kiểm thử hợp đồng: file ASR ghi ra phải
  đọc được bằng chính `src/tien_xu_ly/doc_transcript.py` (điều kiện E1).
- Kiểm thử tự chạy trên GitHub mỗi lần push, cả Linux và Windows (`.github/workflows/kiem_thu.yml`, điều kiện C3;
  tính Đạt khi lần chạy đầu trên GitHub xanh). Kiểm thử: 62 → 64 ca.

---

## Phụ lục: mốc thời gian

| Ngày | Việc chính |
|---|---|
| 30/09 | Thử faster-whisper, chốt `medium`, viết chương trình nhận dạng và xuất JSON |
| 08–09/10 | Làm sạch âm thanh, lọc câu bịa, tách câu; nhận và tách riêng phần làm sạch văn bản |
| 10/10 | Dựng bộ đánh giá trên dữ liệu thật, sửa cách tính WER cho công bằng |
| 11/10 | So cách gợi ý: bỏ từ khóa, giữ câu mở đầu, giới hạn thử lại |
| 12/10 | Đo 100 đoạn mỗi bộ; phát hiện cuộc họp dài bị mất chữ |
| 14/10 | Nhận dạng từng lượt + nhận dạng lại lượt hỏng; công cụ chẩn đoán, khoảng tin cậy; dời dự án sang ổ D |
| 14–15/10 | So model; lọc câu bịa theo tốc độ nói; giới hạn số chữ mỗi lượt |
| 15/10 | Tìm nguyên nhân PhoWhisper bịa (int8, đệm, mốc thời gian, gợi ý, beam): dừng, ghi là giới hạn thư viện |
| 15/10 | Luật bỏ chữ ngoài âm thanh thật; tài liệu định dạng đầu ra; kiểm thử tự chạy trên GitHub |
| 15–16/10 | Đo 8 cấu hình / 5 model qua đêm: PhoWhisper + đệm im lặng chính xác nhất (TỐT HƠN THẬT), chốt A1; còn tốc độ |
| 16/10 | Thử giới hạn token (sai hướng, bỏ) và số luồng CPU (nhanh hơn 17%, giữ); đổi mặc định sang chế độ chính xác |
| 17/10 | Đo thời gian từng bước: PhoWhisper nghe thêm cửa sổ trong phần đệm (15 so với 6) → sửa; file dài xác nhận chế độ chính xác |
| 17/10 | Bản sửa tốc độ: −17–26%, chữ giống hệt; file 2 giờ dùng 2 GB RAM; thêm chế độ nhanh nhất, bộ giữ riêng, đo bật/tắt |
| 17–18/10 | Đo bật/tắt từng thành phần: bỏ câu gợi ý cho PhoWhisper; tốc độ −31–37% không mất chữ; tải bộ kiểm tra giữ riêng |
| 18/10 | Kết quả chính thức trên bộ giữ riêng: 18,1% / 6,8% (TỐT HƠN THẬT); hai vòng phản biện độc lập; kết luận chạm giới hạn model |
| 19/10 | Sửa cắt oan từ cuối lượt (xác nhận trên bộ giữ riêng); chế độ nhanh = PhoWhisper-small (nhanh gấp 2,5 lần); phân loại lỗi; bỏ chữ rác "unk" |

**Về điểm số trong các báo cáo tiến độ:** thang 10 điểm và 16 điều kiện "hoàn thiện" do nhóm tự đặt
(không phải thang của học phần). Mức hoàn thiện = tổng điểm 16 điều kiện ÷ 16 (Đạt = 1, Một phần = 0,5, Chưa = 0),
hiện là 13,5/16 ≈ 84% (còn thiếu: B1, B3, B6, D1, E2 một phần). Điểm chất lượng hiện là 9,3/10.
