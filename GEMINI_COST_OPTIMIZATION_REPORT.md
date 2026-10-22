# SpeakSeed — Báo cáo tối ưu chi phí Gemini

Ngày kiểm tra: **2026-10-23**. Không gọi Gemini thật trong quá trình kiểm thử và không xóa cache audio cũ.

## Kết quả

Gemini TTS đã được loại khỏi toàn bộ luồng học thông thường. Frontend không còn request `/api/tts`; backend giữ route cũ chỉ để trả **HTTP 410 Gone** và không đọc cache, không gọi provider, không ghi `ai_usage`. Thư mục/cache audio hiện có vẫn được giữ nguyên để audit hoặc rollback có chủ đích.

Web Speech API (`window.speechSynthesis`) hiện đảm nhiệm giọng đọc cho:

- Flashcard và Vocabulary;
- quiz, Việt → Anh và luyện phát âm mẫu;
- Listening và Dictation;
- Reading;
- Grammar;
- câu trả lời bằng văn bản của Speaking từng lượt.

Mỗi màn hình liên quan có bộ chọn giọng tiếng Anh trên thiết bị, ưu tiên `en-US`, sau đó `en-GB`, tốc độ 0,75x–1,25x, nút dừng và phát lại. Không có auto-play khi tải trang hoặc mở bài. Nếu trình duyệt chưa tải danh sách giọng, hệ thống dùng giọng tiếng Anh mặc định của thiết bị và hiển thị trạng thái; nếu Web Speech API không tồn tại, hệ thống báo lỗi và không fallback sang Gemini.

## Tính năng vẫn tiêu thụ Gemini quota

| Tính năng | Loại quota | Khi nào gọi |
|---|---|---|
| Gemini Live | Audio vào/ra thời gian thực | Chỉ sau khi người dùng chọn Live, nhấn bắt đầu và xác nhận cảnh báo quota |
| Speaking từng lượt | Gemini text | Khi người dùng gửi hoặc đọc xong một lượt; phần đọc câu trả lời dùng Web Speech, không dùng Gemini TTS |
| Đánh giá nhiệm vụ Speaking | Gemini text | Khi người dùng chủ động nhấn đánh giá và phiên có đủ bằng chứng lượt làm |
| Writing feedback | Gemini text | Khi người dùng chủ động nộp bài đủ giới hạn từ |
| Gia sư AI | Gemini text | Khi người dùng chủ động gửi câu hỏi |

Chấm phát âm từ đơn, nếu được cấu hình, dùng **Azure Speech**, không phải Gemini; dịch vụ này vẫn có thể có quota/chi phí riêng. Nhận dạng giọng nói từng lượt do trình duyệt cung cấp và tùy trình duyệt có thể dùng dịch vụ của nhà cung cấp trình duyệt; điều này không tiêu thụ Gemini API quota nhưng không được tuyên bố là luôn offline hoặc miễn phí tuyệt đối.

## Gemini Live

- Không kết nối khi tải trang, mở bài Speaking hoặc chọn chế độ.
- Hiển thị cảnh báo quota rõ ràng.
- Chỉ tạo WebSocket sau thao tác bắt đầu và hộp xác nhận của người dùng.
- Hủy xác nhận không mở WebSocket.
- Giới hạn server mặc định 600 giây; `GEMINI_LIVE_MAX_SECONDS` có thể giảm, mức tối thiểu 30 giây và tối đa 1.800 giây.
- Không có logic tự reconnect.
- `stopLive()` đóng WebSocket, media tracks, microphone/audio context khi dừng, đổi màn hình, lỗi, `pagehide` hoặc `beforeunload`.
- Audio Gemini trả về chỉ được phát trong phiên Live.

Integration test dùng upstream giả xác nhận proxy vẫn yêu cầu `responseModalities: ["AUDIO"]`, lưu usage `speaking_live`, ghi activity khi có model output và đóng upstream. Không gọi provider thật nên chưa xác nhận quota/network behavior thực tế của tài khoản Gemini.

## Backend và cấu hình

- Xóa toàn bộ mã phát sinh Gemini TTS và cache-serving khỏi endpoint.
- `/api/tts` luôn trả 410 kể cả request hợp lệ.
- Không xóa `audio_cache` hoặc volume `TTS_CACHE_DIR` cũ.
- Gỡ `GEMINI_TTS_MODEL` khỏi Compose và `.env.example`; biến đơn giá TTS còn lại chỉ dùng để diễn giải usage lịch sử.
- API key, rate limit, usage logs, Gemini text và Gemini Live vẫn nằm ở backend.
- Không có migration database vì thay đổi này không cần sửa schema hoặc dữ liệu.

## Kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ pytest | **47 passed**, 0 failed, 1 cảnh báo deprecation |
| Backend TTS hard-disable | PASS: 410, 0 usage row, provider không được gọi |
| Live proxy với upstream giả | PASS |
| Chrome Web Speech E2E | **9/9 PASS** |
| E2E toàn hệ thống sau thay đổi | **15/15 PASS** |
| JavaScript syntax | PASS |
| Python compile | PASS |
| SQLite integrity/FK | `ok`, 0 lỗi |
| Dữ liệu chính | 4.213 từ xuất bản, 100 grammar lesson, 1.000 exercise, 0 user |

Chrome cài trên máy báo có Web Speech API và 3 giọng tiếng Anh. Speech spy xác nhận Vocabulary, Dictation, Grammar, Listening và Reading tạo `SpeechSynthesisUtterance` với đúng nội dung/tốc độ; tổng request Gemini TTS từ UI là **0**. Kiểm thử mobile dùng viewport 390×844 và không có tràn ngang.

Bằng chứng:

- `qa_artifacts/browser_speech_e2e.json`
- `qa_artifacts/cost_optimization_stage6/stage6_e2e_result.json`
- `tests/test_live_cost_controls.py`
- `tests/test_security.py`
- `tests/test_api.py`

## Giới hạn còn lại

- Automated Chrome xác nhận API, controls và utterance; không thể xác nhận chất lượng âm thanh bằng tai người.
- Mobile là Chrome viewport emulation, chưa phải thiết bị Android/iOS thật.
- Điều khiển browser tương tác của Work đang bị tắt; kiểm thử dùng Playwright với Chrome đã cài.
- Chưa gọi Gemini Live thật để tránh quota/chi phí, nên cần một smoke test thủ công ngắn khi chủ dự án cho phép.
- Số lượng/chất lượng giọng phụ thuộc hệ điều hành và trình duyệt của người dùng.

Không có tuyên bố “mọi tính năng đều miễn phí”: các tính năng Gemini text, Gemini Live và Azure Speech nêu trên vẫn có thể tiêu thụ quota hoặc phát sinh chi phí.
