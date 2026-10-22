import json
import sqlite3
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app as application
from migrations import run_migrations


class FakeLiveUpstream:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, value):
        self.sent.append(json.loads(value))

    def __aiter__(self):
        async def messages():
            yield json.dumps({"serverContent": {"outputTranscription": {"text": "Hello from Live."}}})
        return messages()

    async def close(self):
        self.closed = True


def test_live_proxy_keeps_audio_mode_and_bounded_session_without_real_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "server-only-test-key")
    database = tmp_path / "live.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    monkeypatch.setattr(application, "gemini_key", lambda: "server-only-test-key")
    monkeypatch.setenv("GEMINI_LIVE_MAX_SECONDS", "30")
    upstream = FakeLiveUpstream()

    import websockets
    async def fake_connect(*args, **kwargs):
        assert kwargs["open_timeout"] == 15
        return upstream
    monkeypatch.setattr(websockets, "connect", fake_connect)

    client = TestClient(application.app)
    token = client.post("/api/register", json={
        "name": "Live QA", "email": "live@example.com", "password": "correct-horse"
    }).json()["token"]
    with client.websocket_connect("/ws/speaking/live", headers={"Origin": "http://localhost:8000"}) as socket:
        socket.send_json({"token": token, "level": "A1", "topic": "Daily life"})
        assert socket.receive_json()["status"] == "connecting"
        payload = json.loads(socket.receive_text())
        assert payload["serverContent"]["outputTranscription"]["text"] == "Hello from Live."

    setup = upstream.sent[0]["setup"]
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert upstream.closed is True
    with sqlite3.connect(database) as connection:
        usage = connection.execute(
            "SELECT feature,status FROM ai_usage WHERE feature='speaking_live'"
        ).fetchone()
        assert usage == ("speaking_live", "succeeded")
        assert connection.execute(
            "SELECT COUNT(*) FROM learning_events WHERE event_type='speaking_live'"
        ).fetchone()[0] == 1


def test_live_quota_is_rejected_before_provider_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "server-only-test-key")
    database = tmp_path / "live-quota.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    monkeypatch.setenv("AUTH_TRANSPORT", "bearer")
    monkeypatch.setattr(application, "gemini_key", lambda: "server-only-test-key")
    client = TestClient(application.app)
    token = client.post("/api/register", json={
        "name": "Quota QA", "email": "quota-live@example.com", "password": "correct-horse"
    }).json()["token"]
    with sqlite3.connect(database) as connection:
        user_id = connection.execute("SELECT id FROM users WHERE email='quota-live@example.com'").fetchone()[0]
        stamp = datetime.now(timezone.utc).isoformat()
        connection.executemany("""INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,created_at)
            VALUES(?,?,'speaking_live','succeeded','test',?)""", [(user_id, f"h{i}", stamp) for i in range(10)])

    import websockets
    async def forbidden_connect(*args, **kwargs):
        raise AssertionError("Provider must not be contacted after quota rejection")
    monkeypatch.setattr(websockets, "connect", forbidden_connect)

    with client.websocket_connect("/ws/speaking/live", headers={"Origin": "http://localhost:8000"}) as socket:
        socket.send_json({"token": token, "level": "A1", "topic": "Daily life"})
        assert "quota" in socket.receive_json()["error"].lower()
    with sqlite3.connect(database) as connection:
        assert connection.execute("""SELECT COUNT(*) FROM ai_usage
            WHERE user_id=? AND feature='speaking_live' AND status='quota_rejected'""", (user_id,)).fetchone()[0] == 1


def test_live_network_failure_is_metered_as_failed_without_learning_event(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "server-only-test-key")
    database = tmp_path / "live-network.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    monkeypatch.setenv("AUTH_TRANSPORT", "bearer")
    monkeypatch.setattr(application, "gemini_key", lambda: "server-only-test-key")
    client = TestClient(application.app)
    token = client.post("/api/register", json={
        "name": "Network QA", "email": "network-live@example.com", "password": "correct-horse"
    }).json()["token"]

    import websockets
    async def failing_connect(*args, **kwargs):
        raise OSError("simulated network failure")
    monkeypatch.setattr(websockets, "connect", failing_connect)

    with client.websocket_connect("/ws/speaking/live", headers={"Origin": "http://localhost:8000"}) as socket:
        socket.send_json({"token": token, "level": "A1", "topic": "Daily life"})
        assert "Không kết nối được Gemini Live" in socket.receive_json()["error"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM ai_usage WHERE feature='speaking_live'").fetchone()[0] == "failed"
        assert connection.execute("SELECT COUNT(*) FROM learning_events WHERE event_type='speaking_live'").fetchone()[0] == 0


def test_live_is_disabled_before_auth_or_provider_by_default(monkeypatch):
    monkeypatch.setenv("GEMINI_LIVE_ENABLED", "false")
    with TestClient(application.app).websocket_connect(
        "/ws/speaking/live", headers={"Origin": "http://localhost:8000"}
    ) as socket:
        assert "đang tắt" in socket.receive_json()["error"]
