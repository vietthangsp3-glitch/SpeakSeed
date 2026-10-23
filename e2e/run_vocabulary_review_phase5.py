"""Browser smoke test for the protected Phase 5 review UI (QA databases only)."""
import argparse, json, sqlite3, uuid
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p=argparse.ArgumentParser();p.add_argument("--base-url",required=True);p.add_argument("--database",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
    results=[];errors=[];email=f"phase5-review-{uuid.uuid4().hex[:8]}@example.invalid"
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="chrome",headless=True);context=browser.new_context(viewport={"width":390,"height":844})
        page=context.new_page();page.on("pageerror",lambda err:errors.append(str(err)))
        response=context.request.post(a.base_url+"/api/register",data={"name":"Phase5 QA Reviewer","email":email,"password":"correct-horse"})
        assert response.status==200
        assert context.request.get(a.base_url+"/internal/vocabulary-review").status==403
        with sqlite3.connect(a.database) as con:
            uid=con.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()[0]
            con.execute("INSERT INTO content_reviewer_roles VALUES(?,?,?,datetime('now'))",(uid,"reviewer","Phase 5 browser test fixture"))
        page.goto(a.base_url+"/internal/vocabulary-review",wait_until="networkidle")
        page.wait_for_selector(".review-card")
        cards=page.locator(".review-card").count();overflow=page.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
        assert cards>0 and overflow==0
        candidate=int(page.locator(".pick").first.get_attribute("value"));topic=page.locator(f".topic-{candidate}").first
        assert topic.count()>0
        no_csrf=context.request.post(a.base_url+"/api/internal/vocabulary/review-batch",data={"candidate_ids":[candidate],"topic_ids":{str(candidate):[int(topic.get_attribute('value'))]},"decision":"approve","reason":"QA browser attempt"},headers={"X-CSRF-Token":"wrong"})
        assert no_csrf.status==403
        results.append({"name":"protected_review_ui_mobile","status":"PASS","cards_loaded":cards,"overflow":overflow,"unauthorized":403,"csrf_blocked":403})
        browser.close()
    with sqlite3.connect(a.database) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("DELETE FROM users WHERE email=?",(email,))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({"ok":not errors,"results":results,"javascript_errors":errors},indent=2),encoding="utf-8")
    print(json.dumps({"ok":not errors,"output":str(a.output)}))


if __name__=="__main__":main()
