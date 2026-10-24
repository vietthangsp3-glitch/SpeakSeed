"""Repeatable Stage 6 browser E2E against an isolated/staging SpeakSeed URL.

Uses the installed Chrome channel, a fake microphone stream, and never requires
real Gemini credentials. It creates one clearly named QA account in the target.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def run(base_url: str, output_dir: Path, headed: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []; page_errors: list[str] = []; console_errors: list[str] = []

    def step(name, function):
        started = time.perf_counter()
        try:
            detail = function()
            results.append({"name": name, "status": "PASS", "ms": round((time.perf_counter() - started) * 1000, 1), "detail": detail or ""})
        except Exception as exc:
            results.append({"name": name, "status": "FAIL", "ms": round((time.perf_counter() - started) * 1000, 1), "detail": f"{type(exc).__name__}: {exc}"})
            (output_dir / "stage6_e2e_result.json").write_text(json.dumps({"ok": False, "results": results,
                "javascript_errors": page_errors, "console_error_observations": console_errors,
                "fatal": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2), encoding="utf-8")
            raise

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=not headed, args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        ])
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="vi-VN")
        context.grant_permissions(["microphone"], origin=base_url)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(f"pageerror: {error}"))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        marker = secrets.token_hex(5); email = f"stage6-{marker}@example.invalid"; password = "stage6-correct-horse"

        step("desktop_load", lambda: (page.goto(base_url, wait_until="networkidle"), page.locator("h1").first.wait_for())[1])

        def register():
            page.locator("#authBtn").click(); page.locator("#switchAuth").click()
            page.locator("#name").fill("QA <img src=x onerror=window.__stage6xss=1>")
            page.locator("#email").fill(email); page.locator("#password").fill(password)
            with page.expect_response(lambda response: response.url.endswith("/api/register")) as pending:
                page.locator("#authSubmit").click()
            response = pending.value
            if response.status != 200:
                raise AssertionError(f"register HTTP {response.status}: {response.text()}")
            try:
                page.get_by_text("Việc cần làm hôm nay").wait_for(timeout=10000)
            except Exception as exc:
                raise AssertionError(f"dashboard did not load; authError={page.locator('#authError').inner_text()!r}") from exc
            assert page.evaluate("window.__stage6xss !== 1")
            assert page.locator("#content img[src='x']").count() == 0
            cookies = {cookie["name"]: cookie for cookie in context.cookies()}
            assert cookies["ss_session"]["httpOnly"] is True and cookies["ss_csrf"]["httpOnly"] is False
            return {"email": email, "session_same_site": cookies["ss_session"]["sameSite"]}
        step("register_cookie_and_stored_xss", register)
        original_session = next(cookie["value"] for cookie in context.cookies() if cookie["name"] == "ss_session")

        def csrf():
            missing = page.evaluate("""async()=>{const r=await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"daily_goal_minutes":15}'});return r.status}""")
            accepted = page.evaluate("""async()=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('ss_csrf=')).split('=').slice(1).join('='));const r=await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{"daily_goal_minutes":15}'});return r.status}""")
            assert missing == 403 and accepted == 200
            return {"without_token": missing, "with_token": accepted}
        step("csrf_browser", csrf)

        def placement():
            page.locator('[data-view="placement"]').click(); page.locator("#beginPlacement").click()
            played_audio = False
            for index in range(40):
                page.wait_for_function("""()=>document.querySelector('[data-placement-answer],#placementTextForm,[data-order-token],#orderSave')!==null""")
                current_label = page.locator(".placement-progress b").inner_text()
                if page.locator("#playPlacementAudio").count() and not played_audio:
                    with page.expect_response(lambda response: "/api/placement/audio/" in response.url) as pending:
                        page.locator("#playPlacementAudio").click()
                    assert pending.value.status == 200; played_audio = True
                if page.locator("[data-placement-answer]").count():
                    page.locator("[data-placement-answer]").first.click()
                elif page.locator("#placementTextForm").count():
                    page.locator("#placementText").fill("stage6 answer"); page.locator("#placementTextForm button").click()
                else:
                    for _ in range(30):
                        tokens = page.locator("[data-order-token]")
                        if page.locator("#orderSave:not([disabled])").count(): break
                        if not tokens.count(): page.wait_for_timeout(100); continue
                        old_count = tokens.count()
                        with page.expect_response(lambda response: response.url.endswith("/api/placement/answer")) as pending:
                            tokens.first.click()
                        assert pending.value.status == 200
                        page.wait_for_function("count=>document.querySelectorAll('[data-order-token]').length<count || !document.querySelector('#orderSave')?.disabled", arg=old_count)
                    page.locator("#orderSave:not([disabled])").wait_for()
                    page.locator("#orderSave").click()
                if index < 39:
                    page.wait_for_function("label=>document.querySelector('.placement-progress b')?.textContent!==label", arg=current_label)
            page.locator("#submitPlacement").click()
            page.get_by_text("Cấp độ bắt đầu được đề xuất").wait_for()
            assert page.locator(".placement-review").count() == 40
            return {"level": page.locator(".level-badge").inner_text(), "audio_played": played_audio}
        step("placement_40_mixed_questions", placement)

        def vocabulary():
            page.locator('[data-view="learn"]').click(); page.locator("#reveal").click()
            with page.expect_response(lambda response: response.url.endswith("/api/progress")) as pending:
                page.locator("#correct").click()
            assert pending.value.status == 200
            page.locator('[data-view="progress"]').click(); page.get_by_text("Danh sách từ đã học và đã lưu").wait_for()
            assert page.locator(".progressrow").count() >= 1
            return "SRS progress visible"
        step("vocabulary_srs", vocabulary)

        def vocabulary_topics():
            page.locator('[data-view="learn"]').click()
            page.locator('[data-vocab-mode="topic"]').click()
            page.locator(".vocab-topic-grid").wait_for()
            assert page.locator(".vocab-topic-card").count() == 24
            available = page.locator(".vocab-topic-card:not([disabled])")
            available_count = available.count(); assert available_count > 0
            available.first.click(); page.locator(".flash").wait_for()
            page.locator("#vocabSearch").fill(page.locator(".flash h2").inner_text()[:3])
            page.locator("#cardDirection").select_option("vi-en")
            assert page.locator(".flash").is_visible()
            return {"topics": 24, "available_at_level": available_count, "direction": "vi-en"}
        step("vocabulary_topic_learning", vocabulary_topics)

        def grammar():
            page.locator('[data-view="grammar"]').click(); page.locator(".lesson-card").first.click()
            page.locator(".grammar-exercise").wait_for()
            if page.locator("[data-grammar-answer]").count(): page.locator("[data-grammar-answer]").first.click()
            else: page.locator("#grammarAnswer").fill("stage6 answer"); page.locator("#grammarAnswerForm button").click()
            page.locator(".grammar-exercise .feedback").wait_for()
            return page.locator(".exercise-meta span").inner_text()
        step("grammar_attempt", grammar)

        def skill(skill_name: str, save_word: bool = False):
            if page.locator("#backSkills").count(): page.locator("#backSkills").click()
            else: page.locator('[data-view="skills"]').click()
            page.locator(f'[data-skill-tab="{skill_name}"]').click()
            page.locator(".skill-card:not([disabled])").first.click()
            page.locator(".skill-hero").wait_for()
            if save_word and page.locator("[data-save-word]").count(): page.locator("[data-save-word]").first.click()
            if page.locator("[data-skill-answer]").count(): page.locator("[data-skill-answer]").first.click()
            else: page.locator("#skillAnswer").fill("stage6 answer"); page.locator("#skillAnswerForm button").click()
            page.locator(".skill-question .feedback").wait_for()
            return page.locator(".skill-hero h1").inner_text()
        step("listening_attempt", lambda: skill("listening"))
        step("reading_attempt_and_save_word", lambda: skill("reading", True))

        def writing_failure_keeps_draft():
            if page.locator("#backSkills").count(): page.locator("#backSkills").click()
            else: page.locator('[data-view="skills"]').click()
            page.locator('[data-skill-tab="writing"]').click(); page.locator(".skill-card:not([disabled])").first.click(); page.locator(".skill-hero").wait_for()
            paragraph = ("Learning English takes time, so I practise a little every day. I read useful articles, "
                         "review new words, listen to short recordings, and write about ordinary experiences. "
                         "When I make a mistake, I note the correction and try the sentence again. ")
            page.locator("#writingText").fill((paragraph * 5).strip())
            page.locator("#saveWriting").click(); page.locator("#toast.show").wait_for()
            page.locator("#submitWriting").click(); page.locator("#writingFeedback .feedback.no").wait_for(timeout=10000)
            return page.locator("#writingFeedback").inner_text()
        step("writing_provider_failure_preserves_draft", writing_failure_keeps_draft)

        def speaking_failure_not_complete():
            if page.locator("#backSkills").count(): page.locator("#backSkills").click()
            else: page.locator('[data-view="skills"]').click()
            page.locator('[data-skill-tab="speaking"]').click(); page.locator(".skill-card:not([disabled])").first.click(); page.locator("#startTurnTask").wait_for(); page.locator("#startTurnTask").click()
            page.locator("#speakingText").fill("Hello, I would like to practise this task."); page.locator("#speakingForm button").click()
            page.wait_for_function("status => status.textContent !== 'Đang chuẩn bị câu trả lời…'", arg=page.locator("#speakStatus").element_handle(), timeout=10000)
            status = page.locator("#speakStatus").inner_text(); assert "Đã trả lời" not in status
            return status
        step("speaking_provider_failure_not_complete", speaking_failure_not_complete)

        def legacy_tts_is_disabled():
            status = page.evaluate("""async()=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('ss_csrf=')).split('=').slice(1).join('='));const r=await fetch('/api/tts',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({text:'stage six uncached '+Date.now(),voice:'Kore',speed:.85})});return r.status}""")
            assert status == 410
            return {"legacy_endpoint_status": status, "browser_speech_required": True}
        step("legacy_gemini_tts_disabled", legacy_tts_is_disabled)

        def microphone_and_live_guard():
            microphone = page.evaluate("""async()=>{const stream=await navigator.mediaDevices.getUserMedia({audio:true});
                const track=stream.getAudioTracks()[0]; const result={tracks:stream.getAudioTracks().length,state:track.readyState};
                stream.getTracks().forEach(item=>item.stop()); return result}""")
            page.locator('[data-view="conversation"]').click()
            page.locator("#speakingMode").wait_for()
            assert microphone["tracks"] == 1 and microphone["state"] == "live"
            assert page.locator("#speakingMode").is_disabled()
            return {"microphone": microphone, "live_control": "disabled without backend Gemini key"}
        step("microphone_permission_and_live_guard", microphone_and_live_guard)

        def reload_persistence():
            page.reload(wait_until="networkidle"); page.get_by_text("Việc cần làm hôm nay").wait_for()
            page.locator('[data-view="progress"]').click(); assert page.locator(".progressrow").count() >= 1
            return "cookie session and progress persisted"
        step("reload_session_progress", reload_persistence)

        def logout_login_rotation():
            page.locator("#authBtn").click(); page.get_by_role("button", name="Đăng nhập", exact=True).wait_for()
            assert not any(cookie["name"] == "ss_session" for cookie in context.cookies())
            page.locator("#authBtn").click()
            assert page.locator("#authTitle").inner_text() == "Chào mừng trở lại!"
            page.locator("#email").fill(email); page.locator("#password").fill(password)
            with page.expect_response(lambda response: response.url.endswith("/api/login")) as pending:
                page.locator("#authSubmit").click()
            if pending.value.status != 200:
                raise AssertionError(f"login HTTP {pending.value.status}: {pending.value.text()}")
            page.get_by_role("button", name="Đăng xuất", exact=True).wait_for()
            page.locator('[data-view="home"]').click(); page.get_by_text("Việc cần làm hôm nay").wait_for()
            rotated = next(cookie["value"] for cookie in context.cookies() if cookie["name"] == "ss_session")
            assert rotated != original_session
            return "session rotated"
        step("logout_login_session_rotation", logout_login_rotation)

        def mobile():
            page.set_viewport_size({"width": 390, "height": 844}); page.goto(base_url, wait_until="networkidle")
            metrics = page.evaluate("""()=>({overflow:document.documentElement.scrollWidth-window.innerWidth,
                sidebar:getComputedStyle(document.querySelector('.sidebar')).position,
                bottom:getComputedStyle(document.querySelector('.sidebar')).bottom,
                emptyButtons:[...document.querySelectorAll('button')].filter(b=>!(b.getAttribute('aria-label')||b.innerText.trim())).length,
                offenders:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.right>window.innerWidth+1||r.left<-1}).slice(0,10).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:Math.round(e.getBoundingClientRect().right),left:Math.round(e.getBoundingClientRect().left)}))})""")
            assert metrics["overflow"] <= 1 and metrics["sidebar"] == "fixed" and metrics["bottom"] == "0px" and metrics["emptyButtons"] == 0, metrics
            page.screenshot(path=str(output_dir / "stage6-mobile-390.png"), full_page=True)
            return metrics
        step("mobile_390_responsive_accessibility", mobile)
        page.set_viewport_size({"width": 1440, "height": 900}); page.goto(base_url, wait_until="networkidle")
        page.screenshot(path=str(output_dir / "stage6-desktop-1440.png"), full_page=True)
        browser.close()

    return {"ok": all(item["status"] == "PASS" for item in results) and not page_errors,
            "base_url": base_url, "results": results, "javascript_errors": page_errors,
            "console_error_observations": console_errors}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("qa_artifacts")); parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    path = args.output_dir / "stage6_e2e_result.json"
    try:
        result = run(args.base_url.rstrip("/"), args.output_dir, args.headed)
    except (AssertionError, PlaywrightTimeoutError, Exception) as exc:
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8")); result["fatal"] = f"{type(exc).__name__}: {exc}"
        else: result = {"ok": False, "fatal": f"{type(exc).__name__}: {exc}"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result.get("ok", False), "report": str(path), "fatal": result.get("fatal", "")}, ensure_ascii=True))
    if not result.get("ok"): raise SystemExit(1)


if __name__ == "__main__": main()
