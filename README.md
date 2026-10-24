# SpeakSeed

> `A0` in SpeakSeed is an internal pre-A1 onboarding label. It is not an
> official CEFR level; the published vocabulary catalog itself starts at A1.

SpeakSeed là website học tiếng Anh cho người Việt, chạy bằng FastAPI và SQLite. Bản hiện tại có ngân hàng từ vựng thực, lộ trình ngữ pháp A0–B2, chương trình Listening/Reading/Speaking/Writing, placement test, learning path cá nhân, dashboard, daily plan, flashcard, dịch hai chiều, tài khoản và tiến độ học riêng.

Đợt thử nội bộ A0–A1 dùng [checklist 30 phút](BEGINNER_BETA_30_MIN_CHECKLIST.md), [hướng dẫn mạng nội bộ](INTERNAL_BETA_GUIDE.md) và [biểu mẫu phản hồi](BETA_FEEDBACK_TEMPLATE.md). Daily plan A0–A1 ưu tiên từ vựng, ôn tập, grammar, Listening và Reading; AI Speaking/Writing là tùy chọn.

## Số liệu đã kiểm tra

Database `speakseed.db` hiện chứa **6.280 từ đã xuất bản**, không trùng theo dạng chuẩn hóa. Trong đó 4.213 từ ban đầu được giữ nguyên; 2.067 từ mới được phát hành bằng policy `auto-core-v1` sau khi vượt qua kiểm tra tự động về headword/POS, nghĩa Việt, CEFR, provenance cấp mục từ, giấy phép và chống trùng.

- Tất cả từ mới có nghĩa tiếng Việt, loại từ, CEFR và attribution cấp mục từ.
- IPA có ở 929/2.067 từ mới; IPA không phải trường bắt buộc của Core Vocabulary.
- 7 từ mới có topic mapping tự động confidence ≥70; 2.060 từ còn lại hiển thị trong nhóm `Unclassified` thay vì bị ép gán sai chủ đề.
- Từ mới không được gắn `human_reviewed`; bằng chứng kiểm tra tự động bất biến nằm trong `vocabulary_automated_releases`.

Phân bố từ vựng: A1 1.000, A2 1.152, B1 1.957, B2 2.171. A0 hiện là cấp khởi động; chưa có từ A0 vì nguồn CEFR bắt đầu từ A1.

Lộ trình ngữ pháp mới gồm **20 unit, 100 lesson, 200 ví dụ Anh–Việt và 1.000 câu hỏi**. Mỗi cấp A0, A1, A2, B1, B2 có 4 unit, 20 lesson và 200 câu. Năm dạng bài có 200 câu mỗi dạng: multiple choice, fill in the blank, sentence ordering, error correction và Việt → Anh. Ngoài ra, hệ thống cũ vẫn giữ 6 ghi chú ngữ pháp, 18 câu song ngữ, 36 bài tập thư viện và 18 mẫu bài tập cốt lõi.

Nội dung ngữ pháp mang trạng thái `automated_checked`: đã qua kiểm tra cấu trúc, độ đầy đủ, cân bằng CEFR và kiểm tra nội dung trong quá trình phát triển, nhưng **chưa được tuyên bố là có biên tập viên con người kiểm duyệt**. Xem [GRAMMAR_REPORT.md](GRAMMAR_REPORT.md) và báo cáo chi tiết theo level/unit/lesson/dạng bài tại [GRAMMAR_QA_REPORT.md](GRAMMAR_QA_REPORT.md).

Chương trình bốn kỹ năng có **60 bài/nhiệm vụ**: 15 Listening, 15 Reading, 15 Speaking và 15 Writing; mỗi kỹ năng có 3 bài ở từng cấp A0–B2. Listening và Reading có **90 câu hỏi chấm tự động**: 15 multiple choice nghe, 15 điền từ, 15 dictation và 45 câu đọc hiểu. Nội dung này là nội dung gốc của SpeakSeed và mang trạng thái `automated_checked`, chưa phải `human_reviewed`. Xem [STAGE4_REPORT.md](STAGE4_REPORT.md).

## Chạy ứng dụng

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app:app --host 127.0.0.1 --port 8000
```

Mở <http://127.0.0.1:8000>. Các migration được chạy tự động khi server khởi động. Không đặt khóa Gemini trong JavaScript; khóa chỉ được đọc từ `.env` ở backend. Flashcard, Vocabulary, Listening, Dictation, Reading, Grammar và giọng đọc câu trả lời Speaking từng lượt luôn dùng Web Speech API trên thiết bị, không gọi Gemini TTS.

## Xây lại ngân hàng từ vựng

Các file nguồn thô được đặt trong `.source-cache/` và không commit. Tải chúng từ nguồn gốc được liệt kê trong [ATTRIBUTION.md](ATTRIBUTION.md), sau đó chạy:

```powershell
python -X utf8 tools/build_vocabulary.py --dry-run
python -X utf8 tools/build_vocabulary.py
```

Có thể truyền đường dẫn riêng qua `--cefr`, `--dictionary`, `--tatoeba`, `--flores-root`, `--ntrex-en` và `--ntrex-vi`. Importer:

- chạy lặp lại an toàn, cập nhật theo từ chuẩn hóa thay vì tạo bản sao;
- không tự dịch hay tự bịa IPA/ví dụ;
- chỉ xuất bản bản ghi đủ trường bắt buộc;
- từ chối thay đổi database nếu kết quả hợp lệ dưới `--minimum` (mặc định 4.000);
- ghi lần import, SHA-256 gộp của nguồn và attribution vào SQLite.

`import_data.py` là adapter cũ, không còn cho phép publish trực tiếp và chặn các nguồn chưa qua license gate.

## Pipeline dữ liệu mở có kiểm soát

Kiểm tra [DATA_SOURCE_AUDIT.md](DATA_SOURCE_AUDIT.md) trước khi dùng nguồn mới. Pipeline offline mới chỉ ghi vào staging và không có lệnh publish hoặc kết nối Neon:

```powershell
python -X utf8 tools/content_pipeline.py audit --report qa_artifacts/source-audit.json
python -X utf8 tools/content_pipeline.py stage --source cefr-j-1.5 `
  --input .source-cache/cefrj/olp-en-cefrj-master/cefrj-vocabulary-profile-1.5.csv `
  --dry-run --report qa_artifacts/cefrj-dry-run.json
```

Hướng dẫn import theo batch, resume, enrichment, review và PostgreSQL staging trên Windows nằm trong [CONTENT_PIPELINE_RUNBOOK.md](CONTENT_PIPELINE_RUNBOOK.md). Xem bằng chứng Phase 1 tại [DATA_PIPELINE_PHASE1_REPORT.md](DATA_PIPELINE_PHASE1_REPORT.md), số liệu import thật Phase 2 tại [DATA_PIPELINE_PHASE2_REPORT.md](DATA_PIPELINE_PHASE2_REPORT.md), trạng thái ngân hàng câu hỏi Phase 3 tại [DATA_PIPELINE_PHASE3_REPORT.md](DATA_PIPELINE_PHASE3_REPORT.md), và kiểm kê/màn hình học theo chủ đề Phase 4 tại [VOCABULARY_PHASE4_REPORT.md](VOCABULARY_PHASE4_REPORT.md).
Quy trình Core/Enriched, review batch, internal preview và publish an toàn Phase 5 được ghi tại [VOCABULARY_PHASE5_REPORT.md](VOCABULARY_PHASE5_REPORT.md).

## Xây lại chương trình ngữ pháp

```powershell
python -X utf8 tools/build_grammar.py --dry-run
python -X utf8 tools/build_grammar.py
```

Importer ngữ pháp có ID ổn định và chạy lặp lại an toàn. Nó upsert curriculum, giữ nguyên người dùng, lượt làm bài, tiến độ và toàn bộ ngân hàng từ vựng. Khi server khởi động, importer này cũng chạy idempotent để database mới có nội dung học ngay.

## Xây lại chương trình bốn kỹ năng

```powershell
python -X utf8 tools/build_skills.py --dry-run
python -X utf8 tools/build_skills.py
```

Importer dùng ID ổn định, chỉ upsert nội dung và liên kết lại từ vựng; không xóa tài khoản, lượt làm, draft, phiên Speaking hay tiến độ. Migration `007_four_skills.sql` mở rộng schema theo kiểu bảo toàn dữ liệu và được migration runner chạy đúng một lần.

## Kiểm thử và kiểm toán

```powershell
pip install -r requirements-dev.txt
python -X utf8 -m pytest -q
python -X utf8 tools/build_vocabulary.py --dry-run
python -X utf8 tools/build_grammar.py --dry-run
python -X utf8 tools/build_skills.py --dry-run
python -X utf8 tools/audit_grammar.py
```

Test bao phủ migration, tính lặp lại của ba importer, ràng buộc chất lượng, API từ vựng, SRS, curriculum, placement test, dashboard, daily plan, bốn kỹ năng, chấm bài, đăng nhập/đăng xuất, phân tách tiến độ theo tài khoản và ghi SQLite đồng thời. Audit ngữ pháp duyệt toàn bộ 100 lesson/1.000 câu hỏi; validator bốn kỹ năng từ chối câu lựa chọn không có đáp án được chấp nhận. Xem thiết kế cá nhân hóa tại [STAGE3_REPORT.md](STAGE3_REPORT.md), kết quả giai đoạn 4 tại [STAGE4_REPORT.md](STAGE4_REPORT.md), và kiểm toán beta tại [STAGE5_REPORT.md](STAGE5_REPORT.md). Hướng dẫn vận hành nằm trong [DEPLOYMENT.md](DEPLOYMENT.md).

## Tính năng học và AI

- Flashcard có hàng đợi ôn đến hạn và lịch spaced repetition theo tài khoản.
- Lộ trình ngữ pháp A0–B2 theo unit, lesson, kiểm tra cuối unit và tiến độ riêng theo tài khoản.
- Placement test 40 câu A0–B2 gồm grammar, vocabulary, listening, điền khuyết, sắp xếp câu và reading; có lưu từng đáp án, khôi phục sau reload, kết quả chi tiết và learning path.
- 15 bài Listening với transcript, câu hỏi nghe hiểu/điền từ/dictation và giọng đọc Web Speech API trên thiết bị.
- 15 bài Reading với câu đọc hiểu, lời giải và nút lưu từ thật vào hàng đợi spaced repetition.
- 15 nhiệm vụ Speaking thực tế; phiên từng lượt/Live được lưu theo tài khoản và phản hồi không tự nhận tương đương chứng chỉ.
- 15 nhiệm vụ Writing từ câu đến essay/email; có draft, giới hạn từ, phản hồi Gemini tiếng Việt và lưu bài đã nộp.
- Dịch Việt → Anh, Anh → Việt, quiz, nghe chép chính tả và năm dạng bài ngữ pháp.
- Gemini Speaking từng lượt vẫn dùng quota xử lý văn bản; câu trả lời được đọc bằng Web Speech API. Gemini Live chỉ kết nối sau cảnh báo và thao tác bắt đầu của người dùng. Backend Gemini TTS đã bị khóa; cache cũ được giữ lại nhưng không phục vụ hoặc tạo audio mới.
- API key không được gửi xuống frontend.

## Giới hạn hiện tại

- Việc ghép nghĩa với ví dụ được kiểm tra tự động theo loại từ và độ tương đồng từ vựng; chưa thay thế biên tập thủ công từng nghĩa.
- Phân loại chủ đề là heuristic có tính xác định, nên phần lớn từ nằm trong nhóm “Tổng hợp”.
- Chấm câu viết lại hiện dùng đáp án chuẩn hóa; chưa chấp nhận mọi cách diễn đạt tương đương.
- Nội dung ngữ pháp chưa qua vòng kiểm duyệt của giáo viên/biên tập viên con người; cột `review_status` phản ánh rõ điều này.
- Rate limit Gemini được lưu theo tài khoản/IP trong database; triển khai nhiều database hoặc nhiều vùng vẫn cần rate limiter dùng chung.
- Session web mặc định dùng cookie `HttpOnly` + CSRF; bearer chỉ dành cho API client/test được cấu hình rõ.
- PostgreSQL migration/backup/restore và Chrome E2E desktop/mobile đã được xác nhận ở giai đoạn 6; Docker runtime và kiểm thử microphone vật lý/đa trình duyệt vẫn chưa hoàn tất.
- Trước beta công khai vẫn cần security review độc lập và quy trình duyệt nội dung bởi giáo viên.

Chi tiết bản quyền và nguồn dữ liệu nằm trong [ATTRIBUTION.md](ATTRIBUTION.md).

## Vercel preview

Gói chuẩn bị Vercel yêu cầu PostgreSQL ngoài qua `DATABASE_URL` và cố ý từ chối SQLite khi chạy trên Vercel. Gemini Live mặc định tắt; bài học thông thường tiếp tục dùng Web Speech API. Xem trạng thái PASS/FAIL/BLOCKED, danh sách biến môi trường, quy trình migration và checklist URL thật trong [VERCEL_DEPLOYMENT_REPORT.md](VERCEL_DEPLOYMENT_REPORT.md). Không chạy `vercel --prod` trước khi có xác nhận riêng.
