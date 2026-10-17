# Định dạng đầu ra của phần ASR (hợp đồng với phần tóm tắt)

Người phụ trách: Tô Tiểu Hân (ASR + tiền xử lý). Bên dùng: Lê Tuấn Anh (tóm tắt / trích xuất).

Tài liệu này chốt **file transcript JSON** mà `src/asr/chuyen_giong_noi.py` ghi ra và
`src/tien_xu_ly/doc_transcript.py` đọc vào. Hai bên chỉ cần thống nhất đúng các điều dưới;
đổi bất kỳ điều nào phải báo bên kia và sửa ca kiểm thử hợp đồng (cuối tài liệu).

## 1. Vị trí file

| | |
|---|---|
| Đầu vào | file ghi âm `.mp3 .wav .m4a .aac .ogg .flac .wma .webm .mp4` (hoặc thư mục chứa chúng) |
| Đầu ra | `data/transcripts/<tên file ghi âm, bỏ đuôi>.json` |
| Mã hóa | UTF-8, không BOM (bên đọc chấp nhận cả có BOM, vì file soạn tay bằng Notepad có BOM) |
| Không nghe được câu nào | **không tạo file** (in thông báo, file đó tính là thất bại) |

## 2. Cấu trúc

Một **danh sách không rỗng** các câu, theo thứ tự thời gian. Mỗi câu là một đối tượng có
đúng 4 trường:

| Trường | Kiểu | Ý nghĩa | Ràng buộc |
|---|---|---|---|
| `speaker` | chuỗi | người nói | hiện luôn là `"SPEAKER_00"` (chưa tách người nói, xem mục 4) |
| `start` | số thực (giây) | lúc bắt đầu câu, tính từ đầu file | làm tròn 2 chữ số; không NaN; `>= 0` |
| `end` | số thực (giây) | lúc kết thúc câu | làm tròn 2 chữ số; `end >= start` |
| `text` | chuỗi | lời nói, giữ nguyên văn model nghe (có dấu câu, chữ hoa) | không rỗng |

Ví dụ:

```json
[
  {"speaker": "SPEAKER_00", "start": 0.0, "end": 1.95, "text": "Bạn Tuấn phụ trách frontend."},
  {"speaker": "SPEAKER_00", "start": 2.4, "end": 6.1, "text": "Còn bạn Lan làm slide, nộp trước thứ sáu nha."}
]
```

## 3. Những gì phần ASR đã đảm bảo (bên tóm tắt không cần làm lại)

- Câu bịa của model đã bị bỏ: câu kiểu YouTube ("Cảm ơn các bạn đã theo dõi"), lặp chữ, lặp
  đoạn trước, đọc lại câu gợi ý / từ khóa, tốc độ nói bất khả thi (> 12 từ/giây), chữ nằm
  sau cuối âm thanh thật của lượt nói. Các đoạn bị bỏ được in ra màn hình với nhãn `[LOẠI - lý do]`.
- Câu được tách theo dấu câu và khoảng ngừng; câu quá dài bị cắt ở dấu phẩy gần giữa.
- `end` không bao giờ nhỏ hơn `start` (mốc theo từ của Whisper đôi khi ngược, đã sửa khi ghi).
- Từ đệm ("ờ", "ừm"), sửa lỗi nghe nhầm, chuẩn hóa: **không** làm ở bước này mà ở bước tiền
  xử lý `src/tien_xu_ly/tien_xu_ly.py` (đầu ra `data/processed/`), cũng do Hân phụ trách.

## 4. Giới hạn đã biết

- **Một người nói**: chưa tách người nói (diarization đã quyết định bỏ khỏi phạm vi, xem
  `docs/nhat_ky_asr.md`). Bên tóm tắt không được dựa vào `speaker` để gán việc cho người.
- `text` vẫn có thể sai chữ: tỷ lệ lỗi từ đo trên bộ đánh giá xem `README.md` / nhật ký.
- Mốc thời gian là ước lượng của model, có thể lệch vài trăm mili giây.

## 5. Bên đọc kiểm tra gì (`doc_transcript.py`)

Báo lỗi (ValueError) và dừng nếu: không phải danh sách hoặc rỗng; phần tử không phải đối
tượng; thiếu một trong 4 trường; `start`/`end` không phải số (kể cả `true/false`) hoặc là NaN;
`start > end`; `speaker` hoặc `text` không phải chuỗi. Trường thừa được bỏ qua.

## 6. Ca kiểm thử giữ hợp đồng

Trong `src/asr/kiem_thu_asr.py` (chạy tự động trên GitHub mỗi lần push, `.github/workflows/kiem_thu.yml`):

- `ghi_json_dung_format`: đúng 4 trường, đúng kiểu.
- `json_dau_ra_qua_duoc_kiem_tra_cua_phan_tom_tat`: file ASR ghi ra (có cả mốc thời gian ngược
  và câu dài) đọc được bằng chính `doc_transcript.py`, câu theo thứ tự thời gian, `text` không rỗng.
- `end_khong_nho_hon_start`, `khong_ghi_file_khi_khong_nghe_duoc_gi`.
