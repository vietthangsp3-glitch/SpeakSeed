"""Server-side review and transactional publication for Core vocabulary."""
from __future__ import annotations

import json
from datetime import datetime, timezone

POLICY_VERSION = "core-v1"
EDITABLE_FIELDS = {"word", "pos", "meaning_vi", "ipa", "cefr_level", "definition_en", "example_en", "example_vi"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def roles_for(con, user_id: int) -> set[str]:
    return {row[0] for row in con.execute("SELECT role FROM content_reviewer_roles WHERE user_id=?", (user_id,))}


def require_role(con, user_id: int, allowed: set[str]) -> set[str]:
    roles = roles_for(con, user_id)
    if not roles.intersection(allowed):
        raise PermissionError("Reviewer/publisher permission required")
    return roles


def candidate_queue(con, filters: dict, limit: int = 100, offset: int = 0) -> dict:
    where = ["1=1"]; params = []
    field_map = {"cefr": "c.cefr_level", "source": "c.source_key", "qa": "c.qa_status",
                 "review": "c.review_status", "core": "c.core_status", "license": "c.license_status"}
    for key, column in field_map.items():
        value = str(filters.get(key, "")).strip()
        if value:
            where.append(f"{column}=?"); params.append(value)
    for key, column in (("missing_meaning", "meaning_vi"), ("missing_example", "example_en"), ("missing_ipa", "ipa")):
        if filters.get(key): where.append(f"trim(c.{column})=''")
    topic = str(filters.get("topic", "")).strip()
    if topic:
        where.append("EXISTS(SELECT 1 FROM vocabulary_candidate_topics ct JOIN vocabulary_topics t ON t.id=ct.topic_id WHERE ct.candidate_id=c.id AND t.slug=?)")
        params.append(topic)
    clause = " AND ".join(where)
    total = con.execute(f"SELECT COUNT(*) FROM vocabulary_candidates c WHERE {clause}", params).fetchone()[0]
    params.extend([max(1, min(limit, 200)), max(0, offset)])
    rows = [dict(row) for row in con.execute(f"""SELECT c.* FROM vocabulary_candidates c WHERE {clause}
      ORDER BY CASE c.cefr_level WHEN 'A0' THEN 0 WHEN 'A1' THEN 1 WHEN 'A2' THEN 2 WHEN 'B1' THEN 3 ELSE 4 END,c.word,c.id
      LIMIT ? OFFSET ?""", params)]
    for row in rows:
        row["provenance"] = json.loads(row.pop("provenance_json"))
        row["topics"] = [dict(item) for item in con.execute("""SELECT t.id,t.slug,t.name_vi,ct.confidence,ct.source_key,ct.rationale,ct.review_status
          FROM vocabulary_candidate_topics ct JOIN vocabulary_topics t ON t.id=ct.topic_id
          WHERE ct.candidate_id=? ORDER BY ct.confidence DESC,t.id""", (row["id"],))]
    return {"total": total, "items": rows, "limit": params[-2], "offset": params[-1]}


def core_errors(con, candidate_id: int) -> list[str]:
    row = con.execute("SELECT * FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row: return ["unknown_candidate"]
    errors = []
    for field in ("word", "pos", "meaning_vi", "cefr_level", "provenance_json"):
        if not str(row[field] or "").strip() or (field == "cefr_level" and row[field] == "unverified"):
            errors.append("missing_" + field)
    if row["qa_status"] != "pass": errors.append("automated_qa_not_pass")
    if row["license_status"] != "pass": errors.append("license_not_pass")
    if row["policy_version"] != POLICY_VERSION: errors.append("unsupported_policy")
    try: provenance = json.loads(row["provenance_json"])
    except (TypeError,ValueError): provenance = {}
    # Legacy/unverified evidence stays in the audit trail but is explicitly
    # excluded from the releasable fields.  It must not make a recovered Core
    # row depend on the old source's unresolved row-level provenance.
    sources = {
        value.get("source") for value in provenance.values()
        if isinstance(value, dict) and value.get("source")
        and value.get("classification") != "UNVERIFIED"
        and not value.get("excluded_from_release")
    }
    for source_key in sources:
        source = con.execute("SELECT audit_status,commercial_use,license_name,evidence_url FROM content_sources WHERE source_key=?", (source_key,)).fetchone()
        if not source or source["audit_status"] not in {"approved","conditional"} or source["commercial_use"] not in {"allowed","conditional"} or not source["license_name"] or not source["evidence_url"]:
            errors.append("source_license_blocked:" + source_key)
    if not con.execute("SELECT 1 FROM vocabulary_candidate_topics WHERE candidate_id=? AND review_status IN ('pending','human_reviewed')", (candidate_id,)).fetchone():
        errors.append("missing_topic")
    if con.execute("SELECT 1 FROM library_words WHERE normalized_word=? AND reviewed=1", (row["normalized_word"],)).fetchone():
        errors.append("duplicate_published_word")
    return errors


def edit_candidate(con, candidate_id: int, actor: dict, changes: dict, reason: str) -> dict:
    clean = {key: str(value).strip() for key, value in changes.items() if key in EDITABLE_FIELDS}
    if not clean or not reason.strip(): raise ValueError("Changes and reason are required")
    old = con.execute("SELECT review_status,content_revision,policy_version FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not old:
        raise ValueError("Unknown or already-published candidate")
    published = con.execute("SELECT published_word_id FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()[0]
    if published:
        raise ValueError("Unknown or already-published candidate")
    assignments = ",".join(f"{key}=?" for key in clean)
    bump = "" if old["review_status"] == "human_reviewed" else ",content_revision=content_revision+1,review_status='needs_revision'"
    con.execute(f"UPDATE vocabulary_candidates SET {assignments},updated_at=?{bump} WHERE id=?", [*clean.values(), now(), candidate_id])
    revision = con.execute("SELECT content_revision FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()[0]
    con.execute("""INSERT INTO vocabulary_candidate_events(candidate_id,actor_user_id,actor_name,action,reason,policy_version,content_revision,occurred_at)
      VALUES(?,?,?,?,?,?,?,?)""", (candidate_id,actor["id"],actor["name"],"edit",reason.strip(),POLICY_VERSION,revision,now()))
    return {"id": candidate_id, "content_revision": revision, "review_status": "needs_revision"}


def edit_candidate_topics(con, candidate_id: int, topic_ids: list[int], actor: dict, reason: str) -> dict:
    chosen={int(value) for value in topic_ids}
    if not chosen or not reason.strip():raise ValueError("At least one topic and a reason are required")
    row=con.execute("SELECT content_revision,published_word_id FROM vocabulary_candidates WHERE id=?",(candidate_id,)).fetchone()
    if not row or row["published_word_id"]:raise ValueError("Unknown or already-published candidate")
    known={item[0] for item in con.execute("SELECT id FROM vocabulary_topics WHERE active=1")}
    if not chosen<=known:raise ValueError("Unknown topic")
    con.execute("DELETE FROM vocabulary_candidate_topics WHERE candidate_id=? AND review_status<>'human_reviewed'",(candidate_id,))
    for topic_id in chosen:
        con.execute("""INSERT INTO vocabulary_candidate_topics(candidate_id,topic_id,confidence,source_key,rationale,review_status)
          VALUES(?,?,100,'human-review',?,'pending') ON CONFLICT(candidate_id,topic_id) DO UPDATE SET
          confidence=100,source_key='human-review',rationale=excluded.rationale,review_status='pending'""",
          (candidate_id,topic_id,reason.strip()))
    con.execute("UPDATE vocabulary_candidates SET content_revision=content_revision+1,review_status='needs_revision',reviewed_at=NULL,reviewed_by_user_id=NULL,updated_at=? WHERE id=?",(now(),candidate_id))
    revision=con.execute("SELECT content_revision FROM vocabulary_candidates WHERE id=?",(candidate_id,)).fetchone()[0]
    con.execute("""INSERT INTO vocabulary_candidate_events(candidate_id,actor_user_id,actor_name,action,reason,policy_version,content_revision,occurred_at)
      VALUES(?,?,?,'edit',?,?,?,?)""",(candidate_id,actor["id"],actor["name"],reason.strip(),POLICY_VERSION,revision,now()))
    return {"id":candidate_id,"topic_ids":sorted(chosen),"content_revision":revision,"review_status":"needs_revision"}


def review_batch(con, candidate_ids: list[int], topic_ids: dict[int, list[int]], actor: dict,
                 decision: str, reason: str) -> dict:
    if not candidate_ids or len(candidate_ids) > 200: raise ValueError("Select 1-200 candidates")
    if decision not in {"approve", "reject", "needs_revision"} or not reason.strip():
        raise ValueError("Decision and reason are required")
    reviewed = []; rejected = {}
    for candidate_id in dict.fromkeys(candidate_ids):
        row = con.execute("SELECT * FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()
        if not row or row["published_word_id"]:
            rejected[str(candidate_id)] = ["unknown_or_published"]; continue
        errors = core_errors(con, candidate_id) if decision == "approve" else []
        chosen = {int(value) for value in topic_ids.get(candidate_id, [])}
        if decision == "approve" and not chosen: errors.append("reviewer_must_confirm_topic")
        if errors:
            rejected[str(candidate_id)] = errors; continue
        con.execute("""INSERT INTO vocabulary_candidate_events(candidate_id,actor_user_id,actor_name,action,reason,policy_version,content_revision,occurred_at)
          VALUES(?,?,?,?,?,?,?,?)""", (candidate_id,actor["id"],actor["name"],decision,reason.strip(),POLICY_VERSION,row["content_revision"],now()))
        if decision == "approve":
            con.execute("UPDATE vocabulary_candidate_topics SET review_status='rejected' WHERE candidate_id=?", (candidate_id,))
            placeholders = ",".join("?" for _ in chosen)
            con.execute(f"UPDATE vocabulary_candidate_topics SET review_status='human_reviewed' WHERE candidate_id=? AND topic_id IN ({placeholders})", [candidate_id,*chosen])
            con.execute("UPDATE vocabulary_candidates SET review_status='human_reviewed',reviewed_at=?,reviewed_by_user_id=? WHERE id=?", (now(),actor["id"],candidate_id))
        else:
            con.execute("UPDATE vocabulary_candidates SET review_status=? WHERE id=?", ("rejected" if decision == "reject" else "needs_revision",candidate_id))
        reviewed.append(candidate_id)
    return {"updated": reviewed, "blocked": rejected, "decision": decision, "policy_version": POLICY_VERSION}


def publish_batch(con, candidate_ids: list[int], actor: dict) -> dict:
    if not candidate_ids or len(candidate_ids) > 200: raise ValueError("Select 1-200 candidates")
    stamp = now()
    batch = con.execute("""INSERT INTO vocabulary_publish_batches(publisher_user_id,publisher_name,policy_version,status,created_at)
      VALUES(?,?,?,'running',?)""", (actor["id"],actor["name"],POLICY_VERSION,stamp)).lastrowid
    published = []
    for candidate_id in dict.fromkeys(candidate_ids):
        row = con.execute("SELECT * FROM vocabulary_candidates WHERE id=?", (candidate_id,)).fetchone()
        if not row or row["review_status"] != "human_reviewed" or row["published_word_id"] or core_errors(con,candidate_id):
            raise ValueError(f"Candidate {candidate_id} is not publishable")
        topic = con.execute("""SELECT t.id,t.slug,t.name_en FROM vocabulary_candidate_topics ct JOIN vocabulary_topics t ON t.id=ct.topic_id
          WHERE ct.candidate_id=? AND ct.review_status='human_reviewed' ORDER BY ct.confidence DESC,t.id LIMIT 1""", (candidate_id,)).fetchone()
        cur = con.execute("""INSERT INTO library_words(word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,
          normalized_word,example_vi,quality_score,updated_at) VALUES(?,?,?,?,?,'📘',?,?,?,?,'core-v1',1,?,?,100,?)""",
          (row["word"],row["meaning_vi"],row["ipa"],row["example_en"],topic["name_en"],row["cefr_level"],row["pos"],
           "phase5-core-v1",row["source_record_id"],row["normalized_word"],row["example_vi"],stamp))
        word_id = cur.lastrowid
        provenance = json.loads(row["provenance_json"])
        for field_group, evidence in provenance.items():
            if not evidence or not evidence.get("source"): continue
            source = con.execute("SELECT * FROM content_sources WHERE source_key=?", (evidence["source"],)).fetchone()
            if not source: continue
            con.execute("""INSERT INTO data_sources(name,version,source_url,license_name,license_url,attribution,retrieved_at,sha256)
              VALUES(?,?,?,?,?,?,?,'phase5-staged') ON CONFLICT(name) DO NOTHING""",
              (source["source_key"],source["dataset_version"],source["source_url"],source["license_name"],
               source["license_url"],source["attribution"],stamp))
            con.execute("""INSERT INTO word_attributions(word_id,field_name,source_name,source_record_id,source_url,license_name,attribution)
              VALUES(?,?,?,?,?,?,?) ON CONFLICT(word_id,field_name,source_name) DO NOTHING""",
              (word_id,field_group,source["source_key"],str(evidence.get("record",row["source_record_id"])),
               source["source_url"],source["license_name"],source["attribution"]))
        con.execute("""INSERT INTO vocabulary_topic_words(word_id,topic_id,sense_key,review_status,published,confidence,source_key,rationale,created_at,reviewed_at,reviewed_by)
          VALUES(?,?,'','human_reviewed',0,100,'phase5-core-v1','Approved with Core vocabulary candidate',?,?,?)""",
          (word_id,topic["id"],stamp,stamp,actor["name"]))
        con.execute("INSERT INTO vocabulary_topic_reviews(word_id,topic_id,sense_key,reviewer_name,decision,reason,reviewed_at) VALUES(?,?,'',?,'approve','Approved with candidate Core review',?)", (word_id,topic["id"],actor["name"],stamp))
        con.execute("UPDATE vocabulary_topic_words SET published=1 WHERE word_id=? AND topic_id=? AND sense_key=''", (word_id,topic["id"]))
        con.execute("""INSERT INTO vocabulary_candidate_events(candidate_id,actor_user_id,actor_name,action,reason,policy_version,content_revision,occurred_at)
          VALUES(?,?,?,'publish','Separate publisher confirmation',?,?,?)""", (candidate_id,actor["id"],actor["name"],POLICY_VERSION,row["content_revision"],stamp))
        con.execute("UPDATE vocabulary_candidates SET published_word_id=?,updated_at=? WHERE id=?", (word_id,stamp,candidate_id))
        con.execute("INSERT INTO vocabulary_publish_items VALUES(?,?,?,?,?)", (batch,candidate_id,word_id,row["content_revision"],stamp))
        published.append({"candidate_id":candidate_id,"word_id":word_id})
    report = {"published":len(published),"items":published}
    con.execute("UPDATE vocabulary_publish_batches SET status='published',finished_at=?,report_json=? WHERE id=?", (now(),json.dumps(report),batch))
    return {"batch_id":batch,**report}


def rollback_batch(con, batch_id: int, actor: dict) -> dict:
    batch = con.execute("SELECT * FROM vocabulary_publish_batches WHERE id=?", (batch_id,)).fetchone()
    if not batch or batch["status"] != "published": raise ValueError("Published batch does not exist")
    items = con.execute("SELECT * FROM vocabulary_publish_items WHERE batch_id=?", (batch_id,)).fetchall()
    for item in items:
        if con.execute("SELECT 1 FROM progress WHERE word_id=? LIMIT 1", (item["word_id"],)).fetchone():
            raise ValueError(f"Cannot rollback word {item['word_id']}: learner progress exists")
    stamp=now()
    for item in items:
        con.execute("UPDATE vocabulary_topic_words SET published=0 WHERE word_id=?", (item["word_id"],))
        con.execute("UPDATE library_words SET reviewed=0,updated_at=? WHERE id=?", (stamp,item["word_id"]))
        con.execute("UPDATE vocabulary_candidates SET published_word_id=NULL,updated_at=? WHERE id=?", (stamp,item["candidate_id"]))
        con.execute("""INSERT INTO vocabulary_candidate_events(candidate_id,actor_user_id,actor_name,action,reason,policy_version,content_revision,occurred_at)
          VALUES(?,?,?,'rollback','Controlled rollback before learner progress',?,?,?)""",
          (item["candidate_id"],actor["id"],actor["name"],POLICY_VERSION,item["content_revision"],stamp))
    con.execute("UPDATE vocabulary_publish_batches SET status='rolled_back',finished_at=? WHERE id=?", (stamp,batch_id))
    return {"batch_id":batch_id,"rolled_back":len(items),"deleted":0}
