# Nhật ký phần nhận dạng giọng nói (ASR) — Tô Tiểu Hân

## 1. Tóm tắt

**Phần của Hân làm gì:** nhận file ghi âm cuộc họp → chuyển thành chữ → làm sạch chữ → giao văn bản sạch
cho phần tóm tắt của Anh.

```
File ghi âm → Làm sạch âm thanh → Nhận dạng giọng nói (Whisper) → Lọc câu bịa → Tách câu → JSON
           → Làm sạch văn bản (sửa lỗi nhận dạng, bỏ từ đệm, câu xã giao) → Văn bản sạch cho phần tóm tắt
```

**Kết quả hiện tại** (WER = tỉ lệ từ sai, càng thấp càng tốt):

| Loại âm thanh | WER lúc bắt đầu đo | WER hiện tại |
|---|---|---|
| Họp, hội nghị, gọi điện (đoạn ngắn) | 28,2% | 25,4% |
| Cuộc họp dài 5 phút | 36,4% | 29,9% |
| Giọng các miền | 8,3% | 8,2% |
| Model bị kẹt (chạy hàng trăm giây cho vài giây âm thanh) | có | 0 |

**Cấu hình đang dùng:** model Whisper `medium` chạy trên CPU · chỉ dùng câu gợi ý mở đầu · nhận dạng
từng lượt nói · lượt nào ra quá ít chữ thì nhận dạng lại · lọc câu bịa (kể cả câu có tốc độ nói bất khả thi).

**Đang làm:** chọn model tốt nhất. PhoWhisper (bản Whisper được huấn luyện thêm cho tiếng Việt) hứa hẹn
giảm lỗi họp còn ~21% và giọng miền còn ~5% (đã xác nhận bằng chạy thật, chưa chắc về thống kê), nhưng chạy qua
faster-whisper thì không biết dừng, nối câu bịa sau lời thật. Đã cắt được câu bịa bằng mốc thời gian (đệm im lặng +
bỏ chữ sau cuối lượt): họp 20,4% — tốt hơn medium thật sự. Còn chậm khoảng 2,7 lần medium, đang tăng tốc.

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

---

## 4. Phạm vi đã thu hẹp

| Bỏ | Lý do |
|---|---|
| Phân biệt ai nói câu nào (pyannote) | Ngoài yêu cầu của giảng viên, tốn công |
| Giao diện demo | Tập trung vào chất lượng nhận dạng |

---

## 5. Việc tiếp theo
1. Tăng tốc PhoWhisper (giới hạn token theo số đo, số luồng CPU) rồi đổi mặc định sang PhoWhisper + đệm im lặng,
   giữ medium làm chế độ nhanh.
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

**Về điểm số trong các báo cáo tiến độ:** thang 10 điểm và 16 điều kiện "hoàn thiện" do nhóm tự đặt
(không phải thang của học phần). Mức hoàn thiện = tổng điểm 16 điều kiện ÷ 16 (Đạt = 1, Một phần = 0,5, Chưa = 0),
hiện là 7,5/16 ≈ 47% (E1, A1 đạt). Điểm chất lượng hiện là 7,75/10.
