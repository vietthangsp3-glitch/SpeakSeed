import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app as application
from migrations import run_migrations
from tools.vocabulary_review_admin import license_decision
from vocabulary_release import edit_candidate, edit_candidate_topics, publish_batch, review_batch, rollback_batch


def setup_phase5(tmp_path, monkeypatch, *, cookie=False):
    database=tmp_path/"phase5.db";run_migrations(database,application.ROOT/"migrations")
    monkeypatch.setattr(application,"DB",database)
    monkeypatch.setenv("AUTH_TRANSPORT","cookie" if cookie else "bearer")
    client=TestClient(application.app)
    response=client.post("/api/register",json={"name":"Real Reviewer","email":"review@example.com","password":"correct-horse"})
    user=response.json()["user"]; token=response.json().get("token")
    with sqlite3.connect(database) as con:
        con.execute("""INSERT INTO content_sources VALUES('test-source','Test','Test Owner','https://example.test','1',
          'CC0','https://creativecommons.org/publicdomain/zero/1.0/','allowed','Test attribution','','approved',
          'https://creativecommons.org/publicdomain/zero/1.0/','now','test fixture only')""")
        con.execute("INSERT INTO content_reviewer_roles VALUES(?,?,?,?)",(user["id"],"reviewer","Test setup","now"))
        con.execute("INSERT INTO content_reviewer_roles VALUES(?,?,?,?)",(user["id"],"publisher","Test setup","now"))
        provenance=json.dumps({"headword_pos_cefr":{"source":"test-source","record":"x"},"meaning_vi":{"source":"test-source","record":"x"}})
        con.execute("""INSERT INTO vocabulary_candidates(stable_key,normalized_word,word,pos,meaning_vi,ipa,cefr_level,
          source_key,source_record_id,provenance_json,license_status,qa_status,core_status,policy_version,created_at,updated_at)
          VALUES('orchard|noun|A2','orchard','orchard','noun','vườn cây','','A2','test-source','x',?,'pass','pass','review_ready','core-v1','now','now')""",(provenance,))
        candidate=con.execute("SELECT id FROM vocabulary_candidates").fetchone()[0]
        topic=con.execute("SELECT id FROM vocabulary_topics WHERE slug='nature-environment'").fetchone()[0]
        con.execute("INSERT INTO vocabulary_candidate_topics VALUES(?,?,95,'test-source','Test semantic evidence','pending')",(candidate,topic))
    headers={"Authorization":"Bearer "+token} if token else {"X-CSRF-Token":client.cookies.get("ss_csrf")}
    return database,client,headers,user,candidate,topic


def test_internal_review_is_server_authorized_and_preview_isolated(tmp_path,monkeypatch):
    database,client,headers,user,candidate,topic=setup_phase5(tmp_path,monkeypatch)
    other=client.post("/api/register",json={"name":"Learner","email":"learner@example.com","password":"correct-horse"}).json()["token"]
    assert client.get("/api/internal/vocabulary/candidates",headers={"Authorization":"Bearer "+other}).status_code==403
    assert client.get("/internal/vocabulary-review",headers=headers).status_code==200
    preview=client.get(f"/api/internal/vocabulary/preview/{candidate}",headers=headers).json()
    assert preview["persistent_progress"] is False and "CHƯA KIỂM DUYỆT" in preview["label"]
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM progress").fetchone()[0]==0


def test_cookie_review_write_requires_csrf(tmp_path,monkeypatch):
    _,client,headers,_,candidate,topic=setup_phase5(tmp_path,monkeypatch,cookie=True)
    payload={"candidate_ids":[candidate],"topic_ids":{str(candidate):[topic]},"decision":"approve","reason":"Human checked meaning and topic"}
    assert client.post("/api/internal/vocabulary/review-batch",json=payload).status_code==403
    assert client.post("/api/internal/vocabulary/review-batch",headers=headers,json=payload).status_code==200


def test_batch_review_publish_and_controlled_rollback(tmp_path,monkeypatch):
    database,_,_,user,candidate,topic=setup_phase5(tmp_path,monkeypatch)
    actor={"id":user["id"],"name":user["name"]}
    with application.connect_database(database) as con:
        reviewed=review_batch(con,[candidate],{candidate:[topic]},actor,"approve","Checked Core fields and source")
        assert reviewed["updated"]==[candidate]
        result=publish_batch(con,[candidate],actor)
        assert result["published"]==1
        word_id=result["items"][0]["word_id"]
    with sqlite3.connect(database) as con:
        row=con.execute("SELECT word,ipa,example,reviewed FROM library_words WHERE id=?",(word_id,)).fetchone()
        assert row==("orchard","","",1)
        assert con.execute("SELECT COUNT(*) FROM word_attributions WHERE word_id=?",(word_id,)).fetchone()[0]>=1
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            con.execute("UPDATE vocabulary_candidate_events SET reason='tampered'")
    with application.connect_database(database) as con:
        rolled=rollback_batch(con,result["batch_id"],actor)
        assert rolled=={"batch_id":result["batch_id"],"rolled_back":1,"deleted":0}
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT reviewed FROM library_words WHERE id=?",(word_id,)).fetchone()[0]==0


def test_license_gate_and_revision_invalidation(tmp_path,monkeypatch):
    database,_,_,user,candidate,topic=setup_phase5(tmp_path,monkeypatch)
    actor={"id":user["id"],"name":user["name"]}
    with application.connect_database(database) as con:
        con.execute("UPDATE vocabulary_candidates SET license_status='blocked' WHERE id=?",(candidate,))
        blocked=review_batch(con,[candidate],{candidate:[topic]},actor,"approve","Checked")
        assert "license_not_pass" in blocked["blocked"][str(candidate)]
        con.execute("UPDATE vocabulary_candidates SET license_status='pass' WHERE id=?",(candidate,))
        review_batch(con,[candidate],{candidate:[topic]},actor,"approve","Checked")
        before=con.execute("SELECT content_revision FROM vocabulary_candidates WHERE id=?",(candidate,)).fetchone()[0]
        edited=edit_candidate(con,candidate,actor,{"meaning_vi":"vườn cây ăn quả"},"Clarified the Vietnamese sense")
        assert edited["content_revision"]==before+1
        status=con.execute("SELECT review_status FROM vocabulary_candidates WHERE id=?",(candidate,)).fetchone()[0]
        assert status=="needs_revision"
        changed=edit_candidate_topics(con,candidate,[topic],actor,"Reviewer corrected topic selection")
        assert changed["content_revision"]==before+2 and changed["review_status"]=="needs_revision"


def test_existing_ids_and_progress_survive_migration(tmp_path):
    database=tmp_path/"preserve.db";run_migrations(database,application.ROOT/"migrations")
    with sqlite3.connect(database) as con:
        con.execute("INSERT INTO users(name,email,salt,hash,created) VALUES('A','a@x.test','s','h','now')")
        con.execute("""INSERT INTO library_words(id,word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at)
          VALUES(99,'apple','táo','/a/','An apple.','Food','x','A1','noun','test','a','test',1,'apple','Một quả táo.',100,'now')""")
        con.execute("INSERT INTO progress(user_id,word_id,level,correct,wrong,updated) VALUES(1,99,2,3,1,'now')")
    run_migrations(database,application.ROOT/"migrations")
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT id FROM library_words WHERE normalized_word='apple'").fetchone()[0]==99
        assert con.execute("SELECT level,correct,wrong FROM progress WHERE user_id=1 AND word_id=99").fetchone()==(2,3,1)


def test_postgres_phase5_migration_is_native_sql():
    sql=(application.ROOT/"deploy/postgres/018_vocabulary_release_workflow.sql").read_text(encoding="utf-8")
    assert "LANGUAGE plpgsql" in sql and "GENERATED BY DEFAULT AS IDENTITY" in sql
    assert "RAISE(ABORT" not in sql and "INSERT OR IGNORE" not in sql


def test_license_decision_requires_existing_admin_and_is_immutable(tmp_path,monkeypatch):
    database,_,_,user,candidate,topic=setup_phase5(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match="admin"):
        license_decision(database,"test-source","pass","https://evidence.test/license","Legal review complete",user["email"])
    with sqlite3.connect(database) as con:
        con.execute("INSERT INTO content_reviewer_roles VALUES(?,?,?,?)",(user["id"],"admin","Project owner","now"))
    result=license_decision(database,"test-source","pass","https://evidence.test/license","Legal review complete",user["email"])
    assert result["affected_candidates"]==1
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT core_status FROM vocabulary_candidates WHERE id=?",(candidate,)).fetchone()[0]=="review_ready"
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            con.execute("UPDATE content_license_decisions SET reason='changed'")
