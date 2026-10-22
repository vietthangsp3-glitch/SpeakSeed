# SpeakSeed — Báo cáo Stage 7 Beta Release Candidate

Ngày kiểm tra: **2026-10-23** (Asia/Bangkok). Phạm vi: đóng blocker kỹ thuật trước beta; không thêm tính năng học tập, không triển khai công khai, không tạo dịch vụ trả phí và không gọi Gemini thật.

## Kết luận

**NO-GO cho public beta.** Mã ứng dụng, security regression và Chrome E2E trên dữ liệu QA đều PASS. Tuy nhiên Docker runtime, HTTPS/PostgreSQL staging thực, microphone vật lý, Gemini Live round-trip thật và independent security review chưa có bằng chứng nên vẫn BLOCKED. Không có nội dung nào được gắn `human_reviewed` trong Stage 7.

Database chính sau kiểm tra: `integrity_check=ok`, **0** foreign-key violation, **4.213** từ xuất bản, **100** grammar lesson xuất bản, **1.000** grammar exercise xuất bản và **0** tài khoản. Không có test trình duyệt nào ghi vào database chính.

## 1. Ma trận PASS / FAIL / BLOCKED

| Điều kiện | Trạng thái | Bằng chứng thực tế |
|---|---|---|
| Docker CLI 29.8.2 và Compose 5.6.0 | PASS | Hai lệnh version chạy được |
| Docker daemon | FAIL | `com.docker.service` đang `Stopped`; Docker API pipe không tồn tại |
| Parse `docker-compose.yml` | PASS | `docker compose ... config --quiet` exit 0 |
| Parse `docker-compose.staging.yml` | PASS | `docker compose ... config --quiet` exit 0 |
| Build/start/stop/restart/health/log Docker | BLOCKED | Daemon không chạy; không suy diễn PASS từ kiểm tra tĩnh |
| Persistence khi recreate container | BLOCKED | Chưa có container runtime để thử; không dùng `down -v` |
| Docker seed không chứa tài khoản | PASS | Seed tạo lặp lại được; 0 user, 4.213/100/1.000; FK sạch |
| PostgreSQL + HTTPS staging config | PASS | Stack Caddy TLS nội bộ + PostgreSQL + web đã được cấu hình; mặc định chỉ bind `127.0.0.1` |
| PostgreSQL staging migration/verify/rollback hiện tại | BLOCKED | Không có PostgreSQL staging được cấp phép/running trong lần này |
| HTTPS handshake, certificate trust, secure cookie qua proxy thật | BLOCKED | Daemon/proxy chưa chạy; unit regression cho Secure/HSTS/CORS/host đã PASS nhưng không thay thế runtime |
| Pytest đầy đủ | PASS | **53 passed**, 1 deprecation warning, 28,77 giây |
| Chrome desktop/mobile E2E | PASS | **15/15**, Chrome cài trên máy, 1440×900 và 390×844, 0 page error |
| Web Speech regression | PASS | **9/9**, 3 voice tiếng Anh, 0 request `/api/tts` từ UI |
| Microphone giả trong Chrome | PASS | 1 audio track `live`, track được stop sau kiểm thử |
| Microphone vật lý allow/deny/revoke | BLOCKED | Work settings trả về “Local browser use is disabled”; không có quyền điều khiển thiết bị thật |
| Gemini Live fake-upstream integration | PASS | Audio modality, close, quota-before-provider và network-failure metering đều PASS |
| Gemini Live thật | BLOCKED | Không có `.env`/Gemini key và chưa có phê duyệt chi phí; 0 provider call |
| Security self-audit | PASS có giới hạn | Regression auth/authz/CSRF/CORS/host/XSS/IDOR/rate/quota/session đã chạy; 2 lỗi xác minh đã sửa |
| Independent security review | BLOCKED | Chưa có người/đơn vị độc lập; không tuyên bố đã pentest độc lập |

## 2. Thay đổi Stage 7

### Docker và bảo toàn dữ liệu

- Sửa image build để **không COPY database đang hoạt động**. Trước đây `speakseed.db` có thể đi vào build context/layer trước khi seed được làm sạch.
- Thêm `tools/prepare_docker_seed.py`: tạo atomically `.docker-build/seed.db`, xóa dữ liệu tài khoản nhờ foreign-key cascade, kiểm tra đúng số nội dung và cho phép chạy lại.
- Dockerfile chỉ copy các source/runtime file được liệt kê và seed đã làm sạch. `.dockerignore` không còn re-include `speakseed.db`.
- Thêm 2 regression test: seed idempotent/không có account data và runtime image không copy live database.

### HTTPS staging

- Thêm `docker-compose.staging.yml`: PostgreSQL 16, web production-mode và Caddy 2.10 TLS nội bộ.
- HTTPS `8443` và PostgreSQL maintenance `5433` bind `127.0.0.1` mặc định. Muốn cho nhóm QA truy cập phải dùng IP VPN riêng đã phê duyệt; không bind public.
- `deploy/staging/Caddyfile` hỗ trợ WebSocket Gemini Live, ép `X-Forwarded-Proto=https`, ghi đè `X-Forwarded-For`, HSTS và timeout 11 phút.
- `deploy/staging/.env.staging.example` chỉ chứa placeholder; key Gemini để trống mặc định.

### Security self-audit

Phát hiện **2 lỗi có thể xác minh**, đã sửa **2**, còn **0 lỗi xác minh chưa sửa** trong phạm vi thay đổi Stage 7:

1. **High — database gốc trong Docker build layer/cache:** đã tách content-only seed khỏi live DB.
2. **Medium — rate-limit có thể tin `X-Forwarded-For` quá rộng khi bật proxy mode:** giờ chỉ nhận forwarding header nếu direct peer nằm trong `TRUSTED_PROXY_IPS`; giá trị malformed bị bỏ qua.

Regression mới xác nhận Secure/SameSite/HttpOnly cookie, HSTS production, CORS preflight, trusted host, proxy spoofing, Gemini Live account quota trước provider và network failure không tạo learning event. Các regression sẵn có tiếp tục kiểm tra session rotation/revoke, CSRF, origin, stored-XSS smoke, SQL injection input, IDOR/account scoping, brute-force và legacy Gemini TTS 410.

Rủi ro còn mở: CSP vẫn cần `'unsafe-inline'` cho style hiện tại; chưa có MFA/email verification/password reset; chưa chạy dependency CVE scanner/SAST/DAST; chưa có WAF/CAPTCHA; chưa thử cấu hình proxy/TLS thật; chính sách privacy, log retention và incident response cần product owner duyệt. `pip check` PASS nhưng không phải CVE audit.

## 3. Beta QA

E2E dùng database riêng `qa_artifacts/stage7_e2e.db`, key Gemini bị xóa khỏi environment:

- đăng ký, cookie và stored-XSS smoke;
- CSRF thiếu token 403/token đúng 200;
- placement 25 câu, vocabulary SRS, grammar;
- Listening, Reading và lưu từ;
- Writing provider failure giữ draft;
- Speaking provider failure không ghi hoàn thành;
- legacy TTS trả 410;
- fake microphone và Live guard;
- reload giữ session/progress, logout/login rotate session;
- mobile không horizontal overflow và không có button rỗng.

Console observation dự kiến gồm font mạng bị môi trường chặn, favicon 404, `/api/me` 401 trước login, CSRF 403 chủ động, AI 503 do key bị tắt và TTS 410. Không có JavaScript `pageerror`. Accessibility chỉ là smoke check, chưa thay thế keyboard-only, screen reader, axe hoặc contrast audit.

Web Speech E2E xác nhận Vocabulary, Dictation, Grammar, Listening, Reading và Speaking text playback dùng `speechSynthesis`; voice/rate/stop/replay, danh sách voice rỗng và browser không hỗ trợ đều không fallback Gemini. Gemini Live không mở WebSocket trước confirm.

Biểu mẫu beta: `BETA_FEEDBACK_TEMPLATE.md`, có severity, bước tái hiện, môi trường, Request ID, kiểm tra persistence và cảnh báo không gửi secret/PII.

## 4. Gemini và microphone

- **Không gọi Gemini thật:** máy không có `.env`/key và không có phê duyệt phát sinh quota.
- Fake-upstream test xác nhận Live dùng audio response, đóng upstream, quota 10 phiên/giờ/tài khoản chặn trước connect, network failure được ghi `failed` và không tạo thành tích học.
- Giới hạn Live giữ mặc định 600 giây/28 MB, có clamp server-side; UI chỉ connect sau thao tác Start + confirm, và disconnect khi end/pagehide/beforeunload/error.
- Gemini TTS vẫn hard-disabled ở backend. Audio cache cũ không bị xóa.
- Gemini quota còn được dùng khi người dùng chủ động gọi Tutor, Speaking turn/evaluation, Writing feedback hoặc Gemini Live. Browser speech không dùng Gemini quota.

## 5. Việc người vận hành phải làm thủ công

1. Khởi động Docker Desktop/daemon và sửa quyền đọc `C:\Users\Thang Nguyen\.docker\config.json`; xác nhận `docker version` có cả Client và Server.
2. Tạo `.env.staging` từ file mẫu, dùng secret mạnh; không commit file này.
3. Chạy `python tools/prepare_docker_seed.py`, build stack, kiểm tra image history không có live DB.
4. Migrate **bản sao** SQLite vào PostgreSQL staging, chạy verifier, login/progress smoke và backup/restore/rollback; giữ nguyên SQLite gốc.
5. Chạy start/stop/restart/recreate container không `-v`; đối chiếu count, tài khoản và tiến độ trước/sau.
6. Export CA root của Caddy, cài trên thiết bị QA được quản lý, kiểm tra TLS/certificate/secure cookies/WebSocket qua `https://localhost:8443` hoặc VPN hostname.
7. Bật quyền điều khiển browser và dùng thiết bị thật để kiểm tra microphone allow/deny/revoke, unplug/network loss và không hoàn thành bài khi thất bại.
8. Chỉ sau phê duyệt ngân sách, cấu hình key staging và thực hiện **một** Gemini Live round-trip ngắn; kiểm tra usage/quota/timeout/disconnect, không chạy hàng loạt.
9. Thuê/nhờ reviewer độc lập kiểm tra security; xử lý phát hiện trước khi mở public beta.

Lệnh chi tiết cho Docker/PostgreSQL/HTTPS, backup, restore và rollback nằm trong `DEPLOYMENT.md`. Không triển khai công khai cho tới khi các mục BLOCKED quan trọng có bằng chứng PASS.

## 6. Go/No-Go checklist

- [x] 53/53 pytest PASS.
- [x] Desktop/mobile browser E2E và bốn kỹ năng PASS trong phạm vi provider-offline.
- [x] Browser speech không gọi Gemini TTS.
- [x] Live/quota/network security regression PASS với fake upstream.
- [x] Docker seed đã tách khỏi live account/progress data.
- [x] Compose production/staging parse PASS.
- [ ] Docker build/runtime/health/restart/persistence PASS.
- [ ] PostgreSQL staging migration + verify + backup/restore/rollback PASS trên môi trường được cấp phép.
- [ ] HTTPS proxy/certificate/cookie/WebSocket PASS runtime.
- [ ] Microphone vật lý desktop/mobile PASS.
- [ ] Gemini Live thật smoke PASS với quota nhỏ được phê duyệt.
- [ ] Independent security review hoàn tất và blocker được xử lý.
- [ ] Owner phê duyệt privacy/log retention/incident response và danh sách người được truy cập staging.

**Quyết định hiện tại: NO-GO.**
