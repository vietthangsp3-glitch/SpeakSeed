# SpeakSeed: SQLite → Neon PostgreSQL

Quy trình này là thao tác một lần, chạy thủ công từ Windows PowerShell. Ứng dụng Vercel **không** tự tạo hoặc tự migration schema khi cold start.

## Điều kiện trước khi chạy

- Chạy trong thư mục gốc SpeakSeed có `speakseed.db`.
- Neon target phải là branch/database staging trống. Nếu đã có bất kỳ bảng nào trong schema `public`, importer sẽ dừng trước khi tạo bảng; không xóa bảng để cố chạy lại.
- Dùng Neon **direct connection string** cho thao tác migration một lần. Vercel runtime tiếp tục dùng **pooled connection string** (`-pooler` trong hostname).
- Không lưu connection string vào Git, command line hoặc ảnh chụp màn hình.

## 1. Chuẩn bị môi trường và backup

```powershell
Set-Location -LiteralPath 'E:\app\THANG\luyện tiếng anh\speakseed-learning-v3\speakseed-learning-v3'
python -m pip install -r .\requirements.txt

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = ".\backups\pre-neon-$stamp.db"
python -X utf8 .\tools\db_backup.py create .\speakseed.db $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup SQLite thất bại; không tiếp tục.' }
```

Backup dùng SQLite online backup API, kiểm tra integrity/foreign key/count và không sửa nguồn.

## 2. Chạy preflight local, chưa kết nối Neon

```powershell
python -X utf8 .\tools\migrate_to_postgres.py `
  --source .\speakseed.db `
  --plan-json .\qa_artifacts\neon-migration-plan.json
if ($LASTEXITCODE -ne 0) { throw 'Preflight SQLite thất bại; không tiếp tục.' }
```

Kết quả đúng của bản hiện tại phải chứa:

```text
"tables": 35
"latest_schema_version": "008_beta_hardening.sql"
"published_words": 4213
"published_grammar_lessons": 100
"published_grammar_exercises": 1000
```

## 3. Nạp Neon direct URL vào process hiện tại

Đoạn dưới hoạt động trên Windows PowerShell 5.1 và PowerShell 7; ký tự nhập không hiển thị:

```powershell
$secureUrl = Read-Host 'Dán Neon DIRECT connection string' -AsSecureString
$urlPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
try {
  $env:DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($urlPointer)
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($urlPointer)
}
```

Connection string phải bắt đầu bằng `postgresql://` hoặc `postgres://` và bật TLS theo giá trị Neon cung cấp.

## 4. Xác nhận target trống — chỉ đọc

```powershell
python -c "import os, psycopg; c=psycopg.connect(os.environ['DATABASE_URL']); n=c.execute(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'\").fetchone()[0]; c.close(); print('public_tables=', n); raise SystemExit(0 if n == 0 else 2)"
if ($LASTEXITCODE -ne 0) { throw 'Neon target không trống. Dừng lại và tạo branch/database staging mới; không xóa dữ liệu hiện có.' }
```

## 5. Apply migration — bước duy nhất ghi vào Neon

Chỉ chạy sau khi đã kiểm tra URL/branch và chủ động xác nhận muốn ghi:

```powershell
python -X utf8 .\tools\migrate_to_postgres.py --source .\speakseed.db --apply
if ($LASTEXITCODE -ne 0) { throw 'Migration thất bại. Không thay đổi SQLite nguồn; kiểm tra log trước khi thử lại.' }
```

Importer tự kiểm tra target trống lần nữa, tạo/copy đủ bảng, foreign key và index trong một PostgreSQL transaction, kiểm tra count từng bảng rồi commit. Lỗi trước commit sẽ rollback transaction. SQLite được mở `mode=ro`.

## 6. Xác minh toàn bộ dữ liệu

```powershell
python -X utf8 .\tools\verify_postgres_migration.py `
  --source .\speakseed.db `
  --output .\qa_artifacts\neon-migration-verification.json
if ($LASTEXITCODE -ne 0) { throw 'Đối chiếu PostgreSQL thất bại; chưa chuyển Vercel sang database này.' }
```

Kết quả đạt yêu cầu:

```text
"ok": true
"tables": 35
"latest_schema_version": "008_beta_hardening.sql"
"published_content": {
  "published_words": 4213,
  "published_grammar_lessons": 100,
  "published_grammar_exercises": 1000
}
```

Verifier so sánh tập bảng, count và SHA-256 nội dung từng bảng, số foreign key, index, version và ba số lượng nội dung xuất bản. Bảng `schema_migrations` phải có đủ tám version từ `001_initial.sql` đến `008_beta_hardening.sql`.

## 7. Dọn secret khỏi process local

```powershell
Remove-Item Env:DATABASE_URL
$secureUrl = $null
```

Đóng cửa sổ PowerShell sau khi hoàn tất.

## 8. Kiểm tra Vercel

- `DATABASE_URL` trên Vercel phải là Neon **pooled URL** trỏ đúng branch/database vừa migration.
- Không đặt direct URL vào frontend hoặc Git.
- Redeploy preview hoặc tạo deployment mới để environment variables được áp dụng.
- Kiểm tra:

```powershell
$preview = 'https://<your-preview-domain>'
Invoke-RestMethod "$preview/api/health/ready"
```

Kết quả mong đợi:

```text
status            ready
database          True
schema_migrations 8
published_words   4213
```

Sau đó mới chạy browser E2E và kiểm tra đăng ký/đăng nhập/lưu tiến độ qua một lần redeploy preview.

