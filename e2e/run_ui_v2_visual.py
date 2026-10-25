"""Visual and responsive smoke checks for the SpeakSeed V2 dashboard."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from playwright.sync_api import sync_playwright


VIEWPORTS = ((360, 800), (390, 844), (768, 900), (1280, 900), (1440, 1000), (1920, 1080))


def run(base_url: str, output_dir: Path, email: str = "", password: str = "visual-correct-horse") -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome", headless=True, args=["--force-device-scale-factor=1"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1, locale="vi-VN"
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(base_url, wait_until="networkidle")
        if email:
            page.locator("#authBtn").click()
        else:
            page.locator("#startBeginner").click()
            email = f"visual-{secrets.token_hex(5)}@example.invalid"
            page.locator("#name").fill("Visual QA")
        page.locator("#email").fill(email)
        page.locator("#password").fill(password)
        page.locator("#authSubmit").click()
        page.get_by_role("button", name="Đăng xuất", exact=True).wait_for(timeout=15000)
        page.locator(".dashboard-shell").wait_for(timeout=15000)

        for width, height in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            page.reload(wait_until="networkidle")
            page.locator(".dashboard-shell").wait_for()
            overflow = page.evaluate("document.documentElement.scrollWidth-window.innerWidth")
            assert overflow <= 1, f"horizontal overflow {overflow}px at {width}x{height}"
            clipped_controls = page.evaluate("""() => [...document.querySelectorAll(
                '.welcome-copy button,.beginner-onboarding button'
              )].filter(el => {
                const r=el.getBoundingClientRect();
                return r.left < 0 || r.right > window.innerWidth + 1;
              }).map(el=>({text:el.textContent.trim(),rect:el.getBoundingClientRect().toJSON(),innerWidth,
                ancestors:[el.parentElement,el.parentElement?.parentElement,el.parentElement?.parentElement?.parentElement,
                  document.querySelector('.content'),document.querySelector('.main')].filter(Boolean).map(node=>({
                    cls:node.className,rect:node.getBoundingClientRect().toJSON(),width:getComputedStyle(node).width
                  }))}))""")
            assert not clipped_controls, f"clipped controls at {width}x{height}: {clipped_controls}"
            assert page.locator("#menuToggle").is_visible() is (width <= 700)
            assert page.locator(".dashboard-shell").is_visible()
            results.append({"viewport": f"{width}x{height}", "status": "PASS",
                            "overflow_px": overflow, "clipped_controls": len(clipped_controls)})
            if width == 390:
                page.screenshot(path=str(output_dir / "ui_v2_dashboard_mobile.png"), full_page=True, scale="css")
            if width == 1440:
                page.screenshot(path=str(output_dir / "ui_v2_dashboard_desktop.png"), full_page=True, scale="css")

        context.close()
        browser.close()

    report = {"ok": not page_errors, "results": results, "page_errors": page_errors}
    (output_dir / "ui_v2_visual.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("qa_artifacts"))
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="visual-correct-horse")
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.output_dir, args.email, args.password)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
