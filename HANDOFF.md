# HANDOFF: tài liệu bàn giao cho AI hoặc người mới

Cập nhật lần cuối: 11/10/2026, sau khi xong các nhóm sửa lỗi D, G và C (nhánh `nlp`).
Mục đích: để người đọc mới hiểu đúng dự án, trạng thái thật và những gì CHƯA được chứng minh, trước khi đánh giá.
Thứ tự đọc: file này → `AGENTS.md` (luật làm việc cho AI sửa code) → `README.md` (cài đặt, bảng thuật ngữ chi tiết).
Nếu số liệu trong file này lệch với `AGENTS.md`, hãy chạy lại các lệnh ở mục 8 và tin kết quả chạy.

## 1. Tóm tắt nhanh
- Hệ thống tóm tắt cuộc họp tiếng Việt, hoàn toàn rule-based (không API, không LLM): ghi âm → ASR (faster-whisper) → tiền xử lý → NLP bằng TextRank + regex.
- Đầu ra mỗi cuộc họp: nội dung chính (tóm tắt trích rút), quyết định, bảng việc cần làm (việc, người phụ trách, hạn chót), cuộc họp tiếp theo.
- Chia làm 2 phần lớn. Phần 1: audio → transcript. Phần 2: transcript → tiền xử lý → NLP → tóm tắt.
- Điểm mạnh: kiểm thử nhiều, có vết xử lý (`vet.py`) để truy ngược vì sao một câu bị loại hay giữ.
- Điểm yếu cần biết ngay: luật được chỉnh theo chính tập mẫu nên số 1.00 không nói lên khả năng tổng quát; phần ASR chưa đo trên ghi âm thật; tóm tắt chưa có thước đo; chỉ kiểm tra trên họp có việc hoặc quyết định.

## 2. Nhánh, phân công, quy trình
- Nhánh `nlp`: phần NLP (người phụ trách NLP). Hân làm ASR và tiền xử lý trên nhánh `han-asr-tien-xu-ly` (theo README). `main` chưa bị động đến trong đợt sửa này.
- Sửa lỗi theo từng nhóm, mỗi nhóm một commit tiếng Việt. Xem `git log` để thấy lịch sử.
- Quy trình mỗi nhóm lỗi: viết ca kiểm thử trước (phải đỏ đúng chỗ), kèm ca âm bảo vệ; AI nêu kế hoạch (file, hàm, số dòng) và chờ duyệt; sửa tối đa 2 lần; chạy các lệnh kiểm thử và dán nguyên kết quả; khôi phục `outputs/` bằng `git checkout -- outputs/`; không tự commit.
- Công cụ sửa code: AI trong VS Code (Cline) đọc `AGENTS.md` mỗi phiên.

## 3. Luồng dữ liệu và định dạng chính xác
**Đầu ra phần 1** = `data/transcripts/<tên>.json`, danh sách các mục:
`{"speaker": "SPEAKER_00", "start": <giây>, "end": <giây>, "text": "..."}`
- `speaker` luôn là `SPEAKER_00` (chưa tách người nói).
- `text` là chữ Whisper nghe được, giữ dấu câu và chữ hoa, chưa sửa lỗi.
- Code phần 1 cắt thành từng câu: sau `.` `?` `!` (trừ chữ viết tắt kiểu "TP." và "..." khi chữ sau viết thường), khi ngừng ≥ 5 giây (hoặc ≥ 2 giây nếu câu đã dài ≥ 3 giây), và khi câu > 20 giây (cắt ở dấu phẩy gần giữa nhất, nếu không có thì cắt giữa câu).
- Không ghi file rỗng: nếu không nghe được gì thì không có file.
- Phần 1 KHÔNG lưu: điểm tin cậy từng từ, các câu bị lọc (`[LOẠI…]` chỉ in ra màn hình), cảnh báo chất lượng ghi âm.
- Định dạng này đã thống nhất với Hân, không được đổi.

**Tiền xử lý** (`src/tien_xu_ly`): kiểm tra 4 trường, chuẩn hóa mã hóa dấu, sửa chữ nghe nhầm bằng bảng luật (khoảng 60 mẫu, chỉ những lỗi đã gặp), bỏ từ đệm, chuẩn hóa khoảng trắng, tách từ bằng PyVi, gắn cờ `xa_giao`. Nó KHÔNG thêm lại nội dung bị sót.
Ghi `data/processed/<tên>.json` với 8 trường: `stt, speaker, start, end, goc, sach, tach_tu, xa_giao`. Phần NLP chỉ đọc file này.

**NLP** (`src/nlp`): `chay_nlp.py` là điểm vào, ghi `outputs/<tên>.json` và `outputs/<tên>.md`. Mục nào trống thì in "Không có".

## 4. Bản đồ mã nguồn
- `src/asr/chuyen_giong_noi.py`: nhận dạng giọng nói, tiền xử lý âm thanh (lọc tiếng ù dưới khoảng 90 Hz, chuẩn hóa âm lượng, giảm tạp âm tùy chọn và tắt mặc định), VAD, lọc câu bịa và lặp, tách câu, ghi JSON. Đi kèm `danh_gia_wer.py`, `kiem_thu_asr.py` (34 ca), `thu_faster_whisper.py`.
- `src/tien_xu_ly/`: `lam_sach.py`, `tu_dien_tien_xu_ly.py`, kiểm tra đầu vào, `kiem_thu_tien_xu_ly.py` (9 nhóm).
- `src/nlp/trich_viec.py` (khoảng 800 dòng): trích việc và hạn. Hàm `lay_viec` dài khoảng 240 dòng là trung tâm và là chỗ dễ vỡ; phần khai báo hằng/regex chỉ khoảng 76 dòng, còn lại là logic nhiều nhánh phụ thuộc thứ tự.
- Còn lại: `trich_quyet_dinh.py`, `trich_lich_hop.py`, `tom_tat.py` (TextRank), `nhan_dien_ten.py`, `nhan_dien_han.py`, `tu_dien.py`, `trich_xuat.py`, `vet.py` (`bat_vet`, `ghi_vet`, `lay_vet`).
- Kiểm thử NLP: `kiem_thu.py` (mặc định 4 file), `kiem_cau.py` (ca mức câu, `DANH_SACH_CA`, có cờ `dang_loi_da_biet`), `do_chat_luong.py` (đo độ chính xác với đáp án).
- Đường dẫn và danh sách file có thể lệch nhẹ giữa các nhánh; dùng `git ls-files` để chắc chắn.

## 5. Dữ liệu mẫu và nguồn gốc
- `data/transcripts/` có 9 file: `thu_nghiem`, `thu_nghiem1`, `thu_nghiem2` (có dấu hiệu nhận dạng thật, ví dụ "Spring" thay "Sprint"), `thu_nghiem3`, `thu_nghiem4`, `thu_nghiem5`, `phat_trien`, `giu_rieng_01`, `giu_rieng_02`. Chỉ nhóm đầu có dấu hiệu là đầu ra ASR thật; phần lớn còn lại và đặc biệt `giu_rieng_*` là bản họp tự soạn (tên giả). Chưa xác minh chính xác file nào ra từ ghi âm.
- File audio KHÔNG nằm trong repo (`data/audio` rỗng).
- Đáp án: `data/nhan_dap_an.json` cho tập phát triển; đáp án của `giu_rieng_*` ở file nhãn riêng (xem `do_chat_luong.py` để biết đường dẫn). Văn bản gốc để đo WER chỉ có cho `thu_nghiem` (`data/dap_an/thu_nghiem.txt`).
- **Tập phát triển** = 7 file đầu (đã dùng để chỉnh luật). **Tập 2** = `giu_rieng_01`, `giu_rieng_02`. Tập 2 từng được giữ riêng nhưng sau đó đã bị dùng để tìm nhóm lỗi và sửa luật, nên KHÔNG còn độc lập. Hiện chưa có tập kiểm thử độc lập thật sự.

## 6. Cách đọc số liệu của `do_chat_luong.py`
- ĐÚNG: việc bắt buộc được trích đúng người, từ khóa và hạn.
- SAI_HẠN: đúng việc nhưng hạn sai hoặc thiếu. HẠN_BỊ_THAY: hạn bị đổi giữa chừng nhưng hệ thống giữ hạn cũ.
- THIẾU: việc bắt buộc không được trích. CẤM: sinh ra việc nằm trong danh sách cấm. TRÙNG: việc bị trích lặp.
- GIẢ: việc sinh ra nhưng không khớp việc bắt buộc, tùy chọn hay cấm trong đáp án. Hệ quả: nếu hệ thống tìm ra một việc thật mà đáp án chưa ghi, nó vẫn bị tính GIẢ.
- P, R theo định nghĩa trong `do_chat_luong.py`. Rck là recall không tính đúng sai hạn (suy ra từ số liệu là (ĐÚNG + SAI_HẠN + HẠN_BỊ_THAY) chia số việc bắt buộc; xác nhận trong code).
- QĐ x/y: quyết định trích đúng; "thừa" là quyết định giả. Lịch x/y: cuộc họp tiếp theo đúng.

## 7. Trạng thái hiện tại (11/10/2026)
**Số liệu mốc (không được tụt):**
- `kiem_thu.py`: 4/4 file OK.
- `kiem_cau.py`: 22/23 ca đạt; ca 19 là lỗi đã biết.
- `kiem_thu_tien_xu_ly.py`: 9/9 nhóm (đo ngày 10/10, không đổi vì chưa sửa tiền xử lý).
- `do_chat_luong.py`: tập phát triển P=1.00, R=1.00 (ĐÚNG=29, 7 file). Tập 2 P=0.62, R=0.67 (ĐÚNG=8, THIẾU=4, GIẢ=5; `giu_rieng_01` P=1.00 R=0.80; `giu_rieng_02` P=0.44 R=0.57).

**Nhóm sửa lỗi:**
| Nhóm | Nội dung | Trạng thái |
|---|---|---|
| D | hạn đổi giữa chừng (lấy hạn sau cùng) | xong |
| G | một hạn nói một lần cho nhiều việc khác người trong cùng một câu | xong |
| C | hạn đứng trước việc ("Hạn X là Y" rồi mới giao việc) | xong |
| E | việc giả: mảnh câu như "phần này giúp anh", "đợi X làm xong rồi…", "gửi mọi người…" bị coi là giao việc; thêm luật "tự anh/tự mình" là tự nhận | chưa |
| H | nội dung việc bị cắt hoặc hai câu dính vào một việc (ca 19); gốc là tách mệnh đề chỉ theo dấu phẩy | chưa |
| A+B | khi người nói xưng "anh/chị", "em" là người được gọi tên chứ không phải Người chủ trì; câu "Tên, phần X giao cho em" chưa nhận được chủ | chưa |
| F | tên ba chữ đầu câu không nhận được; tên hai chữ bị cắt còn một chữ | chưa |
Thứ tự dự kiến: E → H → A+B → F.

**Lỗi còn lại trong đo đạc:**
- THIẾU (4): `giu_rieng_01` Đặng Mỹ Duyên ("trích dẫn", thứ Năm); `giu_rieng_02` Mỹ Linh ("tem giá khuyến mại", thứ Tư), Tín ("phiếu nhận hàng", thứ Năm), Người chủ trì ("biên lợi nhuận tuần", thứ Năm).
- GIẢ (5, đều ở `giu_rieng_02`): "phần này giúp anh"; "bản mới vào thứ Tư… riêng mốc này động"; "làm mẫu ngắn"; "xong rồi xem có cùng một món không"; "gửi mọi người trước thứ Năm., đối chiếu…".
- Quyết định và lịch họp: không có lỗi trên cả 9 file.

## 8. Cách chạy và kiểm chứng
Python 3.11 (README). Dùng `venv` 3.11; thư mục `.venv` 3.14 không dùng. `requirements.txt` ghim `av<19` cho faster-whisper. Hệ điều hành của nhóm: Windows, PowerShell. Chạy từ thư mục gốc repo:
```
python src/nlp/kiem_thu.py
python src/nlp/kiem_cau.py
python src/nlp/do_chat_luong.py
python src/tien_xu_ly/kiem_thu_tien_xu_ly.py
python src/asr/kiem_thu_asr.py
python src/nlp/chay_nlp.py data/processed/<tên>.json
```
Lưu ý: `kiem_thu.py` ghi đè `outputs/`; dùng `git checkout -- outputs/` sau khi chạy nếu không muốn commit kết quả. Muốn truy vết một câu, dùng `vet.py` (`bat_vet`, rồi `lay_vet`).

## 9. Những gì CHƯA được chứng minh (đọc kỹ trước khi đánh giá)
- **Tổng quát hóa:** số 1.00 trên tập phát triển và số ở tập 2 đều xuất phát từ luật đã chỉnh theo mẫu. Giá trị thật chỉ có khi đo trên tập mới chưa dùng để sửa luật. Người phụ trách dự định tạo tập này sau khi hết lỗi hiện tại, đo một lần và không dùng để sửa luật.
- **ASR trên ghi âm thật:** README ghi chưa có WER trên bản ghi thật; chỉ `thu_nghiem` có đáp án, WER 2,0% trên 102 từ (mẫu quá nhỏ để kết luận). Hai lựa chọn tiền xử lý âm thanh mới được kiểm tra trên âm thanh tổng hợp. Model được chọn từ thử nghiệm trên một file ghi âm. Hiệu quả của lọc ồn, giảm tạp âm trên ghi âm thật là chưa biết.
- **Hình dạng đầu vào không khớp:** `giu_rieng_01/02` và `thu_nghiem5` có đoạn chứa nhiều câu, trong khi hàm tách câu của phần 1 sẽ chẻ chúng thành 73, 116 và 12 mục. Khi chẻ như vậy rồi chạy lại (thử trên bản sao trước các nhóm D, G, C) kết quả `giu_rieng_01` xuống P=0.60 R=0.60 và `giu_rieng_02` P=0.18 R=0.29. Tức là phần gắn hạn khi hạn và việc nằm ở các mục khác nhau là điểm yếu thật với đầu ra thật của phần 1. Nhóm C đã cho hạn chờ sống tối đa 2 đoạn để chịu được dạng này.
- **Độ nhạy với nhiễu** (thí nghiệm làm hỏng 7 transcript tập phát triển, mô hình thô, chạy trên bản sao trước nhóm D, G, C; nền 1.00 vốn đã chỉnh luật nên số tụt có phần do luật mong manh): nghe sai 5% từ → P/R ≈ 0.63/0.65; 10% → ≈ 0.41; 20% → ≈ 0.18; tên người sai 50% lần nhắc → 0.65/0.71; từ chỉ hạn sai 50% → 0.34/0.37 (vẫn tìm ra việc nhưng sai hạn); mất 20% câu → R 0.75, P vẫn ≥ 0.90; gộp mỗi 2 câu thành 1 → 0.64/0.55 và quyết định tụt từ 1.00 xuống 0.22. Hệ thống không bao giờ báo lỗi, chỉ trả kết quả sai một cách tự tin.
- **Tóm tắt (TextRank):** chưa có thước đo nào, chỉ có nhận xét định tính.
- **Loại họp khác:** mọi transcript mẫu đều là họp có việc hoặc quyết định. Thăm dò nhỏ trên 3 đoạn tự viết: họp báo cáo thuần và họp thông báo quy định ra đúng (không có việc giả); họp brainstorm sinh 3 việc giả vì cụm gợi ý như "có thể", "cũng được", "lo là" bị coi là giao việc. Chưa đo trên dữ liệu thật.
- **Động từ ngoài từ điển:** ví dụ "soạn", "vẽ" không có trong `tu_dien.py`, có trường hợp làm mất việc. Chưa thống kê mức độ.
- **Môi trường:** README ghi Python 3.12 và 3.13 lỗi thư viện, nhưng phần NLP chạy được trên 3.12 ở một môi trường thử khác (chưa thử đủ cả ASR). Cần kiểm chứng lại với đúng `requirements.txt`.

## 10. Hạn chế đã biết của các luật
- Hạn nói một lần chỉ lan sang việc của người khác khi cùng đoạn và đoạn không có dấu kết câu ở bất kỳ đâu (an toàn, có thể bỏ sót).
- Hạn đứng trước chỉ được gắn khi cụm hạn nằm cuối mệnh đề "Hạn X là Y"; nếu sau hạn còn chữ khác thì bị bỏ sót.
- Câu "Hạn X là Y" đứng ngay sau một việc chưa có hạn vẫn có thể bị gắn ngược cho việc đó dù nội dung không khớp (chưa gặp trong dữ liệu).
- Hai câu độc lập trong cùng một đoạn có thể bị gộp thành một việc (ca 19, nhóm H).
- Tiền xử lý không bù được nội dung bị sót. Luật quyết định có từ khóa phụ riêng của một cuộc họp mẫu ("kpi", "miễn phí vận chuyển"), nguy cơ chỉnh theo mẫu.

## 11. Ý tưởng để sau (chưa làm, không phải việc ưu tiên)
- Mở rộng cho các loại họp khác (báo cáo, ra quyết định, brainstorm): nhận diện loại họp, trích số liệu và nguyên nhân, trích phương án và lý do, tách quyết định chắc khỏi chưa chốt.
- `src/nlp/llm_ho_tro.py` (tùy chọn): chỉ xử lý các câu luật không chắc chắn, tắt mặc định, đầu ra phải qua kiểm tra bám sát câu gốc, lưu lại câu trả lời để kiểm thử lặp lại được. Xung đột với quy tắc "không có LLM", nên cần sửa `AGENTS.md` và README trước khi làm.
- Ghi chú dọn code: có thể tách `lay_viec` thành các hàm nhỏ trong một đợt riêng, không đổi hành vi, chứng minh bằng kết quả kiểm thử giống hệt. Chưa nên làm khi còn đang sửa các nhóm lỗi.

## 12. Câu hỏi nên đặt khi đánh giá
1. Bộ đo hiện tại có đo đúng thứ cần đo không, và tập kiểm thử độc lập nên được thiết kế thế nào?
2. Với đầu ra thật của phần 1 (câu theo dấu chấm, không tách người nói, có lỗi nghe), phần 2 chịu nhiễu tới đâu?
3. Rule-based có đủ để làm tiếp, hay lớp hỗ trợ nào đáng thêm trước?
4. Rủi ro nào lớn nhất cho buổi bảo vệ luận văn: số liệu, phạm vi, hay thiếu đo trên ghi âm thật?
