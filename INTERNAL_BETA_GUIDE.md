# Chạy SpeakSeed cho 2–3 người thử trong mạng nội bộ

Hướng dẫn này không mở public beta, không cấu hình port forwarding và không dùng dịch vụ trả phí. Người vận hành chịu trách nhiệm xác nhận mạng LAN là mạng riêng đáng tin cậy.

## 1. Chuẩn bị trên máy chạy SpeakSeed

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python tools/db_backup.py create speakseed.db backups/internal-beta-before.db
ipconfig
```

Từ `ipconfig`, lấy IPv4 của adapter LAN/Wi-Fi đang dùng, ví dụ `192.168.1.25`. Không dùng IP public. Tạo secret cho phiên chạy và thay `<LAN_IP>` bằng IP vừa kiểm tra:

```powershell
$env:APP_ENV='development'
$env:APP_SECRET='replace-with-a-random-secret-at-least-32-characters'
$env:AUTH_TRANSPORT='cookie'
$env:COOKIE_SECURE='false'
$env:DB_PATH=(Resolve-Path '.\speakseed.db').Path
$env:ALLOWED_HOSTS='<LAN_IP>,localhost,127.0.0.1'
$env:ALLOWED_ORIGINS='http://<LAN_IP>:8000,http://127.0.0.1:8000'
$env:TRUST_PROXY_HEADERS='false'
$env:GEMINI_API_KEY=''
python -m uvicorn app:app --host <LAN_IP> --port 8000
```

Người thử truy cập `http://<LAN_IP>:8000`. Bind đúng IP LAN thay vì `0.0.0.0` để tránh nghe trên adapter không cần thiết. Không bật router port forwarding, UPnP, tunnel hoặc cloud relay.

HTTP trong LAN phù hợp cho thử nghiệm ngắn trên mạng tin cậy nhưng không đủ cho Internet. Microphone thường yêu cầu HTTPS hoặc localhost và vì vậy được xem là ngoài phạm vi buổi beginner beta này. Web Speech playback có thể hoạt động tùy trình duyệt/thiết bị.

Nếu Windows Firewall chặn, chỉ tạo rule inbound TCP 8000 cho profile `Private` và scope `LocalSubnet`, sau khi người vận hành xem lại phạm vi. Xóa/tắt rule sau buổi thử. Không cho phép profile Public hoặc Any remote address.

## 2. Quy tắc tài khoản và Gemini

- Mỗi người dùng một tài khoản riêng; không dùng dữ liệu tiến độ giả.
- Để `GEMINI_API_KEY` trống trong buổi thử mặc định. Vocabulary, grammar, Listening, Reading và Web Speech vẫn hoạt động.
- Nếu chủ dự án chủ động cho phép thử AI, chỉ cấu hình **một** key backend. SpeakSeed không xoay key. Tutor mặc định 10 lượt/giờ/tài khoản; Writing feedback 3 lượt/giờ/tài khoản.
- Gemini Live chỉ kết nối sau khi người dùng chọn Live, bấm bắt đầu và xác nhận cảnh báo quota.

## 3. Kết thúc và kiểm tra dữ liệu

Dừng Uvicorn bằng `Ctrl+C`, sau đó tạo backup mới:

```powershell
python tools/db_backup.py create speakseed.db backups/internal-beta-after.db
python -m pytest -q
```

Không xóa database hoặc tài khoản sau buổi thử nếu chưa có chính sách lưu giữ và sự đồng ý phù hợp. Nếu cần khôi phục, làm theo `DEPLOYMENT.md` và luôn restore sang file mới trước khi chuyển cấu hình.
