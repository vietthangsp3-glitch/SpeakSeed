"""Desktop/mobile smoke audit for learner-facing copy and navigation."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


VIEWS = (
    "home", "placement", "learn", "reverse", "grammar", "skills", "rewrite",
    "dictation", "speak", "quiz", "conversation", "tutor", "progress",
)
FORBIDDEN_VISIBLE_TEXT = (
    "Gemini API", "API key", "quota API", "Web Speech API", "Web Speech Recognition",
    "Azure Speech", "automated_checked", "human_reviewed", "môi trường thử nghiệm",
    "backend nhận", "Invalid mode", "Exercise not found",
)
AI_ROUTES = ("/api/chat", "/api/pronunciation/ai", "/api/speaking/", "/writing/submit")


def audit_views(page: Page, viewport_name: str) -> list[dict]:
    results: list[dict] = []
    for view in VIEWS:
        page.locator(f'[data-view="{view}"]').click()
        page.locator("#content").wait_for(state="visible")
        text = page.locator("body").inner_text()
        assert page.locator("#content").inner_text().strip(), f"{view} has no content"
        for phrase in FORBIDDEN_VISIBLE_TEXT:
            assert phrase.lower() not in text.lower(), f"{view} exposes technical phrase: {phrase}"
        overflow = page.evaluate("document.documentElement.scrollWidth-window.innerWidth")
        assert overflow <= 1, f"{view} overflows viewport by {overflow}px"
        results.append({"viewport": viewport_name, "view": view, "status": "PASS"})
    return results


def run(base_url: str, output: Path) -> dict:
    results: list[dict] = []
    page_errors: list[str] = []
    console_errors: list[str] = []
    ai_requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900}, locale="vi-VN")
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: ai_requests.append(request.url) if any(
            marker in request.url for marker in AI_ROUTES
        ) or request.url.startswith("ws") else None)
        page.goto(base_url, wait_until="networkidle")

        page.locator("#authBtn").click()
        page.locator("#switchAuth").click()
        marker = secrets.token_hex(6)
        page.locator("#name").fill("Kiểm tra giao diện")
        page.locator("#email").fill(f"ui-audit-{marker}@example.invalid")
        page.locator("#password").fill("ui-audit-password")
        page.locator("#authSubmit").click()
        page.get_by_role("button", name="Đăng xuất", exact=True).wait_for(timeout=15_000)

        results.extend(audit_views(page, "desktop-1366x900"))
        page.set_viewport_size({"width": 390, "height": 844})
        results.extend(audit_views(page, "mobile-390x844"))

        assert not page_errors, page_errors
        # The external font request can be blocked in an offline QA environment, and
        # the initial anonymous /api/me check intentionally returns 401.
        unexpected_console_errors = [message for message in console_errors if not any(
            expected in message for expected in ("ERR_NETWORK_ACCESS_DENIED", "status of 401")
        )]
        assert not unexpected_console_errors, unexpected_console_errors
        assert not ai_requests, f"AI requests happened without an explicit learning action: {ai_requests}"
        assert page.locator("button:visible").count() > 0
        page.screenshot(path=str(output.with_suffix(".png")), full_page=True)
        context.close()
        browser.close()

    report = {
        "ok": True,
        "base_url": base_url,
        "results": results,
        "page_errors": page_errors,
        "console_errors": console_errors,
        "unexpected_console_errors": [],
        "automatic_ai_requests": ai_requests,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("qa_artifacts/user_facing_audit.json"))
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.output)
    print(json.dumps({"ok": result["ok"], "report": str(args.output)}))
