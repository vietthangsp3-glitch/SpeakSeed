"""Explicit local administration for reviewer roles and Phase 5 reporting."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def grant(path: Path, email: str, role: str, granted_by: str) -> dict:
    if role not in {"reviewer", "publisher", "admin"} or not granted_by.strip():
        raise ValueError("Valid role and real grantor identity are required")
    with connect(path) as con:
        user = con.execute("SELECT id,email FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
        if not user: raise ValueError("Account does not exist; no account was created")
        con.execute("INSERT INTO content_reviewer_roles VALUES(?,?,?,?) ON CONFLICT(user_id,role) DO NOTHING",
                    (user["id"],role,granted_by.strip(),datetime.now(timezone.utc).isoformat()))
        return {"user_id":user["id"],"email":user["email"],"role":role,"granted_by":granted_by.strip()}


def report(path: Path) -> dict:
    with connect(path) as con:
        grouped = {row[0]:row[1] for row in con.execute("SELECT core_status,COUNT(*) FROM vocabulary_candidates GROUP BY core_status")}
        return {
            "published_vocabulary": con.execute("SELECT COUNT(*) FROM library_words WHERE reviewed=1").fetchone()[0],
            "candidates": con.execute("SELECT COUNT(*) FROM vocabulary_candidates").fetchone()[0],
            "by_core_status": grouped,
            "review_ready": grouped.get("review_ready",0),
            "human_reviewed": con.execute("SELECT COUNT(*) FROM vocabulary_candidates WHERE review_status='human_reviewed'").fetchone()[0],
            "published_from_candidates": con.execute("SELECT COUNT(*) FROM vocabulary_candidates WHERE published_word_id IS NOT NULL").fetchone()[0],
            "internal_preview": con.execute("SELECT COUNT(*) FROM vocabulary_candidates WHERE published_word_id IS NULL").fetchone()[0],
            "topic_proposals": con.execute("SELECT COUNT(*) FROM vocabulary_topic_words WHERE review_status='pending' AND published=0").fetchone()[0],
            "reviewer_role_assignments": con.execute("SELECT COUNT(*) FROM content_reviewer_roles").fetchone()[0],
        }


def license_decision(path: Path, source_key: str, decision: str, evidence_url: str,
                     reason: str, actor_email: str) -> dict:
    if decision not in {"pass","blocked"} or not evidence_url.startswith(("https://","http://")) or not reason.strip():
        raise ValueError("Decision, evidence URL and reason are required")
    with connect(path) as con:
        actor=con.execute("""SELECT u.id,u.name FROM users u JOIN content_reviewer_roles r ON r.user_id=u.id
          WHERE u.email=? AND r.role='admin'""",(actor_email.strip().lower(),)).fetchone()
        if not actor:raise ValueError("An existing admin account is required; no role was granted")
        if not con.execute("SELECT 1 FROM content_sources WHERE source_key=?",(source_key,)).fetchone():
            raise ValueError("Unknown content source")
        stamp=datetime.now(timezone.utc).isoformat()
        con.execute("""INSERT INTO content_license_decisions(source_key,decision,evidence_url,reason,actor_user_id,actor_name,policy_version,occurred_at)
          VALUES(?,?,?,?,?,?,?,?)""",(source_key,decision,evidence_url,reason.strip(),actor["id"],actor["name"],"core-v1",stamp))
        pattern='%"source": "'+source_key+'"%'
        if decision=="pass":
            con.execute("""UPDATE vocabulary_candidates SET license_status='pass',
              core_status=CASE WHEN qa_status='pass' AND trim(word)<>'' AND trim(pos)<>'' AND trim(meaning_vi)<>''
                AND cefr_level<>'unverified' AND EXISTS(SELECT 1 FROM vocabulary_candidate_topics t WHERE t.candidate_id=vocabulary_candidates.id)
                THEN 'review_ready' ELSE 'needs_data' END,updated_at=? WHERE provenance_json LIKE ?""",(stamp,pattern))
        else:
            con.execute("""UPDATE vocabulary_candidates SET license_status='blocked',
              core_status=CASE WHEN trim(meaning_vi)='' THEN 'needs_data' ELSE 'license_blocked' END,
              review_status=CASE WHEN review_status='human_reviewed' THEN 'needs_revision' ELSE review_status END,
              updated_at=? WHERE provenance_json LIKE ?""",(stamp,pattern))
        affected=con.execute("SELECT changes()").fetchone()[0]
        return {"source_key":source_key,"decision":decision,"affected_candidates":affected,
                "actor":actor["name"],"policy_version":"core-v1"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command",choices=("grant-role","license-decision","report"))
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--email",default="")
    parser.add_argument("--role",default="")
    parser.add_argument("--granted-by",default="")
    parser.add_argument("--source",default="")
    parser.add_argument("--decision",default="")
    parser.add_argument("--evidence-url",default="")
    parser.add_argument("--reason",default="")
    parser.add_argument("--actor-email",default="")
    args=parser.parse_args()
    if args.command=="grant-role":result=grant(args.database,args.email,args.role,args.granted_by)
    elif args.command=="license-decision":result=license_decision(args.database,args.source,args.decision,args.evidence_url,args.reason,args.actor_email)
    else:result=report(args.database)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
