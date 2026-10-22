"""Import openly licensed language datasets into SpeakSeed SQLite.
Imported content defaults to reviewed=0. Review before publication.
Usage: python import_data.py cefrj-vocab path.csv [--publish]
"""
import argparse,csv,sqlite3,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def normlevel(s):
 s=str(s or '').upper().strip().replace(' ','')
 for v in ('A0','A1.1','A1.2','A2.1','A2.2','B1','A1','A2'):
  if s.startswith(v):return {'A1':'A1.1','A2':'A2.1'}.get(v,v)
 return None

def rows_csv(path):
 with open(path,encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f)
  for row in r:yield {str(k).strip().lower():str(v or '').strip() for k,v in row.items() if k}

def pick(row,*keys):
 for key in keys:
  if row.get(key):return row[key]
 return ''

def main():
 p=argparse.ArgumentParser();p.add_argument('source',choices=['cefrj-vocab','cefrj-grammar','words-cefr','openjam','kaikki','tatoeba']);p.add_argument('file');p.add_argument('--publish',action='store_true',help='Only for human-reviewed content with verified rights');p.add_argument('--language',default='vi');p.add_argument('--limit',type=int,default=50000);a=p.parse_args()
 con=sqlite3.connect(ROOT/'speakseed.db'); con.execute('PRAGMA busy_timeout=15000')
 published=int(a.publish);inserted=0;skipped=0
 def word(w,level,meaning='',ipa='',example='',pos='',sourceid='',license=''):
  nonlocal inserted,skipped
  w=w.strip().lower();level=normlevel(level)
  if not level or not re.fullmatch(r"[a-z][a-z '\-]{0,69}",w):skipped+=1;return
  # Imported untranslated words remain unpublished and are excluded from practice.
  rev=published if meaning else 0
  con.execute('''INSERT INTO library_words(word,meaning,ipa,example,stage,pos,source,source_id,license,reviewed) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(word,source) DO UPDATE SET stage=excluded.stage,pos=excluded.pos,source_id=excluded.source_id''',(w,meaning,ipa,example,level,pos,a.source,sourceid,license,rev));inserted+=1
 if a.source=='cefrj-vocab':
  for r in rows_csv(a.file):
   word(pick(r,'headword','word','lemma','entry','vocabulary'),pick(r,'cefr-j level','cefrj level','cefr level','level','cefr-j','cefrj'),pos=pick(r,'pos','part of speech'),sourceid=pick(r,'id'),license='CEFR-J attribution required')
 elif a.source=='cefrj-grammar':
  for r in rows_csv(a.file):
   level=normlevel(pick(r,'cefr-j level','cefrj level','level','cefr-j','cefrj'))
   title=pick(r,'grammar item','grammar','grammatical item','item','title','structure')
   if not title or not level:skipped+=1;continue
   con.execute('INSERT INTO library_grammar(level,title,explanation,source,source_id,license,reviewed) VALUES(?,?,?,?,?,?,?)',(level,title,pick(r,'description','explanation','example'),a.source,pick(r,'id'),'CEFR-J attribution required',published));inserted+=1
 elif a.source=='words-cefr':
  db=sqlite3.connect(a.file);db.row_factory=sqlite3.Row
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if 'words' not in tables or 'word_pos' not in tables:raise ValueError('Expected words and word_pos tables from Words-CEFR-Dataset')
  # Supports official SQLite schema, with dynamic column inspection.
  wc={r[1] for r in db.execute('PRAGMA table_info(words)')};pc={r[1] for r in db.execute('PRAGMA table_info(word_pos)')}
  if not {'word_id','word'}<=wc or not {'word_id','level'}<=pc:raise ValueError('Unexpected SQLite schema; inspect dataset first')
  for r in db.execute('SELECT w.word AS word, MIN(p.level) AS level FROM words w JOIN word_pos p ON p.word_id=w.word_id GROUP BY w.word LIMIT ?',(a.limit,)):
   try:level=float(r['level']);level=['A1','A1','A2','B1','B1','B1'][max(0,min(5,round(level)-1))]
   except (ValueError,TypeError):level=r['level']
   word(r['word'],level,license='MIT; verify upstream dataset notices')
 elif a.source=='openjam':
  # JSON array or JSONL exports. PostgreSQL SQL dumps require conversion to JSON first.
  text=Path(a.file).read_text(encoding='utf-8');items=json.loads(text) if text.lstrip().startswith('[') else (json.loads(x) for x in text.splitlines() if x.strip())
  if isinstance(items,dict):items=items.get('words',[])
  for r in items:
   if not isinstance(r,dict):continue
   translation=r.get('meaning_vi') or r.get('vi') or ''
   if not translation and isinstance(r.get('translations'),dict):translation=r['translations'].get('vi','')
   word(str(r.get('english') or r.get('word') or ''),r.get('level'),str(translation),str(r.get('ipa') or ''),str(r.get('example') or ''),sourceid=str(r.get('id') or ''),license='MIT; preserve attribution')
 elif a.source=='kaikki':
  with open(a.file,encoding='utf-8') as f:
   for line in f:
    if inserted>=a.limit:break
    try:r=json.loads(line)
    except json.JSONDecodeError:skipped+=1;continue
    if r.get('lang_code')!='en':continue
    ipa=next((x.get('ipa','') for x in r.get('sounds',[]) if x.get('ipa')),'')
    # Kaikki doesn't reliably provide CEFR/VI translation; imported as draft A1.1 only.
    word(r.get('word',''),'A1.1',ipa=ipa,pos=r.get('pos',''),license='Wiktionary CC BY-SA / GFDL; attribution and share-alike obligations')
 elif a.source=='tatoeba':
  # TSV: id<TAB>language_code<TAB>sentence; English only; optional translations require joining a separate links export.
  with open(a.file,encoding='utf-8') as f:
   for line in f:
    if inserted>=a.limit:break
    cols=line.rstrip('\n').split('\t')
    if len(cols)<3 or cols[1]!='eng':continue
    sentence=cols[2].strip()
    if not sentence or len(sentence)>250:continue
    con.execute('INSERT OR IGNORE INTO library_sentences(english,level,source,source_id,license,reviewed) VALUES(?,?,?,?,?,?)',(sentence,'A1.1','tatoeba',cols[0],'Tatoeba: verify per-sentence CC BY 2.0 FR / CC0',0));inserted+=1
 con.commit();con.close();print(f'Imported/updated: {inserted}; skipped: {skipped}. Unreviewed content is hidden until verified and published.')
if __name__=='__main__':main()
