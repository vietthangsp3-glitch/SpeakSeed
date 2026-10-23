# SpeakSeed Placement Test v2 Report

## Trạng thái

- Hoàn tất implementation local; chưa push GitHub, chưa deploy Vercel, chưa chạy migration trên Neon.
- 40/40 câu có key duy nhất, prompt duy nhất, đáp án, CEFR, section, topic, giải thích và source.
- Tất cả 40 câu mang nhãn `automated_checked`; không có bằng chứng human review và không được tuyên bố là `human_reviewed`.

## Phân bố

| Section | Số câu |
|---|---:|
| Grammar multiple choice | 7 |
| Vocabulary multiple choice | 5 |
| Listening | 8 (4 multiple choice, 4 fill blank) |
| Fill in the blanks | 8 |
| Sentence ordering | 6 |
| Reading comprehension | 6 |

Mỗi level A0, A1, A2, B1 và B2 có đúng 8 câu. Câu hỏi được chọn xác định từ grammar curriculum, four-skills curriculum và vocabulary bank đã xuất bản; không gọi Gemini khi tạo hoặc chấm lượt làm.

## Chấm điểm

Trọng số: Grammar 20%, Vocabulary 10%, Listening 25%, Fill blank 15%, Sentence ordering 10%, Reading 20%. Backend chấm từ question snapshot trong `placement_attempts`; frontend không gửi điểm.

Level được đề xuất theo cổng tuần tự, không chỉ theo tỉ lệ tổng: A0 55%, A1 58%, A2 60%, B1 65%. Phải đạt cổng thấp hơn trước khi được đề xuất level tiếp theo. Câu bỏ qua tính sai; Listening được đánh dấu `audio_unavailable` không vào mẫu số và làm confidence thành `reduced`.

## Lưu và khôi phục

Migration `009_placement_test_v2.sql` thêm `placement_responses`; `010_placement_order_drafts.sql` cho phép lưu thứ tự câu đang sắp xếp. Mỗi row có `attempt_id`, `user_id`, `question_key`, answer, state và timestamp. API ownership luôn kiểm tra cả attempt và `user_id`.

Lịch sử cũ trong `placement_attempts` không bị xóa. Placement không ghi vào `progress`, vì vậy không tự coi từ là đã thuộc.

## Kiểm thử

- Pytest: 69 passed, 1 deprecation warning từ Starlette TestClient.
- Browser E2E Chrome desktop + viewport mobile 390x844: PASS 15/15 steps, 0 JavaScript error.
- Placement E2E: 40 mixed questions, Web Speech audio endpoint theo thao tác người dùng, submit và 40 review rows: PASS.
- API tests: answer-key non-disclosure, equivalent normalized answers, audio failure, resume, history, IDOR hai account, no vocabulary mastery side effect: PASS.

## Triển khai an toàn

Neon hiện tại schema 008 phải được backup/branch trước. Nạp direct URL vào `DATABASE_URL`, sau đó chạy dry-run:

```powershell
python -X utf8 .\tools\apply_postgres_placement_v2.py
```

Chỉ sau khi output xác nhận đúng count user/attempt và người vận hành cho phép:

```powershell
python -X utf8 .\tools\apply_postgres_placement_v2.py --apply
```

Sau migration phải có 36 bảng và latest schema `010_placement_order_drafts.sql`. Sau đó mới push/redeploy code; app không tự migration PostgreSQL khi cold start.

## Giới hạn

- Web Speech API cần transcript ở client để tổng hợp giọng. Transcript không nằm trong payload khởi tạo và không hiển thị trước submit, nhưng người có kiến thức DevTools có thể xem response audio theo yêu cầu. Muốn chống điều này phải dùng file audio có bản quyền hợp lệ.
- Chưa kiểm thử trên thiết bị mobile vật lý; mới kiểm thử Chrome với mobile viewport.
- Placement không đánh giá speaking/writing tự do và không tương đương chứng chỉ CEFR.
