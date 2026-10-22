# SpeakSeed — Báo cáo giai đoạn 6

Ngày chốt: **2026-10-23**. Phạm vi: hoàn tất điều kiện kỹ thuật trước beta công khai; không thêm tính năng học tập, không triển khai public, không gọi Gemini thật và không tạo tài nguyên trả phí.

## Kết luận

**NO-GO cho beta công khai.** PostgreSQL local QA, backup/restore, rollback SQLite, browser E2E và security regression đã có bằng chứng PASS. Các blocker còn lại là Docker runtime chưa chạy, chưa có PostgreSQL staging được cấp quyền, chưa thử Gemini/TTS/Live thật với ngân sách được duyệt, chưa kiểm thử microphone vật lý/đa trình duyệt, chưa có HTTPS production và chưa có security review độc lập.

Database SQLite chính được giữ nguyên: `integrity_check=ok`, 0 lỗi foreign key, 0 tài khoản, **4.213 từ đã xuất bản**, **100 grammar lesson**, **1.000 grammar exercise**. Có 4.216 dòng `library_words` tổng cộng, trong đó 4.213 dòng có `reviewed=1`; cờ này là trạng thái xuất bản của pipeline cũ, không được diễn giải là `human_reviewed`.

## 1. PostgreSQL staging và rollback

Không có DSN/credential cho PostgreSQL staging do chủ dự án cấp, nên **không đụng tới hai service PostgreSQL cài sẵn** và không thay đổi production. Để kiểm thử adapter an toàn, một PostgreSQL 18 QA cluster cục bộ, độc lập được tạo tại vùng QA của Codex, dùng trust chỉ trên `127.0.0.1:55432`; đây không phải staging chính thức.

Kết quả migration từ bản sao SQLite:

| Hạng mục | Kết quả |
|---|---:|
| Bảng | 35/35 |
| Dòng nguồn được đối chiếu | 20.825 |
| Foreign key | 33 |
| Index từ migration plan | 43 |
| Digest dữ liệu theo từng bảng | 35/35 khớp |
| Ứng dụng chạy với PostgreSQL | PASS |
| Health live/ready | 200/200 |
| Login tài khoản QA + dashboard | 200/200 |

Lỗi xác minh và đã sửa trong quá trình chạy thật:

1. Migration làm mất `WHERE` của partial unique index, biến index thành unique toàn bảng và làm import dừng. Import lỗi đã rollback sạch; công cụ nay đọc predicate từ `sqlite_master` và có regression test.
2. Alias `day` trong dashboard xung đột từ khóa PostgreSQL; đã quote đúng.
3. Một số `ON CONFLICT DO UPDATE` dùng tên cột trần gây ambiguous column; adapter nay qualify cột đích.
4. `dict_row` làm mất giá trị khi query có nhiều cột trùng tên; `HybridRow` nay giữ đầy đủ vị trí và tạo key không trùng.

Backup thực tế bằng `pg_dump -Fc` tạo file 763.656 byte, restore vào database mới thành công. So sánh source/restore sau E2E và benchmark khớp tuyệt đối **35 bảng, 21.174 dòng, 33 foreign key, 78 index** (78 gồm cả PK/unique index do PostgreSQL tạo). SQLite rollback được chạy thành ứng dụng riêng và health/content API đều 200; SQLite gốc không bị xóa hoặc ghi đè.

Bằng chứng: `qa_artifacts/stage6_postgres_verify.json`, `qa_artifacts/stage6_postgres_restore_verify.json`, `qa_artifacts/stage6_postgres.dump`, `qa_artifacts/stage6_runtime_smoke.json`.

## 2. Docker

- `docker compose config --quiet`: **PASS** khi cấp biến mẫu bắt buộc `APP_SECRET`, `ALLOWED_HOSTS`, `ALLOWED_ORIGINS`.
- Docker client: 29.8.2.
- Docker daemon: **NOT RUN / BLOCKED**; Windows service `com.docker.service` đang `Stopped`, startup type `Manual`, named pipe không tồn tại.
- Vì daemon không khả dụng, build image, Compose startup/shutdown/restart, health check trong container và volume persistence đều **chưa được chạy**. Không tự khởi động dịch vụ hệ thống thay người dùng.

## 3. Browser E2E

Bộ `e2e/run_stage6.py` dùng Playwright 1.64.1 và Chrome đã cài trên máy. Chạy thật trên ứng dụng PostgreSQL QA, desktop 1440×900 và mobile 390×844, Gemini key bị xóa khỏi environment để không phát sinh chi phí.

**15/15 bước PASS, 0 page JavaScript exception:**

- tải desktop;
- đăng ký bằng cookie HttpOnly/SameSite Strict và payload stored-XSS;
- CSRF thiếu token bị 403, token hợp lệ được 200;
- placement test 25 câu;
- vocabulary/SRS và tiến độ;
- grammar attempt;
- Listening attempt;
- Reading attempt và lưu từ;
- Writing provider failure vẫn giữ draft;
- Speaking provider failure không hoàn thành bài;
- TTS không cấu hình trả 503 có kiểm soát;
- microphone permission qua fake media stream và Live control bị khóa khi backend thiếu key;
- session/progress còn sau reload;
- logout/login cấp session mới;
- mobile không tràn document, bottom navigation cố định, không có button rỗng accessible name theo phép kiểm cơ bản.

Hai lỗi frontend đã sửa: logout sau đăng ký không reset modal về login; mobile 390 px bị tràn ngang 26 px bởi navigation. Screenshot và báo cáo ở `qa_artifacts/stage6-desktop-1440.png`, `qa_artifacts/stage6-mobile-390.png`, `qa_artifacts/stage6_e2e_result.json`.

Console có các quan sát dự kiến: font ngoài bị môi trường chặn, favicon 404, `/api/me` 401 trước đăng nhập, CSRF 403 chủ động và ba 503 provider chủ động. Không có `pageerror`. Kiểm thử accessibility chỉ là smoke check; chưa thay thế axe, keyboard-only, screen reader hoặc contrast audit.

## 4. Microphone, Gemini và kiểm soát thất bại

- Không gọi Gemini/TTS thật; không phát sinh usage/cost bên ngoài.
- Fake microphone stream trong Chrome tạo 1 audio track trạng thái `live`, sau đó track được stop.
- Writing/Speaking/TTS khi thiếu provider trả lỗi kiểm soát; draft được giữ và Speaking không bị ghi hoàn thành.
- Backend quota/timeout/session limits tiếp tục được kiểm tra bằng unit/integration test hiện có.
- **Chưa PASS**: microphone vật lý allow/deny/revoke, playback âm thanh thực, browser speech fallback nghe được, Gemini Speaking response thật, Gemini Live audio round-trip, provider quota/network timeout thật. Các mục này cần key/budget và thao tác phần cứng được chủ dự án phê duyệt.

## 5. Security review tự thực hiện

Đây là self-review bằng Codex, **không phải security review độc lập hay chứng nhận an toàn tuyệt đối**.

Regression test mới/được mở rộng:

- session fixation: cookie do attacker đặt bị thay bằng token mới;
- logout revocation: replay token cũ trả 401;
- brute-force: đổi `X-Forwarded-For` không bypass rate limit khi proxy header chưa được trust;
- IDOR Speaking: tài khoản khác không evaluate được session;
- IDOR Writing/usage/progress đã có test tách tài khoản;
- CSRF, Origin, cookie flags, SQL injection input, security headers, AI account quota và concurrency tiếp tục PASS;
- browser stored-XSS payload không được render thành `<img>` và không chạy handler.

Rủi ro còn mở: chưa có pentest độc lập, SAST/DAST và dependency CVE scan; CSP vẫn cần inline style hiện tại; chưa kiểm tra cấu hình reverse proxy thật; chưa có MFA/email verification/password reset/WAF/CAPTCHA; shared rate limiting nhiều app instance chưa được thử; privacy/log-retention/incident response vẫn cần owner.

## 6. Test và benchmark

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ pytest | **45 passed**, 0 failed, 1 deprecation warning |
| Security + skills + DB targeted | **17 passed** |
| Grammar automated QA | 100 lesson, 200 example, 1.000 exercise; 0 structural failure; `human_reviewed=0` |
| `node --check static/app.js` | PASS |
| `py_compile` app/adapter/security/tools/E2E | PASS |
| `pip check` | PASS, không có dependency hỏng |
| SQLite integrity/FK | PASS: `ok`, 0 lỗi |
| PostgreSQL migration/restore | PASS trên local QA copy |
| Docker Compose config | PASS |
| Docker runtime | NOT RUN — daemon unavailable |
| Browser E2E | **15/15 PASS** |

Benchmark trên PostgreSQL restore local, chỉ phản ánh máy phát triển:

| Scenario | Request / concurrency | p50 | p95 | Max | Error | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Public read mix | 500 / 20 | 276,08 ms | 526,13 ms | 621,60 ms | 0% | 71,05 req/s |
| Account read/write mix | 200 / 8 | 261,93 ms | 407,51 ms | 494,08 ms | 0% | 30,87 req/s |

Không dùng số này để tuyên bố capacity production. Bằng chứng: `qa_artifacts/stage6_benchmark.json`.

## 7. Cách chạy lại

```powershell
pip install -r requirements-dev.txt
pip install -r requirements-e2e.txt
python -m pytest -q
python -m uvicorn app:app --host 127.0.0.1 --port 8000
python e2e/run_stage6.py --base-url http://127.0.0.1:8000 --output-dir qa_artifacts
```

Migration PostgreSQL chỉ chạy với database đích rỗng hoặc bản sao được phép:

```powershell
python tools/migrate_to_postgres.py --source speakseed.db --target-url $env:STAGING_DATABASE_URL --apply
python tools/verify_postgres_migration.py --source speakseed.db --target-url $env:STAGING_DATABASE_URL
```

Backup/restore nên dùng database QA mới, không restore đè production. Sau restore:

```powershell
python tools/verify_postgres_restore.py --source $env:SOURCE_DATABASE_URL --restored $env:RESTORED_DATABASE_URL
```

## 8. Checklist Go/No-Go beta công khai

- [x] SQLite gốc còn nguyên, integrity/FK/count được đối chiếu.
- [x] PostgreSQL adapter và migration chạy end-to-end trên bản sao local QA.
- [x] Digest tất cả bảng, FK và index được kiểm tra.
- [x] PostgreSQL backup/restore và application smoke trên restore PASS.
- [x] Rollback cấu hình về SQLite và application smoke PASS.
- [x] Full pytest PASS.
- [x] Browser E2E desktop/mobile trên Chrome PASS.
- [x] Session/CSRF/XSS/IDOR/rate-limit regression PASS trong phạm vi self-review.
- [ ] Chạy lại migration/restore trên PostgreSQL staging chính thức có credential và backup policy.
- [ ] Docker build/Compose lifecycle/health/persistence PASS trên daemon thực.
- [ ] HTTPS, reverse proxy, production host/origin/secret store và secure cookie được xác nhận trên môi trường deploy.
- [ ] Gemini Speaking/Live/TTS/Writing smoke thật với budget nhỏ, quota alert và key staging.
- [ ] Microphone vật lý và audio playback được thử trên Chrome/Edge/Safari mục tiêu, gồm deny/revoke/network loss.
- [ ] Accessibility audit bằng axe + keyboard + screen reader + contrast.
- [ ] Load test trên hạ tầng staging với SLO và tải dự kiến.
- [ ] Security review độc lập, dependency vulnerability scan và pentest có biên bản.
- [ ] Monitoring/alert/on-call, backup schedule, restore drill định kỳ và rollback release có owner.
- [ ] Privacy policy, terms, export/delete account, retention và incident-response process được duyệt.
- [ ] Human review nội dung ưu tiên B1–B2 được ghi nhận bằng bằng chứng; hiện vẫn `automated_checked`.

**Quyết định hiện tại: NO-GO cho public beta; phù hợp tiếp tục QA nội bộ có kiểm soát.**
