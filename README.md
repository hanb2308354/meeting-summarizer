# Hệ thống tóm tắt cuộc họp từ bản ghi âm

Đồ án nhóm: nhận file ghi âm cuộc họp tiếng Việt (có trộn từ tiếng Anh), tự động xuất ra:

- Bản tóm tắt nội dung chính
- Danh sách thông tin có cấu trúc: quyết định, việc cần làm, người phụ trách, hạn hoàn thành, lịch họp tiếp theo

## Thành viên và phân công

| Thành viên  | MSSV     | Phụ trách                                                                            |
| ----------- | -------- | ------------------------------------------------------------------------------------ |
| Tô Tiểu Hân | B2308354 | Nhận dạng giọng nói (`src/asr`), ghép nối hệ thống, giao diện demo, đánh giá kết quả |
| Lê Tuấn Anh | B2308345 | Xử lý văn bản (`src/nlp`): chuẩn hóa, tách từ, tóm tắt, trích xuất thông tin         |

## Luồng xử lý

```
File ghi âm (.mp3)
   → [src/asr] faster-whisper: chuyển giọng nói thành văn bản
   → File JSON trong data/transcripts/
   → [src/nlp] Regex → PyVi → TextRank → Trích xuất
   → Bản tóm tắt + danh sách việc cần làm
```

## Cấu trúc thư mục

| Thư mục                 | Nội dung                                                                          |
| ----------------------- | --------------------------------------------------------------------------------- |
| `data/audio/`           | File ghi âm (không đưa lên GitHub vì nặng)                                        |
| `data/transcripts/`     | File JSON do phần ASR xuất ra, là **đầu vào của phần NLP**                        |
| `data/dap_an/`          | Văn bản gốc của từng file ghi âm, dùng để đánh giá                                |
| `data/nhan_dap_an.json` | Đáp án mẫu (người, việc, hạn, quyết định, lịch họp) để đo độ chính xác trích xuất |
| `src/asr/`              | Code nhận dạng giọng nói                                                          |
| `src/nlp/`              | Code xử lý văn bản                                                                |
| `outputs/`              | Kết quả cuối cùng (`.json` và `.md` cho từng transcript)                          |

## Cài đặt

Yêu cầu: Cài mới **Python 3.11** (bản 3.12, 3.13 lỗi thư viện).

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
  {
    "speaker": "SPEAKER_00",
    "start": 0.0,
    "end": 2.14,
    "text": "Ok, mình bắt đầu meeting nha."
  }
]
```

| Trường         | Ý nghĩa                                                      |
| -------------- | ------------------------------------------------------------ |
| `speaker`      | Người nói. Hiện chưa tách người nói nên luôn là `SPEAKER_00` |
| `start`, `end` | Thời điểm bắt đầu / kết thúc câu (giây)                      |
| `text`         | Nội dung câu                                                 |

Lưu ý: Whisper tự đặt dấu chấm nên đôi khi một câu chứa nhiều ý, hoặc thông tin của một việc bị tách sang câu sau. Phần NLP nên tách thêm theo dấu phẩy khi trích xuất.

## Định dạng kết quả đầu ra

Mỗi transcript sinh ra hai file trong `outputs/`: `ten_file.json` (cho phần ghép nối) và `ten_file.md` (bản đọc được). File `.md` gồm bốn phần: Nội dung chính, Quyết định, Việc cần làm, Cuộc họp tiếp theo.

| Phần                                | Trường                                                                                        |
| ----------------------------------- | --------------------------------------------------------------------------------------------- |
| Việc cần làm (`tasks`)              | `task` (mô tả việc), `owner` (người phụ trách), `deadline` (hạn, có thể rỗng), `start` (giây) |
| Quyết định (`decisions`)            | `text`, `start`                                                                               |
| Cuộc họp tiếp theo (`next_meeting`) | `time`, `place`, `start`; rỗng nếu không có                                                   |

Quy ước: nếu người nói tự xưng ("mình", "tôi", "em") thì `owner` là `Người chủ trì`; nếu là "mọi người" thì `owner` là `Mọi người`.

## Cách chạy

**Nhận dạng giọng nói** (file ghi âm → JSON):

```powershell
python src/asr/chuyen_giong_noi.py data/audio/ten_file.mp3
```

Kết quả được lưu vào `data/transcripts/ten_file.json`.

**Xử lý văn bản** (JSON → tóm tắt, quyết định, việc cần làm, lịch họp):

```powershell
python src/nlp/chay_nlp.py data/transcripts/thu_nghiem2.json
```

Kết quả được ghi vào `outputs/ten_file.json` và `outputs/ten_file.md`.

**Kiểm tra kết quả trích xuất trên transcript mẫu:**

```powershell
python src/nlp/kiem_thu.py
```

Lần chạy mặc định cũng kiểm tra transcript phát triển [phat_trien.json](./data/transcripts/phat_trien.json).
Chế độ mặc định chỉ in tên file và mã kết quả ổn định. Để xem lý do cùng nội dung việc trên máy cục bộ:

```powershell
python src/nlp/kiem_thu.py --chi-tiet thu_nghiem1.json
```

**Đo độ chính xác trích xuất trên toàn bộ transcript mẫu** (so với `data/nhan_dap_an.json`) và kiểm tra các ca mức câu:

```powershell
python src/nlp/do_chat_luong.py
python src/nlp/kiem_cau.py
```

## Các file trong src/asr

| File                    | Vai trò                                                      |
| ----------------------- | ------------------------------------------------------------ |
| `chuyen_giong_noi.py`   | **Code chính**: file ghi âm → JSON                           |
| `thu_faster_whisper.py` | Chỉ dùng để thử nghiệm chọn model, không dùng trong hệ thống |

## Các file trong src/nlp

| Nhóm       | File                                             | Vai trò                                                                   |
| ---------- | ------------------------------------------------ | ------------------------------------------------------------------------- |
| Chuẩn hóa  | `doc_transcript.py`                              | Đọc và kiểm tra file transcript JSON                                      |
| Chuẩn hóa  | `tien_xu_ly.py`                                  | Sửa lỗi nhận dạng, bỏ từ đệm, nhận diện câu xã giao, tách từ bằng PyVi    |
| Chuẩn hóa  | `tu_dien.py`                                     | Hằng số dùng chung (động từ, mẫu câu, từ điển lỗi nhận dạng)              |
| Tóm tắt    | `tom_tat.py`                                     | Tách câu, TextRank có điểm cộng/phạt, chọn câu kiểu MMR, rút gọn          |
| Trích xuất | `nhan_dien_ten.py`                               | Nhận diện tên người phụ trách                                             |
| Trích xuất | `nhan_dien_han.py`                               | Tìm hạn chót trong câu                                                    |
| Trích xuất | `trich_viec.py`                                  | Trích việc cần làm kèm người phụ trách                                    |
| Trích xuất | `trich_quyet_dinh.py`                            | Trích các quyết định                                                      |
| Trích xuất | `trich_lich_hop.py`                              | Trích thời gian và địa điểm cuộc họp tiếp theo                            |
| Trích xuất | `trich_xuat.py`                                  | Ghép các bước trích xuất thành kết quả cuối                               |
| Chạy       | `chay_nlp.py`                                    | **Code chính**: chạy cả luồng NLP trên một transcript, ghi vào `outputs/` |
| Kiểm thử   | `kiem_thu.py`, `kiem_cau.py`, `do_chat_luong.py` | Kiểm tra trên transcript mẫu, 14 ca mức câu, đo độ chính xác trích xuất   |
| Kiểm thử   | `vet.py`, `bat_bien.py`, `dap_an.py`             | Xem vết xử lý, kiểm định dạng đầu ra, đáp án mẫu                          |

## Đánh giá và hạn chế

Kết quả đo bằng `do_chat_luong.py` trên 9 transcript mẫu:

| Tập                                          | Số file | Độ chính xác (P) | Độ bao phủ (R) |
| -------------------------------------------- | ------- | ---------------- | -------------- |
| Tập phát triển (`thu_nghiem*`, `phat_trien`) | 7       | 1.00             | 1.00           |
| Tập phát triển 2 (`giu_rieng_*`)             | 2       | 0.46             | 0.50           |

Tập phát triển là tập đã dùng để chỉnh luật nên số 1.00 chưa chứng minh khả năng tổng quát hóa. Tập phát triển 2 không dùng để viết luật ban đầu, nhưng sau lần đo đầu (P 0.17 / R 0.33) các luật chung đã được sửa theo loại lỗi của nó, nên 0.46 / 0.50 cũng chưa phải kiểm thử độc lập. Chưa có tập giữ riêng gán nhãn tay.

Ở tập phát triển 2, P giảm từ 0.55 xuống 0.46 sau lần sửa gần nhất vì hai việc đã tìm ra nhưng gắn sai hạn (hạn đứng trước việc, hạn đổi giữa chừng) nên chưa tính là đúng. Nếu không xét hạn thì độ bao phủ là 0.67. Bộ 14 ca mức câu (`kiem_cau.py`) đạt 13/14.

Hạn chế đã biết:

- Phần tóm tắt là trích chọn câu rồi gọt, chưa viết lại bằng mô hình ngôn ngữ, và chưa có thước đo định lượng riêng.
- Văn bản đã tách từ bằng PyVi (trường `tach_tu`) chưa được dùng trong bước tóm tắt; tóm tắt hiện xếp hạng trên văn bản gốc.
- Chưa thử trên cuộc họp dài (hàng chục phút trở lên).
- Một số kiểu giao việc chưa nhận được hoặc gắn sai hạn (ví dụ hạn nêu một lần cho hai việc; hạn đứng trước việc "Hạn X là thứ Ba nhé"; hạn đổi giữa chừng từ thứ Sáu sang thứ Năm).
- Người nói xưng "anh/chị" với người nghe là "em/bạn" có thể sinh việc thừa gán cho `Người chủ trì`; cụm "gửi mọi người" có thể biến `Mọi người` thành người làm; câu giao việc dạng "Tên, phần X giao cho em" chưa nhận được người phụ trách.
- Bản tóm tắt nghiêng về các câu giao việc và hạn, chưa lọc câu trùng mục "Việc cần làm"; ở cuộc họp rất ngắn có thể xuất hiện mảnh câu cụt.
- Phần rút gọn câu đổi "bên mình" thành "công ty", chỉ đúng với một số kiểu cuộc họp.
- Tên người viết thường hoặc tên ba chữ chỉ nhận được khi câu giao việc có đủ ngữ cảnh (danh xưng, động từ đi kèm).
- `kiem_thu.py` có một mục tùy chọn riêng cho `thu_nghiem1.json` và cho phép hai việc cùng chủ ở các đoạn liền nhau dùng chung hạn, nên nới hơn `do_chat_luong.py`.

Hướng mở rộng: gắn hạn theo vị trí (hạn đứng trước việc, hạn đổi giữa chừng), nhận xưng hô theo cả cuộc họp, học tên từ lời gọi, chia đoạn cho cuộc họp dài, dựng tập giữ riêng gán nhãn tay, và thêm lớp hỗ trợ bằng mô hình ngôn ngữ (tùy chọn).

## Quy ước làm việc với Git

- Không code trực tiếp trên `main`. Hân code trên nhánh `asr`, Anh code trên nhánh `nlp`.
- Xong một phần chạy được thì mới gộp vào `main`.
- Commit message ghi tiếng Việt, nói rõ đã làm gì.

## Tiến độ

- [x] Chọn công cụ nhận dạng giọng nói: faster-whisper, model `medium`, int8
- [x] Code chuyển ghi âm thành JSON
- [x] Xử lý văn bản (`src/nlp`):
  - [x] Chuẩn hóa và tách từ
  - [x] Tóm tắt
  - [x] Trích xuất thông tin
- [ ] Ghép nối toàn bộ hệ thống
- [ ] Giao diện demo
- [ ] Đánh giá kết quả (WER, độ chính xác trích xuất)
