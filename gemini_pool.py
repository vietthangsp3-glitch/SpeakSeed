"""Dynamic Gemini project configuration without persisting or logging API keys."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeminiProject:
    project_id: str
    label: str
    key: str = field(repr=False)
    weight: int = 1


def _safe_label(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")[:60]
    return cleaned or fallback


def _project(raw_key: str, label: str = "", weight: int = 1) -> GeminiProject | None:
    key = raw_key.strip()
    if not key:
        return None
    fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16]
    safe = _safe_label(label, f"key-{fingerprint}")
    # The durable identifier cannot reveal the key and stays stable across restarts.
    project_id = "gemini-" + hashlib.sha256((safe + "\0" + fingerprint).encode()).hexdigest()[:20]
    return GeminiProject(project_id, safe, key, max(1, min(int(weight), 1000)))


def parse_gemini_projects(primary_key: str = "", dynamic_value: str = "") -> list[GeminiProject]:
    """Parse an unbounded key list.

    Supported forms:
    - comma/semicolon/newline separated keys;
    - ``project_alias=key`` entries;
    - JSON strings or objects: ``[{"project":"p1","key":"...","weight":2}]``.
    Duplicate key values are removed while preserving configuration order.
    """
    entries: list[tuple[str, str, int]] = []
    if primary_key.strip():
        entries.append(("primary", primary_key.strip(), 1))
    raw = dynamic_value.strip()
    if raw:
        parsed = None
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, list):
            for index, item in enumerate(parsed, 1):
                if isinstance(item, str):
                    entries.append(("", item, 1))
                elif isinstance(item, dict):
                    entries.append((str(item.get("project") or item.get("label") or f"project-{index}"),
                                    str(item.get("key") or ""), item.get("weight") or 1))
        else:
            for item in re.split(r"[,;\r\n]+", raw):
                item = item.strip()
                if not item:
                    continue
                if "=" in item:
                    label, key = item.split("=", 1)
                    entries.append((label, key, 1))
                else:
                    entries.append(("", item, 1))
    result: list[GeminiProject] = []
    seen: set[str] = set()
    for label, key, weight in entries:
        if not key.strip() or key.strip() in seen:
            continue
        try:
            project = _project(key, label, int(weight))
        except (TypeError, ValueError):
            project = _project(key, label, 1)
        if project:
            result.append(project); seen.add(key.strip())
    return result


def retryable_provider_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    return (code in {429, 500, 502, 503, 504} or isinstance(exc, (TimeoutError, ConnectionError))
            or type(exc).__name__ in {"URLError", "TimeoutError"})
