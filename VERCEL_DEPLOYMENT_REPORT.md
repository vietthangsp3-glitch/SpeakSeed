# SpeakSeed — Vercel Preview Deployment Report

Ngày kiểm tra: 2026-10-23  
Phạm vi: chuẩn bị preview nội bộ cho 2–3 người học A0–A1; **không triển khai production, không tạo dịch vụ trả phí**.

## Kết luận

**NO-GO cho deployment thực tế ở thời điểm lập báo cáo.** Mã local đã được chuẩn bị và kiểm thử, nhưng repository GitHub đang trống, thư mục local không có `.git`, chưa có PostgreSQL staging được cấp phép và chưa có Vercel preview URL. Vì vậy không có cơ sở để tuyên bố deploy thành công hoặc dữ liệu tồn tại qua redeploy.

| Hạng mục | Trạng thái | Bằng chứng / blocker |
|---|---|---|
| FastAPI entrypoint `app.py` | PASS | Export `app = FastAPI(...)`; phù hợp cơ chế nhận diện FastAPI hiện hành của Vercel. |
| Dependencies và static assets | PASS | `requirements.txt`, Python 3.12, `/static` và `/` chạy local; không thêm routing `vercel.json` kiểu cũ. |
| Code đã push GitHub | **FAIL** | Trang `github.com/vietthangsp3-glitch/SpeakSeed` báo repository trống; local không có `.git`. |
| Secret scan working tree | PASS có giới hạn | Không thấy Google API key/private key thực. Các URL có password chỉ là placeholder/test. Không thể kiểm tra lịch sử commit vì không có Git history local và remote trống. |
| Loại DB/.env khỏi deployment | PASS | `.gitignore` và `.vercelignore` loại `.env*`, `*.db`, WAL/SHM, cache và QA artifacts. Đã bỏ ngoại lệ từng cho phép `speakseed.db`. |
| Không dùng SQLite trên Vercel | PASS | Runtime từ chối khởi động khi `VERCEL=1` nhưng thiếu `DATABASE_URL`; không fallback xuống filesystem tạm. |
| PostgreSQL staging/migration | **BLOCKED** | Adapter và công cụ có sẵn; chưa có database URL/ủy quyền nên chưa chạy `--apply`, backup/restore hay redeploy-persistence test. |
| Cookie/CSRF/CORS/trusted host | PASS local | Cookie HttpOnly/SameSite, CSRF và host checks có regression test; `VERCEL_URL` được thêm tự động. Alias preview khác phải cấu hình rõ. |
| Rate limit nhiều instance | PASS về thiết kế, BLOCKED thực địa | Auth và AI usage/quota lưu trong PostgreSQL dùng chung; IP Vercel đọc từ platform header đã kiểm thử. Chưa load-test nhiều instance Vercel thật. |
| Gemini TTS | PASS | `/api/tts` bị khóa; bài học dùng Web Speech API. |
| Gemini Live mặc định tắt | PASS | Backend, WebSocket và UI đều yêu cầu `GEMINI_LIVE_ENABLED=true` **và** có key. Mặc định false. |
| Vercel build/preview URL | **BLOCKED** | Không có Vercel CLI/project/credentials và code chưa có trên GitHub. |
| E2E trên URL thật + PostgreSQL | **BLOCKED** | Chưa có URL/database staging. E2E local không thay thế kiểm thử preview. |

## Thay đổi đã thực hiện

- Thêm `.python-version` = `3.12`; giữ root `app.py`, không tạo `vercel.json` vì Vercel hỗ trợ FastAPI zero-config.
- Thêm `.vercelignore`; database, `.env`, cache, báo cáo QA và test artifacts không được upload.
- Bắt buộc PostgreSQL trên Vercel, nhưng vẫn giữ nguyên SQLite cho local; không sửa hoặc xóa SQLite gốc.
- Chuyển import bộ công cụ seed SQLite sang nhánh local để giảm phụ thuộc runtime Vercel. PostgreSQL production chỉ kiểm tra schema, không tự migration khi cold start.
- Tự thêm origin/host của `VERCEL_URL`; vẫn giữ allowlist rõ ràng, không dùng wildcard CORS với cookie.
- Dùng `x-vercel-forwarded-for` chỉ khi platform đặt `VERCEL=1`, phục vụ quota/rate limit theo IP qua nhiều instance.
- Thêm `/api/runtime-config` không chứa secret. Gemini Live mặc định tắt ở frontend và backend; session mặc định 240 giây để có khoảng đệm dưới giới hạn Function Hobby 300 giây nếu sau này được bật và kiểm thử.
- Không tạo cache audio trên filesystem Vercel. Cache local cũ không bị xóa.
- Sửa luồng A0: dùng trực tiếp bộ từ A1 đã kiểm định khi học vocabulary, không nhân bản hoặc thay đổi ngân hàng từ.
- Công cụ PostgreSQL nhận `DATABASE_URL` từ environment, tránh phải đưa mật khẩu vào command line.

## Dữ liệu đã xác minh tại local

Truy vấn trực tiếp `speakseed.db`:

| Dữ liệu | Số lượng |
|---|---:|
| Từ đã xuất bản (`reviewed=1`) | **4.213** |
| Tổng hàng `library_words` | 4.216 |
| Grammar units | 20 |
| Grammar lessons | **100** |
| Grammar exercises | **1.000** |
| Skill lessons | 60 |
| Skill questions | 90 |
| Tài khoản hiện có trong bản local | 0 |

`PRAGMA integrity_check = ok`; `PRAGMA foreign_key_check = 0 lỗi`. Toàn bộ 100 grammar lesson có nhãn `automated_checked`; không có tuyên bố `human_reviewed`.

Migration plan ở chế độ read-only xác định **35 bảng, 20.825 hàng và 33 foreign key definitions**. Chưa áp dụng lên PostgreSQL bên ngoài.

## Kết quả kiểm thử

- `python -m pytest -q`: **61 passed**, 1 cảnh báo deprecation từ FastAPI/Starlette TestClient, 0 failed.
- `node --check static/app.js`: PASS.
- Mobile beginner smoke local 390×844: **6/6 PASS** — onboarding, đăng ký, daily plan A0, hoạt động từ đầu tiên, session/progress sau reload và 0 AI request tự động.
- Secret pattern scan: không thấy key Google/private key; bốn match URL PostgreSQL là placeholder trong `.env.example`, tài liệu, Compose và test.
- Lần E2E đầu phát hiện A0 không có flashcard do dữ liệu CEFR bắt đầu ở A1; đã sửa bằng fallback A0 → nội dung A1 và chạy lại PASS.

Các kiểm thử **chưa chạy**: Vercel build, cold start, URL preview HTTPS, Deployment Protection, PostgreSQL thật, persistence qua redeploy, backup/restore PostgreSQL, Gemini Live thật, microphone trên URL preview, tải nhiều serverless instances.

## Environment variables

Chỉ cấu hình cho môi trường **Preview** trước. Không ghi giá trị bí mật vào Git.

### Bắt buộc

| Tên | Giá trị/ý nghĩa |
|---|---|
| `DATABASE_URL` | URL PostgreSQL **pooled/serverless** của nhà cung cấp, có TLS; database staging trống khi migration lần đầu. |
| `APP_ENV` | `production` |
| `APP_SECRET` | Chuỗi ngẫu nhiên bí mật tối thiểu 32 ký tự. |
| `AUTH_TRANSPORT` | `cookie` |
| `COOKIE_SECURE` | `true` |
| `GEMINI_LIVE_ENABLED` | `false` cho preview ban đầu. |

### Theo hostname preview

| Tên | Giá trị/ý nghĩa |
|---|---|
| `PRIMARY_HOST` | `speak-seed.vercel.app`; hostname production chính xác, không có protocol/path. |
| `ALLOWED_ORIGINS` | Các origin bổ sung nếu có; `PRIMARY_HOST` và hostname Vercel được code tự thêm dưới dạng HTTPS. |
| `ALLOWED_HOSTS` | Các alias bổ sung, phân cách bằng dấu phẩy; không có protocol/path và tuyệt đối không dùng `*`. |

`VERCEL`, `VERCEL_URL`, `VERCEL_BRANCH_URL` và `VERCEL_PROJECT_PRODUCTION_URL` là system variables của Vercel, không tự tạo. Ba hostname Vercel này được code tự thêm vào allowlist. `PRIMARY_HOST` nên được đặt rõ ràng cho production domain.

### AI tùy chọn

| Tên | Ghi chú |
|---|---|
| `GEMINI_API_KEY` | Server-only. Để trống thì Tutor/Writing/Speaking AI trả thông báo cấu hình thiếu; bài thường vẫn hoạt động. |
| `GEMINI_API_KEYS` | Tùy chọn danh sách project động (`label=key,...` hoặc JSON); server-only, không có biến đánh số. |
| `GEMINI_FAILOVER_MAX_ATTEMPTS` | Số project tối đa thử cho một request; mặc định `2`, giới hạn an toàn `1–10`. |
| `GEMINI_PROJECT_QUOTA_COOLDOWN_SECONDS` | Cooldown sau HTTP 429; mặc định `3600`. |
| `GEMINI_PROJECT_ERROR_COOLDOWN_SECONDS` | Cooldown ngắn cho lỗi provider có thể thử lại; mặc định `30`. |
| `GEMINI_PROJECT_AUTH_COOLDOWN_SECONDS` | Cooldown cho key bị từ chối 401/403; mặc định `86400`. |
| `GEMINI_TEXT_MODEL` | Model text được phép dùng. |
| `GEMINI_LIVE_MODEL` | Chỉ có tác dụng khi Live được bật thủ công. |
| `GEMINI_LIVE_MAX_SECONDS` | Khuyến nghị `240` trên Hobby. |
| `GEMINI_LIVE_MAX_AUDIO_BYTES` | Giới hạn audio mỗi phiên. |
| `GEMINI_INPUT_USD_PER_MILLION`, `GEMINI_OUTPUT_USD_PER_MILLION` | Đơn giá để ước tính usage; 0 nghĩa là chưa cấu hình, không có nghĩa miễn phí. |

`AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` chỉ cần nếu chủ động dùng chấm phát âm Azure. Không đặt `DB_PATH` hay `TTS_CACHE_DIR` trên Vercel.

## Quy trình PostgreSQL staging — chỉ chạy sau khi cho phép

1. Tạo database staging bên ngoài bằng gói miễn phí đã chọn; dùng pooled/serverless connection URL và TLS. Vercel Postgres cũ không còn được cung cấp trực tiếp, nên phải chọn integration/provider bên ngoài.
2. Tạo backup SQLite đã kiểm tra, không xóa nguồn:

   ```powershell
   python -X utf8 tools/db_backup.py create speakseed.db backups/pre-vercel.db
   ```

3. Đặt URL trong biến process hiện tại để không lộ trong command history, rồi chạy plan trước:

   ```powershell
   $env:DATABASE_URL='<pooled PostgreSQL staging URL>'
   python -X utf8 tools/migrate_to_postgres.py --source speakseed.db
   ```

4. Chỉ sau khi xác nhận target trống và được phép ghi:

   ```powershell
   python -X utf8 tools/migrate_to_postgres.py --source speakseed.db --apply
   python -X utf8 tools/verify_postgres_migration.py --source speakseed.db --output qa_artifacts/vercel_postgres_verify.json
   ```

Importer từ chối target đã có bảng. Nó copy trong transaction, đối chiếu count và giữ nguyên SQLite nguồn. Sau migration phải kiểm tra lại 4.213 published words, 100 lessons, 1.000 exercises, user/progress, FK/index và chạy backup/restore của chính provider.

## Đưa code lên GitHub an toàn

Remote hiện trống và local không có Git metadata. Chạy thủ công sau khi xem lại danh sách file:

```powershell
git init
git branch -M main
git remote add origin https://github.com/vietthangsp3-glitch/SpeakSeed.git
git add .
git status --short
git ls-files | Select-String -Pattern '\.env$|\.db($|-)|audio_cache|qa_artifacts|\.source-cache'
```

Lệnh `git ls-files` cuối phải không trả ra database/cache/secret. Sau đó mới commit và push:

```powershell
git commit -m "Prepare SpeakSeed Vercel preview"
git push -u origin main
```

Vì repo hiện trống, không có lịch sử từ xa để audit. Nếu sau này phát hiện secret từng được commit, phải revoke/rotate secret và làm sạch history; chỉ xóa file ở commit mới là chưa đủ.

## Tạo preview Vercel, không production

1. Đăng nhập Vercel bằng tài khoản Hobby; chưa chọn gói trả phí/integration trả phí.
2. Tạo/link project bằng Vercel CLI hoặc dashboard, nhưng **không chạy `vercel --prod` và không bấm production deploy**.
3. Trong Project → Settings → Environment Variables, nhập các biến trên với scope **Preview**.
4. Trong Security → Deployment Protection, bật Vercel Authentication cho preview/all deployments trước khi chia sẻ. Hobby giới hạn external access; Shareable Link có thể dùng cho nhóm nhỏ nhưng bất kỳ ai có link có thể chuyển tiếp link, nên phải thu hồi sau đợt test.
5. Tạo preview bằng CLI mặc định:

   ```powershell
   vercel link
   vercel --target=preview
   ```

6. Sau khi preview đầu hoạt động, có thể vào Project → Settings → Git để kết nối repository. Push nhánh không phải production branch để tạo preview. Không merge/deploy production khi chưa có xác nhận.
7. Ghi lại hostname thật, cập nhật `ALLOWED_ORIGINS`/`ALLOWED_HOSTS` nếu dùng branch alias, rồi redeploy preview.

Vercel hỗ trợ `app.py` FastAPI và `requirements.txt` theo zero-config; cấu hình routing cũ không cần thiết. Static mount hiện vẫn đi qua FastAPI vì app có middleware toàn cục — đúng chức năng nhưng chưa được CDN hóa riêng.

## Checklist kiểm thử URL thật

Chỉ đổi thành PASS khi có log/screenshot/response thực tế:

- [ ] Incognito bị chặn bởi Deployment Protection; 2–3 tester được cấp đúng quyền/link.
- [ ] `/api/health/live` trả 200 và `/api/health/ready` trả `ready`, 4.213 published words.
- [ ] Đăng ký, đăng nhập, logout; cookie có Secure/HttpOnly/SameSite; CSRF và host/origin sai bị chặn.
- [ ] Placement, vocabulary A0→A1, grammar, listening, reading, writing và dashboard hoạt động.
- [ ] Tiến độ còn nguyên sau reload và một preview redeploy.
- [ ] Tài khoản A không đọc/sửa được draft, progress hoặc session của tài khoản B.
- [ ] Bài thường chỉ dùng Web Speech API; Network log không có `/api/tts` hoặc Gemini call tự động.
- [ ] Tutor/Writing quota và lỗi hết quota không chặn bài thường.
- [ ] Gemini Live vẫn hiển thị disabled; chỉ test thật sau một xác nhận riêng, với tối đa một phiên ngắn.
- [ ] Microphone/TTS được kiểm tra trên ít nhất Chrome desktop và một thiết bị mobile thật.
- [ ] PostgreSQL backup/restore và đối chiếu digest/count hoàn tất.

## Giới hạn Vercel Hobby cần chấp nhận

- Function Python dùng Fluid Compute có thời lượng tối đa 300 giây trên Hobby; vì vậy Live 10 phút cũ không phù hợp. Cấu hình 240 giây chỉ là biện pháp phòng ngừa, chưa phải bằng chứng Live ổn định.
- WebSocket support hiện được tài liệu FastAPI/Vercel mới mô tả là khả dụng nhưng connection bị ràng buộc bởi function duration và instance; tài liệu Vercel cũ từng ghi không hỗ trợ. Vì chưa có API-key test trên preview, Live tiếp tục tắt.
- Quota Hobby có thể dừng/pause workload khi chạm giới hạn; runtime logs có thời gian lưu hạn chế. Không coi Hobby là production SLA.
- Vercel Authentication khả dụng trên Hobby, nhưng số external collaborator bị giới hạn; Shareable Link bảo vệ bằng tính bí mật của URL hơn là danh tính từng tester.
- PostgreSQL không nằm trên filesystem Vercel và không được tạo trong công việc này; độ sẵn sàng, backup, connection limits và chi phí thuộc provider được chọn.

## Nguồn Vercel chính thức

- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel Functions limits](https://vercel.com/docs/functions/limitations)
- [Fluid Compute](https://vercel.com/docs/fluid-compute)
- [Request headers](https://vercel.com/docs/headers/request-headers)
- [Deployment Protection](https://vercel.com/docs/deployment-protection)
- [Vercel Authentication](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication)
- [Sharing preview deployments](https://vercel.com/docs/deployments/sharing-deployments)
- [Environment variables](https://vercel.com/docs/environment-variables)

