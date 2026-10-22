# Báo cáo QA ngữ pháp giai đoạn 2.5

Ngày kiểm tra: 2026-10-22.

Phạm vi: toàn bộ catalog nguồn và dữ liệu được sinh lại gồm 20 unit, 100 lesson, 200 ví dụ Anh–Việt và 1.000 câu hỏi. Đây là kết quả kiểm tra tự động và rà soát kỹ thuật; **không phải bằng chứng kiểm duyệt bởi giáo viên/người biên tập**. Tất cả nội dung tiếp tục mang nhãn `automated_checked`; số mục `human_reviewed` là 0.

Số “affected” giữa các hạng mục có thể chồng lắp, vì vậy không được cộng chúng để suy ra số bản ghi duy nhất. Hai bài B1 ở ranh giới CEFR được giữ làm nội dung cầu nối và nêu rõ để chờ đánh giá chuyên môn bên ngoài.

## Summary

```json
{
  "units_checked": 20,
  "lessons_checked": 100,
  "examples_checked": 200,
  "exercises_checked": 1000,
  "structural_failures": 0,
  "fixed_finding_categories": 9,
  "open_finding_categories": 3,
  "human_reviewed": 0,
  "review_status": "automated_checked"
}
```

## By level

| Level | Units | Lessons | Exercises | Structural failures | CEFR boundary notes |
|---|---:|---:|---:|---:|---:|
| A0 | 4 | 20 | 200 | 0 | 0 |
| A1 | 4 | 20 | 200 | 0 | 0 |
| A2 | 4 | 20 | 200 | 0 | 0 |
| B1 | 4 | 20 | 200 | 0 | 2 |
| B2 | 4 | 20 | 200 | 0 | 0 |

## By unit

| Unit | Level | Title | Lessons | Exercises | Test / lesson / kind coverage | Status |
|---:|---|---|---:|---:|---|---|
| 1 | A0 | Câu đầu tiên | 5 | 50 | 10 / 5 / 5 | pass |
| 2 | A0 | Danh từ và sở hữu | 5 | 50 | 10 / 5 / 5 | pass |
| 3 | A0 | Hiện tại cơ bản | 5 | 50 | 10 / 5 / 5 | pass |
| 4 | A0 | Giao tiếp thiết yếu | 5 | 50 | 10 / 5 / 5 | pass |
| 5 | A1 | Thói quen và hiện tại | 5 | 50 | 10 / 5 / 5 | pass |
| 6 | A1 | Kể chuyện quá khứ | 5 | 50 | 10 / 5 / 5 | pass |
| 7 | A1 | Kế hoạch và so sánh | 5 | 50 | 10 / 5 / 5 | pass |
| 8 | A1 | Mở rộng câu | 5 | 50 | 10 / 5 / 5 | pass |
| 9 | A2 | Kinh nghiệm và thời gian | 5 | 50 | 10 / 5 / 5 | pass |
| 10 | A2 | Điều kiện và sắc thái | 5 | 50 | 10 / 5 / 5 | pass |
| 11 | A2 | Câu bị động và tường thuật | 5 | 50 | 10 / 5 / 5 | pass |
| 12 | A2 | Câu phức thực dụng | 5 | 50 | 10 / 5 / 5 | pass |
| 13 | B1 | Các thì nâng cao | 5 | 50 | 10 / 5 / 5 | pass |
| 14 | B1 | Giả định và suy luận | 5 | 50 | 10 / 5 / 5 | pass |
| 15 | B1 | Biến đổi câu | 5 | 50 | 10 / 5 / 5 | pass |
| 16 | B1 | Liên kết và nhấn mạnh | 5 | 50 | 10 / 5 / 5 | pass |
| 17 | B2 | Điều kiện và đảo ngữ | 5 | 50 | 10 / 5 / 5 | pass |
| 18 | B2 | Cấu trúc học thuật | 5 | 50 | 10 / 5 / 5 | pass |
| 19 | B2 | Rút gọn và liên kết | 5 | 50 | 10 / 5 / 5 | pass |
| 20 | B2 | Sắc thái nâng cao | 5 | 50 | 10 / 5 / 5 | pass |

## By lesson

| ID | Level | Unit | Lesson | Status | Accepted cloze variants | Note |
|---:|---|---:|---|---|---:|---|
| 1 | A0 | 1 | Đại từ nhân xưng | pass | 0 |  |
| 2 | A0 | 1 | Động từ be: khẳng định | pass | 0 |  |
| 3 | A0 | 1 | Động từ be: phủ định | pass | 0 |  |
| 4 | A0 | 1 | Động từ be: câu hỏi | pass | 0 |  |
| 5 | A0 | 1 | Mạo từ a và an | pass | 0 |  |
| 6 | A0 | 2 | Danh từ số nhiều | pass | 0 |  |
| 7 | A0 | 2 | This, that, these, those | pass | 0 |  |
| 8 | A0 | 2 | Tính từ sở hữu | pass | 0 |  |
| 9 | A0 | 2 | Sở hữu cách với 's | pass | 0 |  |
| 10 | A0 | 2 | Have và has | pass | 0 |  |
| 11 | A0 | 3 | There is và there are | pass | 0 |  |
| 12 | A0 | 3 | Câu mệnh lệnh | pass | 0 |  |
| 13 | A0 | 3 | Can chỉ khả năng | pass | 0 |  |
| 14 | A0 | 3 | Hiện tại đơn: khẳng định | pass | 0 |  |
| 15 | A0 | 3 | Hiện tại đơn: phủ định | pass | 0 |  |
| 16 | A0 | 4 | Hiện tại đơn: câu hỏi | pass | 0 |  |
| 17 | A0 | 4 | Câu hỏi Wh- cơ bản | pass | 0 |  |
| 18 | A0 | 4 | Giới từ nơi chốn | pass | 0 |  |
| 19 | A0 | 4 | Tính từ trong câu | pass | 0 |  |
| 20 | A0 | 4 | And, but và or | pass | 0 |  |
| 21 | A1 | 5 | Trạng từ tần suất | pass | 0 |  |
| 22 | A1 | 5 | Hiện tại tiếp diễn | pass | 0 |  |
| 23 | A1 | 5 | Hiện tại đơn và tiếp diễn | pass | 0 |  |
| 24 | A1 | 5 | Động từ chỉ trạng thái | pass | 0 |  |
| 25 | A1 | 5 | Đại từ tân ngữ | pass | 0 |  |
| 26 | A1 | 6 | Quá khứ của be | pass | 0 |  |
| 27 | A1 | 6 | Quá khứ đơn: động từ có quy tắc | pass | 0 |  |
| 28 | A1 | 6 | Quá khứ đơn: động từ bất quy tắc | pass | 0 |  |
| 29 | A1 | 6 | Quá khứ đơn: phủ định | pass | 0 |  |
| 30 | A1 | 6 | Quá khứ đơn: câu hỏi | pass | 0 |  |
| 31 | A1 | 7 | Tương lai với will | pass | 0 |  |
| 32 | A1 | 7 | Be going to | pass | 0 |  |
| 33 | A1 | 7 | So sánh hơn | pass | 0 |  |
| 34 | A1 | 7 | So sánh nhất | pass | 0 |  |
| 35 | A1 | 7 | Much, many và a lot of | pass | 1 |  |
| 36 | A1 | 8 | Some và any | pass | 1 |  |
| 37 | A1 | 8 | Like, love, hate + V-ing | pass | 0 |  |
| 38 | A1 | 8 | Động từ nguyên mẫu chỉ mục đích | pass | 0 |  |
| 39 | A1 | 8 | Should và shouldn't | pass | 2 |  |
| 40 | A1 | 8 | Must và have to | pass | 1 |  |
| 41 | A2 | 9 | Hiện tại hoàn thành: trải nghiệm | pass | 0 |  |
| 42 | A2 | 9 | Just, already và yet | pass | 0 |  |
| 43 | A2 | 9 | For và since | pass | 0 |  |
| 44 | A2 | 9 | Quá khứ tiếp diễn | pass | 0 |  |
| 45 | A2 | 9 | Quá khứ đơn và tiếp diễn | pass | 0 |  |
| 46 | A2 | 10 | Hiện tại tiếp diễn cho lịch hẹn | pass | 0 |  |
| 47 | A2 | 10 | Câu điều kiện loại 0 | pass | 0 |  |
| 48 | A2 | 10 | Câu điều kiện loại 1 | pass | 0 |  |
| 49 | A2 | 10 | Mệnh đề thời gian tương lai | pass | 0 |  |
| 50 | A2 | 10 | May, might và could | pass | 2 |  |
| 51 | A2 | 11 | Used to | pass | 0 |  |
| 52 | A2 | 11 | Too và enough | pass | 0 |  |
| 53 | A2 | 11 | Bị động hiện tại đơn | pass | 0 |  |
| 54 | A2 | 11 | Bị động quá khứ đơn | pass | 0 |  |
| 55 | A2 | 11 | Câu tường thuật cơ bản | pass | 0 |  |
| 56 | A2 | 12 | Mệnh đề quan hệ xác định | pass | 2 |  |
| 57 | A2 | 12 | Danh động từ và nguyên mẫu | pass | 0 |  |
| 58 | A2 | 12 | Few, a few, little, a little | pass | 0 |  |
| 59 | A2 | 12 | Câu hỏi gián tiếp | pass | 1 |  |
| 60 | A2 | 12 | Câu hỏi đuôi | pass | 0 |  |
| 61 | B1 | 13 | Hiện tại hoàn thành tiếp diễn | pass | 0 |  |
| 62 | B1 | 13 | Quá khứ hoàn thành | pass | 0 |  |
| 63 | B1 | 13 | Các thì kể chuyện | pass | 0 |  |
| 64 | B1 | 13 | Tương lai tiếp diễn | pass | 0 |  |
| 65 | B1 | 13 | Tương lai hoàn thành | review_boundary | 0 | B1+/B2 boundary: future perfect |
| 66 | B1 | 14 | Câu điều kiện loại 2 | pass | 1 |  |
| 67 | B1 | 14 | Câu điều kiện loại 3 | pass | 0 |  |
| 68 | B1 | 14 | Wish ở hiện tại | pass | 0 |  |
| 69 | B1 | 14 | Wish về quá khứ | pass | 0 |  |
| 70 | B1 | 14 | Suy luận ở hiện tại | pass | 0 |  |
| 71 | B1 | 15 | Suy luận về quá khứ | review_boundary | 0 | B1+/B2 boundary: past modal deduction |
| 72 | B1 | 15 | Bị động với nhiều thì | pass | 0 |  |
| 73 | B1 | 15 | Cấu trúc have/get something done | pass | 0 |  |
| 74 | B1 | 15 | Câu hỏi tường thuật | pass | 0 |  |
| 75 | B1 | 15 | Mệnh lệnh tường thuật | pass | 0 |  |
| 76 | B1 | 16 | Mệnh đề quan hệ không xác định | pass | 0 |  |
| 77 | B1 | 16 | Liên từ tương phản | pass | 1 |  |
| 78 | B1 | 16 | Nguyên nhân và kết quả | pass | 2 |  |
| 79 | B1 | 16 | So và such | pass | 0 |  |
| 80 | B1 | 16 | Unless và as long as | pass | 0 |  |
| 81 | B2 | 17 | Câu điều kiện hỗn hợp | pass | 0 |  |
| 82 | B2 | 17 | Đảo ngữ với trạng từ phủ định | pass | 0 |  |
| 83 | B2 | 17 | Đảo ngữ điều kiện | pass | 0 |  |
| 84 | B2 | 17 | Câu chẻ với it | pass | 2 |  |
| 85 | B2 | 17 | Câu chẻ với what | pass | 0 |  |
| 86 | B2 | 18 | Bị động với động từ tường thuật | pass | 0 |  |
| 87 | B2 | 18 | Động từ khuyết thiếu hoàn thành | pass | 0 |  |
| 88 | B2 | 18 | Thức giả định | pass | 1 |  |
| 89 | B2 | 18 | Would rather và it's time | pass | 1 |  |
| 90 | B2 | 18 | Mệnh đề phân từ | pass | 2 |  |
| 91 | B2 | 19 | Mệnh đề phân từ hoàn thành | pass | 0 |  |
| 92 | B2 | 19 | Danh hóa | pass | 0 |  |
| 93 | B2 | 19 | Mạo từ trong nghĩa khái quát | pass | 0 |  |
| 94 | B2 | 19 | Lược bỏ và thay thế | pass | 0 |  |
| 95 | B2 | 19 | Từ nối bổ sung và đối lập | pass | 2 |  |
| 96 | B2 | 20 | Ngôn ngữ giảm nhẹ | pass | 1 |  |
| 97 | B2 | 20 | Giới từ trong mệnh đề quan hệ | pass | 1 |  |
| 98 | B2 | 20 | Tương lai trong quá khứ | pass | 0 |  |
| 99 | B2 | 20 | Tường thuật với động từ đa dạng | pass | 1 |  |
| 100 | B2 | 20 | No sooner và hardly | pass | 0 |  |

## By exercise kind

| Kind | Count | Multi-answer items | Remaining risk |
|---|---:|---:|---|
| multiple_choice | 200 | 0 | none detected |
| fill_blank | 200 | 25 | none detected |
| sentence_ordering | 200 | 0 | none detected |
| error_correction | 200 | 0 | none detected |
| vi_to_en | 200 | 0 | open paraphrases |

## Fixed findings

- **QA-001 · high** — Multiple-choice mixed examples from different contexts, allowing more than one grammatical option. Affected: 200. Fix: Use the Vietnamese target and only the correct/common-error pair from the same example.
- **QA-002 · high** — Error-correction prompts lacked semantic context, so a grammatical sentence with another meaning could be defensible. Affected: 200. Fix: Include the Vietnamese target in every error-correction prompt.
- **QA-003 · high** — A2 second conditional duplicated the B1 objective and was above the intended A2 progression. Affected: 10. Fix: Replace it with A2 future time clauses; keep the second conditional at B1.
- **QA-004 · medium** — An A0 possessive example used the plural apostrophe rule. Affected: 5. Fix: Use a singular possessive example and keep plural possessives out of A0.
- **QA-005 · medium** — Contractions such as I'm/can't were rejected against expanded model answers. Affected: grading mechanism. Fix: Canonicalize common English contractions before comparison.
- **QA-006 · medium** — Some cloze prompts permit multiple valid words or phrases. Affected: 25. Fix: Store explicit accepted alternatives for verified ambiguous cloze items.
- **QA-007 · medium** — Several learner-error examples contained meta wording or implausible phrasing. Affected: 9. Fix: Replace them with plausible, unambiguously incorrect learner errors.
- **QA-008 · medium** — The first nominalisation example used a verb rather than a nominalised structure. Affected: 5. Fix: Replace it with “The company's decision was to expand.” and regenerate its five exercises.
- **QA-009 · high** — Two cloze prompts omitted a time expression from the model sentence, so inserting the answer could not reconstruct the target. Affected: 2. Fix: Restore the missing time expressions in lessons 64 and 65 and rerun the reconstruction audit.

## Open findings

- **QA-R01 · medium** — 200 vi_to_en exercises: Open translation can have valid paraphrases beyond stored answers. Recommendation: Add teacher-authored alternatives per item or a separately evaluated semantic grader; do not silently accept unrestricted AI output.
- **QA-R02 · low** — B1 lessons 65 and 71: Future perfect and past modal deduction sit near the B1+/B2 boundary in different CEFR-aligned syllabi. Recommendation: Retain as bridge content but request external teacher review before claiming strict CEFR certification.
- **QA-R03 · info** — all content: No evidence of review by a human teacher/editor is stored. Recommendation: Keep automated_checked until named human review evidence is recorded.

