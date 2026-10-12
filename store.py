import os, sqlite3, json, hashlib, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('HEALTH_DATA', ROOT / 'data'))

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()

def connect():
    c = sqlite3.connect(DATA / 'records.db', timeout=30, factory=ClosingConnection)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init():
    for folder in ['originals', 'pages']: (DATA / folder).mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT,pages INTEGER,created TEXT);
        CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY,document_id TEXT REFERENCES documents(id),number INTEGER,status TEXT DEFAULT 'queued',error TEXT,raw TEXT DEFAULT '',blocks TEXT DEFAULT '[]',image_hash TEXT, UNIQUE(document_id,number));
        CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY,page_id INTEGER UNIQUE REFERENCES pages(id),date TEXT DEFAULT '',patient TEXT DEFAULT '',category TEXT DEFAULT '其他',priority TEXT DEFAULT '背景备查',reason TEXT DEFAULT '',status TEXT DEFAULT 'pending',summary TEXT DEFAULT '',issues TEXT DEFAULT '[]',duplicate_of INTEGER REFERENCES reports(id),updated TEXT);
        CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,report_id INTEGER REFERENCES reports(id),name TEXT,code TEXT DEFAULT '',value TEXT,unit TEXT DEFAULT '',reference TEXT DEFAULT '',method TEXT DEFAULT '',flag TEXT DEFAULT '',box TEXT DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY,report_id INTEGER,at TEXT,before_json TEXT,after_json TEXT);
        CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY,text TEXT,done INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY,title TEXT,detail TEXT,source_ids TEXT DEFAULT '[]',resolved INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS ai_messages(id INTEGER PRIMARY KEY,role TEXT,content TEXT,at TEXT,model TEXT DEFAULT '',fingerprint TEXT DEFAULT '',sources TEXT DEFAULT '[]',usage TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS ai_analyses(id INTEGER PRIMARY KEY,content TEXT,at TEXT,model TEXT,fingerprint TEXT,sources TEXT DEFAULT '[]',usage TEXT DEFAULT '{}');
        ''')
        columns={r['name'] for r in c.execute('PRAGMA table_info(reports)')}
        for name,definition in [('relevance',"TEXT NOT NULL DEFAULT 'clinical'"),('relevance_reason',"TEXT NOT NULL DEFAULT ''")]:
            if name not in columns:c.execute(f'ALTER TABLE reports ADD COLUMN {name} {definition}')

def is_clinical(r):return r.get('relevance','clinical')!='unrelated'

def setting(key, default=''):
    with connect() as c:
        r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return r[0] if r else default

def set_setting(key,value):
    with connect() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,value))

def import_pdf(content,name):
    import fitz
    digest=hashlib.sha256(content).hexdigest()
    with connect() as c:
        if c.execute('SELECT 1 FROM documents WHERE id=?',(digest,)).fetchone(): return digest,False
    doc=fitz.open(stream=content,filetype='pdf')
    if doc.needs_pass or not len(doc): raise ValueError('PDF 已加密或没有页面，请先解锁。')
    n=len(doc); doc.close()
    (DATA/'originals'/f'{digest}.pdf').write_bytes(content)
    with connect() as c:
        c.execute('INSERT INTO documents VALUES(?,?,?,?)',(digest,Path(name).name,n,now()))
        c.executemany('INSERT INTO pages(document_id,number) VALUES(?,?)',[(digest,i+1) for i in range(n)])
    return digest,True

def reports():
    with connect() as c:
        rows=[dict(r) for r in c.execute('SELECT r.*,p.document_id,p.number,p.status page_status,d.name filename FROM reports r JOIN pages p ON p.id=r.page_id JOIN documents d ON d.id=p.document_id ORDER BY r.date DESC,r.id')]
        for r in rows:
            r['issues']=json.loads(r['issues']); r['observations']=[dict(o) for o in c.execute('SELECT * FROM observations WHERE report_id=?',(r['id'],))]
        return rows

def report_snapshot(c,rid):
    r=dict(c.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone())
    r['observations']=[dict(o) for o in c.execute('SELECT * FROM observations WHERE report_id=?',(rid,))]
    return r
