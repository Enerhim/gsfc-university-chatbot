import hashlib, json, re, sqlite3, threading
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True,mode=0o700)
CONFIG=json.loads((ROOT/'config.json').read_text())
def now(): return datetime.now(timezone.utc).isoformat()
class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()

_ready=False
_init_lock=threading.Lock()
def db():
    global _ready
    c=sqlite3.connect(DATA/'knowledge.sqlite3',timeout=60,factory=ClosingConnection)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=60000')
    if _ready:return c
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,url TEXT,title TEXT,kind TEXT,visibility TEXT,published TEXT,fetched TEXT,hash TEXT,text TEXT,metadata TEXT);
    CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY,document_id TEXT,text TEXT,embedding BLOB,embedding_model TEXT);
    CREATE INDEX IF NOT EXISTS chunk_doc ON chunks(document_id);
    CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(text,content=chunks,content_rowid=id);
    CREATE TABLE IF NOT EXISTS crawl(url TEXT PRIMARY KEY,status TEXT,detail TEXT,checked TEXT);
    CREATE TABLE IF NOT EXISTS links(url TEXT,source TEXT,host TEXT,PRIMARY KEY(url,source));''')
    _ready=True
    return c

def ingest(url,title,text,kind='web',visibility='public',published='',metadata=None):
    text=re.sub(r'[ \t]+',' ',text).strip()
    if len(text)<30:return False
    key=hashlib.sha256(url.encode()).hexdigest()[:24]; digest=hashlib.sha256(text.encode()).hexdigest()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        prev=c.execute('SELECT hash FROM documents WHERE id=?',(key,)).fetchone()
        if prev and prev['hash']==digest:
            c.execute('UPDATE documents SET fetched=? WHERE id=?',(now(),key));return False
        for ch in c.execute('SELECT id,text FROM chunks WHERE document_id=?',(key,)).fetchall():
            c.execute("INSERT INTO search(search,rowid,text) VALUES('delete',?,?)",(ch['id'],ch['text']))
        c.execute('DELETE FROM chunks WHERE document_id=?',(key,))
        c.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?)',(key,url,title,kind,visibility,published,now(),digest,text,json.dumps(metadata or {})))
        # Overlapping sentence/paragraph chunks keep source context with every fragment.
        words=text.split(); size=280; overlap=55
        for start in range(0,len(words),size-overlap):
            chunk=title+'\n'+' '.join(words[start:start+size])
            row=c.execute('INSERT INTO chunks(document_id,text) VALUES(?,?)',(key,chunk))
            c.execute('INSERT INTO search(rowid,text) VALUES(?,?)',(row.lastrowid,chunk))
    return True

def record(url,status,detail=''):
    with db() as c:c.execute('INSERT OR REPLACE INTO crawl VALUES(?,?,?,?)',(url,status,detail[:1000],now()))

def stats():
    with db() as c:
        return {'university':CONFIG['university'],'documents':c.execute('SELECT count(*) FROM documents').fetchone()[0],
        'chunks':c.execute('SELECT count(*) FROM chunks').fetchone()[0],
        'embedded_chunks':c.execute('SELECT count(*) FROM chunks WHERE embedding IS NOT NULL').fetchone()[0],
        'sources':[dict(r) for r in c.execute('SELECT kind,visibility,count(*) count FROM documents GROUP BY kind,visibility')],
        'crawl':[dict(r) for r in c.execute('SELECT status,count(*) count FROM crawl GROUP BY status')],
        'last_updated':c.execute('SELECT max(fetched) FROM documents').fetchone()[0]}

STOP=set('the a an is are was were what which who how when where why can could should would do does did of in on to for and or with my me i at by it as about university gsfc please tell find lets say want work applicable eligible'.split())
def tokens(q):return [t for t in re.findall(r'[a-zA-Z0-9]+',q.lower()) if len(t)>1 and t not in STOP]

def retrieve(question,scope='public',limit=8,vector=None):
    ts=tokens(question)
    if not ts:return []
    vis='' if scope=='personal' else " AND d.visibility='public'"
    base='SELECT c.id,c.text,d.id document_id,d.url,d.title,d.kind,d.visibility,d.published,d.fetched FROM chunks c JOIN documents d ON c.document_id=d.id '
    ranked={}; texts={}
    with db() as c:
        fts=' OR '.join('"'+t+'"' for t in ts[:24])
        rows=c.execute(base+'JOIN search ON search.rowid=c.id WHERE search MATCH ?'+vis+' ORDER BY bm25(search) LIMIT 80',(fts,)).fetchall()
        for rank,r in enumerate(rows):
            d=dict(r); ranked[d['id']]=1/(40+rank);texts[d['id']]=d
        # Contact questions need current directory pages ahead of historical event reports.
        if re.search(r'(?i)\b(contact|approach|email|reach|manager|team|mentor|supervis|faculty|teach)\w*\b',question):
            directories=c.execute(base+"JOIN search ON search.rowid=c.id WHERE search MATCH ?"+vis+" AND (d.url LIKE '%team%' OR d.url LIKE '%contact%' OR d.url LIKE '%FacultyProfile%' OR d.url LIKE '%about%') ORDER BY bm25(search) LIMIT 30",(fts,)).fetchall()
            anchors=[t for t in ts if t not in {'contact','team','manager','director','email','reach','approach','funding','should'}]
            for rank,r in enumerate(directories):
                d=dict(r)
                if 'guiitar' in question.lower() and 'guiitar' not in d['url'].lower():continue
                if anchors and not any(t in d['text'].lower() for t in anchors):continue
                bonus=.095/(1+rank*.05)
                name_tokens=[t for t in tokens(d['title']) if t not in {'dr','prof','professor','mr','ms','mrs'}]
                if 'FacultyProfile' in d['url'] and name_tokens and all(t in ts for t in name_tokens):
                    bonus+=.3
                    if re.search(r'Email\s*:',d['text'],re.I):bonus+=.2
                # Research overviews explain fit better than incidental bibliography matches.
                if 'FacultyProfile' in d['url'] and re.search(r'research interests?|interest includes',d['text'],re.I):bonus+=.05
                ranked[d['id']]=ranked.get(d['id'],0)+bonus;texts[d['id']]=d
        if re.search(r'(?i)\b(when|dates?|held|scheduled)\b',question):
            # Multi-day event schedules carry the overall date range; ceremony invitations don't.
            schedules=c.execute(base+"JOIN search ON search.rowid=c.id WHERE search MATCH ?"+vis+" AND (d.title LIKE '%schedule%' OR d.title LIKE '%calendar%' OR d.title LIKE '%participation%') ORDER BY bm25(search) LIMIT 12",(fts,)).fetchall()
            entities=[t for t in ts if not t.isdigit() and t not in {'exactly','dates','date','held','scheduled','happen','taking','place'}]
            for rank,r in enumerate(schedules):
                d=dict(r)
                if entities and not any(t in d['title'].lower() for t in entities):continue
                ranked[d['id']]=ranked.get(d['id'],0)+.06/(1+rank*.1);texts[d['id']]=d
        if vector is not None:
            rows=c.execute(base+"WHERE c.embedding IS NOT NULL AND c.embedding_model=?"+vis,(CONFIG['embedding_model'],)).fetchall()
            emb={r['id']:r['embedding'] for r in c.execute('SELECT id,embedding FROM chunks WHERE embedding IS NOT NULL AND embedding_model=?',(CONFIG['embedding_model'],))}
            q=np.array(vector,dtype=np.float32);qn=np.linalg.norm(q)
            scores=[]
            for r in rows:
                v=np.frombuffer(emb[r['id']],dtype=np.float32)
                if v.shape!=q.shape:continue
                scores.append((float(np.dot(q,v)/(qn*np.linalg.norm(v)+1e-9)),r))
            for rank,(sim,r) in enumerate(sorted(scores,key=lambda x:x[0],reverse=True)[:80]):
                if sim<.3:continue
                d=dict(r);ranked[d['id']]=ranked.get(d['id'],0)+1/(40+rank);texts[d['id']]=d
    result=[]; per_doc={}
    for cid,score in sorted(ranked.items(),key=lambda x:x[1],reverse=True):
        d=texts[cid];did=d['document_id']
        requested=re.findall(r'\b20\d{2}\b',question)
        if requested:
            # Explicit named editions in titles take precedence over incidental email dates.
            editions=re.findall(r"(?i)ananta[’'\s-]*(?:20)?(\d{2})\b",d['title'])
            if editions and not any(y[-2:] in editions for y in requested):continue
        if per_doc.get(did,0)>=2:continue
        per_doc[did]=per_doc.get(did,0)+1
        d['score']=round(score,5);result.append(d)
        if len(result)>=limit:break
    return result
