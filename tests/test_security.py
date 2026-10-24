import base64
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app as application
from migrations import run_migrations


def setup_app(tmp_path, monkeypatch):
    database = tmp_path / "security.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    application._rate.clear()
    return TestClient(application.app), database


def seed_pronunciation_word(database):
    with sqlite3.connect(database) as con:
        con.execute("ATTACH DATABASE ? AS bundled", (str(application.ROOT / "speakseed.db"),))
        columns = "word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at"
        con.execute(f"INSERT INTO library_words({columns}) SELECT {columns} FROM bundled.library_words WHERE reviewed=1 LIMIT 1")
        con.commit()
        return con.execute("SELECT id FROM library_words LIMIT 1").fetchone()[0]


def fake_webm(marker=0):
    return base64.b64encode(b"\x1aE\xdf\xa3" + bytes([marker]) + b"\0" * 256).decode()


def valid_pronunciation_feedback():
    return json.dumps({
        "target_result": "clear_match", "overall_vi": "Bạn đọc đúng từ mẫu và âm thanh khá rõ.",
        "clear_parts": ["Từ mục tiêu nghe rõ"], "improve_parts": [],
        "correction_steps_vi": ["Nghe mẫu một lần rồi đọc lại chậm rãi."],
        "retry_vi": "Bạn có thể ghi lại để luyện độ tự nhiên.", "needs_retry": False,
    }, ensure_ascii=False)


def test_cookie_session_is_httponly_and_csrf_protected(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TRANSPORT", "cookie")
    client, _ = setup_app(tmp_path, monkeypatch)
    response = client.post("/api/register", json={"name": "Lan", "email": "lan@example.com", "password": "correct-horse"})
    assert response.status_code == 200 and "token" not in response.json()
    cookies = response.headers.get("set-cookie", "")
    assert "ss_session=" in cookies and "HttpOnly" in cookies and "SameSite=strict" in cookies
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/profile", json={"current_level": "A1"}).status_code == 403
    csrf = client.cookies.get("ss_csrf")
    assert client.post("/api/profile", headers={"X-CSRF-Token": csrf}, json={"current_level": "A1"}).status_code == 200


def test_origin_headers_and_sensitive_headers(tmp_path, monkeypatch):
    client, _ = setup_app(tmp_path, monkeypatch)
    blocked = client.post("/api/login", headers={"Origin": "https://evil.invalid"}, json={"email": "x@y.com", "password": "password1"})
    assert blocked.status_code == 403
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_login_bruteforce_limit_and_sql_injection_input(tmp_path, monkeypatch):
    client, database = setup_app(tmp_path, monkeypatch)
    credentials = {"name": "Lan", "email": "lan@example.com", "password": "correct-horse"}
    assert client.post("/api/register", json=credentials).status_code == 200
    for _ in range(8):
        assert client.post("/api/login", json={"email": credentials["email"], "password": "wrong-pass"}).status_code == 401
    limited = client.post("/api/login", json={"email": credentials["email"], "password": "wrong-pass"})
    assert limited.status_code == 429 and limited.headers["retry-after"] == "900"
    attack = client.post("/api/login", json={"email": "' OR 1=1 --@example.com", "password": "wrong-pass"})
    assert attack.status_code in {401, 429}
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_ai_usage_endpoint_is_account_scoped(tmp_path, monkeypatch):
    client, database = setup_app(tmp_path, monkeypatch)
    first = client.post("/api/register", json={"name": "A", "email": "a@example.com", "password": "correct-horse"}).json()["token"]
    second = client.post("/api/register", json={"name": "B", "email": "b@example.com", "password": "correct-horse"}).json()["token"]
    with sqlite3.connect(database) as con:
        user_id = con.execute("SELECT id FROM users WHERE email='a@example.com'").fetchone()[0]
        con.execute("INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,input_units,created_at) VALUES(?,?,'tutor','succeeded','test',10,datetime('now'))", (user_id, "hash"))
    one = client.get("/api/usage", headers={"Authorization": "Bearer " + first}).json()
    two = client.get("/api/usage", headers={"Authorization": "Bearer " + second}).json()
    assert sum(item["requests"] for item in one["items"]) == 1
    assert two["items"] == []


def test_ai_account_quota_is_enforced_before_provider_call(tmp_path, monkeypatch):
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={"name": "A", "email": "a@example.com", "password": "correct-horse"}).json()["token"]
    with sqlite3.connect(database) as con:
        user_id = con.execute("SELECT id FROM users").fetchone()[0]
        created = datetime.now(timezone.utc).isoformat()
        con.executemany("INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,created_at) VALUES(?,?,'tutor','succeeded','test',?)", [(user_id, f"h{i}", created) for i in range(40)])
    response = client.post("/api/chat", headers={"Authorization": "Bearer " + token}, json={"message": "Hello"})
    assert response.status_code == 429 and response.headers["retry-after"] == "3600"


def test_login_replaces_attacker_supplied_session_and_logout_revokes_it(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TRANSPORT", "cookie")
    client, _ = setup_app(tmp_path, monkeypatch)
    credentials = {"name": "Lan", "email": "rotation@example.com", "password": "correct-horse"}
    assert client.post("/api/register", json=credentials).status_code == 200
    csrf = client.cookies.get("ss_csrf")
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    client.cookies.set("ss_session", "attacker-fixed-session", domain="testserver.local", path="/")
    response = client.post("/api/login", json={"email": credentials["email"], "password": credentials["password"]})
    assert response.status_code == 200
    issued = client.cookies.get("ss_session")
    assert issued and issued != "attacker-fixed-session"
    csrf = client.cookies.get("ss_csrf")
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    replay = TestClient(application.app)
    replay.cookies.set("ss_session", issued, domain="testserver.local", path="/")
    assert replay.get("/api/me").status_code == 401


def test_forwarded_for_does_not_bypass_login_limit_without_trusted_proxy(tmp_path, monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    client, _ = setup_app(tmp_path, monkeypatch)
    credentials = {"name": "Lan", "email": "rate@example.com", "password": "correct-horse"}
    assert client.post("/api/register", json=credentials).status_code == 200
    for attempt in range(8):
        response = client.post(
            "/api/login",
            headers={"X-Forwarded-For": f"198.51.100.{attempt + 1}"},
            json={"email": credentials["email"], "password": "wrong-pass"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/login",
        headers={"X-Forwarded-For": "203.0.113.99"},
        json={"email": credentials["email"], "password": "wrong-pass"},
    )
    assert limited.status_code == 429


def test_forwarded_for_requires_explicitly_trusted_direct_peer(monkeypatch):
    from starlette.requests import Request

    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,172.16.0.0/12")
    headers = [(b"x-forwarded-for", b"198.51.100.25")]
    untrusted = Request({"type": "http", "method": "GET", "path": "/", "headers": headers,
                         "client": ("203.0.113.10", 50000), "server": ("test", 80), "scheme": "http"})
    trusted = Request({"type": "http", "method": "GET", "path": "/", "headers": headers,
                       "client": ("172.20.0.3", 50000), "server": ("test", 80), "scheme": "http"})
    malformed = Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-forwarded-for", b"not-an-ip")],
                         "client": ("172.20.0.3", 50000), "server": ("test", 80), "scheme": "http"})
    assert application.request_ip(untrusted) == "203.0.113.10"
    assert application.request_ip(trusted) == "198.51.100.25"
    assert application.request_ip(malformed) == "172.20.0.3"


def test_vercel_platform_client_ip_header_is_used_only_on_vercel(monkeypatch):
    from starlette.requests import Request

    headers = [(b"x-vercel-forwarded-for", b"198.51.100.42")]
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": headers,
                       "client": ("10.0.0.7", 50000), "server": ("test", 80), "scheme": "https"})
    monkeypatch.delenv("VERCEL", raising=False)
    assert application.request_ip(request) == "10.0.0.7"
    monkeypatch.setenv("VERCEL", "1")
    assert application.request_ip(request) == "198.51.100.42"


def test_runtime_config_keeps_live_off_by_default(monkeypatch):
    monkeypatch.delenv("GEMINI_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    response = TestClient(application.app).get("/api/runtime-config")
    assert response.status_code == 200
    assert response.json() == {
        "gemini_live_enabled": False,
        "gemini_text_enabled": False,
        "gemini_pronunciation_enabled": False,
        "gemini_pronunciation_daily_limit": 5,
        "gemini_project_count": 0,
        "browser_speech_only": True,
        "azure_pronunciation_enabled": False,
    }


def test_unconfigured_advanced_pronunciation_does_not_start_provider_usage(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={
        "name": "Speech", "email": "speech@example.com", "password": "correct-horse"
    }).json()["token"]
    word_id = seed_pronunciation_word(database)
    response = client.post("/api/pronunciation", headers={"Authorization": "Bearer " + token},
                           json={"word_id": word_id, "wav_base64": "not-used"})
    assert response.status_code == 503
    assert "Luyện nói cơ bản" in response.json()["detail"]
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0] == 0


def test_gemini_pronunciation_is_explicit_validated_and_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_PRONUNCIATION_ENABLED", "true")
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={"name": "AI", "email": "ai@example.com", "password": "correct-horse"}).json()["token"]
    word_id = seed_pronunciation_word(database)
    calls = []

    def mocked_provider(target, audio, mime, key, model):
        calls.append((target, mime, key, model))
        return valid_pronunciation_feedback(), 42

    monkeypatch.setattr(application, "gemini_pronunciation_generate", mocked_provider)
    payload = {"word_id": word_id, "target_kind": "word", "audio_base64": fake_webm(),
               "mime_type": "audio/webm;codecs=opus", "duration_ms": 1200}
    response = client.post("/api/pronunciation/ai", headers={"Authorization": "Bearer " + token}, json=payload)
    assert response.status_code == 200
    assert response.json()["feedback"]["target_result"] == "clear_match"
    assert response.json()["cached"] is False and len(calls) == 1
    duplicate = client.post("/api/pronunciation/ai", headers={"Authorization": "Bearer " + token}, json=payload)
    assert duplicate.status_code == 200 and duplicate.json()["cached"] is True and len(calls) == 1
    with sqlite3.connect(database) as con:
        row = con.execute("SELECT status,request_fingerprint,result_json FROM ai_usage WHERE feature='pronunciation'").fetchone()
        assert row[0] == "succeeded" and len(row[1]) == 64 and payload["audio_base64"] not in row[2]


def test_gemini_pronunciation_rejects_bad_audio_before_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_PRONUNCIATION_ENABLED", "true")
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={"name": "AI", "email": "bad@example.com", "password": "correct-horse"}).json()["token"]
    word_id = seed_pronunciation_word(database)
    monkeypatch.setattr(application, "gemini_pronunciation_generate", lambda *args: (_ for _ in ()).throw(AssertionError("provider called")))
    response = client.post("/api/pronunciation/ai", headers={"Authorization": "Bearer " + token}, json={
        "word_id": word_id, "target_kind": "word", "audio_base64": base64.b64encode(b"not audio" * 20).decode(),
        "mime_type": "audio/webm", "duration_ms": 1000,
    })
    assert response.status_code == 400
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0] == 0


def test_gemini_pronunciation_daily_quota_and_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_PRONUNCIATION_ENABLED", "true")
    monkeypatch.setenv("GEMINI_PRONUNCIATION_DAILY_LIMIT", "5")
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={"name": "AI", "email": "quota@example.com", "password": "correct-horse"}).json()["token"]
    word_id = seed_pronunciation_word(database)
    monkeypatch.setattr(application, "gemini_pronunciation_generate", lambda *args: (valid_pronunciation_feedback(), 20))
    headers = {"Authorization": "Bearer " + token}
    for marker in range(5):
        response = client.post("/api/pronunciation/ai", headers=headers, json={"word_id": word_id, "target_kind": "word",
            "audio_base64": fake_webm(marker), "mime_type": "audio/webm", "duration_ms": 1000})
        assert response.status_code == 200
    limited = client.post("/api/pronunciation/ai", headers=headers, json={"word_id": word_id, "target_kind": "word",
        "audio_base64": fake_webm(9), "mime_type": "audio/webm", "duration_ms": 1000})
    assert limited.status_code == 429 and limited.headers["retry-after"] == "86400"

    other = client.post("/api/register", json={"name": "Other", "email": "invalid-json@example.com", "password": "correct-horse"}).json()["token"]
    monkeypatch.setenv("GEMINI_PRONUNCIATION_IP_DAILY_LIMIT", "50")
    monkeypatch.setattr(application, "gemini_pronunciation_generate", lambda *args: ("{not-json", 1))
    malformed = client.post("/api/pronunciation/ai", headers={"Authorization": "Bearer " + other}, json={
        "word_id": word_id, "target_kind": "word", "audio_base64": fake_webm(10),
        "mime_type": "audio/webm", "duration_ms": 1000})
    assert malformed.status_code == 502
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT status FROM ai_usage WHERE user_id=(SELECT id FROM users WHERE email='invalid-json@example.com')").fetchone()[0] == "failed"


def test_gemini_provider_quota_error_has_no_automatic_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.setenv("GEMINI_PRONUNCIATION_ENABLED", "true")
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={"name": "AI", "email": "provider-quota@example.com", "password": "correct-horse"}).json()["token"]
    word_id = seed_pronunciation_word(database)
    calls = []

    def quota_error(*args):
        calls.append(args)
        raise application.urllib.error.HTTPError("https://provider.invalid", 429, "quota", {}, None)

    monkeypatch.setattr(application, "gemini_pronunciation_generate", quota_error)
    response = client.post("/api/pronunciation/ai", headers={"Authorization": "Bearer " + token}, json={
        "word_id": word_id, "target_kind": "word", "audio_base64": fake_webm(12),
        "mime_type": "audio/webm", "duration_ms": 1000})
    assert response.status_code == 429 and len(calls) == 1
    assert "Luyện nói cơ bản" in response.json()["detail"]


def test_production_cookie_hsts_cors_and_trusted_host(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "stage7-test-secret-with-more-than-32-characters")
    monkeypatch.setenv("AUTH_TRANSPORT", "cookie")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    client, _ = setup_app(tmp_path, monkeypatch)
    response = client.post("/api/register", json={"name": "Lan", "email": "secure@example.com", "password": "correct-horse"})
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    assert response.headers["strict-transport-security"].startswith("max-age=31536000")
    assert client.get("/api/health/live", headers={"Host": "evil.invalid"}).status_code == 400
    preflight = client.options("/api/profile", headers={
        "Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:8000"


def test_exact_production_host_allows_root_favicon_and_readiness(tmp_path, monkeypatch):
    client, _ = setup_app(tmp_path, monkeypatch)
    headers = {"Host": "speak-seed.vercel.app"}
    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/favicon.ico", headers=headers).status_code == 204
    ready = client.get("/api/health/ready", headers=headers)
    assert ready.status_code != 400
    assert ready.text != "Invalid host header"


def test_vercel_system_hosts_are_added_without_global_wildcard(monkeypatch):
    from fastapi import FastAPI
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    monkeypatch.setenv("PRIMARY_HOST", "speak-seed.vercel.app")
    monkeypatch.setenv("ALLOWED_HOSTS", "beta.speakseed.example")
    monkeypatch.setenv("VERCEL_URL", "speak-seed-a1b2c3.vercel.app")
    monkeypatch.setenv("VERCEL_BRANCH_URL", "speak-seed-preview-team.vercel.app")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "speak-seed.vercel.app")
    hosts = application.configured_deployment_hosts()
    assert hosts == [
        "localhost", "127.0.0.1", "testserver", "speak-seed.vercel.app",
        "beta.speakseed.example", "speak-seed-a1b2c3.vercel.app",
        "speak-seed-preview-team.vercel.app",
    ]
    assert "*" not in hosts
    preview_app = FastAPI()
    preview_app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @preview_app.get("/")
    def preview_home():
        return {"ok": True}

    client = TestClient(preview_app)
    assert client.get("/", headers={"Host": "speak-seed-a1b2c3.vercel.app"}).status_code == 200
    assert client.get("/", headers={"Host": "attacker.vercel.app"}).status_code == 400


def test_host_allowlist_rejects_wildcard(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "*")
    with pytest.raises(RuntimeError, match="Hostname không hợp lệ"):
        application.configured_deployment_hosts()


def test_legacy_tts_endpoint_is_hard_disabled_without_usage_or_provider_call(tmp_path, monkeypatch):
    client, database = setup_app(tmp_path, monkeypatch)

    def forbidden_provider_call(*args, **kwargs):
        raise AssertionError("The disabled TTS route must never call an external provider")

    monkeypatch.setattr(application.urllib.request, "urlopen", forbidden_provider_call)
    response = client.post("/api/tts", json={"text": "Hello", "voice": "Kore", "speed": 1})
    assert response.status_code == 410
    assert "nút Nghe" in response.json()["detail"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ai_usage WHERE feature='tts'").fetchone()[0] == 0


def test_legacy_gemini_key_helper_returns_first_configured_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEYS", "first-key,second-key")
    assert application.gemini_key() == "first-key"
    assert application.gemini_key() == "first-key"


def test_beginner_ai_limits_are_account_scoped_and_explain_non_ai_continuity(tmp_path, monkeypatch):
    client, database = setup_app(tmp_path, monkeypatch)
    token = client.post("/api/register", json={"name": "A", "email": "limit@example.com", "password": "correct-horse"}).json()["token"]
    with sqlite3.connect(database) as con:
        user_id = con.execute("SELECT id FROM users WHERE email='limit@example.com'").fetchone()[0]
        created = datetime.now(timezone.utc).isoformat()
        con.executemany("INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,created_at) VALUES(?,?,'tutor','succeeded','test',?)", [(user_id, f"h{i}", created) for i in range(10)])
    response = client.post("/api/chat", headers={"Authorization": "Bearer " + token}, json={"message": "Hello"})
    assert response.status_code == 429
    assert "từ vựng, ngữ pháp, nghe và đọc vẫn hoạt động bình thường" in response.json()["detail"]

