"""Deterministic QA audit for all grammar lessons and exercises.

This audit checks structure, answer consistency, duplicate objectives, unit-test
coverage, CEFR review notes and known ambiguity. It never upgrades content to
human_reviewed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.build_grammar import ALTERNATE_CLOZE, KINDS, build_rows, validate


FIXED_FINDINGS = [
    {"id": "QA-001", "severity": "high", "finding": "Multiple-choice mixed examples from different contexts, allowing more than one grammatical option.", "affected": 200, "fix": "Use the Vietnamese target and only the correct/common-error pair from the same example."},
    {"id": "QA-002", "severity": "high", "finding": "Error-correction prompts lacked semantic context, so a grammatical sentence with another meaning could be defensible.", "affected": 200, "fix": "Include the Vietnamese target in every error-correction prompt."},
    {"id": "QA-003", "severity": "high", "finding": "A2 second conditional duplicated the B1 objective and was above the intended A2 progression.", "affected": 10, "fix": "Replace it with A2 future time clauses; keep the second conditional at B1."},
    {"id": "QA-004", "severity": "medium", "finding": "An A0 possessive example used the plural apostrophe rule.", "affected": 5, "fix": "Use a singular possessive example and keep plural possessives out of A0."},
    {"id": "QA-005", "severity": "medium", "finding": "Contractions such as I'm/can't were rejected against expanded model answers.", "affected": "grading mechanism", "fix": "Canonicalize common English contractions before comparison."},
    {"id": "QA-006", "severity": "medium", "finding": "Some cloze prompts permit multiple valid words or phrases.", "affected": len(ALTERNATE_CLOZE), "fix": "Store explicit accepted alternatives for verified ambiguous cloze items."},
    {"id": "QA-007", "severity": "medium", "finding": "Several learner-error examples contained meta wording or implausible phrasing.", "affected": 9, "fix": "Replace them with plausible, unambiguously incorrect learner errors."},
    {"id": "QA-008", "severity": "medium", "finding": "The first nominalisation example used a verb rather than a nominalised structure.", "affected": 5, "fix": "Replace it with “The company's decision was to expand.” and regenerate its five exercises."},
    {"id": "QA-009", "severity": "high", "finding": "Two cloze prompts omitted a time expression from the model sentence, so inserting the answer could not reconstruct the target.", "affected": 2, "fix": "Restore the missing time expressions in lessons 64 and 65 and rerun the reconstruction audit."},
]

OPEN_FINDINGS = [
    {"id": "QA-R01", "severity": "medium", "scope": "200 vi_to_en exercises", "finding": "Open translation can have valid paraphrases beyond stored answers.", "recommendation": "Add teacher-authored alternatives per item or a separately evaluated semantic grader; do not silently accept unrestricted AI output."},
    {"id": "QA-R02", "severity": "low", "scope": "B1 lessons 65 and 71", "finding": "Future perfect and past modal deduction sit near the B1+/B2 boundary in different CEFR-aligned syllabi.", "recommendation": "Retain as bridge content but request external teacher review before claiming strict CEFR certification."},
    {"id": "QA-R03", "severity": "info", "scope": "all content", "finding": "No evidence of review by a human teacher/editor is stored.", "recommendation": "Keep automated_checked until named human review evidence is recorded."},
]

BOUNDARY_NOTES = {
    65: "B1+/B2 boundary: future perfect",
    71: "B1+/B2 boundary: past modal deduction",
}


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower().replace("’", "'")))


def audit() -> dict:
    units, lessons, examples, exercises = build_rows()
    validate(units, lessons, examples, exercises)
    failures = []
    lesson_rows = []
    exercises_by_lesson = defaultdict(list)
    examples_by_lesson = defaultdict(list)
    for row in exercises: exercises_by_lesson[row["lesson_id"]].append(row)
    for row in examples: examples_by_lesson[row["lesson_id"]].append(row)

    titles = Counter(norm(row["title"]) for row in lessons)
    if any(value > 1 for value in titles.values()):
        failures.append({"severity": "high", "check": "duplicate_titles", "detail": dict(titles)})
    objectives = Counter((norm(row["topic"]), norm(row["formula"])) for row in lessons)
    duplicate_objectives = {" / ".join(key): value for key, value in objectives.items() if value > 1}
    if duplicate_objectives:
        failures.append({"severity": "high", "check": "duplicate_objectives", "detail": duplicate_objectives})
    english_examples = Counter(norm(row["english"]) for row in examples)
    duplicate_examples = {text: value for text, value in english_examples.items() if value > 1}
    if duplicate_examples:
        failures.append({"severity": "medium", "check": "duplicate_examples", "detail": duplicate_examples})

    for lesson in lessons:
        lid = lesson["id"]
        lesson_exercises = exercises_by_lesson[lid]
        lesson_examples = examples_by_lesson[lid]
        issues = []
        if len(lesson_exercises) != 10: issues.append("exercise_count")
        if len(lesson_examples) != 2: issues.append("example_count")
        if Counter(x["kind"] for x in lesson_exercises) != Counter({kind: 2 for kind in KINDS}): issues.append("kind_balance")
        if any(norm(error["wrong"]) == norm(error["correct"]) for error in lesson["common_errors"]): issues.append("error_equals_correct")
        for index, raw in enumerate(lesson["examples"], 1):
            english, vietnamese, cloze, answer, wrong = raw
            if norm(cloze.replace("___", answer)) != norm(english): issues.append(f"cloze_reconstruction_{index}")
            if norm(wrong) == norm(english): issues.append(f"wrong_equals_correct_{index}")
            if not re.search(r"[À-ỹ]", vietnamese): issues.append(f"vietnamese_diacritic_{index}")
        mcq = [x for x in lesson_exercises if x["kind"] == "multiple_choice"]
        if any(len(set(x["options"])) != 2 or x["answers"][0] not in x["options"] for x in mcq): issues.append("mcq_option_integrity")
        lesson_rows.append({
            "id": lid, "level": lesson["level"], "unit_id": lesson["unit_id"], "title": lesson["title"],
            "status": "fail" if issues else ("review_boundary" if lid in BOUNDARY_NOTES else "pass"),
            "issues": issues, "cefr_note": BOUNDARY_NOTES.get(lid, ""),
            "accepted_cloze_variants": sum(1 for key in ALTERNATE_CLOZE if key[0] == lesson["title"]),
        })
        for issue in issues:
            failures.append({"severity": "high", "lesson_id": lid, "check": issue})

    unit_rows = []
    for unit in units:
        unit_lessons = [x for x in lessons if x["unit_id"] == unit["id"]]
        unit_exercises = [x for x in exercises if x["unit_id"] == unit["id"]]
        test = [x for x in unit_exercises if x["is_unit_test"]]
        unit_rows.append({
            "id": unit["id"], "level": unit["level"], "sequence": unit["sequence"], "title": unit["title"],
            "lessons": len(unit_lessons), "exercises": len(unit_exercises), "test_questions": len(test),
            "test_lesson_coverage": len({x["lesson_id"] for x in test}),
            "test_kind_coverage": len({x["kind"] for x in test}),
            "status": "pass" if len(unit_lessons) == 5 and len(unit_exercises) == 50 and len(test) == 10 and len({x["lesson_id"] for x in test}) == 5 and len({x["kind"] for x in test}) == 5 else "fail",
        })

    level_rows = []
    for level in ("A0", "A1", "A2", "B1", "B2"):
        selected_lessons = [x for x in lesson_rows if x["level"] == level]
        selected_units = [x for x in unit_rows if x["level"] == level]
        level_rows.append({"level": level, "units": len(selected_units), "lessons": len(selected_lessons),
                           "exercises": sum(x["exercises"] for x in selected_units),
                           "structural_failures": sum(x["status"] == "fail" for x in selected_lessons),
                           "cefr_boundary_notes": sum(bool(x["cefr_note"]) for x in selected_lessons)})

    kind_rows = []
    for kind in KINDS:
        selected = [x for x in exercises if x["kind"] == kind]
        kind_rows.append({"kind": kind, "count": len(selected),
                          "multi_answer_items": sum(len(x["answers"]) > 1 for x in selected),
                          "remaining_risk": "open paraphrases" if kind == "vi_to_en" else "none detected"})

    return {
        "summary": {"units_checked": len(units), "lessons_checked": len(lessons), "examples_checked": len(examples),
                    "exercises_checked": len(exercises), "structural_failures": len(failures),
                    "fixed_finding_categories": len(FIXED_FINDINGS), "open_finding_categories": len(OPEN_FINDINGS),
                    "human_reviewed": 0, "review_status": "automated_checked"},
        "fixed_findings": FIXED_FINDINGS, "open_findings": OPEN_FINDINGS,
        "by_level": level_rows, "by_unit": unit_rows, "by_lesson": lesson_rows, "by_kind": kind_rows,
        "failures": failures,
    }


def markdown(report: dict) -> str:
    out = ["# Grammar QA audit", "", "Generated by `tools/audit_grammar.py`.", "",
           "## Summary", "", "```json", json.dumps(report["summary"], ensure_ascii=False, indent=2), "```", "",
           "## By level", "", "| Level | Units | Lessons | Exercises | Structural failures | CEFR boundary notes |", "|---|---:|---:|---:|---:|---:|"]
    for row in report["by_level"]: out.append(f"| {row['level']} | {row['units']} | {row['lessons']} | {row['exercises']} | {row['structural_failures']} | {row['cefr_boundary_notes']} |")
    out += ["", "## By unit", "", "| Unit | Level | Title | Lessons | Exercises | Test / lesson / kind coverage | Status |", "|---:|---|---|---:|---:|---|---|"]
    for row in report["by_unit"]: out.append(f"| {row['id']} | {row['level']} | {row['title']} | {row['lessons']} | {row['exercises']} | {row['test_questions']} / {row['test_lesson_coverage']} / {row['test_kind_coverage']} | {row['status']} |")
    out += ["", "## By lesson", "", "| ID | Level | Unit | Lesson | Status | Accepted cloze variants | Note |", "|---:|---|---:|---|---|---:|---|"]
    for row in report["by_lesson"]: out.append(f"| {row['id']} | {row['level']} | {row['unit_id']} | {row['title']} | {row['status']} | {row['accepted_cloze_variants']} | {row['cefr_note']} |")
    out += ["", "## By exercise kind", "", "| Kind | Count | Multi-answer items | Remaining risk |", "|---|---:|---:|---|"]
    for row in report["by_kind"]: out.append(f"| {row['kind']} | {row['count']} | {row['multi_answer_items']} | {row['remaining_risk']} |")
    out += ["", "## Fixed findings", ""]
    for item in report["fixed_findings"]: out.append(f"- **{item['id']} · {item['severity']}** — {item['finding']} Affected: {item['affected']}. Fix: {item['fix']}")
    out += ["", "## Open findings", ""]
    for item in report["open_findings"]: out.append(f"- **{item['id']} · {item['severity']}** — {item['scope']}: {item['finding']} Recommendation: {item['recommendation']}")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else markdown(report), end="")
    raise SystemExit(1 if report["summary"]["structural_failures"] else 0)


if __name__ == "__main__":
    main()
