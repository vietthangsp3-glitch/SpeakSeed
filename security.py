"""Security primitives shared by authentication and metered AI endpoints."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat()


def app_secret() -> bytes:
    value = os.getenv("APP_SECRET", "").strip()
    if value:
        if os.getenv("APP_ENV", "development") == "production" and len(value) < 32:
            raise RuntimeError("APP_SECRET production phải có ít nhất 32 ký tự")
        return value.encode()
    if os.getenv("APP_ENV", "development") == "production":
        raise RuntimeError("APP_SECRET bắt buộc trong production")
    # Stable development-only value so local sessions survive reload. Never use in production.
    return b"speakseed-development-only-change-me"


def privacy_hash(value: str) -> str:
    return hmac.new(app_secret(), value.strip().casefold().encode(), hashlib.sha256).hexdigest()


def request_ip(request: Request) -> str:
    peer = (request.client.host if request.client else "unknown")[:100]
    # Vercel overwrites this platform header with the public client address.
    # Only honor it when the runtime itself declares VERCEL=1; local/proxied
    # deployments continue to require an explicitly trusted direct peer.
    if os.getenv("VERCEL") == "1":
        forwarded = request.headers.get("x-vercel-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    if os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true" and _trusted_proxy(peer):
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return peer


def _trusted_proxy(peer: str) -> bool:
    """Only accept forwarding headers from an explicitly trusted direct peer."""
    configured = os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for raw in configured:
        value = raw.strip()
        if not value:
            continue
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            logging.getLogger("speakseed.security").warning("Ignoring invalid TRUSTED_PROXY_IPS entry")
            continue
        if address in network:
            return True
    return False


def check_auth_limit(con, subjects: list[str], action: str) -> None:
    current = stamp()
    for subject in subjects:
        row = con.execute(
            "SELECT blocked_until FROM auth_rate_limits WHERE subject_hash=? AND action=?",
            (privacy_hash(subject), action),
        ).fetchone()
        if row and row["blocked_until"] and row["blocked_until"] > current:
            raise HTTPException(429, "Quá nhiều lần thử. Vui lòng thử lại sau.", headers={"Retry-After": "900"})


def record_auth_failure(con, subjects: list[str], action: str, *, limit: int = 8,
                        window_seconds: int = 900, block_seconds: int = 900) -> None:
    current = utcnow(); current_text = stamp(current)
    window_floor = current - timedelta(seconds=window_seconds)
    for subject in subjects:
        key = privacy_hash(subject)
        row = con.execute(
            "SELECT window_started_at,hits FROM auth_rate_limits WHERE subject_hash=? AND action=?",
            (key, action),
        ).fetchone()
        if not row or row["window_started_at"] < stamp(window_floor):
            con.execute("""INSERT INTO auth_rate_limits(subject_hash,action,window_started_at,hits,blocked_until)
                VALUES(?,?,?,1,NULL) ON CONFLICT(subject_hash,action) DO UPDATE SET
                window_started_at=excluded.window_started_at,hits=1,blocked_until=NULL""",
                (key, action, current_text))
            continue
        hits = row["hits"] + 1
        blocked = stamp(current + timedelta(seconds=block_seconds)) if hits >= limit else None
        con.execute("UPDATE auth_rate_limits SET hits=?,blocked_until=? WHERE subject_hash=? AND action=?",
                    (hits, blocked, key, action))


def clear_auth_subject(con, subject: str, action: str) -> None:
    con.execute("DELETE FROM auth_rate_limits WHERE subject_hash=? AND action=?",
                (privacy_hash(subject), action))


AI_LIMITS = {
    "speaking_turn": (40, 120),
    "speaking_live": (10, 30),
    "speaking_evaluation": (10, 30),
    "writing_feedback": (3, 12),
    "tts": (80, 120),
    "tutor": (10, 30),
    "pronunciation": (30, 90),
}


def start_ai_usage(con, *, user_id: int | None, ip: str, feature: str, model: str,
                   input_units: int = 0) -> int:
    account_limit, ip_limit = AI_LIMITS[feature]
    since = stamp(utcnow() - timedelta(hours=1)); ip_digest = privacy_hash(ip)
    if user_id is not None:
        count = con.execute("""SELECT COUNT(*) total FROM ai_usage WHERE user_id=? AND feature=?
            AND created_at>=? AND status<>'quota_rejected'""", (user_id, feature, since)).fetchone()["total"]
        if count >= account_limit:
            con.execute("""INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,input_units,error_code,created_at,finished_at)
                VALUES(?,?,?,'quota_rejected',?,?, 'account_limit',?,?)""",
                (user_id, ip_digest, feature, model, input_units, stamp(), stamp()))
            raise HTTPException(429, "Bạn đã dùng hết lượt AI của tính năng này trong giờ. Từ vựng, ngữ pháp, nghe và đọc vẫn dùng bình thường; hãy thử AI lại sau.", headers={"Retry-After": "3600"})
    count = con.execute("""SELECT COUNT(*) total FROM ai_usage WHERE ip_hash=? AND feature=?
        AND created_at>=? AND status<>'quota_rejected'""", (ip_digest, feature, since)).fetchone()["total"]
    if count >= ip_limit:
        con.execute("""INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,input_units,error_code,created_at,finished_at)
            VALUES(?,?,?,'quota_rejected',?,?, 'ip_limit',?,?)""",
            (user_id, ip_digest, feature, model, input_units, stamp(), stamp()))
        raise HTTPException(429, "Thiết bị đã dùng hết lượt AI của tính năng này trong giờ. Các bài học không dùng AI vẫn hoạt động bình thường; hãy thử AI lại sau.", headers={"Retry-After": "3600"})
    cursor = con.execute("""INSERT INTO ai_usage(user_id,ip_hash,feature,status,model,input_units,created_at)
        VALUES(?,?,?,'started',?,?,?)""", (user_id, ip_digest, feature, model, input_units, stamp()))
    return cursor.lastrowid


def finish_ai_usage(con, usage_id: int, *, succeeded: bool, output_units: int = 0,
                    latency_ms: int = 0, error_code: str = "") -> None:
    row = con.execute("SELECT feature,input_units FROM ai_usage WHERE id=?", (usage_id,)).fetchone()
    if not row:
        return
    input_rate = float(os.getenv("GEMINI_INPUT_USD_PER_MILLION", "0") or 0)
    output_rate = float(os.getenv("GEMINI_OUTPUT_USD_PER_MILLION", "0") or 0)
    if row["feature"] == "tts":
        input_rate = float(os.getenv("GEMINI_TTS_USD_PER_MILLION_CHARS", "0") or 0)
        output_rate = 0
    estimated = row["input_units"] * input_rate / 1_000_000 + output_units * output_rate / 1_000_000
    con.execute("""UPDATE ai_usage SET status=?,output_units=?,estimated_cost_usd=?,latency_ms=?,
        error_code=?,finished_at=? WHERE id=?""",
        ("succeeded" if succeeded else "failed", max(0, output_units), max(0, estimated),
         max(0, latency_ms), error_code[:80], stamp(), usage_id))


def safe_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return f"http_{code}" if code else type(exc).__name__[:80]


def configure_logging() -> None:
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
