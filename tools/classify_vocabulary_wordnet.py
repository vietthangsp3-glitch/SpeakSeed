"""Conservative WordNet-domain classification for published vocabulary.

Only lexicographer domains that directly correspond to a SpeakSeed topic are
mapped without extra conditions. Broad WordNet domains require an explicit
definition keyword. Dry-run is the default; no AI service is used.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from migrations import run_migrations

RULE_VERSION = "wordnet-domain-v1"
WORDNET = ROOT / ".source-cache" / "WordNet-3.0.tar.gz"
AMBIGUOUS_SENSES = {"extension", "prince", "princess"}

# Only these inherited labels are automatically withdrawn. Each pair is a
# verified contradiction, not merely a different (possibly additional) topic.
LEGACY_CORRECTIONS = {
    "teacher": ("family-relationships", "work-careers"), "birthday": ("emotions-personality", "daily-life"),
    "shopping": ("emotions-personality", "shopping-money"), "winter": ("emotions-personality", "daily-life"),
    "bird": ("food-drinks", "animals-plants"), "cow": ("food-drinks", "animals-plants"),
    "monkey": ("food-drinks", "animals-plants"), "pet": ("food-drinks", "animals-plants"),
    "turkey": ("home-furniture", "animals-plants"), "cousin": ("nature-environment", "family-relationships"),
    "flower": ("nature-environment", "animals-plants"), "wednesday": ("nature-environment", "daily-life"),
    "daddy": ("society-culture", "family-relationships"), "frog": ("society-culture", "animals-plants"),
    "sheep": ("society-culture", "animals-plants"), "city": ("society-culture", "places-directions"),
    "august": ("travel-tourism", "daily-life"), "bike": ("work-careers", "transportation"),
    "pleasure": ("work-careers", "emotions-personality"), "supper": ("communication", "food-drinks"),
    "chef": ("family-relationships", "work-careers"), "fisherman": ("family-relationships", "work-careers"),
    "garlic": ("emotions-personality", "animals-plants"), "shore": ("food-drinks", "nature-environment"),
    "discussion": ("home-furniture", "communication"), "envy": ("society-culture", "emotions-personality"),
    "scene": ("society-culture", "places-directions"), "countryside": ("society-culture", "places-directions"),
    "refer": ("society-culture", "communication"), "zone": ("society-culture", "places-directions"),
    "niece": ("communication", "family-relationships"), "gymnastics": ("family-relationships", "sports-fitness"),
    "preference": ("family-relationships", "emotions-personality"), "chemistry": ("emotions-personality", "science"),
    "ocean": ("home-furniture", "nature-environment"), "bulletin": ("nature-environment", "communication"),
    "gorilla": ("nature-environment", "animals-plants"), "region": ("nature-environment", "places-directions"),
    "destination": ("society-culture", "places-directions"), "boast": ("daily-life", "communication"),
    "demand": ("travel-tourism", "communication"), "malaria": ("communication", "health-body"),
    "helicopter": ("daily-life", "transportation"), "judo": ("daily-life", "sports-fitness"),
    "extension": ("society-culture", "education"),
}

# WordNet is English-only and therefore cannot by itself disambiguate the
# Vietnamese sense published by SpeakSeed (bank=river bank vs nhà ngân hàng,
# server=waiter vs máy chủ, etc.).  A domain is released only when the
# published Vietnamese meaning independently confirms the same domain.  These
# are intentionally high-precision cues rather than a general-purpose NLP
# classifier.
VI_CONFIRM = {
    "animals-plants": re.compile(r"(?:\bcon\s+(?:vật|chim|cá|chó|mèo|khỉ|ong|bướm|ếch|rắn|cừu|thỏ|chuột)\b|\bloài\s+(?:vật|chim|cá|cây)\b|\bđộng vật\b|\bthực vật\b|\bcây\s+(?:cối|hoa|cỏ|tỏi|nấm|bụi)|\bhoa\b|\blá cây\b|\bvật cưng\b|\bgà tây\b|\bbò cái\b|\blợn\b|\bheo\b|\bngựa\b|\bsư tử\b|\bkhủng long\b)", re.I),
    "food-drinks": re.compile(r"(?:\bmón ăn\b|\bđồ uống\b|\bbữa (?:ăn|cơm)\b|\bthịt\b|\bbánh\b|\bcà phê\b|\bsữa\b|\btrà\b|\bchè\b|\bnước ép\b|\bkem\b|\bkẹo\b|\bphó mát\b|\bbơ\b|\bgạo\b|\bcơm\b|\brau\b|\bquả (?:táo|cam|nho|chuối)\b|\bgia vị\b)", re.I),
    "health-body": re.compile(r"(?:\bbộ phận cơ thể\b|\bcơ thể\b|\bsức khoẻ\b|\bsức khỏe\b|\b(?:căn |chứng )?bệnh\b|\by học\b|\bdược\b|\bthuốc\b|\bphẫu thuật\b|\b(?:máu|xương|não|óc|tai|mắt|mặt|tóc|đầu gối|cánh tay|bàn tay|chân|miệng|mồm|răng|bụng|dạ dày|ngực|ngón chân|cằm|môi|vú|khuỷu tay|trán|hông|gan|phổi|cơ bắp)\b)", re.I),
    "emotions-personality": re.compile(r"(?:\bcảm thấy\b|\bcảm xúc\b|\btính cách\b|\btâm trạng\b|\bniềm vui\b|\bnỗi buồn\b|\bhy vọng\b|\bmong ước\b|\byêu\b|\bthích\b|\bghét\b|\bsợ\b|\bkinh hãi\b|\bghen\b|\btức giận\b|\bngạc nhiên\b|\bhối tiếc\b|\bthất vọng\b|\bkhâm phục\b|\bthương hại\b)", re.I),
    "communication": re.compile(r"(?:\bngôn ngữ\b|\bnói\b|\bhỏi\b|\btrả lời\b|\bcâu hỏi\b|\bthảo luận\b|\bphỏng vấn\b|\btin nhắn\b|\bthông điệp\b|\bthông báo\b|\bthư\b|\bbài báo\b|\btạp chí\b|\btừ điển\b|\bdanh sách\b|\bbiểu mẫu\b|\bmô tả\b|\bphát âm\b|\bngữ pháp\b|\btừ vựng\b)", re.I),
    "places-directions": re.compile(r"(?:\bvị trí\b|\bphương hướng\b|\bkhu vực\b|\bvùng\b|\bnơi\b|\bchỗ\b|\bthành phố\b|\bthị xã\b|\bnông thôn\b|\bmiền quê\b|\bbiên giới\b|\bquận\b|\bhuyện\b|\bcảng\b|\bkhuôn viên\b|\bsân chơi\b)", re.I),
    "daily-life": re.compile(r"(?:\bngày\b|\btháng\b|\bnăm\b|\btuần\b|\bgiờ\b|\bphút\b|\bbuổi sáng\b|\bbuổi chiều\b|\bbuổi tối\b|\bđêm\b|\bmùa\b|\bsinh nhật\b|\bkỳ nghỉ\b|\bcuối tuần\b)", re.I),
    "family-relationships": re.compile(r"(?:\bmẹ\b|\bcha\b|\bbố\b|\bông\b|\bbà\b|\bcô\b|\bdì\b|\bchú\b|\bbác\b|\bcậu\b|\bdượng\b|\bcon dâu\b|\bcháu\b|\btổ tiên\b|\bquả phụ\b|\bgóa\b|\bgoá\b)", re.I),
    "work-careers": re.compile(r"(?:\bnghề\b|\bnhân viên\b|\bcông nhân\b|\bngười làm công\b|\bthợ\b|\bgiáo viên\b|\bluật sư\b|\bđầu bếp\b|\bthủ thư\b|\bdược sĩ\b|\bngười bán hàng\b|\bngười phục vụ\b|\bngười đánh cá\b)", re.I),
    "clothing-fashion": re.compile(r"(?:\bquần áo\b|\báo quần\b|\báo sơ mi\b|\báo choàng\b|\báo len\b|\btạp dề\b|\bgiày\b|\bkhăn quàng\b|\bđồng phục\b|\btay áo\b|\btrang phục\b|\bkhuyên tai\b|\bchuỗi hạt\b)", re.I),
    "transportation": re.compile(r"(?:\bxe\b|\bxe buýt\b|\bxe đạp\b|\bô tô\b|\bmáy bay\b|\btàu bay\b|\bxe lửa\b|\bđường băng\b|\btrực thăng\b|\bgiao thông\b)", re.I),
    "technology": re.compile(r"(?:\bmáy tính\b|\bmáy chủ\b|\bserver\b|\bphần mềm\b|\bđiện tử\b|\bkỹ thuật số\b|\bbàn phím\b|\bweb\b|\binternet\b|\bdữ liệu\b)", re.I),
    "education": re.compile(r"(?:\btrường\b|\bđại học\b|\bcao đẳng\b|\bhọc viện\b|\bgiáo dục\b|\bhọc tập\b|\bmôn học\b)", re.I),
    "science": re.compile(r"(?:\bkhoa học\b|\btoán học\b|\bhóa học\b|\bhoá học\b|\bvật lý\b|\bsinh học\b|\bđịa chất\b|\btâm lý\b|\bthiên văn\b)", re.I),
    "shopping-money": re.compile(r"(?:\btiền\b|\btiền mặt\b|\bthẻ tín dụng\b|\bthẻ ghi nợ\b|\bngân sách\b|\bgiá\b|\bchi phí\b|\bmua hàng\b|\bbán lẻ\b|\bhoàn tiền\b|\btỉ giá\b|\bséc\b)", re.I),
    "business-finance": re.compile(r"(?:\bcông ty\b|\bdoanh nghiệp\b|\bcổ phần\b|\bvốn\b|\bđầu tư\b|\btài chính\b|\blợi nhuận\b)", re.I),
    "sports-fitness": re.compile(r"(?:\bmôn thể thao\b|\bthể dục\b|\bbóng chày\b|\bbóng rổ\b|\bquần vợt\b|\bcầu lông\b|\bbóng ném\b|\bbăng cầu\b|\btrượt ván\b|\blướt sóng\b|\bjuđô\b)", re.I),
    "weather-seasons": re.compile(r"(?:\bthời tiết\b|\bbão\b|\bdông tố\b|\bvòi rồng\b|\btuyết\b|\bmưa\b|\bgió\b)", re.I),
    "home-furniture": re.compile(r"(?:\bđồ gỗ\b|\bđồ nội thất\b|\bgiường\b|\btủ sách\b|\btủ quần áo\b|\bngăn kéo\b|\bbàn\b)", re.I),
    "nature-environment": re.compile(r"(?:\bthiên nhiên\b|\bmôi trường\b|\bđại dương\b|\bbiển\b|\bbờ biển\b|\bsông\b|\bsuối\b|\bphong cảnh\b|\bđịa lý\b)", re.I),
}

DIRECT = {
    "noun.animal": "animals-plants", "noun.plant": "animals-plants",
    "noun.food": "food-drinks", "noun.body": "health-body",
    "noun.feeling": "emotions-personality", "noun.communication": "communication",
    "noun.location": "places-directions", "noun.time": "daily-life",
    "verb.communication": "communication", "verb.emotion": "emotions-personality",
}

# Broad lexicographer files are accepted only when a sense definition contains
# one of these high-specificity expressions.
CONDITIONAL: dict[str, list[tuple[str, str]]] = {
    "noun.person": [
        ("family-relationships", r"\b(?:relative|parent|mother|father|sibling|brother|sister|spouse|wife|husband|son|daughter|grandparent|grandchild|uncle|aunt|cousin|nephew|niece)\b"),
        ("work-careers", r"\b(?:professional|employee|worker|tradesman|craftsman|whose job|occupation is|employed to|works in|works for)\b"),
    ],
    "noun.artifact": [
        ("clothing-fashion", r"\b(?:garment|clothing|footwear|headwear|wearing apparel|jewelry|jewellery)\b"),
        ("transportation", r"(?:^(?:a|an) (?:motor )?vehicle\b|\b(?:vehicle designed|vehicle used|wheeled vehicle|aircraft|automobile|motorcycle|bicycle|railway|railroad|ship used|boat used|passenger transport)\b)"),
        ("technology", r"\b(?:computer|software|electronic device|digital device|telecommunication|data processing|internet|network device)\b"),
        ("home-furniture", r"\b(?:piece of furniture|household appliance|household utensil|used in a house|used in the home|bedroom|kitchen utensil)\b"),
        ("sports-fitness", r"\b(?:sports equipment|used in playing|athletic equipment|exercise machine)\b"),
    ],
    "noun.substance": [
        ("food-drinks", r"\b(?:food|beverage|drink|edible|ingredient|spice|seasoning)\b"),
        ("health-body", r"\b(?:medicine|medication|pharmaceutical|drug used to|medical drug)\b"),
    ],
    "noun.state": [
        ("health-body", r"\b(?:disease|illness|medical condition|disorder characterized|pathological)\b"),
        ("emotions-personality", r"\b(?:emotional state|state of mind|feeling of|mood)\b"),
    ],
    "noun.phenomenon": [
        ("weather-seasons", r"\b(?:weather|meteorological|rainfall|snowfall|snowstorm|thunderstorm|tornado|windstorm|atmospheric temperature)\b"),
        ("nature-environment", r"\b(?:natural phenomenon|geological|environmental phenomenon)\b"),
    ],
    "noun.object": [
        ("nature-environment", r"\b(?:natural object|geographical|geographic|landform|body of water|celestial body)\b"),
    ],
    "noun.group": [
        ("business-finance", r"\b(?:business organization|commercial organization|corporation|company that|financial institution)\b"),
        ("society-culture", r"\b(?:social group|community of people|human community|government body|political organization|religious group)\b"),
        ("education", r"\b(?:school|university|college|educational institution)\b"),
    ],
    "noun.possession": [
        ("shopping-money", r"\b(?:money|currency|payment|price|cost of|purchase)\b"),
        ("business-finance", r"\b(?:investment|financial asset|profit|capital|stock ownership)\b"),
    ],
    "noun.event": [
        ("sports-fitness", r"\b(?:sporting event|athletic contest|sports competition|game between|match between)\b"),
        ("entertainment", r"\b(?:performance|concert|show for|theatrical|entertainment event)\b"),
    ],
    "noun.act": [
        ("sports-fitness", r"\b(?:sport|athletic activity|physical exercise|game played)\b"),
        ("communication", r"\b(?:act of communicating|speech act|written communication)\b"),
        ("shopping-money", r"\b(?:buying|selling|shopping|payment for)\b"),
    ],
    "noun.cognition": [
        ("education", r"\b(?:learning|teaching|course of study|academic discipline|education)\b"),
        ("science", r"\b(?:science|scientific theory|scientific knowledge|branch of knowledge)\b"),
    ],
    "noun.process": [
        ("science", r"\b(?:biological process|chemical process|physical process|scientific process)\b"),
        ("health-body", r"\b(?:bodily process|physiological process|medical treatment)\b"),
    ],
    "noun.attribute": [
        ("emotions-personality", r"\b(?:personality trait|temperament|emotional quality|character trait)\b"),
    ],
    "verb.body": [
        ("health-body", r"\b(?:bodily|body|physiological|pain|injury|disease|breath|blood)\b"),
        ("food-drinks", r"\b(?:eat|drink|swallow|digest|taste food)\b"),
        ("daily-life", r"\b(?:sleep|wake|wash|bathe|dress oneself)\b"),
    ],
    "verb.social": [
        ("work-careers", r"\b(?:employ|hire|work for|do business|manage a business)\b"),
        ("society-culture", r"\b(?:government|law|social relation|political|religious)\b"),
        ("education", r"\b(?:teach|educate|study|attend school)\b"),
    ],
}
CONDITIONAL = {lex: [(topic, re.compile(pattern, re.I)) for topic, pattern in rules]
               for lex, rules in CONDITIONAL.items()}


def normalize(value: str) -> str:
    return " ".join(value.replace("_", " ").casefold().split())


def load_senses(path: Path, wanted: dict[str, str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    with tarfile.open(path, "r:gz") as archive:
        lex_member = next(m for m in archive.getmembers() if m.name.endswith("/dict/lexnames"))
        lexnames = {}
        for raw in archive.extractfile(lex_member):
            parts = raw.decode("utf-8").split()
            if len(parts) >= 2:
                lexnames[int(parts[0])] = parts[1]
        first_offsets: dict[tuple[str, str], str] = {}
        for suffix in ("noun", "verb"):
            member = next(m for m in archive.getmembers() if m.name.endswith(f"/dict/index.{suffix}"))
            for raw in archive.extractfile(member):
                line = raw.decode("utf-8", "replace")
                if not line[:1].isalnum():
                    continue
                parts = line.split()
                try:
                    pointer_count = int(parts[3])
                    offsets_start = 6 + pointer_count
                    lemma = normalize(parts[0])
                    first_offsets[(lemma, suffix)] = parts[offsets_start]
                except (ValueError, IndexError):
                    continue
        for suffix in ("noun", "verb"):
            member = next(m for m in archive.getmembers() if m.name.endswith(f"/dict/data.{suffix}"))
            for raw in archive.extractfile(member):
                line = raw.decode("utf-8", "replace")
                if not line[:1].isdigit() or "|" not in line:
                    continue
                left, gloss = line.split("|", 1)
                parts = left.split()
                try:
                    lexname = lexnames[int(parts[1])]
                    word_count = int(parts[3], 16)
                except (ValueError, IndexError, KeyError):
                    continue
                for index in range(word_count):
                    lemma = normalize(parts[4 + index * 2])
                    # WordNet index order is frequency-ranked. Use only the
                    # primary sense matching SpeakSeed's published POS; rare
                    # homonyms must not create misleading topic mappings.
                    if (wanted.get(lemma) == suffix and
                            first_offsets.get((lemma, suffix)) == parts[0]):
                        result[lemma].append({"lexname": lexname, "gloss": gloss.strip()})
    return result


def proposed_topics(senses: list[dict], meaning: str = "") -> dict[str, dict]:
    found: dict[str, dict] = {}
    for sense in senses:
        lexname, gloss = sense["lexname"], sense["gloss"]
        definition = gloss.split('; "', 1)[0]
        if lexname in DIRECT:
            topic = DIRECT[lexname]
            confirmation = VI_CONFIRM.get(topic)
            hit = confirmation.search(meaning or "") if confirmation else None
            if hit:
                found.setdefault(topic, {"confidence": 96, "rule_id": f"bilingual:{lexname}:{hit.group(0).casefold()}",
                                         "evidence": f"WordNet domain {lexname}, confirmed by Vietnamese meaning '{hit.group(0)}'; {gloss}"})
        for topic, pattern in CONDITIONAL.get(lexname, []):
            hit = pattern.search(definition)
            vi = VI_CONFIRM.get(topic)
            vi_hit = vi.search(meaning or "") if vi else None
            if hit and vi_hit:
                found.setdefault(topic, {"confidence": 94,
                    "rule_id": f"bilingual-definition:{lexname}:{hit.group(0).casefold()}:{vi_hit.group(0).casefold()}",
                    "evidence": f"WordNet {lexname} definition '{hit.group(0)}', confirmed by Vietnamese meaning '{vi_hit.group(0)}'; {gloss}"})
    return found


def classify(database: Path, wordnet: Path, apply: bool) -> dict:
    run_migrations(database, ROOT / "migrations")
    con = sqlite3.connect(database, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    words = list(con.execute("SELECT id,word,normalized_word,meaning,topic,pos FROM library_words WHERE reviewed=1 ORDER BY id"))
    pos_map = {"noun": "noun", "verb": "verb"}
    senses = load_senses(wordnet, {row["normalized_word"]: pos_map[row["pos"]]
                                   for row in words if row["pos"] in pos_map})
    topic_ids = {row["slug"]: row["id"] for row in con.execute("SELECT id,slug FROM vocabulary_topics WHERE active=1")}
    existing = {(row[0], row[1]) for row in con.execute(
        "SELECT word_id,topic_id FROM vocabulary_topic_words WHERE published=1")}
    rows = []
    for word in words:
        if word["normalized_word"] in AMBIGUOUS_SENSES:
            continue
        for slug, evidence in proposed_topics(senses.get(word["normalized_word"], []), word["meaning"]).items():
            if (word["id"], topic_ids[slug]) not in existing:
                rows.append({"word_id": word["id"], "word": word["word"], "topic_id": topic_ids[slug],
                             "topic": slug, **evidence})
    before = con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0]
    corrections = []
    for word in words:
        pair = LEGACY_CORRECTIONS.get(word["normalized_word"])
        if pair and (word["id"], topic_ids[pair[0]]) in existing:
            corrections.append({"word_id": word["id"], "word": word["word"],
                                "old_topic": pair[0], "old_topic_id": topic_ids[pair[0]],
                                "new_topic": pair[1], "new_topic_id": topic_ids[pair[1]]})
    summary = {"mode": "apply" if apply else "dry-run", "proposed_mappings": len(rows),
               "proposed_words": len({r['word_id'] for r in rows}), "classified_before": before,
               "legacy_corrections": len(corrections),
               "matched_wordnet_words": len(senses), "by_topic": dict(sorted(Counter(r["topic"] for r in rows).items())),
               "samples": {topic: [r["word"] for r in rows if r["topic"] == topic][:12]
                           for topic in sorted({r["topic"] for r in rows})}}
    if not apply:
        con.close()
        return summary
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        con.execute("BEGIN IMMEDIATE")
        for row in rows:
            payload = json.dumps({"rule_version": RULE_VERSION, "rule_id": row["rule_id"],
                                  "evidence": row["evidence"], "word": row["word"]}, ensure_ascii=False)
            con.execute("""INSERT OR IGNORE INTO vocabulary_automated_topic_releases
              (word_id,topic_id,rule_version,rule_id,evidence_json,released_at) VALUES(?,?,?,?,?,?)""",
              (row["word_id"], row["topic_id"], RULE_VERSION, row["rule_id"], payload, stamp))
            con.execute("""INSERT INTO vocabulary_topic_words
              (word_id,topic_id,sense_key,review_status,published,confidence,source_key,rationale,created_at)
              VALUES(?,?,'','pending',1,?,'automated-topic-v1',?,?)
              ON CONFLICT(word_id,topic_id,sense_key) DO NOTHING""",
              (row["word_id"], row["topic_id"], row["confidence"], row["evidence"], stamp))
        for row in corrections:
            rationale = ("Published Vietnamese meaning and primary WordNet sense contradict the inherited "
                         f"'{row['old_topic']}' label and support '{row['new_topic']}'.")
            con.execute("""INSERT OR IGNORE INTO vocabulary_topic_corrections
              (word_id,old_topic_id,new_topic_id,rule_version,rationale,corrected_at) VALUES(?,?,?,?,?,?)""",
              (row["word_id"], row["old_topic_id"], row["new_topic_id"], RULE_VERSION, rationale, stamp))
            con.execute("""UPDATE vocabulary_topic_words SET published=0,review_status='rejected',rationale=?
              WHERE word_id=? AND topic_id=? AND source_key='library_words.topic' AND published=1""",
              (rationale, row["word_id"], row["old_topic_id"]))
            con.execute("""UPDATE library_words SET topic=(SELECT name_en FROM vocabulary_topics WHERE id=?)
              WHERE id=? AND topic=(SELECT name_en FROM vocabulary_topics WHERE id=?)""",
              (row["new_topic_id"], row["word_id"], row["old_topic_id"]))
        con.execute("""UPDATE library_words SET topic=(SELECT t.name_en FROM vocabulary_topic_words tw
          JOIN vocabulary_topics t ON t.id=tw.topic_id WHERE tw.word_id=library_words.id AND tw.published=1
          ORDER BY t.id LIMIT 1) WHERE topic='Unclassified' AND (SELECT COUNT(*) FROM vocabulary_topic_words tw
          WHERE tw.word_id=library_words.id AND tw.published=1)=1""")
        con.commit()
    except Exception:
        con.rollback()
        raise
    after = con.execute("SELECT COUNT(DISTINCT word_id) FROM vocabulary_topic_words WHERE published=1").fetchone()[0]
    summary.update({"classified_after": after, "newly_classified_words": after-before,
                    "unclassified_after": con.execute("""SELECT COUNT(*) FROM library_words w WHERE w.reviewed=1
                      AND NOT EXISTS(SELECT 1 FROM vocabulary_topic_words tw WHERE tw.word_id=w.id AND tw.published=1)""").fetchone()[0]})
    con.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "speakseed.db")
    parser.add_argument("--wordnet", type=Path, default=WORDNET)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = classify(args.database, args.wordnet, args.apply)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
