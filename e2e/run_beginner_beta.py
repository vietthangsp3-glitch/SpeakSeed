"""A0-A1 onboarding smoke test against an isolated SpeakSeed instance."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from playwright.sync_api import sync_playwright


def run(base_url: str, output: Path) -> dict:
    results = []
    ai_requests = []

    def passed(name: str, detail=""):
        results.append({"name": name, "status": "PASS", "detail": detail})

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale="vi-VN")
        page = context.new_page()
        page.on("request", lambda request: ai_requests.append(request.url) if any(
            marker in request.url for marker in ("/api/chat", "/api/speaking/", "/writing/submit", "/ws/speaking/live")
        ) else None)
        page.goto(base_url, wait_until="networkidle")
        assert page.get_by_text("Mới học tiếng Anh?", exact=False).is_visible()
        assert page.get_by_text("Ba bước bắt đầu", exact=False).count() == 0  # aria-label, not duplicate visible copy
        assert page.locator(".beginner-steps > div").count() == 3
        assert page.evaluate("document.documentElement.scrollWidth-window.innerWidth") <= 1
        passed("guest_mobile_onboarding", "3 bước, CTA đăng ký, không tràn ngang")

        page.locator("#startBeginner").click()
        assert page.locator("#authTitle").inner_text() == "Tạo tài khoản miễn phí"
        marker = secrets.token_hex(5)
        email = f"beginner-{marker}@example.invalid"
        page.locator("#name").fill("Người học A0")
        page.locator("#email").fill(email)
        page.locator("#password").fill("beginner-correct-horse")
        page.locator("#authSubmit").click()
        page.get_by_text("Chọn điểm bắt đầu của bạn").wait_for(timeout=15000)
        passed("registration_reaches_beginner_choice", email)

        plan_labels = page.locator(".daily-plan .plan-item b").all_inner_texts()
        assert plan_labels == ["Học từ mới", "Ôn từ đến hạn", "Luyện grammar", "Luyện nghe", "Luyện đọc"]
        assert "AI Speaking" not in plan_labels and "Luyện viết" not in plan_labels
        assert page.get_by_text("Gợi ý tiếp theo").is_visible()
        passed("a0_daily_plan_is_core_only", plan_labels)

        page.locator("#onboardVocabulary").click()
        page.locator("#reveal").click()
        with page.expect_response(lambda response: response.url.endswith("/api/progress")) as pending:
            page.locator("#correct").click()
        assert pending.value.status == 200
        page.locator('[data-view="home"]').click()
        page.get_by_text("Việc cần làm hôm nay").wait_for()
        assert int(page.locator(".metric-grid .metric").first.locator("b").inner_text()) >= 1
        passed("first_vocabulary_activity_is_saved")

        page.reload(wait_until="networkidle")
        page.get_by_text("Việc cần làm hôm nay").wait_for()
        assert int(page.locator(".metric-grid .metric").first.locator("b").inner_text()) >= 1
        assert page.get_by_role("button", name="Đăng xuất", exact=True).is_visible()
        passed("session_and_progress_survive_reload")

        assert not ai_requests
        passed("no_automatic_ai_request", "0 request Gemini khi onboarding/học từ/reload")
        page.screenshot(path=str(output.with_suffix(".png")), full_page=True)
        browser.close()

    report = {"ok": all(item["status"] == "PASS" for item in results), "base_url": base_url,
              "results": results, "automatic_ai_requests": ai_requests}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("qa_artifacts/beginner_beta_e2e.json"))
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.output)
    print(json.dumps({"ok": result["ok"], "report": str(args.output)}, ensure_ascii=True))
    raise SystemExit(0 if result["ok"] else 1)
