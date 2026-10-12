import sqlite3
import store

def test_old_database_receives_reversible_classification_columns(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    with sqlite3.connect(tmp_path/'records.db') as c:
        c.execute("CREATE TABLE reports(id INTEGER PRIMARY KEY,status TEXT,summary TEXT)")
        c.execute("INSERT INTO reports VALUES(1,'confirmed','original summary')")
    store.init();store.init()
    with store.connect() as c:
        r=dict(c.execute('SELECT * FROM reports WHERE id=1').fetchone())
    assert r['summary']=='original summary' and r['status']=='confirmed'
    assert r['relevance']=='clinical' and r['relevance_reason']==''
