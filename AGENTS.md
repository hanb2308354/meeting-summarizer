# Quy tắc cho AI làm việc trong repo này

## Dự án

Hệ thống tóm tắt cuộc họp tiếng Việt, hoàn toàn rule-based: ASR (faster-whisper) → tiền xử lý (`src/tien_xu_ly`) → NLP bằng TextRank + regex (`src/nlp`).
Không có API hay LLM. Không đề xuất FastAPI, OpenRouter hay đổi cấu trúc thư mục.

## Nguyên tắc làm việc

1. Nghĩ trước khi code: yêu cầu chưa rõ thì hỏi một câu, không tự đoán.
2. Đơn giản trước: viết ít code nhất giải quyết được việc, không thêm tính năng chưa được yêu cầu.
3. Sửa đúng chỗ: chỉ đụng vào dòng cần sửa.
4. Có tiêu chí xong: nêu lệnh kiểm tra trước khi sửa, chạy và báo kết quả sau khi sửa.

## Trước khi viết code

Liệt kê: file nào, hàm nào, khoảng bao nhiêu dòng sẽ đổi. Chờ người dùng đồng ý rồi mới viết.

## Không được làm

- Đổi tên hàm hoặc biến có sẵn, di chuyển hoặc đổi tên file.
- Thêm thư viện vào `requirements.txt`, hoặc thêm tham số cho hàm đang chạy.
- Sửa file ngoài file được nêu trong yêu cầu.
- Viết lại cả hàm khi chỉ cần sửa vài dòng.
- Đọc cả file lớn khi chỉ cần một đoạn. `src/nlp/trich_viec.py` dài khoảng 800 dòng toàn regex: dùng tìm kiếm rồi xem đoạn liên quan.
- Thêm tên người, từ khóa hay câu cụ thể của transcript vào luật. Mọi `data/transcripts/*` (kể cả `giu_rieng_*`) là tập phát triển: được dùng để tìm nhóm lỗi, nhưng luật phải viết theo mẫu câu tổng quát. Tập kiểm thử độc lập sẽ tạo sau, không dùng để sửa luật.
- Sửa số liệu trong README cho đẹp hơn thực tế.
- Tự commit hoặc push khi chưa được yêu cầu.

## Quy ước của repo

- Tên hàm, biến, commit message bằng tiếng Việt.
- Import dạng phẳng (ví dụ `from doc_van_ban_sach import ...`), không đổi thành package.
- Không đổi định dạng file transcript và văn bản sạch (đã thống nhất với Hân).
- Sửa cách làm sạch văn bản thì sửa ở `src/tien_xu_ly`, rồi chạy lại cho cả thư mục `data/transcripts/` và commit `data/processed/`.
- Làm việc trên nhánh `nlp`, không code trực tiếp trên `main`.

## Kiểm tra trước khi báo "xong"

Chạy từ thư mục gốc repo và dán kết quả:

```
python src/nlp/kiem_thu.py
python src/nlp/kiem_cau.py
python src/nlp/do_chat_luong.py
python src/tien_xu_ly/kiem_thu_tien_xu_ly.py   # chỉ khi có sửa src/tien_xu_ly
```

Số liệu mốc (đo ngày 11/10/2026, sau nhóm D và G), không được tụt:

- `kiem_thu.py`: 4/4 file OK.
- `kiem_cau.py`: 18/19 ca đạt; ca 19 (đoạn chứa hai câu bị gộp thành một việc) là lỗi đã biết, xử lý ở nhóm H.
- `do_chat_luong.py`: tập phát triển P=1.00, R=1.00; tập `giu_rieng_*` P=0.54, R=0.58.
- `kiem_thu_tien_xu_ly.py`: 9/9 nhóm đạt.

## Khi kiểm thử vẫn đỏ

Thử sửa tối đa 2 lần. Sau đó dừng, báo dòng lỗi cụ thể và nguyên nhân nghi ngờ, không vá lan sang chỗ khác.
