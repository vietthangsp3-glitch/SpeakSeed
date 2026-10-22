from pathlib import Path

import pytest

from database import configured_database


def test_vercel_refuses_ephemeral_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL PostgreSQL bắt buộc"):
        configured_database(tmp_path / "never-create.db")


def test_vercel_accepts_external_postgres_url(monkeypatch, tmp_path):
    url = "postgresql://user:secret@example.invalid/speakseed?sslmode=require"
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", url)
    assert configured_database(Path(tmp_path / "local.db")) == url
