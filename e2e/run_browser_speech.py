"""Chrome regression checks for browser-only speech and Gemini Live consent."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from playwright.sync_api import sync_playwright


SPEECH_SPY = """
window.__speechCalls=[];
if (window.speechSynthesis) {
  window.speechSynthesis.speak=(utterance)=>window.__speechCalls.push({
    text:utterance.text, rate:utterance.rate, lang:utterance.lang,
    voice:utterance.voice ? utterance.voice.name : null
  });
  window.speechSynthesis.cancel=()=>window.__speechCanceled=(window.__speechCanceled||0)+1;
}
"""


def run(base_url: str, output: Path) -> dict:
    results: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="vi-VN")
        context.add_init_script(SPEECH_SPY)
        page = context.new_page()
        tts_requests: list[str] = []
        websocket_urls: list[str] = []
        page.on("request", lambda request: tts_requests.append(request.url) if "/api/tts" in request.url else None)
        page.on("websocket", lambda socket: websocket_urls.append(socket.url))
        page.goto(base_url, wait_until="networkidle")
        native = page.evaluate("()=>({synthesis:typeof speechSynthesis!=='undefined',utterance:typeof SpeechSynthesisUtterance==='function',voices:speechSynthesis?.getVoices?.().filter(v=>/^en[-_]/i.test(v.lang)).length||0})")
        assert native["synthesis"] and native["utterance"]
        assert page.evaluate("window.__speechCalls.length") == 0
        results.append({"name": "native_web_speech_available", "status": "PASS", "detail": native})

        page.locator('[data-view="learn"]').click()
        page.locator(".speech-panel").wait_for()
        assert page.locator('[data-speech-speed]').get_attribute("min") == "0.75"
        assert page.locator('[data-speech-speed]').get_attribute("max") == "1.25"
        page.locator("#listen").click()
        first = page.evaluate("window.__speechCalls.at(-1)")
        assert first and first["text"]
        page.locator('[data-speech-speed]').evaluate("el=>{el.value='1.25';el.dispatchEvent(new Event('input',{bubbles:true}))}")
        page.locator("#listen").click()
        assert page.evaluate("window.__speechCalls.at(-1).rate") == 1.25
        page.locator('[data-speech-stop]').click(); page.locator('[data-speech-replay]').click()
        assert page.evaluate("window.__speechCalls.length") >= 3
        assert not tts_requests
        results.append({"name": "vocabulary_voice_speed_stop_replay_without_tts", "status": "PASS"})

        page.locator('[data-view="dictation"]').click(); page.locator("#playAudio").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        results.append({"name": "dictation_browser_speech_without_tts", "status": "PASS"})

        page.locator("#authBtn").click(); page.locator("#switchAuth").click()
        marker = secrets.token_hex(5)
        page.locator("#name").fill("Speech QA"); page.locator("#email").fill(f"speech-{marker}@example.invalid")
        page.locator("#password").fill("speech-test-password"); page.locator("#authSubmit").click()
        page.get_by_role("button", name="Đăng xuất", exact=True).wait_for(timeout=15000)
        page.locator('[data-view="home"]').click(); page.get_by_text("Việc cần làm hôm nay").wait_for()

        page.locator('[data-view="grammar"]').click(); page.locator(".lesson-card:not([disabled])").first.click()
        page.locator(".speech-panel [data-speech-current]").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        results.append({"name": "grammar_browser_speech_without_tts", "status": "PASS"})

        page.locator('[data-view="skills"]').click(); page.locator('[data-skill-tab="listening"]').click()
        page.locator(".skill-card:not([disabled])").first.click(); page.locator("#playSkillAudio").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        page.locator("#backSkills").click(); page.locator('[data-skill-tab="reading"]').click()
        page.locator(".skill-card:not([disabled])").first.click(); page.locator(".speech-panel [data-speech-current]").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        results.append({"name": "listening_reading_browser_speech_without_tts", "status": "PASS"})

        page.locator('[data-view="conversation"]').click()
        assert page.get_by_text("Gemini Live sử dụng quota API", exact=False).is_visible()
        page.locator("#speakingMode").select_option("live")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#startSpeaking").click()
        assert not websocket_urls
        assert "Chưa kết nối" in page.locator("#speakStatus").inner_text()
        results.append({"name": "live_requires_explicit_confirm_and_no_auto_connect", "status": "PASS"})

        page.set_viewport_size({"width": 390, "height": 844}); page.reload(wait_until="networkidle")
        page.locator('[data-view="learn"]').click(); page.locator(".speech-panel").wait_for()
        assert page.evaluate("document.documentElement.scrollWidth-window.innerWidth") <= 1
        results.append({"name": "mobile_390_speech_controls", "status": "PASS"})
        context.close()

        missing = browser.new_context(viewport={"width": 390, "height": 844})
        missing.add_init_script(SPEECH_SPY + "speechSynthesis.getVoices=()=>[];")
        no_voice_page = missing.new_page(); no_voice_tts: list[str] = []
        no_voice_page.on("request", lambda request: no_voice_tts.append(request.url) if "/api/tts" in request.url else None)
        no_voice_page.goto(base_url, wait_until="networkidle"); no_voice_page.locator('[data-view="learn"]').click()
        no_voice_page.locator("#listen").click()
        assert no_voice_page.evaluate("window.__speechCalls.length") == 1 and not no_voice_tts
        assert "Chưa tải" in no_voice_page.locator('[data-speech-voice] option').inner_text()
        results.append({"name": "empty_voice_list_uses_device_default_without_gemini", "status": "PASS"})
        missing.close()

        unsupported = browser.new_context(viewport={"width": 390, "height": 844})
        unsupported.add_init_script("""Object.defineProperty(window,'speechSynthesis',{value:undefined,configurable:true});
            Object.defineProperty(window,'SpeechSynthesisUtterance',{value:undefined,configurable:true});""")
        unsupported_page = unsupported.new_page(); unsupported_tts: list[str] = []
        unsupported_page.on("request", lambda request: unsupported_tts.append(request.url) if "/api/tts" in request.url else None)
        unsupported_page.goto(base_url, wait_until="networkidle"); unsupported_page.locator('[data-view="learn"]').click()
        assert "không hỗ trợ Web Speech API" in unsupported_page.locator('[data-speech-status]').inner_text()
        unsupported_page.locator("#listen").click()
        assert "không hỗ trợ Web Speech API" in unsupported_page.locator("#toast").inner_text()
        assert not unsupported_tts
        results.append({"name": "unsupported_web_speech_never_falls_back_to_gemini", "status": "PASS"})
        unsupported.close(); browser.close()

    report = {"ok": all(item["status"] == "PASS" for item in results), "base_url": base_url,
              "results": results, "gemini_tts_requests_from_ui": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("qa_artifacts/browser_speech_e2e.json"))
    args = parser.parse_args()
    result = run(args.base_url.rstrip("/"), args.output)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
