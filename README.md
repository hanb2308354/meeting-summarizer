# Hệ thống tóm tắt cuộc họp từ bản ghi âm

Đồ án nhóm: nhận file ghi âm cuộc họp tiếng Việt (có trộn từ tiếng Anh), tự động xuất ra:
- Bản tóm tắt nội dung chính
- Danh sách thông tin có cấu trúc: quyết định, việc cần làm, người phụ trách, hạn hoàn thành

## Thành viên và phân công

| Thành viên | MSSV | Phụ trách |
|---|---|---|
| Tô Tiểu Hân | B2308354 | Nhận dạng giọng nói (`src/asr`), ghép nối hệ thống, giao diện demo, đánh giá kết quả |
| Lê Tuấn Anh | B2308345 | Xử lý văn bản (`src/nlp`): chuẩn hóa, tách từ, tóm tắt, trích xuất thông tin |

## Luồng xử lý

```
File ghi âm (.mp3)
   → [src/asr] faster-whisper: chuyển giọng nói thành văn bản
   → File JSON trong data/transcripts/
   → [src/nlp] Regex → PyVi → TextRank → Trích xuất
   → Bản tóm tắt + danh sách việc cần làm
```

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `data/audio/` | File ghi âm (không đưa lên GitHub vì nặng) |
| `data/transcripts/` | File JSON do phần ASR xuất ra, là **đầu vào của phần NLP** |
| `data/dap_an/` | Văn bản gốc của từng file ghi âm, dùng để đánh giá |
| `src/asr/` | Code nhận dạng giọng nói |
| `src/nlp/` | Code xử lý văn bản |
| `outputs/` | Kết quả cuối cùng |

## Cài đặt

Yêu cầu: **Python 3.11** (bản 3.12, 3.13 dễ lỗi thư viện).

```powershell
git clone https://github.com/hanb2308354/meeting-summarizer.git
cd meeting-summarizer
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu PowerShell báo `running scripts is disabled`, chạy lệnh sau một lần rồi kích hoạt lại venv:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Định dạng file transcript (đã thống nhất, không tự ý đổi)

Mỗi file trong `data/transcripts/` là một danh sách các câu:

```json
[
  {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.14, "text": "Ok, mình bắt đầu meeting nha."}
]
```

| Trường | Ý nghĩa |
|---|---|
| `speaker` | Người nói. Hiện chưa tách người nói nên luôn là `SPEAKER_00` |
| `start`, `end` | Thời điểm bắt đầu / kết thúc câu (giây) |
| `text` | Nội dung câu |

Lưu ý: Whisper tự đặt dấu chấm nên đôi khi một câu chứa nhiều ý, hoặc thông tin của một việc bị tách sang câu sau. Phần NLP nên tách thêm theo dấu phẩy khi trích xuất.

## Cách chạy

**Nhận dạng giọng nói** (file ghi âm → JSON):
```powershell
python src/asr/chuyen_giong_noi.py data/audio/ten_file.mp3
```
Kết quả được lưu vào `data/transcripts/ten_file.json`.

**Xử lý văn bản:** *(đang làm)*

## Các file trong src/asr

| File | Vai trò |
|---|---|
| `chuyen_giong_noi.py` | **Code chính**: file ghi âm → JSON |
| `thu_faster_whisper.py` | Chỉ dùng để thử nghiệm chọn model, không dùng trong hệ thống |

## Quy ước làm việc với Git

- Không code trực tiếp trên `main`. Hân code trên nhánh `asr`, Anh code trên nhánh `nlp`.
- Xong một phần chạy được thì mới gộp vào `main`.
- Commit message ghi tiếng Việt, nói rõ đã làm gì.

## Tiến độ

- [x] Chọn công cụ nhận dạng giọng nói: faster-whisper, model `medium`, int8
- [x] Code chuyển ghi âm thành JSON
- [ ] Xử lý văn bản: chuẩn hóa, tách từ, tóm tắt, trích xuất
- [ ] Ghép nối toàn bộ hệ thống
- [ ] Giao diện demo
- [ ] Đánh giá kết quả (WER, độ chính xác trích xuất)
- [ ] Hướng mở rộng: tách người nói (pyannote), sửa lỗi nhận dạng bằng glossary