# Báo cáo chương trình ngữ pháp

## Phạm vi

- 5 cấp độ: A0, A1, A2, B1, B2.
- 20 unit: 4 unit mỗi cấp.
- 100 lesson: 20 lesson mỗi cấp, 5 lesson mỗi unit.
- 200 ví dụ Anh–Việt: 2 ví dụ mỗi lesson.
- 1.000 câu hỏi: 10 câu mỗi lesson.
- 200 câu kiểm tra cuối unit: 10 câu mỗi unit.

Mỗi bài kiểm tra unit lấy hai câu từ từng lesson trong unit. Năm dạng bài đều xuất hiện hai lần, tránh việc bài kiểm tra chỉ đo chủ điểm cuối cùng.

## Phân bố dạng bài

| Dạng | Số câu |
|---|---:|
| Multiple choice | 200 |
| Fill in the blank | 200 |
| Sentence ordering | 200 |
| Error correction | 200 |
| Vietnamese-to-English | 200 |

## Trường nội dung lesson

Mỗi lesson có cấp CEFR, unit, thứ tự, chủ điểm, giải thích tiếng Việt, công thức, hai ví dụ Anh–Việt và hai lỗi thường gặp kèm câu sửa đúng. Mỗi exercise có đáp án, lời giải, dạng bài, cấp độ và quan hệ đến lesson/unit.

939/1.000 câu hỏi liên kết được với ít nhất một từ nội dung trong ngân hàng 4.213 từ. Các function word như đại từ, trợ động từ và mạo từ bị loại khỏi phần gợi ý để tránh hiển thị sai nghĩa theo ngữ cảnh. Con số này được đo lại sau đợt sửa prompt QA 2.5.

## Trạng thái kiểm duyệt

Giá trị hiện tại là `automated_checked`, không phải `human_reviewed`. Pipeline tự động kiểm tra:

- đúng số lượng và cân bằng cấp độ/dạng bài;
- không có prompt trùng;
- đủ đáp án, lời giải, công thức và ví dụ;
- mỗi unit test phủ đủ năm lesson và năm dạng bài;
- importer chạy lại không nhân bản hoặc xóa dữ liệu người dùng;
- API không gửi đáp án xuống frontend trước khi người học trả lời.
- toàn bộ cloze tái tạo đúng câu đích; không trùng chính xác mục tiêu (chủ điểm + công thức), tiêu đề hoặc ví dụ tiếng Anh.

Nội dung đã được rà soát trong quá trình triển khai nhưng chưa thay thế vòng phản biện của giáo viên tiếng Anh. Khi có kiểm duyệt chuyên môn, chỉ cập nhật `review_status='human_reviewed'` cho những lesson/exercise thực sự đã được duyệt.

## Tái tạo dữ liệu

```powershell
python -X utf8 tools/build_grammar.py --dry-run
python -X utf8 tools/build_grammar.py
python -X utf8 tools/audit_grammar.py
python -X utf8 -m pytest -q
```

Báo cáo QA chi tiết, bao gồm 9 nhóm lỗi đã sửa và 3 rủi ro còn mở, nằm tại [GRAMMAR_QA_REPORT.md](GRAMMAR_QA_REPORT.md).
