from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_learner_interface_does_not_expose_old_technical_messages():
    interface = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in ("static/index.html", "static/app.js")
    )
    forbidden_messages = (
        "Gemini Live sử dụng quota API",
        "Chưa cấu hình Gemini API key",
        "không đưa API key ra trình duyệt",
        "Web Speech API trên thiết bị",
        "không hỗ trợ Web Speech API",
        "không hỗ trợ Web Speech Recognition",
        "Chưa cấu hình Azure Speech",
        "GEMINI AI · ĐÃ BẬT",
        "automated_checked không đồng nghĩa với human_reviewed",
        "môi trường thử nghiệm",
        "backend nhận",
        "Gemini trả về HTTP",
    )
    for message in forbidden_messages:
        assert message not in interface


def test_learner_interface_uses_actionable_vietnamese_fallbacks():
    javascript = (ROOT / "static/app.js").read_text(encoding="utf-8")
    expected_messages = (
        "Hội thoại trực tiếp hiện chưa khả dụng",
        "Trình duyệt này chưa hỗ trợ nhận diện giọng nói",
        "Không thể phát bài nghe",
        "Đánh giá phát âm chi tiết",
        "Bạn vẫn có thể dùng Luyện nói cơ bản",
        "Đã mở lại bài kiểm tra đang làm",
    )
    for message in expected_messages:
        assert message in javascript


def test_internal_provider_names_are_not_used_as_navigation_labels():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    assert "AI Speaking" not in html
    assert "Luyện hội thoại" in html
