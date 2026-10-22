# Triển khai beta SpeakSeed

## Điều kiện bắt buộc

- Python 3.11+ hoặc Docker; tên miền HTTPS và reverse proxy do người vận hành quản lý.
- `APP_SECRET` ngẫu nhiên ít nhất 32 ký tự, `ALLOWED_ORIGINS` là origin HTTPS chính xác và `ALLOWED_HOSTS` là hostname công khai.
- Nếu tin cậy proxy header, `TRUSTED_PROXY_IPS` phải chỉ chứa IP/CIDR của reverse proxy trực tiếp; không đặt `0.0.0.0/0` hoặc `::/0`.
- Gemini/Azure key chỉ đặt trong secret/environment của backend. Không commit `.env`.
- Chạy toàn bộ test, backup được xác minh và hoàn thành checklist trong `STAGE5_REPORT.md` trước khi mở truy cập.

Tạo secret ví dụ: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Sao chép `.env.example` thành `.env`, thay toàn bộ placeholder, đặt `APP_ENV=production`, `COOKIE_SECURE=true`. Chỉ bật `TRUST_PROXY_HEADERS=true` khi cổng ứng dụng chỉ nhận lưu lượng từ reverse proxy tin cậy.

## Chạy Python trực tiếp

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest -q
uvicorn app:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Reverse proxy phải kết thúc TLS, chuyển `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`, hỗ trợ WebSocket tại `/ws/speaking/live`, đặt giới hạn request body và timeout dài hơn giới hạn Live. Không công khai trực tiếp cổng Uvicorn.

Health checks:

- `/api/health/live`: process đang trả lời.
- `/api/health/ready`: database truy cập được, đủ migration và đúng 4.213 từ xuất bản.

## Docker Compose

`docker-compose.yml` bind cổng vào loopback và dùng volume bền vững. Image tạo `seed.db` chỉ chứa nội dung xuất bản; lần đầu volume rỗng sẽ được khởi tạo với 4.213 từ, 100 lesson và 1.000 bài tập. Seed không chứa tài khoản và không ghi đè database đã có.

```powershell
$env:APP_SECRET='replace-with-a-random-48-byte-secret'
$env:ALLOWED_ORIGINS='https://beta.example.com'
$env:ALLOWED_HOSTS='beta.example.com'
$env:GEMINI_API_KEY='server-side-key'
python tools/prepare_docker_seed.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

`prepare_docker_seed.py` tạo `.docker-build/seed.db` bằng phép SQLite backup rồi xóa toàn bộ tài khoản/tiến độ. `speakseed.db` gốc bị loại khỏi Docker build context và không nằm trong image layer. Chạy lại bước này trước mỗi build cần cập nhật nội dung xuất bản.

## HTTPS staging cục bộ với PostgreSQL

`docker-compose.staging.yml` là stack độc lập gồm PostgreSQL, ứng dụng và Caddy TLS nội bộ. Cổng HTTPS và cổng bảo trì PostgreSQL chỉ bind loopback theo mặc định, nên máy khác không thể truy cập nếu người vận hành chưa chủ động đổi sang IP VPN riêng. Không đổi sang `0.0.0.0` cho beta hạn chế.

```powershell
Copy-Item deploy/staging/.env.staging.example .env.staging
# Thay APP_SECRET và POSTGRES_PASSWORD trong file không commit này.
python tools/prepare_docker_seed.py
docker compose --env-file .env.staging -f docker-compose.staging.yml config --quiet
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d postgres
$env:STAGING_DATABASE_URL='postgresql://speakseed:REPLACE@127.0.0.1:5433/speakseed'
python tools/migrate_to_postgres.py --source speakseed.db --target-url $env:STAGING_DATABASE_URL --apply
python tools/verify_postgres_migration.py --source speakseed.db --target-url $env:STAGING_DATABASE_URL
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d --build web proxy
curl.exe --cacert .\path\to\exported-caddy-root.crt https://localhost:8443/api/health/ready
```

Caddy dùng CA nội bộ cho staging; chỉ cài CA root trên thiết bị QA được quản lý. Không bỏ qua xác minh TLS trong kiểm thử Go/No-Go. Trước khi tạo lại volume PostgreSQL, phải có backup đã verify. Dừng stack bằng `docker compose --env-file .env.staging -f docker-compose.staging.yml down` và không thêm `-v` trừ khi đang hủy môi trường disposable có phê duyệt rõ ràng.

## Backup và restore SQLite

Tạo hot backup có checksum, count từng bảng, integrity và foreign-key validation:

```powershell
python tools/db_backup.py create speakseed.db backups/speakseed-YYYYMMDD.db
```

Restore luôn tạo file mới và từ chối ghi đè:

```powershell
python tools/db_backup.py restore backups/speakseed-YYYYMMDD.db restore-candidate.db
```

Sau đó dừng ứng dụng, giữ nguyên database hiện hành, trỏ `DB_PATH` đến `restore-candidate.db`, chạy `/api/health/ready` và smoke test bằng tài khoản nội bộ. Chỉ xóa bản cũ sau thời gian lưu giữ đã phê duyệt. Rollback là dừng release mới, trỏ lại image/config và database backup trước release; không dùng `git reset` hay ghi đè file DB đang chạy.

## Chuyển SQLite sang PostgreSQL

Mặc định công cụ chỉ lập kế hoạch đọc-only:

```powershell
python tools/migrate_to_postgres.py --source speakseed.db --plan-json postgres-plan.json
```

`--apply` chỉ chấp nhận PostgreSQL đích trống, sao chép trong transaction, tạo PK/FK/unique/index, cập nhật identity sequence và so sánh count mọi bảng. SQLite nguồn không bị xóa hay đổi cấu hình:

```powershell
python tools/migrate_to_postgres.py --source speakseed.db --target-url "$env:TARGET_DATABASE_URL" --apply
```

Sau khi kiểm tra độc lập count, liên kết, đăng nhập và tiến độ trên staging, mới đặt `DATABASE_URL` cho một release canary. Giữ SQLite gốc để rollback. Lần kiểm toán này mới xác nhận plan trên 35 bảng/20.825 dòng/33 FK; chưa chạy `--apply` vì không có PostgreSQL đích được cấp phép.

Ứng dụng dùng adapter DB-API hỗ trợ SQLite/psycopg. Chưa chuyển sang SQLAlchemy/Alembic: mã hiện có có nhiều truy vấn SQL đã được kiểm thử và một lần thay toàn bộ ORM trước beta làm tăng rủi ro dữ liệu. Migration SQL có version vẫn là nguồn schema chính trong giai đoạn này.

## Vận hành và chi phí AI

- Xem usage 30 ngày của tài khoản qua `GET /api/usage`; cost là ước tính từ các biến đơn giá, không thay thế hóa đơn provider.
- Rate limit được lưu trong DB theo tài khoản/IP. Live mặc định tối đa 10 phút và 28 MB audio; Writing/Speaking có giới hạn payload và timeout. Gemini TTS đã bị vô hiệu hóa; bài học thường dùng Web Speech API phía trình duyệt.
- Cảnh báo theo tỷ lệ 429/5xx, p95 latency, dung lượng DB/volume, quota provider và tổng cost. Không log API key, token, CSRF token, audio hay nội dung bài viết.
- Chạy backup hàng ngày và diễn tập restore định kỳ trên host tách biệt.

