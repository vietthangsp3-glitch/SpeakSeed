# Báo cáo hệ thống học cá nhân hóa — giai đoạn 3

Ngày kiểm tra: 2026-10-22.

## Phạm vi đã triển khai

- Placement test 25 câu: 15 câu grammar và 10 câu vocabulary lấy trực tiếp từ nội dung đã xuất bản.
- Hồ sơ riêng theo tài khoản: cấp đề xuất, cấp đang học, mục tiêu phút/ngày và thời điểm hoàn thành placement test.
- Learning path A0–B2 với trạng thái đã làm, hoàn thành, được đề xuất mở và bài tiếp theo.
- Dashboard dựa trên dữ liệu thật: từ đã học, từ đến hạn, độ chính xác, grammar hoàn thành, streak và mục tiêu ngày.
- Daily plan gồm từ mới, SRS đến hạn, grammar, dictation và AI Speaking.
- Phát hiện điểm yếu theo dạng grammar, chủ đề vocabulary và mode bài tập sau ít nhất ba lượt làm.
- Lịch sử `learning_events` chỉ được ghi sau khi backend nhận/chấm một hoạt động hợp lệ.

## Placement test

Bài kiểm tra có 25 câu và không gửi đáp án xuống frontend:

| Cấp | Grammar | Vocabulary | Tổng |
|---|---:|---:|---:|
| A0 | 3 | 0 | 3 |
| A1 | 3 | 3 | 6 |
| A2 | 3 | 3 | 6 |
| B1 | 3 | 2 | 5 |
| B2 | 3 | 2 | 5 |
| Tổng | 15 | 10 | 25 |

CEFR-J bắt đầu từ A1 nên A0 hiện được đánh giá bằng grammar. Thuật toán đi tuần tự từ A0 đến B2 và đề xuất cấp đầu tiên chưa đạt ngưỡng: A0 50%, A1–B1 60%, B2 70%. Kết quả cao ở cấp trên không bỏ qua lỗ hổng ở cấp dưới.

Kết quả luôn kèm cảnh báo: đây chỉ là gợi ý xếp lớp nhanh, không đánh giá đầy đủ nghe, nói, đọc, viết và **không phải chứng chỉ CEFR**.

## Bằng chứng tiến độ

Các mục daily plan chỉ hoàn thành dựa trên `learning_events`:

- `vocabulary_learning`: người học thực sự đánh dấu một flashcard.
- `vocabulary_review`: thẻ đã đến hạn được trả lời.
- `grammar_answer`: backend đã chấm một câu grammar.
- `listening_answer`: backend đã chấm một bài dictation.
- `speaking_turn`: Gemini đã trả lời thành công một lượt.
- `speaking_live`: Gemini Live đã bắt đầu trả về nội dung cho phiên hội thoại.

Chỉ mở trang, phát âm thanh hoặc bắt đầu một placement attempt không tạo tiến độ. Kế hoạch ngày được snapshot theo tài khoản/ngày; đổi cấp độ sẽ tái tạo snapshot nhưng giữ nguyên toàn bộ sự kiện hoạt động.

## API mới

- `POST /api/placement/start`
- `POST /api/placement/submit`
- `GET /api/placement/latest`
- `POST /api/profile`
- `GET /api/learning-path`
- `GET /api/daily-plan`
- `GET /api/dashboard`

Mọi API cá nhân hóa đều yêu cầu bearer token. Placement attempt được kiểm tra quyền sở hữu ở backend và chỉ được nộp một lần.

## Migration

`006_personalized_learning.sql` bổ sung `learner_profiles`, `placement_attempts`, `learning_events` và `daily_plans`. Migration runner hiện tại ghi version trong `schema_migrations`, chạy transaction và không chạy lại migration đã áp dụng. Không có bảng cũ hoặc dữ liệu tiến độ cũ nào bị xóa hay thay thế.

## Kiểm thử

- 24 test tự động đạt.
- Placement: đủ 25 câu, không lộ đáp án, kết quả A0/B2, chống nộp chéo tài khoản và chống nộp lại.
- Learning path: bài tiếp theo chỉ đổi trạng thái sau bằng chứng hoàn thành 8/10 câu ở backend.
- Dashboard: tài khoản mới có số liệu 0/“chưa đủ dữ liệu”; một hoạt động thật chỉ cập nhật đúng tài khoản đó.
- Ghi đồng thời: tạo daily plan cho năm tài khoản song song và 60 lượt ghi grammar của sáu tài khoản.
- Browser: desktop và viewport 390×844; không có console warning/error.

## Giới hạn còn lại

- Placement test không đo trực tiếp listening hoặc speaking để tránh phụ thuộc micro/API ngoài trong bài xếp lớp cơ bản.
- Streak chỉ bắt đầu từ các `learning_events` sau migration 006; hệ thống không dựng lịch sử giả từ bản ghi tổng hợp cũ.
- Mục tiêu phút/ngày là tùy chọn của người học. Hệ thống chưa suy diễn số phút từ số click; daily plan dùng số hoạt động có bằng chứng.
- Điểm yếu chỉ xuất hiện sau tối thiểu ba lượt, nên tài khoản mới hiển thị “chưa đủ dữ liệu”.
- Learning path cung cấp trạng thái mở khóa do backend tính. Nội dung grammar công khai vẫn có thể được đọc tự do; mở khóa ở đây là thứ tự đề xuất học, không phải paywall.
