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
giảm lỗi họp còn ~21% và giọng miền còn ~5%, đang chạy thật để xác nhận.

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
- **Đang kiểm tra:** chạy PhoWhisper bằng thư viện gốc (transformers) trên cùng đoạn để biết việc nối câu bịa
  và chạy chậm là do chính model hay do bản chuyển đổi sang faster-whisper; đếm số token model sinh ra mỗi đoạn.
- Sự cố: sau khi dời bộ nhớ đệm model sang ổ D, file model `medium` bị hỏng (không tải được); cần tải lại.

---

## 4. Phạm vi đã thu hẹp

| Bỏ | Lý do |
|---|---|
| Phân biệt ai nói câu nào (pyannote) | Ngoài yêu cầu của giảng viên, tốn công |
| Giao diện demo | Tập trung vào chất lượng nhận dạng |

---

## 5. Việc tiếp theo
1. Xác nhận PhoWhisper bằng chạy thật; thử thêm model lớn hơn (large-v3, PhoWhisper-large).
2. Tạo bộ kiểm tra giữ riêng (≥ 100 đoạn mỗi bộ, chưa từng dùng để chỉnh) + 15–20 phút họp thật tự ghi.
3. Bật/tắt từng thành phần để chắc thành phần nào cũng có ích.
4. Tăng tốc độ, thử file 2 giờ, thêm luật sửa lỗi từ các cặp hay nghe nhầm.
5. Tài liệu định dạng đầu ra cho phần tóm tắt, chương báo cáo.

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
| 14–15/10 | So model; lọc câu bịa theo tốc độ nói; giới hạn số chữ mỗi lượt (đang đo) |

**Về điểm số trong các báo cáo tiến độ:** thang 10 điểm và 16 điều kiện "hoàn thiện" do nhóm tự đặt
(không phải thang của học phần). Mức hoàn thiện = tổng điểm 16 điều kiện ÷ 16 (Đạt = 1, Một phần = 0,5, Chưa = 0),
hiện là 6,5/16 = 41%. Điểm chất lượng hiện là 7,5/10.
