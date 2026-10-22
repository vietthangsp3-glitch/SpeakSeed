# SpeakSeed — Báo cáo giai đoạn 5

Ngày kiểm tra: 2026-10-22. Phạm vi: chuẩn bị beta; không triển khai ra dịch vụ ngoài và không phát sinh cuộc gọi Gemini có phí.

## Kết quả dữ liệu và migration

Database chính sau thay đổi có `integrity_check=ok`, 0 lỗi foreign key và đúng:

| Dữ liệu | Số lượng |
|---|---:|
| Từ vựng xuất bản (`reviewed=1`) | 4.213 |
| Grammar lesson xuất bản | 100 (20 mỗi cấp A0–B2) |
| Grammar exercise xuất bản | 1.000 |
| Bài bốn kỹ năng | 60 (15 mỗi kỹ năng) |
| Câu hỏi Listening/Reading | 90 |
| Tài khoản trong DB chính lúc chốt | 0 |
| Migration đã áp dụng | 8 |

Không chỉnh sửa nội dung học tập. Grammar lesson/exercise và skill lesson vẫn là `automated_checked`; không có bản ghi nào được tự đổi thành `human_reviewed`. Cờ `library_words.reviewed` là cờ xuất bản/kiểm tra pipeline lịch sử, không phải bằng chứng kiểm duyệt con người.

Migration `008_beta_hardening.sql` thêm metadata session, bảng chống brute-force, bảng usage/cost AI và index cho các truy vấn nóng. Runner chỉ áp dụng version chưa có nên chạy lại không nhân đôi schema. Backup/restore thực tế tạo một bản sao QA, xác minh checksum/count/integrity/FK; bản restore vẫn đúng 4.213 / 100 / 1.000 và DB gốc không bị xóa.

Công cụ SQLite → PostgreSQL mặc định read-only. Plan thực tế bao phủ 35 bảng, 20.825 dòng và 33 khai báo FK. Chưa chạy apply vì không có PostgreSQL đích được cấp phép, nên chưa tuyên bố migration PostgreSQL end-to-end thành công. Adapter runtime hỗ trợ SQLite và psycopg; SQLAlchemy/Alembic được hoãn để tránh thay đồng thời hàng trăm truy vấn raw SQL trước beta.

## Kiểm toán bảo mật

Các vấn đề có thể xác minh đã được sửa:

1. Token từng nằm trong `localStorage`: frontend chuyển sang session cookie `HttpOnly`, `SameSite=Strict`, `Secure` trong production và xóa token cũ.
2. Các POST dùng cookie chưa có CSRF: thêm double-submit token ràng buộc với session; WebSocket Live cũng kiểm tra origin và CSRF.
3. Login chưa có chống brute-force bền vững: thêm limit theo IP và email, lỗi đăng nhập chung và phép băm giả khi email không tồn tại.
4. Hạn mức Gemini cũ chỉ ở RAM: thêm quota theo tài khoản/IP trong DB, usage/status/latency/estimated cost, timeout và giới hạn thời lượng/dung lượng Live.
5. Cấu hình host/origin/header chưa đủ chặt: từ chối wildcard CORS với credential, kiểm tra unsafe Origin, Trusted Host, CSP, frame denial, nosniff, referrer policy và HSTS production.
6. Production có thể chạy với secret yếu: startup production giờ từ chối thiếu `APP_SECRET` hoặc secret dưới 32 ký tự; cookie secure mặc định.

Test mới kiểm tra CSRF, cookie, origin, security headers, brute-force, chuỗi SQL injection không làm thay đổi schema, quota AI và tách usage giữa tài khoản. API tiến độ/draft/session hiện có tiếp tục lọc `user_id` ở backend. Không có kết luận “an toàn tuyệt đối”.

Rủi ro còn mở: chưa có email verification, reset password, MFA, CAPTCHA/WAF; CSP còn cần `'unsafe-inline'` cho CSS hiện tại; limit IP có thể ảnh hưởng người dùng chung NAT; secret rotation/session revocation theo thiết bị chưa có UI; chưa có pentest độc lập/SAST dependency CVE feed; chưa có Redis/shared limiter cho nhiều database/app cluster (DB limiter hiện phù hợp một database dùng chung).

## Gemini và kiểm soát chi phí

- API key vẫn chỉ ở backend; test ngăn chuỗi key/config xuất hiện ở frontend.
- Quota mặc định mỗi giờ theo account/IP: Speaking turn 40/120, Live 10/30, evaluation 10/30, Writing 10/30, TTS 80/120, tutor 40/120, pronunciation 30/90.
- Live tối đa 600 giây và 28 MB audio theo mặc định; text/TTS/provider giữ timeout 35/55 giây, Live connect 15 giây.
- `GET /api/usage` chỉ trả usage của tài khoản hiện tại. Đơn giá lấy từ environment; 0 được giải thích là “chưa cấu hình”, không phải miễn phí.
- Không gọi provider thật trong kiểm thử, nên retry/quota thực tế và độ chính xác cost vẫn cần staging với budget nhỏ được phê duyệt.

## Hiệu năng

Index mới được xác nhận bằng `EXPLAIN QUERY PLAN` cho từ theo level, grammar path, skill path và learning events. Benchmark chạy bằng Uvicorn trên máy phát triển, database restore QA, không đại diện hạ tầng production:

| Scenario | Requests / concurrency | p50 | p95 | Max | Error rate | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Public read mix | 500 / 20 | 205,77 ms | 355,84 ms | 429,23 ms | 0% | 92,05 req/s |
| 8 account read/write mix | 200 / 8 | 60,05 ms | 852,37 ms | 5.056,61 ms | 0% | 38,76 req/s |

SQLite WAL xử lý được phép thử nhưng p95/max ghi còn cao. Không suy diễn capacity từ số này. Trước beta rộng cần benchmark trên máy triển khai, realistic think-time/dataset, quan sát CPU/I/O và ưu tiên PostgreSQL nếu có nhiều ghi đồng thời.

## Frontend, mobile và deploy

Frontend có timeout, lỗi dễ hiểu, retry bootstrap, trạng thái nút submit, cookie credentials, CSRF, skip link, focus-visible, dialog/status semantics và touch target tối thiểu trên mobile. Breakpoint hiện có cho 950/800/700/650/620 px. Dockerfile chạy user không đặc quyền; Compose dùng volume, required secrets, loopback bind và health check. Image seed được test bằng unit test để bảo toàn nội dung và loại dữ liệu tài khoản.

`docker compose config --quiet` đã pass với biến mẫu. Docker daemon không chạy nên chưa build/run image. Điều khiển browser bị tắt trong Work settings, vì vậy chưa thể xác nhận trực tiếp viewport desktop/mobile, microphone permission, TTS playback hay Gemini Live trong giai đoạn này. Các mục đó là blocker trước khi mời người dùng thật.

## Kết quả kiểm thử

- Automated suite cuối: **41 passed**, 1 cảnh báo deprecation `fastapi.testclient`; 0 failed.
- `node --check static/app.js`: pass.
- `py_compile` cho app/security/database và các tool mới: pass.
- `pip check`: không có dependency hỏng.
- Backup/restore CLI: pass trên bản sao thật.
- PostgreSQL plan: pass; PostgreSQL apply: chưa chạy.
- Docker Compose config: pass; Docker build/runtime: chưa chạy vì daemon không khả dụng.
- Browser E2E: bị chặn bởi cài đặt local browser, chưa pass.

## Checklist chặn trước beta thật

- [ ] Giáo viên/người biên tập duyệt mẫu ưu tiên B1–B2; cập nhật `human_reviewed` chỉ với bằng chứng.
- [ ] Chạy PostgreSQL migration trên staging trống; đối chiếu count/FK/tài khoản/tiến độ và diễn tập rollback.
- [ ] Build và chạy Docker image; xác nhận health/readiness, volume persistence và chạy restore drill trong container.
- [ ] Cấu hình HTTPS thật, secret store, hostname/origin chính xác; xác nhận không thể truy cập trực tiếp Uvicorn.
- [ ] Cấu hình đơn giá Gemini/Azure, budget/cảnh báo quota và chạy smoke test provider có phê duyệt chi phí.
- [ ] Chạy browser E2E desktop + 360/390/768 px: đăng ký, login/logout, placement, SRS, grammar, Listening, Reading, Speaking, Writing, dashboard.
- [ ] Kiểm tra microphone deny/allow/revoke, TTS cache/fallback và Gemini Live disconnect/timeout trên Chrome/Edge/Safari mục tiêu.
- [ ] Thực hiện accessibility audit bằng keyboard + screen reader + contrast tool.
- [ ] Chạy load test trên staging với tải dự kiến; đặt SLO p50/p95/error và quyết định SQLite hay PostgreSQL bằng số đo.
- [ ] Thực hiện security review độc lập: dependency scan, SAST/DAST, session fixation, password policy/reset, abuse/WAF và privacy/log retention.
- [ ] Viết privacy policy/terms, retention/deletion/export tài khoản và quy trình phản hồi sự cố.
- [ ] Chốt owner/on-call, monitoring, alert, backup schedule, restore drill và rollback release.

Đánh giá hiện tại: **chưa sẵn sàng mở beta công khai**. Bản build đã có nền tảng beta nội bộ tốt hơn, nhưng PostgreSQL staging, Docker runtime, browser/mobile/microphone E2E và kiểm tra bảo mật độc lập vẫn là điều kiện chặn.
