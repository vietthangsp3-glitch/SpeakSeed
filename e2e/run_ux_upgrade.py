"""Smoke tests for the personalized dashboard and paginated vocabulary UX."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from playwright.sync_api import sync_playwright


def open_view(page, view: str) -> None:
    target = page.locator(f'[data-view="{view}"]').first
    if (page.viewport_size or {}).get("width", 1000) <= 700 or not target.is_visible():
        page.locator("#menuToggle").click()
    target.click()


def run(base_url: str, output: Path) -> dict:
    results = []
    ai_requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale="vi-VN")
        page = context.new_page()
        page.on("request", lambda request: ai_requests.append(request.url) if any(
            marker in request.url for marker in ("/api/chat", "/api/speaking/", "/writing/submit", "/ws/speaking/live")
        ) else None)
        page.goto(base_url, wait_until="networkidle")
        marker = secrets.token_hex(5)
        page.locator("#startBeginner").click()
        page.locator("#name").fill("UX QA")
        page.locator("#email").fill(f"ux-{marker}@example.invalid")
        page.locator("#password").fill("ux-correct-horse")
        page.locator("#authSubmit").click()
        page.locator(".xp-panel").wait_for()
        assert page.locator(".journey-unit").count() > 0
        assert page.locator(".achievement").count() == 4
        results.append({"name": "dashboard_xp_journey", "status": "PASS"})

        open_view(page, "learn")
        page.locator("#reveal").wait_for()
        assert page.get_by_text("Tải thêm 80 từ", exact=True).is_visible()
        assert "80" in page.locator(".counter").inner_text() or "/ 1000" in page.locator(".counter").inner_text()
        results.append({"name": "paginated_vocabulary", "status": "PASS"})

        page.locator("#topicPractice").click()
        page.get_by_text("Ghép cặp", exact=True).click()
        assert page.locator(".match-board [data-match-word]").count() == 4
        assert page.locator(".match-board [data-match-meaning]").count() == 4
        page.get_by_text("Nghe chọn từ", exact=True).click()
        assert page.locator("#listen").is_visible()
        results.append({"name": "vocabulary_game_modes", "status": "PASS"})

        assert page.evaluate("document.documentElement.scrollWidth-window.innerWidth") <= 1
        assert not ai_requests
        results.append({"name": "mobile_no_automatic_ai", "status": "PASS"})
        page.screenshot(path=str(output.with_suffix(".png")), full_page=True)
        browser.close()
    report = {"ok": True, "base_url": base_url, "results": results,
              "automatic_ai_requests": ai_requests}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("qa_artifacts/ux_upgrade_e2e.json"))
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.output)
    print(json.dumps({"ok": result["ok"], "report": str(args.output)}))
