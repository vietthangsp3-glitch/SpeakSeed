# SpeakSeed — Báo cáo giai đoạn 4

Ngày kiểm tra: 2026-10-22.

## Kết quả triển khai

Giai đoạn 4 bổ sung 60 bài/nhiệm vụ A0–B2 và 90 câu hỏi khách quan:

| Kỹ năng | A0 | A1 | A2 | B1 | B2 | Tổng bài | Câu hỏi |
|---|---:|---:|---:|---:|---:|---:|---:|
| Listening | 3 | 3 | 3 | 3 | 3 | 15 | 45 |
| Reading | 3 | 3 | 3 | 3 | 3 | 15 | 45 |
| Speaking | 3 | 3 | 3 | 3 | 3 | 15 | — |
| Writing | 3 | 3 | 3 | 3 | 3 | 15 | — |
| **Tổng** | **12** | **12** | **12** | **12** | **12** | **60** | **90** |

Phân bố câu hỏi: 15 multiple choice Listening, 15 fill blank, 15 dictation và 45 reading comprehension. Speaking/Writing là nhiệm vụ mở, không được đếm giả thành câu hỏi khách quan.

Database sau import vẫn có 4.216 hàng từ, trong đó đúng **4.213 từ `reviewed=1`**, 100 grammar lesson và 1.000 grammar exercise. Không có tài khoản hay learning event nào trong database chính khi chốt báo cáo. `PRAGMA integrity_check` trả về `ok`.

## Listening

- Transcript gốc của SpeakSeed, đáp án và lời giải tiếng Việt.
- Ba dạng: nghe hiểu multiple choice, điền từ và dictation.
- TTS chỉ được gọi khi người học bấm phát; dùng cache backend hiện có và fallback giọng trình duyệt. Importer không tạo audio hàng loạt.
- Backend chấm đáp án và chỉ ghi hoạt động thật sau khi người dùng gửi câu trả lời.

## Reading

- 15 bài đọc tăng dần từ câu ngắn A0 đến lập luận B2, mỗi bài có ba câu đọc hiểu và lời giải.
- Từ quan trọng được nối với ngân hàng từ hiện có; có 591 liên kết lesson–word sau khi lọc stopword.
- Lưu từ tạo thẻ SRS đến hạn với 0 lượt đúng/sai, vì vậy không bị tính thành “đã học” khi người dùng mới chỉ lưu.
- Nội dung không sử dụng văn bản ngoài; nguồn/giấy phép được lưu trong từng lesson và ghi tại `ATTRIBUTION.md`.

## Speaking

- 15 tình huống thực tế, dùng được với Gemini từng lượt và Gemini Live hiện có.
- Lưu session/transcript theo tài khoản. Phiên chỉ hoàn thành sau tối thiểu hai lượt người học và một lần đánh giá thành công.
- Phản hồi gồm grammar, vocabulary, naturalness và task completion.
- Không chấm pronunciation trong bộ đánh giá nhiệm vụ hiện tại. Trường pronunciation trả `null` và giải thích chưa có dữ liệu audio phù hợp; tính năng chấm phát âm từ đơn hiện hữu vẫn chỉ chạy khi nhận WAV thật.
- Mọi điểm đều có tuyên bố rõ là điểm luyện tập, không tương đương chứng chỉ CEFR.

## Writing

- 15 đề từ câu, đoạn, email đến essay; giới hạn từ nằm trong metadata từng bài.
- Draft được lưu trước khi gọi AI. Nếu Gemini lỗi, draft vẫn còn.
- Phản hồi yêu cầu JSON có grammar, vocabulary, coherence, naturalness, lỗi cụ thể và giải thích tiếng Việt.
- Tối đa 10 lượt nộp AI/tài khoản/giờ trong một process; payload tối đa 5.000 ký tự và response token đã giới hạn ở backend.

## Learning Path và dữ liệu tài khoản

- Bốn kỹ năng có chuỗi mở khóa riêng tại cấp hiện tại.
- Daily plan có Listening, Reading, Speaking và Writing. Listening/Reading cần câu trả lời; Speaking cần đánh giá hoàn tất; Writing cần nộp và nhận phản hồi thành công.
- Dashboard báo số bài hoàn thành theo từng kỹ năng. Phát hiện điểm yếu dùng lịch sử câu hỏi khách quan khi có ít nhất ba lượt.
- Mọi bảng tiến độ, saved word, session và draft đều có `user_id`; API kiểm tra quyền sở hữu ở backend.

## Migration, importer và AI

- `007_four_skills.sql` tạo các bảng mới và mở rộng CHECK của `learning_events` trong transaction, sao chép toàn bộ event cũ trước khi đổi bảng.
- `tools/build_skills.py` dùng stable ID, upsert, chạy lặp lại an toàn và không xóa dữ liệu người dùng.
- Gemini API key chỉ được đọc từ biến môi trường backend. Timeout hiện tại: text 35 giây, TTS 55 giây, Live open 15 giây; lỗi provider được chuyển thành 5xx có thông báo phù hợp.
- Rate limit: Speaking turn 40/giờ, Live 10/giờ, Speaking evaluation 10/giờ, Writing submission 10/giờ, TTS 80/IP/giờ. Đây là giới hạn in-memory, chưa đồng bộ giữa nhiều process.

## Kiểm thử

- Automated suite cuối: **32 passed**, 1 cảnh báo deprecation từ `fastapi.testclient`; không có test thất bại.
- Có test importer idempotent, không gắn `human_reviewed`, phân bố CEFR/dạng câu, không rò đáp án, auth/account isolation, SRS từ Reading, Speaking/Writing mock Gemini, daily plan/dashboard và 8 tài khoản ghi SQLite đồng thời.
- Kiểm thử trình duyệt desktop trực tiếp xác nhận: đăng nhập tài khoản QA tạm, dashboard không có tiến độ giả, mở Listening, chấm đúng và hiện lời giải, mở Reading, chấm biến thể đáp án đúng, lưu từ vào ôn tập, mở Writing và lưu draft 20 từ.
- Trong kiểm thử trình duyệt đã phát hiện 8 câu lựa chọn có phương án đúng về nghĩa nhưng chưa nằm trong tập đáp án. Đã sửa cả 8 và thêm validator/test ngăn tái phát. Cũng đã lọc đại từ hỏi khỏi danh sách từ quan trọng.
- Kiểm thử mobile trực tiếp chưa hoàn tất vì quyền điều khiển trình duyệt bị tắt giữa phiên. CSS có breakpoint 800px/620px và kiểm tra cú pháp JavaScript đạt, nhưng báo cáo không coi đây là bằng chứng tương đương kiểm thử tương tác mobile.

## Trạng thái nội dung và giới hạn

Tất cả 60 bài mang nhãn `automated_checked`; **0 bài mang nhãn `human_reviewed`**. Các kiểm tra tự động xác nhận cấu trúc, trường bắt buộc, phân bố, liên kết đáp án lựa chọn và giới hạn TTS. Chưa có bằng chứng về vòng duyệt độc lập của giáo viên, vì vậy không tuyên bố nội dung đã được con người kiểm duyệt.

Phản hồi Gemini có thể sai và phụ thuộc model/quota. Rate limit in-memory không đủ cho triển khai nhiều worker. Trước production cần test mobile thật lại, rate limiter dùng chung, backup, logging/monitoring và security review.
