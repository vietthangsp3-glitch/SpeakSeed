"""Build SpeakSeed's publishable vocabulary from traceable open datasets.

The command is repeatable: records are updated in place and provenance rows are
upserted.  It never invents translations, pronunciations, CEFR levels or example
sentences.  A word is published only when all required fields are available.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from migrations import run_migrations

VERSION = "1.0.0"
LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4}
WORD_RE = re.compile(r"[a-z]+(?:['-][a-z]+)*")
VIETNAMESE_RE = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)

SOURCE_ROWS = {
    "cefr-j-1.5": ("1.5", "https://github.com/openlanguageprofiles/olp-en-cefrj", "CEFR-J terms of use", "https://github.com/openlanguageprofiles/olp-en-cefrj#terms-of-use", "The CEFR-J Wordlist Version 1.5, Tono Laboratory, TUFS"),
    "skypedia-en-vi": ("2026-10 snapshot", "https://github.com/skypediacode/english-vietnamese-dictionary", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/", "Skypedia English-Vietnamese Dictionary and its credited upstream projects"),
    "tatoeba-vie-eng": ("2026-02-13", "https://www.manythings.org/anki/", "CC BY 2.0 FR", "https://creativecommons.org/licenses/by/2.0/fr/", "Tatoeba contributors; selection distributed by ManyThings.org"),
    "flores-200": ("2022-07", "https://github.com/facebookresearch/flores", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/", "FLORES-200, Meta AI / No Language Left Behind contributors"),
    "ntrex-128": ("2022-11-24", "https://github.com/MicrosoftTranslator/NTREX", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/", "NTREX-128 by Microsoft Translator and the WMT19 contributors"),
}

TOPICS = {
    "Food": {"food","eat","drink","meal","bread","rice","fruit","vegetable","meat","water","coffee","tea","milk","restaurant","cook","kitchen"},
    "Family": {"family","mother","father","parent","sister","brother","child","baby","wife","husband","son","daughter"},
    "School": {"school","student","teacher","learn","study","book","class","lesson","exam","university","college","education"},
    "Work": {"work","job","office","company","business","career","manager","employee","customer","meeting","salary"},
    "Travel": {"travel","trip","airport","station","train","bus","hotel","ticket","flight","journey","tourist","passport"},
    "Home": {"home","house","room","door","window","bed","chair","table","garden","bathroom","bedroom"},
    "Health": {"health","doctor","hospital","medicine","pain","sick","disease","exercise","body","head","heart"},
    "Nature": {"animal","plant","tree","flower","river","sea","weather","rain","sun","earth","forest","mountain"},
    "Technology": {"computer","phone","internet","software","machine","technology","online","digital","email","website"},
    "Time": {"time","day","week","month","year","today","tomorrow","yesterday","morning","evening","night"},
    "People": {"person","people","friend","man","woman","boy","girl","name","community","neighbor"},
    "Communication": {"speak","say","tell","ask","answer","talk","write","read","language","question","word"},
    "Feelings": {"happy","sad","angry","afraid","love","hate","feel","excited","tired","sorry","hope"},
    "Society": {"government","law","country","city","society","public","money","war","peace","police"},
}
TOPIC_EMOJI = {"Food":"🍎","Family":"👪","School":"📚","Work":"💼","Travel":"✈️","Home":"🏠","Health":"🩺","Nature":"🌿","Technology":"💻","Time":"⏰","People":"🧑","Communication":"💬","Feelings":"💚","Society":"🌍","General":"📘"}
POS_CODES = {
    "noun":{"N","noun","n"}, "verb":{"V","verb"}, "adjective":{"A","adj"},
    "adverb":{"D","adv"}, "pronoun":{"P","pron"}, "preposition":{"E"},
    "determiner":{"X"}, "conjunction":{"C"}, "number":{"M"},
    "modal auxiliary":{"V"}, "be-verb":{"V"}, "do-verb":{"V"},
    "have-verb":{"V"}, "infinitive-to":{"X"}, "interjection":{"O","X"},
}
VI_STOPWORDS = {"là","gì","có","được","đã","đang","những","các","của","cho","trong","trên","ở","và","hoặc","thì","mà","với","này","đó"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_word(value: str) -> str:
    return " ".join(value.casefold().replace("’", "'").split())


def load_cefr(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            word = normalize_word(row.get("headword", ""))
            level = row.get("CEFR", "").strip().upper()
            pos = row.get("pos", "").strip().lower()
            if level not in LEVEL_ORDER or not pos or not re.fullmatch(r"[a-z][a-z '-]{0,59}", word):
                continue
            current = result.get(word)
            if current is None or LEVEL_ORDER[level] < LEVEL_ORDER[current["level"]]:
                result[word] = {"level": level, "positions": {pos}, "source_id": word}
            elif level == current["level"]:
                current["positions"].add(pos)
    return result


def add_example(examples, vocabulary, english, vietnamese, attribution, source):
    if not english or not vietnamese or len(english) > 260 or len(vietnamese) > 320:
        return
    # CEFR-J entries used here contain at most short multi-word expressions.
    max_terms = 5
    tokens = WORD_RE.findall(english.casefold().replace("’", "'"))
    candidates = set()
    for size in range(1, min(max_terms, len(tokens)) + 1):
        candidates.update(" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1))
    for word in candidates & vocabulary:
        old = examples.get(word)
        if old is None or len(english) + len(vietnamese) < len(old[0]) + len(old[1]):
            examples[word] = (english, vietnamese, attribution, source)


def load_examples(tatoeba_path: Path, flores_root: Path, ntrex_en: Path, ntrex_vi: Path, vocabulary: set[str]) -> dict[str, tuple[str, str, str, str]]:
    examples: dict[str, tuple[str, str, str, str]] = {}
    with tatoeba_path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            english, vietnamese, attribution = (part.strip() for part in parts[:3])
            add_example(examples, vocabulary, english, vietnamese, attribution, "tatoeba-vie-eng")
    for split in ("dev", "devtest"):
        en_path, vi_path = flores_root / split / "eng_Latn.dev", flores_root / split / "vie_Latn.dev"
        if split == "devtest":
            en_path, vi_path = flores_root / split / "eng_Latn.devtest", flores_root / split / "vie_Latn.devtest"
        with en_path.open(encoding="utf-8") as en_file, vi_path.open(encoding="utf-8") as vi_file:
            for number, (english, vietnamese) in enumerate(zip(en_file, vi_file, strict=True), 1):
                add_example(examples, vocabulary, english.strip(), vietnamese.strip(), f"FLORES-200 {split}:{number}", "flores-200")
    with ntrex_en.open(encoding="utf-8") as en_file, ntrex_vi.open(encoding="utf-8") as vi_file:
        for number, (english, vietnamese) in enumerate(zip(en_file, vi_file, strict=True), 1):
            add_example(examples, vocabulary, english.strip(), vietnamese.strip(), f"NTREX-128 line {number}", "ntrex-128")
    return examples


def dictionary_entry(con: sqlite3.Connection, word: str, cefr_positions, vietnamese_example: str = ""):
    rows = con.execute("""
        SELECT d.definition,d.pos,wd.example,p.ipa,wd.id
        FROM words w
        JOIN word_definitions wd ON wd.word_id=w.id
        JOIN definitions d ON d.id=wd.definition_id
        JOIN pronunciations p ON p.word_id=w.id
        WHERE w.word=?
    """, (word,)).fetchall()
    if not rows:
        return None
    allowed_codes = set().union(*(POS_CODES.get(pos, set()) for pos in cefr_positions))
    example_tokens = set(re.findall(r"[a-zà-ỹ]+", vietnamese_example.casefold())) - VI_STOPWORDS
    def score(row):
        meaning, pos, _, ipa, relation_id = row
        pos_match = str(pos or "") in allowed_codes
        meaning_tokens = set(re.findall(r"[a-zà-ỹ]+", str(meaning).casefold())) - VI_STOPWORDS
        overlap = len(example_tokens & meaning_tokens)
        similarity = overlap / max(1, len(meaning_tokens))
        # Source order is lexicographic/editorial order: the first matching sense
        # is safer than choosing the shortest gloss, which can select abbreviations.
        return (not pos_match, -similarity, relation_id, len(str(meaning)), len(str(ipa)))
    meaning, source_pos, _, ipa, _ = min(rows, key=score)
    meaning, ipa = str(meaning).strip(), str(ipa).strip()
    selected_pos = next((pos for pos in cefr_positions if source_pos in POS_CODES.get(pos,set())), sorted(cefr_positions)[0])
    return (meaning, ipa, selected_pos) if meaning and ipa else None


def choose_topic(word: str, meaning: str, example: str) -> str:
    tokens = set(WORD_RE.findall((word + " " + example).casefold()))
    best = max(TOPICS, key=lambda topic: len(tokens & TOPICS[topic]))
    return best if tokens & TOPICS[best] else "General"


def validate(record: dict) -> list[str]:
    errors = []
    for field in ("word","meaning","ipa","pos","stage","topic","example","example_vi"):
        if not str(record.get(field, "")).strip():
            errors.append("missing_" + field)
    if record.get("stage") not in LEVEL_ORDER:
        errors.append("invalid_level")
    if not VIETNAMESE_RE.search(record.get("meaning", "") + " " + record.get("example_vi", "")):
        errors.append("no_vietnamese_text")
    if normalize_word(record.get("word", "")) != record.get("word"):
        errors.append("not_normalized")
    return errors


def build(args) -> dict:
    run_migrations(args.database, args.migrations)
    cefr = load_cefr(args.cefr)
    examples = load_examples(args.tatoeba, args.flores_root, args.ntrex_en, args.ntrex_vi, set(cefr))
    dictionary = sqlite3.connect(args.dictionary)
    dictionary.execute("PRAGMA query_only=ON")
    records, rejected = [], Counter()
    for word, meta in cefr.items():
        pair = examples.get(word)
        if not pair:
            rejected["missing_bilingual_example"] += 1
            continue
        entry = dictionary_entry(dictionary, word, meta["positions"], pair[1])
        if not entry:
            rejected["missing_dictionary_entry"] += 1
            continue
        meaning, ipa, selected_pos = entry
        english, vietnamese, attribution, example_source = pair
        topic = choose_topic(word, meaning, english)
        record = {"word":word,"meaning":meaning,"ipa":ipa,"pos":selected_pos,"stage":meta["level"],"topic":topic,"emoji":TOPIC_EMOJI[topic],"example":english,"example_vi":vietnamese,"example_attribution":attribution,"example_source":example_source}
        errors = validate(record)
        if errors:
            rejected.update(errors)
        else:
            records.append(record)
    dictionary.close()
    levels = Counter(row["stage"] for row in records)
    topics = Counter(row["topic"] for row in records)
    report = {"valid":len(records),"cefr_candidates":len(cefr),"with_bilingual_example":len(examples),"levels":dict(sorted(levels.items())),"topics":dict(topics.most_common()),"rejected":dict(rejected)}
    if args.dry_run:
        return report
    if len(records) < args.minimum:
        raise RuntimeError(f"Only {len(records)} complete records; required minimum is {args.minimum}. Database was not changed.")

    con = sqlite3.connect(args.database)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    started = utcnow()
    run_id = con.execute("INSERT INTO import_runs(importer_version,started_at,status) VALUES(?,?,'running')", (VERSION, started)).lastrowid
    try:
        flores_files = [args.flores_root / split / f"{lang}.{split}" for split in ("dev","devtest") for lang in ("eng_Latn","vie_Latn")]
        source_files = {"cefr-j-1.5":[args.cefr],"skypedia-en-vi":[args.dictionary],"tatoeba-vie-eng":[args.tatoeba],"flores-200":flores_files,"ntrex-128":[args.ntrex_en,args.ntrex_vi]}
        for name, values in SOURCE_ROWS.items():
            version, url, license_name, license_url, attribution = values
            combined_hash = hashlib.sha256("".join(sha256(path) for path in source_files[name]).encode()).hexdigest()
            con.execute("""INSERT INTO data_sources VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET version=excluded.version,source_url=excluded.source_url,license_name=excluded.license_name,license_url=excluded.license_url,attribution=excluded.attribution,retrieved_at=excluded.retrieved_at,sha256=excluded.sha256""", (name,version,url,license_name,license_url,attribution,started,combined_hash))
        inserted = updated = 0
        seen_ids = []
        for record in records:
            existing = con.execute("SELECT id FROM library_words WHERE normalized_word=? OR (normalized_word='' AND lower(word)=?) ORDER BY id LIMIT 1", (record["word"],record["word"])).fetchone()
            values = (record["word"],record["meaning"],record["ipa"],record["example"],record["topic"],record["emoji"],record["stage"],record["pos"],"merged-open-v1",record["word"],"CEFR-J terms + CC BY-SA 4.0 + CC BY 2.0 FR",1,record["word"],record["example_vi"],100,started)
            if existing:
                word_id = existing["id"]
                con.execute("""UPDATE library_words SET word=?,meaning=?,ipa=?,example=?,topic=?,emoji=?,stage=?,pos=?,source=?,source_id=?,license=?,reviewed=?,normalized_word=?,example_vi=?,quality_score=?,updated_at=? WHERE id=?""", values + (word_id,))
                updated += 1
            else:
                word_id = con.execute("""INSERT INTO library_words(word,meaning,ipa,example,topic,emoji,stage,pos,source,source_id,license,reviewed,normalized_word,example_vi,quality_score,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values).lastrowid
                inserted += 1
            seen_ids.append(word_id)
            attributions = [
                ("level,pos","cefr-j-1.5",record["word"],""),
                ("meaning,ipa","skypedia-en-vi",record["word"],""),
                ("example,example_vi",record["example_source"],record["example_attribution"],record["example_attribution"]),
            ]
            for field, source, source_id, note in attributions:
                src = SOURCE_ROWS[source]
                con.execute("""INSERT INTO word_attributions(word_id,field_name,source_name,source_record_id,source_url,license_name,attribution) VALUES(?,?,?,?,?,?,?) ON CONFLICT(word_id,field_name,source_name) DO UPDATE SET source_record_id=excluded.source_record_id,attribution=excluded.attribution""", (word_id,field,source,source_id,src[1],src[2],note))
        placeholders = ",".join("?" for _ in seen_ids)
        con.execute(f"UPDATE library_words SET reviewed=0 WHERE reviewed=1 AND id NOT IN ({placeholders})", seen_ids)
        report.update({"inserted":inserted,"updated":updated,"published":len(seen_ids)})
        con.execute("UPDATE import_runs SET finished_at=?,status='completed',inserted=?,updated=?,skipped=?,report_json=? WHERE id=?", (utcnow(),inserted,updated,sum(rejected.values()),json.dumps(report,ensure_ascii=False,sort_keys=True),run_id))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return report


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=root / "speakseed.db")
    parser.add_argument("--migrations", type=Path, default=root / "migrations")
    parser.add_argument("--cefr", type=Path, default=root / ".source-cache/cefrj/olp-en-cefrj-master/cefrj-vocabulary-profile-1.5.csv")
    parser.add_argument("--dictionary", type=Path, default=root / ".source-cache/dictionary_en_vi.db")
    parser.add_argument("--tatoeba", type=Path, default=root / ".source-cache/tatoeba/vie.txt")
    parser.add_argument("--flores-root", type=Path, default=root / ".source-cache/flores/flores200_dataset")
    parser.add_argument("--ntrex-en", type=Path, default=root / ".source-cache/ntrex.eng.txt")
    parser.add_argument("--ntrex-vi", type=Path, default=root / ".source-cache/ntrex.vie.txt")
    parser.add_argument("--minimum", type=int, default=4000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for path in (args.cefr,args.dictionary,args.tatoeba,args.ntrex_en,args.ntrex_vi,args.flores_root / "dev/eng_Latn.dev",args.flores_root / "dev/vie_Latn.dev",args.flores_root / "devtest/eng_Latn.devtest",args.flores_root / "devtest/vie_Latn.devtest"):
        if not path.is_file():
            parser.error(f"Missing source file: {path}")
    print(json.dumps(build(args),ensure_ascii=False,indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
