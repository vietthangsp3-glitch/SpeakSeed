"""Chrome regression checks for browser-only speech and Gemini Live consent."""
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
        native = page.evaluate("()=>({synthesis:typeof speechSynthesis!=='undefined',utterance:typeof SpeechSynthesisUtterance==='function',voices:speechSynthesis?.getVoices?.().filter(v=>/^en[-_]/i.test(v.lang)).length||0,recognition:typeof SpeechRecognition==='function'||typeof webkitSpeechRecognition==='function'})")
        assert native["synthesis"] and native["utterance"]
        assert page.evaluate("window.__speechCalls.length") == 0
        results.append({"name": "native_web_speech_available", "status": "PASS", "detail": native})

        open_view(page, "learn")
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

        open_view(page, "dictation"); page.locator("#playAudio").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        results.append({"name": "dictation_browser_speech_without_tts", "status": "PASS"})

        page.locator("#authBtn").click(); page.locator("#switchAuth").click()
        marker = secrets.token_hex(5)
        page.locator("#name").fill("Speech QA"); page.locator("#email").fill(f"speech-{marker}@example.invalid")
        page.locator("#password").fill("speech-test-password"); page.locator("#authSubmit").click()
        page.get_by_role("button", name="Đăng xuất", exact=True).wait_for(timeout=15000)
        open_view(page, "home"); page.get_by_text("Kế hoạch học hôm nay").wait_for()

        open_view(page, "grammar"); page.locator(".lesson-card:not([disabled])").first.click()
        page.locator(".speech-panel [data-speech-current]").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        results.append({"name": "grammar_browser_speech_without_tts", "status": "PASS"})

        open_view(page, "skills"); page.locator('[data-skill-tab="listening"]').click()
        page.locator(".skill-card:not([disabled])").first.click(); page.locator("#playSkillAudio").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        page.locator("#backSkills").click(); page.locator('[data-skill-tab="reading"]').click()
        page.locator(".skill-card:not([disabled])").first.click(); page.locator(".speech-panel [data-speech-current]").click()
        assert page.evaluate("window.__speechCalls.at(-1).text.length") > 0 and not tts_requests
        results.append({"name": "listening_reading_browser_speech_without_tts", "status": "PASS"})

        open_view(page, "conversation")
        assert page.get_by_text("Hội thoại trực tiếp hiện chưa khả dụng", exact=False).is_visible()
        page.locator("#speakingMode").select_option("live")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#startSpeaking").click()
        assert not websocket_urls
        assert any(message in page.locator("#speakStatus").inner_text()
                   for message in ("Chưa bắt đầu", "chưa khả dụng"))
        results.append({"name": "live_requires_explicit_confirm_and_no_auto_connect", "status": "PASS"})

        page.set_viewport_size({"width": 390, "height": 844}); page.reload(wait_until="networkidle")
        open_view(page, "learn"); page.locator(".speech-panel").wait_for()
        assert page.evaluate("document.documentElement.scrollWidth-window.innerWidth") <= 1
        results.append({"name": "mobile_390_speech_controls", "status": "PASS"})
        context.close()

        missing = browser.new_context(viewport={"width": 390, "height": 844})
        missing.add_init_script(SPEECH_SPY + "speechSynthesis.getVoices=()=>[];")
        no_voice_page = missing.new_page(); no_voice_tts: list[str] = []
        no_voice_page.on("request", lambda request: no_voice_tts.append(request.url) if "/api/tts" in request.url else None)
        no_voice_page.goto(base_url, wait_until="networkidle"); open_view(no_voice_page, "learn")
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
        unsupported_page.goto(base_url, wait_until="networkidle"); open_view(unsupported_page, "learn")
        assert "chưa hỗ trợ đọc thành tiếng" in unsupported_page.locator('[data-speech-status]').inner_text()
        unsupported_page.locator("#listen").click()
        assert "chưa hỗ trợ đọc thành tiếng" in unsupported_page.locator("#toast").inner_text()
        assert not unsupported_tts
        results.append({"name": "unsupported_web_speech_never_falls_back_to_gemini", "status": "PASS"})
        unsupported.close()

        recognition = browser.new_context(viewport={"width": 390, "height": 844})
        recognition.add_init_script(SPEECH_SPY + """
            navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[{stop(){}}]});
            class MockRecognition {
              start(){this.onstart?.();setTimeout(()=>{this.onresult?.({results:[[{transcript:'A.'}]]});this.onend?.()},10)}
              stop(){this.onend?.()}
            }
            Object.defineProperty(window,'SpeechRecognition',{value:MockRecognition,configurable:true});
            Object.defineProperty(window,'webkitSpeechRecognition',{value:MockRecognition,configurable:true});
        """)
        recognition_page = recognition.new_page(); provider_requests: list[str] = []
        recognition_page.on("request", lambda request: provider_requests.append(request.url) if any(
            marker in request.url for marker in ("/api/pronunciation", "/api/chat", "/api/speaking/")
        ) else None)
        recognition_page.goto(base_url, wait_until="networkidle")
        open_view(recognition_page, "speak")
        assert recognition_page.get_by_text("MIỄN PHÍ · LUYỆN NÓI CƠ BẢN", exact=True).is_visible()
        assert recognition_page.locator("#advancedMic").is_disabled()
        recognition_page.locator("#basicMic").click()
        recognition_page.get_by_text("Mức khớp nội dung nhận diện:", exact=False).wait_for()
        result_text = recognition_page.locator("#basicResult").inner_text()
        assert "100%" in result_text and "không phải điểm phát âm" in result_text
        assert recognition_page.evaluate("speechMatch(\"I'm ready!\",'I am ready')") == 1
        assert not provider_requests
        results.append({"name": "basic_recognition_case_punctuation_no_provider_api", "status": "PASS"})
        recognition.close()

        denied = browser.new_context(viewport={"width": 390, "height": 844})
        denied.add_init_script("""
            class MockRecognition {start(){this.onstart?.()} stop(){this.onend?.()}}
            Object.defineProperty(window,'SpeechRecognition',{value:MockRecognition,configurable:true});
            Object.defineProperty(window,'webkitSpeechRecognition',{value:MockRecognition,configurable:true});
            navigator.mediaDevices.getUserMedia=async()=>{const error=new Error('denied');error.name='NotAllowedError';throw error};
        """)
        denied_page = denied.new_page(); denied_page.goto(base_url, wait_until="networkidle")
        open_view(denied_page, "speak"); denied_page.locator("#basicMic").click()
        assert "từ chối quyền micro" in denied_page.locator("#basicStatus").inner_text()
        results.append({"name": "basic_recognition_permission_denied_message", "status": "PASS"})
        denied.close()

        no_recognition = browser.new_context(viewport={"width": 390, "height": 844})
        no_recognition.add_init_script("""
            Object.defineProperty(window,'SpeechRecognition',{value:undefined,configurable:true});
            Object.defineProperty(window,'webkitSpeechRecognition',{value:undefined,configurable:true});
        """)
        no_recognition_page = no_recognition.new_page(); no_recognition_page.goto(base_url, wait_until="networkidle")
        open_view(no_recognition_page, "speak")
        assert no_recognition_page.locator("#basicMic").is_disabled()
        assert "chưa hỗ trợ nhận diện giọng nói" in no_recognition_page.locator("#basicStatus").inner_text()
        results.append({"name": "unsupported_recognition_has_honest_fallback", "status": "PASS"})
        no_recognition.close()

        gemini = browser.new_context(viewport={"width": 390, "height": 844})
        gemini.add_init_script(SPEECH_SPY + """
            navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[{stop(){}}]});
            class MockMediaRecorder {
              static isTypeSupported(){return true}
              constructor(stream,options){this.state='inactive';this.mimeType=options.mimeType}
              start(){this.state='recording'}
              stop(){
                this.state='inactive';
                const bytes=new Uint8Array([0x1a,0x45,0xdf,0xa3,...new Array(256).fill(0)]);
                this.ondataavailable?.({data:new Blob([bytes],{type:this.mimeType})});
                this.onstop?.();
              }
            }
            Object.defineProperty(window,'MediaRecorder',{value:MockMediaRecorder,configurable:true});
        """)
        gemini_page = gemini.new_page(); assessment_requests: list[str] = []
        gemini_page.route("**/api/runtime-config", lambda route: route.fulfill(json={
            "gemini_live_enabled": False, "gemini_text_enabled": False,
            "gemini_pronunciation_enabled": True, "gemini_pronunciation_daily_limit": 5,
            "browser_speech_only": True, "azure_pronunciation_enabled": False,
        }))

        def mock_assessment(route):
            assessment_requests.append(route.request.url)
            route.fulfill(json={"target": "a", "model": "gemini-2.5-flash", "cached": False, "feedback": {
                "target_result": "clear_match", "overall_vi": "Bản ghi nghe rõ.",
                "clear_parts": ["Từ mẫu"], "improve_parts": [],
                "correction_steps_vi": ["Nghe và đọc lại."], "retry_vi": "Thử lại khi sẵn sàng.",
                "needs_retry": False, "disclaimer_vi": "Không phải điểm thi.",
            }})

        gemini_page.route("**/api/pronunciation/ai", mock_assessment)
        gemini_page.goto(base_url, wait_until="networkidle")
        gemini_page.locator("#authBtn").click(); gemini_page.locator("#switchAuth").click()
        marker = secrets.token_hex(5)
        gemini_page.locator("#name").fill("Gemini Speech QA")
        gemini_page.locator("#email").fill(f"gemini-speech-{marker}@example.invalid")
        gemini_page.locator("#password").fill("speech-test-password")
        gemini_page.locator("#authSubmit").click()
        gemini_page.get_by_role("button", name="Đăng xuất", exact=True).wait_for(timeout=15000)
        open_view(gemini_page, "speak")
        assert gemini_page.get_by_text("PHẢN HỒI NÂNG CAO · SẴN SÀNG", exact=True).is_visible()
        assert not assessment_requests
        gemini_page.locator("#geminiRecord").click(); gemini_page.wait_for_timeout(400)
        gemini_page.locator("#geminiStop").click()
        gemini_page.get_by_text("Hãy nghe lại trước khi nhận phản hồi", exact=False).wait_for()
        assert gemini_page.locator("#geminiAssess").is_enabled() and not assessment_requests
        gemini_page.locator("#geminiAssess").click()
        gemini_page.get_by_text("Bản ghi nghe rõ.", exact=True).wait_for()
        assert len(assessment_requests) == 1
        assert "Không phải điểm thi." in gemini_page.locator("#geminiResult").inner_text()
        results.append({"name": "gemini_audio_only_sent_after_explicit_assess", "status": "PASS"})
        gemini.close(); browser.close()

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
