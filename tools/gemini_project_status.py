"""Read-only Gemini project pool status. API key values are never printed."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import configured_database, connect_database
from gemini_pool import parse_gemini_projects


def main() -> None:
    projects = parse_gemini_projects(os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_API_KEYS", ""))
    configured = {item.project_id: item for item in projects}
    target = configured_database(ROOT / "speakseed.db")
    with connect_database(target) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM gemini_project_state ORDER BY project_label,project_id"
        )]
    now = datetime.now(timezone.utc).isoformat()
    known = {row["project_id"] for row in rows}
    for project in projects:
        if project.project_id not in known:
            rows.append({"project_id": project.project_id, "project_label": project.label,
                         "weight": project.weight, "selection_count": 0, "success_count": 0,
                         "failure_count": 0, "quota_failure_count": 0, "cooldown_until": None,
                         "last_status": "not_used", "last_selected_at": None, "updated_at": None})
    safe = []
    for row in rows:
        safe.append({key: row.get(key) for key in (
            "project_id", "project_label", "weight", "selection_count", "success_count",
            "failure_count", "quota_failure_count", "cooldown_until", "last_status",
            "last_selected_at", "updated_at"
        )} | {"configured": row["project_id"] in configured,
             "available": row["project_id"] in configured and
                          (not row.get("cooldown_until") or row["cooldown_until"] <= now)})
    print(json.dumps({"configured_projects": len(projects), "projects": safe}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
