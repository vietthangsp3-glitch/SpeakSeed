import sqlite3
import urllib.error

import pytest

import app as application
from gemini_pool import parse_gemini_projects
from migrations import run_migrations


@pytest.mark.parametrize("size", [1, 15, 30, 100])
def test_dynamic_key_list_has_no_business_cap(size):
    projects = parse_gemini_projects("", ",".join(f"key-{index}" for index in range(size)))
    assert len(projects) == size
    assert len({item.project_id for item in projects}) == size
    assert "key-0" not in repr(projects[0])


def test_json_projects_support_labels_weights_and_primary_compatibility():
    projects = parse_gemini_projects("legacy-primary", """[
      {"project":"school-a","key":"key-a","weight":3},
      {"project":"school-b","key":"key-b"},
      "key-c",
      "key-a"
    ]""")
    assert [item.label for item in projects[:3]] == ["primary", "school-a", "school-b"]
    assert [item.weight for item in projects[:3]] == [1, 3, 1]
    assert len(projects) == 4  # duplicate key-a is removed


def test_project_pool_tracks_each_project_without_persisting_keys(tmp_path, monkeypatch):
    database = tmp_path / "pool.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEYS", "project-one=fake-secret-one,project-two=fake-secret-two")
    monkeypatch.setenv("GEMINI_FAILOVER_MAX_ATTEMPTS", "2")
    calls = []

    def provider(key):
        calls.append(key)
        if len(calls) == 1:
            raise urllib.error.HTTPError("https://provider.invalid", 429, "quota", {}, None)
        return "ok"

    assert application.gemini_pool_call(provider) == "ok"
    assert len(calls) == 2 and len(set(calls)) == 2
    with sqlite3.connect(database) as con:
        rows = con.execute("SELECT project_id,project_label,selection_count,success_count,failure_count,quota_failure_count,cooldown_until FROM gemini_project_state ORDER BY project_label").fetchall()
        stored = " ".join(str(value) for row in rows for value in row)
    assert len(rows) == 2
    assert sum(row[2] for row in rows) == 2
    assert sum(row[3] for row in rows) == 1
    assert sum(row[4] for row in rows) == 1
    assert sum(row[5] for row in rows) == 1
    assert "fake-secret" not in stored


def test_pool_configuration_can_change_without_code_changes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "legacy")
    monkeypatch.setenv("GEMINI_API_KEYS", "a=one,b=two")
    assert len(application.gemini_projects()) == 3
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEYS", "x=three")
    assert [(item.label, item.key) for item in application.gemini_projects()] == [("x", "three")]


def test_weighted_distribution_uses_project_weights(tmp_path, monkeypatch):
    database = tmp_path / "weighted-pool.db"
    run_migrations(database, application.ROOT / "migrations")
    monkeypatch.setattr(application, "DB", database)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEYS", """[
      {"project":"larger-quota","key":"fake-large","weight":3},
      {"project":"smaller-quota","key":"fake-small","weight":1}
    ]""")

    selected = [application.gemini_pool_call(lambda key: key) for _ in range(40)]

    assert selected.count("fake-large") == 30
    assert selected.count("fake-small") == 10
