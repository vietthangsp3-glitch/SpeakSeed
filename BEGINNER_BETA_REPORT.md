# SpeakSeed — Beginner Beta A0–A1

Ngày kiểm tra: **2026-10-23** (Asia/Bangkok). Phạm vi: chuẩn bị cho 2–3 người dùng thử nội bộ; không triển khai Internet/public beta, không thuê server, không gọi Gemini thật và không thêm tính năng học tập lớn.

## Kết luận

**Có thể bắt đầu một buổi thử nội bộ có người vận hành trên mạng LAN tin cậy sau khi hoàn thành các bước thủ công trong `INTERNAL_BETA_GUIDE.md`. Không public-beta ready.**

Luồng kỹ thuật A0–A1, lưu tiến độ, browser speech và phân tách tài khoản đã PASS bằng automated test. Khả năng một người mới thực sự hiểu onboarding mà không được hướng dẫn vẫn **BLOCKED** cho đến khi 2–3 người thật hoàn thành checklist; automated E2E không thay thế usability test.

Database chính sau kiểm tra: `integrity_check=ok`, **0** foreign-key violation, **4.213** từ xuất bản, **100** grammar lesson, **1.000** grammar exercise, **0** tài khoản. Browser QA chỉ dùng `qa_artifacts/beginner_beta.db`; không ghi tiến độ giả vào database chính.

## PASS / FAIL / BLOCKED

| Điều kiện | Trạng thái | Bằng chứng |
|---|---|---|
| Trang khách giải thích cách bắt đầu | PASS kỹ thuật | Mobile E2E thấy CTA đăng ký và 3 bước onboarding |
| Người mới hiểu mà không cần hướng dẫn | BLOCKED | Cần quan sát 2–3 người thật; không suy diễn từ E2E |
| Đăng ký dẫn đến lựa chọn placement/bắt đầu học | PASS | Beginner E2E chạy trên Chrome |
| Placement 25 câu, giới hạn kết quả | PASS | Unit/integration và full browser E2E; kết quả ghi rõ không phải chứng chỉ |
| Learning path/backend unlock | PASS | Regression backend; bài tiếp theo chỉ mở từ bằng chứng hoạt động |
| Daily plan A0–A1 hợp lý | PASS | Chỉ gồm Học từ mới, Ôn đến hạn, Grammar, Listening, Reading |
| Speaking/Writing/Gemini bắt buộc | PASS | Không nằm trong daily plan A0–A1; chức năng cũ vẫn còn dưới dạng tùy chọn |
| Tiến độ sau reload/login | PASS | Beginner E2E và full E2E |
| Tiến độ tách theo tài khoản | PASS | Unit/integration test nhiều tài khoản và concurrency hiện có |
| Giao diện mobile 390×844 | PASS kỹ thuật | 0 horizontal overflow; CTA và kế hoạch hiển thị được |
| Usability trên điện thoại thật | BLOCKED | Chưa có người thật/thiết bị thật thực hiện checklist |
| Web Speech không dùng Gemini | PASS | 9/9 browser speech checks, 3 English voices, 0 `/api/tts` request |
| Âm thanh nghe rõ trên thiết bị người thử | BLOCKED | Headless Chrome không xác nhận chất lượng loa/giọng thực tế |
| Không tự gọi Gemini | PASS | 0 AI request trong onboarding, học từ và reload |
| Gemini Live | PASS theo thiết kế / BLOCKED thực tế | Chỉ connect sau thao tác + confirm; không có key/call thật trong đợt này |
| Chạy trên thiết bị thứ hai trong LAN | BLOCKED | Chưa mở firewall/bind LAN vì không tự ý thay đổi mạng máy người dùng |
| Public beta | FAIL/không thuộc phạm vi | Không triển khai và không tuyên bố sẵn sàng public beta |

## Thay đổi thực hiện

### Beginner mode

- Trang khách có CTA “Tạo tài khoản và bắt đầu”, lựa chọn xem thử từ vựng, và ba bước: tài khoản → placement → kế hoạch hôm nay.
- Dashboard tài khoản mới hiển thị lựa chọn placement 25 câu hoặc học 5 từ cơ bản trước.
- Daily plan A0–A1 chỉ giữ năm mục cốt lõi. Plan cũ của A0–A1 được chuẩn hóa idempotent khi đọc; lịch sử và learning event không bị xóa.
- Mục có target bằng 0 hiển thị “không có mục đến hạn” nhưng không mang dấu hoàn thành; tổng kế hoạch bỏ qua mục này thay vì tạo thành tích giả.
- “Gợi ý tiếp theo” vẫn dẫn tới grammar lesson được backend mở khóa.
- Listening hiển thị đúng rằng audio dùng Web Speech API; bỏ mô tả cache/Gemini TTS cũ.
- Navigation và Tutor ghi rõ AI là tùy chọn; lỗi và hướng dẫn vẫn bằng tiếng Việt.

### Gemini quota

- Bỏ lựa chọn round-robin nhiều Gemini key. `GEMINI_API_KEY` là cấu hình chính; nếu cấu hình legacy nhiều key thì chỉ key đầu tiên được dùng và server ghi warning.
- Hạn mức mặc định theo tài khoản/IP trong database: Tutor **10/30** lượt mỗi giờ; Writing feedback **3/12** lượt mỗi giờ.
- HTTP 429 giải thích rõ AI đã hết lượt nhưng Vocabulary, Grammar, Listening và Reading vẫn hoạt động.
- Gemini Live, Speaking và Writing cũ được bảo toàn; Live không tự kết nối. Gemini TTS tiếp tục trả 410 và cache cũ không bị xóa.

## Kết quả kiểm thử

- `node --check static/app.js`: **PASS**.
- `pytest` cuối cùng: **56 passed**, 1 Starlette/httpx deprecation warning, 34,45 giây.
- Targeted personalization/security/API: **21 passed**.
- Beginner Chrome mobile E2E: **6/6 PASS**; 0 automatic AI request.
- Full Chrome desktop/mobile E2E: **15/15 PASS**, 0 JavaScript page error.
- Browser Speech E2E: **9/9 PASS**, 0 Gemini TTS request.
- Main DB: integrity PASS, FK PASS, count 4.213/100/1.000 giữ nguyên.

Full E2E chủ động tạo lỗi 401/403/410/503 để kiểm tra session, CSRF, TTS-disabled và provider-offline; các console observation này là dự kiến. Accessibility mới là smoke check, chưa thay thế screen reader, keyboard-only hoặc contrast audit.

## Tài liệu cho buổi thử

- `BEGINNER_BETA_30_MIN_CHECKLIST.md`: kịch bản 30 phút và tiêu chí quan sát.
- `BETA_FEEDBACK_TEMPLATE.md`: lỗi kỹ thuật và câu hỏi trải nghiệm A0–A1.
- `INTERNAL_BETA_GUIDE.md`: bind đúng IP LAN, không port-forward, Gemini tắt mặc định, backup trước/sau.

## Công việc thủ công trước và trong buổi thử

1. Chọn mạng LAN riêng, xác nhận không có port forwarding/tunnel và backup database.
2. Bind Uvicorn vào đúng IPv4 LAN; nếu cần firewall rule, giới hạn profile `Private` + `LocalSubnet`, rồi tắt/xóa sau buổi thử.
3. Cho từng người một tài khoản riêng; không cung cấp chỉ dẫn trong 5 phút đầu.
4. Quan sát người thử có tìm được CTA, hiểu placement, tìm được “Gợi ý tiếp theo” và hiểu AI là tùy chọn hay không.
5. Nghe thử Web Speech trên từng điện thoại; ghi trường hợp thiếu voice hoặc phát không rõ.
6. Reload, logout/login và đối chiếu tiến độ từng tài khoản; kiểm tra không nhìn thấy dữ liệu người khác.
7. Thu feedback, Request ID nếu có; không thu password, cookie, key hay audio riêng tư.
8. Dừng server, backup sau phiên và ghi quyết định sửa lỗi trước phiên tiếp theo.

## Go/No-Go cho internal beginner beta

- [x] Nội dung/database được bảo toàn.
- [x] Pytest và browser E2E PASS.
- [x] A0–A1 không bắt buộc Gemini.
- [x] Quota Tutor/Writing theo tài khoản và thông báo 429 rõ ràng.
- [x] Checklist, feedback form và LAN guide đã có.
- [ ] Người vận hành chạy thử từ một thiết bị thứ hai trong LAN.
- [ ] 2–3 người mới hoàn thành usability checklist.
- [ ] Các lỗi S1/S2 từ buổi thử được xử lý hoặc có quyết định No-Go.

**Trạng thái:** sẵn sàng về mã nguồn cho một phiên internal beta có giám sát; chưa có bằng chứng để tuyên bố usability PASS hoặc public beta ready.
