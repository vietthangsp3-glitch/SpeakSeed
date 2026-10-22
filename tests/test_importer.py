import argparse
import sqlite3
from pathlib import Path

from tools.build_vocabulary import build, dictionary_entry


ROOT = Path(__file__).resolve().parents[1]


def test_import_is_complete_and_idempotent(tmp_path):
    cefr = tmp_path / "cefr.csv"
    cefr.write_text("headword,pos,CEFR,CoreInventory 1,CoreInventory 2,Threshold\napple,noun,A1,,,\n", encoding="utf-8")
    tatoeba = tmp_path / "pairs.txt"
    tatoeba.write_text("I have an apple.\tTôi có một quả táo.\tTatoeba #1 & #2\n", encoding="utf-8")
    dictionary = tmp_path / "dictionary.db"
    con = sqlite3.connect(dictionary)
    con.executescript("""CREATE TABLE words(id INTEGER PRIMARY KEY,word TEXT);
        CREATE TABLE definitions(id INTEGER PRIMARY KEY,definition TEXT,pos TEXT);
        CREATE TABLE word_definitions(id INTEGER PRIMARY KEY,word_id INTEGER,definition_id INTEGER,example TEXT);
        CREATE TABLE pronunciations(word_id INTEGER,ipa TEXT);
        INSERT INTO words VALUES(1,'apple'); INSERT INTO definitions VALUES(1,'quả táo','N');
        INSERT INTO word_definitions VALUES(1,1,1,'I eat an apple.'); INSERT INTO pronunciations VALUES(1,'/ˈæp.əl/');""")
    con.close()
    flores = tmp_path / "flores"
    for split in ("dev", "devtest"):
        (flores / split).mkdir(parents=True)
        for lang in ("eng_Latn", "vie_Latn"):
            (flores / split / f"{lang}.{split}").write_text("", encoding="utf-8")
    ntrex_en, ntrex_vi = tmp_path / "ntrex.en", tmp_path / "ntrex.vi"
    ntrex_en.write_text("", encoding="utf-8"); ntrex_vi.write_text("", encoding="utf-8")
    args = argparse.Namespace(database=tmp_path/"app.db",migrations=ROOT/"migrations",cefr=cefr,dictionary=dictionary,tatoeba=tatoeba,flores_root=flores,ntrex_en=ntrex_en,ntrex_vi=ntrex_vi,minimum=1,dry_run=False)
    first, second = build(args), build(args)
    assert first["published"] == 1 and first["inserted"] == 1
    assert second["published"] == 1 and second["inserted"] == 0
    con = sqlite3.connect(args.database)
    row = con.execute("SELECT word,meaning,ipa,pos,stage,topic,example,example_vi,reviewed FROM library_words").fetchone()
    assert row[-1] == 1 and all(row[:-1])


def test_dictionary_selection_respects_cefr_part_of_speech(tmp_path):
    database = tmp_path / "senses.db"
    con = sqlite3.connect(database)
    con.executescript("""CREATE TABLE words(id INTEGER PRIMARY KEY,word TEXT);
      CREATE TABLE definitions(id INTEGER PRIMARY KEY,definition TEXT,pos TEXT);
      CREATE TABLE word_definitions(id INTEGER PRIMARY KEY,word_id INTEGER,definition_id INTEGER,example TEXT);
      CREATE TABLE pronunciations(word_id INTEGER,ipa TEXT);
      INSERT INTO words VALUES(1,'a');
      INSERT INTO definitions VALUES(1,'một; một nào đó','X');
      INSERT INTO definitions VALUES(2,'đang','E');
      INSERT INTO word_definitions VALUES(1,1,1,'A book.');
      INSERT INTO word_definitions VALUES(2,1,2,'A book.');
      INSERT INTO pronunciations VALUES(1,'/ə/');""")
    assert dictionary_entry(con, "a", {"determiner"}, "UFO là gì?")[0] == "một; một nào đó"
