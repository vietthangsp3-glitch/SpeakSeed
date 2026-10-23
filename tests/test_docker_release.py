import sqlite3
import shutil

import app as application
from tools.prepare_docker_seed import prepare


def test_docker_seed_is_repeatable_and_contains_no_account_data(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "build" / "seed.db"
    shutil.copy2(application.ROOT / "speakseed.db", source)
    with sqlite3.connect(source) as connection:
        connection.execute("""INSERT INTO users(name,email,salt,hash,created)
            VALUES('Private QA','private@example.invalid','00','00','2026-01-01T00:00:00+00:00')""")
    prepare(source, destination)
    prepare(source, destination)
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0] == 6280
        assert connection.execute("SELECT COUNT(*) FROM grammar_lessons WHERE published=1").fetchone()[0] == 100
        assert connection.execute("SELECT COUNT(*) FROM grammar_exercises WHERE published=1").fetchone()[0] == 1000
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_runtime_image_never_copies_the_live_database():
    dockerfile = (application.ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (application.ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "COPY --chown=speakseed:speakseed .docker-build/seed.db /app/seed.db" in dockerfile
    assert "COPY --chown=speakseed:speakseed . ." not in dockerfile
    assert "!speakseed.db" not in dockerignore
