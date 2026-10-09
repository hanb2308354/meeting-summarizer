# Hệ thống tóm tắt cuộc họp từ bản ghi âm

Đồ án nhóm: nhận file ghi âm cuộc họp tiếng Việt (có trộn từ tiếng Anh), tự động xuất ra:

- Bản tóm tắt nội dung chính
- Danh sách thông tin có cấu trúc: quyết định, việc cần làm, người phụ trách, hạn hoàn thành, lịch họp tiếp theo

## Thành viên và phân công

| Thành viên  | MSSV     | Phụ trách                                                                            |
| ----------- | -------- | ------------------------------------------------------------------------------------ |
| Tô Tiểu Hân | B2308354 | Nhận dạng giọng nói (`src/asr`), tiền xử lý văn bản (`src/tien_xu_ly`), ghép nối hệ thống, giao diện demo, đánh giá kết quả |
| Lê Tuấn Anh | B2308345 | Xử lý văn bản (`src/nlp`): chuẩn hóa, tách từ, tóm tắt, trích xuất thông tin         |

## Luồng xử lý

```
File ghi âm (.mp3)
   → [src/asr] faster-whisper: chuyển giọng nói thành văn bản
   → File JSON trong data/transcripts/
   → [src/tien_xu_ly] sửa lỗi nghe nhầm, bỏ từ đệm, đánh dấu câu xã giao, tách từ PyVi   (Hân)
   → File văn bản sạch trong data/processed/   ← ranh giới giữa hai phần
   → [src/nlp] đọc văn bản sạch → TextRank → Trích xuất                                    (Anh)
   → Bản tóm tắt + danh sách việc cần làm
```

## Cấu trúc thư mục

| Thư mục                 | Nội dung                                                                          |
| ----------------------- | --------------------------------------------------------------------------------- |
| `data/audio/`           | File ghi âm (không đưa lên GitHub vì nặng)                                        |
| `data/transcripts/`     | File JSON do phần ASR xuất ra, là **đầu vào của phần NLP**                        |
| `data/processed/`       | Văn bản sạch do `src/tien_xu_ly` ghi ra, là **đầu vào của phần NLP**                |
| `data/dap_an/`          | Văn bản gốc của từng file ghi âm, dùng để đánh giá                                |
| `data/nhan_dap_an.json` | Đáp án mẫu (người, việc, hạn, quyết định, lịch họp) để đo độ chính xác trích xuất |
| `src/asr/`              | Code nhận dạng giọng nói                                                          |
| `src/tien_xu_ly/`       | Code làm sạch văn bản (transcript → văn bản sạch)                                 |
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
python src/tien_xu_ly/tien_xu_ly.py data/transcripts/thu_nghiem2.json   # làm sạch trước
python src/nlp/chay_nlp.py data/processed/thu_nghiem2.json
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
| `danh_gia_wer.py`       | Đo tỷ lệ lỗi từ (WER) so với văn bản gốc trong `data/dap_an/` |
| `kiem_thu_asr.py`       | Kiểm thử tự động (không cần tải model)                       |
| `thu_faster_whisper.py` | Chỉ dùng để thử nghiệm chọn model, không dùng trong hệ thống |

Lần đầu chạy cần **internet** để tải model `medium` (khoảng 1,5 GB); các lần sau dùng bản đã lưu trên máy.

```powershell
python src/asr/chuyen_giong_noi.py data/audio/ten_file.mp3      # một file
python src/asr/chuyen_giong_noi.py data/audio/                  # cả thư mục
python src/asr/danh_gia_wer.py thu_nghiem hop_01 hop_02         # đo WER, nhiều file thì ra WER gộp
python src/asr/kiem_thu_asr.py                                  # kiểm thử
```

**Tiền xử lý âm thanh đang BẬT mặc định** (lọc tiếng ù dưới 90 Hz + chuẩn hóa âm lượng); giảm tạp âm (`--loc-nhieu`) thì TẮT mặc định. Hai lựa chọn này mới chỉ kiểm tra trên âm thanh tổng hợp, **chưa có số đo WER trên bản ghi thật**. Cách so sánh trên một file có đáp án trong `data/dap_an/`:

```powershell
python src/asr/chuyen_giong_noi.py data/audio/hop_01.mp3 --khong-tien-xu-ly   # tắt tiền xử lý
python src/asr/danh_gia_wer.py hop_01                                         # ghi lại WER
python src/asr/chuyen_giong_noi.py data/audio/hop_01.mp3                      # mặc định
python src/asr/danh_gia_wer.py hop_01
python src/asr/chuyen_giong_noi.py data/audio/hop_01.mp3 --loc-nhieu          # thêm giảm tạp âm
python src/asr/danh_gia_wer.py hop_01
```

Mỗi lần chạy ghi đè `data/transcripts/hop_01.json`, nên đo WER ngay sau từng lần. Các dòng `[LOẠI - ...]` in ra khi chạy là đoạn bị bỏ vì nghi Whisper "bịa chữ"; nên đọc lại để đếm câu thật bị loại oan.

## Văn bản sạch: src/tien_xu_ly (Hân)

Làm sạch transcript do ASR xuất ra: sửa chữ máy nghe nhầm (vd "bích link" → deadline), bỏ từ đệm (ừm, à, nhé...), dọn dấu câu, tách từ bằng PyVi, đánh dấu câu chào hỏi/cảm ơn. Giữ nguyên từ tiếng Anh, không dịch.

```powershell
python src/tien_xu_ly/tien_xu_ly.py data/transcripts/ten_file.json   # một file
python src/tien_xu_ly/tien_xu_ly.py data/transcripts/                # cả thư mục
python src/tien_xu_ly/kiem_thu_tien_xu_ly.py                         # kiểm thử
```

Kết quả nằm trong `data/processed/<tên>.json`, mỗi câu gồm:

| Trường    | Ý nghĩa                                                                  |
| --------- | ------------------------------------------------------------------------ |
| `stt`     | Số thứ tự câu, đánh liên tục (câu chỉ có từ đệm như "Ừm." đã bị bỏ)      |
| `speaker`, `start`, `end` | Giữ nguyên từ transcript                                  |
| `goc`     | Nguyên văn ASR                                                           |
| `sach`    | Đã sửa lỗi nghe nhầm, bỏ từ đệm, dọn dấu câu                             |
| `tach_tu` | Bản `sach` đã tách từ bằng PyVi (vd `hạn_chót`, `phụ_trách`)             |
| `xa_giao` | `true` nếu câu ngắn chỉ là chào hỏi, cảm ơn, hỏi ý kiến, chào kết thúc. `false` nếu có vế giao việc, kể cả khi Whisper bỏ dấu phẩy làm câu chào dính vào câu giao việc ("Hello team bạn Tuấn sẽ làm phần API"), có động từ giao việc (sẽ, làm, nhận, gửi...) hoặc có mốc thời gian |

Phần NLP **chỉ đọc** các file này (qua `src/nlp/doc_van_ban_sach.py`), không tự làm sạch văn bản nữa. Sửa cách làm sạch thì sửa ở `src/tien_xu_ly`, rồi chạy lại lệnh trên cho cả thư mục và commit `data/processed/`; nếu quên, kiểm thử sẽ báo file đã cũ.

| File                     | Vai trò                                                                       |
| ------------------------ | ----------------------------------------------------------------------------- |
| `lam_sach.py`            | **Code chính**: hàm `tien_xu_ly()` làm sạch danh sách câu (không đọc/ghi file) |
| `tien_xu_ly.py`          | Chạy từ dòng lệnh: transcript → `data/processed/<tên>.json`                   |
| `doc_transcript.py`      | Đọc và kiểm tra file transcript JSON (đọc được file có BOM)                   |
| `tu_dien_tien_xu_ly.py`  | Bảng sửa lỗi nghe nhầm, từ đệm, mẫu câu xã giao, cụm từ cần nối khi tách từ   |
| `kiem_thu_tien_xu_ly.py` | Kiểm thử: câu làm sạch, câu đúng không được đổi, tách từ, đọc/ghi file, phần NLP đọc được mọi file `data/processed`, `data/processed` khớp với code |

**Tên dễ nhầm:** thư mục `src/tien_xu_ly/` là toàn bộ phần làm sạch của Hân; trong đó `lam_sach.py` chứa code làm sạch, còn `tien_xu_ly.py` là lệnh chạy để ghi ra `data/processed/`.

Bảng sửa lỗi nghe nhầm hiện được viết theo các lỗi gặp khi chạy thử, chưa thống kê trên nhiều bản ghi thật; luật nào có thể đụng tên người hoặc từ có thật thì chỉ áp dụng khi có ngữ cảnh (xem ghi chú trong `tu_dien_tien_xu_ly.py`).

## Các file trong src/nlp

| Nhóm       | File                                             | Vai trò                                                                   |
| ---------- | ------------------------------------------------ | ------------------------------------------------------------------------- |
| Đầu vào    | `doc_van_ban_sach.py`                            | Đọc và kiểm tra file văn bản sạch trong `data/processed/` (do Hân xuất ra) |
| Cấu hình   | `tu_dien.py`                                     | Hằng số dùng chung của tóm tắt và trích xuất (động từ, mẫu câu). Bảng của phần tiền xử lý nằm ở `src/tien_xu_ly/tu_dien_tien_xu_ly.py` |
| Tóm tắt    | `tom_tat.py`                                     | Tách câu, TextRank có điểm cộng/phạt, chọn câu kiểu MMR, rút gọn          |
| Trích xuất | `nhan_dien_ten.py`                               | Nhận diện tên người phụ trách                                             |
| Trích xuất | `nhan_dien_han.py`                               | Tìm hạn chót trong câu                                                    |
| Trích xuất | `trich_viec.py`                                  | Trích việc cần làm kèm người phụ trách                                    |
| Trích xuất | `trich_quyet_dinh.py`                            | Trích các quyết định                                                      |
| Trích xuất | `trich_lich_hop.py`                              | Trích thời gian và địa điểm cuộc họp tiếp theo                            |
| Trích xuất | `trich_xuat.py`                                  | Ghép các bước trích xuất thành kết quả cuối                               |
| Chạy       | `chay_nlp.py`                                    | **Code chính**: chạy cả luồng NLP trên một file văn bản sạch, ghi vào `outputs/` |
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

- Không code trực tiếp trên `main`. Hân code trên nhánh `han-asr-tien-xu-ly`, Anh code trên nhánh `nlp`.
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
