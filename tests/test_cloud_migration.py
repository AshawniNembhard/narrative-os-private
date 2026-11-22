import sqlite3
from pathlib import Path
import cloud_migration as cm
from fastapi.testclient import TestClient

def test_copy_earlier_research(tmp_path):
    old=tmp_path/'before.db'; new=tmp_path/'after.db'
    for path in (old,new):
        with sqlite3.connect(path) as con:
            con.execute('CREATE TABLE events(id TEXT PRIMARY KEY,mode TEXT,occurred TEXT,created TEXT,payload TEXT)')
            con.execute('CREATE TABLE chart_imports (id INTEGER PRIMARY KEY AUTOINCREMENT,symbol TEXT,interval TEXT,uploaded TEXT,last_candle TEXT,payload TEXT)')
            con.execute('CREATE TABLE council_plans (id TEXT PRIMARY KEY,created TEXT,payload TEXT)')
            con.execute('CREATE TABLE council_runs (id TEXT PRIMARY KEY,plan_id TEXT,created TEXT,payload TEXT)')
            con.execute('CREATE TABLE council_bias_states (focus TEXT,horizon TEXT,updated TEXT,payload TEXT, PRIMARY KEY(focus,horizon))')
            con.execute('CREATE TABLE runtime_settings(key TEXT PRIMARY KEY,value TEXT)')
    with sqlite3.connect(old) as con:
        con.execute('INSERT INTO events VALUES (?,?,?,?,?)',('e-1','manual','2026-11-01T00:00:00Z','2026-11-01T00:00:00Z','{"id":"e-1","time":"2026-11-01T00:00:00Z","title":"Test"}'))
        con.execute('INSERT INTO council_bias_states VALUES (?,?,?,?)',('XAUUSD','daily','2026-11-01T00:00:00Z','{"direction":"Bullish"}'))
        con.execute('INSERT INTO runtime_settings VALUES (?,?)',('automatic_ai','1'))
    with sqlite3.connect(new) as con:
        imported=cm.copy_rows(old,con)
        assert imported['events']==1 and imported['council_bias_states']==1
        assert con.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
        assert con.execute('SELECT value FROM runtime_settings').fetchone() is None
        assert cm.copy_rows(old,con)['events']==0

def test_backup_data(tmp_path):
    p=tmp_path/'test.db'
    def make_conn():return sqlite3.connect(p)
    with make_conn() as con:con.execute('CREATE TABLE x(y TEXT)')
    import threading
    response=cm.backup_db(make_conn,threading.RLock())
    assert response.body[:16]==b'SQLite format 3\x00'

def test_authenticated_legacy_upload(tmp_path, monkeypatch):
    import cloud_security as cs
    import app as a
    monkeypatch.setenv('CLOUD_MODE','1')
    monkeypatch.setenv('APP_PASSWORD','A-Secure-Test-Password-123!')
    monkeypatch.setenv('APP_SESSION_SECRET','S'*60)
    original=a.DB_PATH
    monkeypatch.setattr(a,'DB_PATH',tmp_path/'target.db')
    a.initialize()
    legacy=tmp_path/'legacy.db'
    with sqlite3.connect(legacy) as c:
        c.execute('CREATE TABLE events(id TEXT PRIMARY KEY,mode TEXT,occurred TEXT,created TEXT,payload TEXT)')
        c.execute('INSERT INTO events VALUES (?,?,?,?,?)',('migration-test-1','manual','2026-11-01T00:00:00Z','2026-11-01T00:00:00Z','{"id":"migration-test-1","time":"2026-11-01T00:00:00Z","title":"Moved research"}'))
    with TestClient(a.app,base_url='https://testserver') as client:
        assert client.post('/api/admin/import-db',content=legacy.read_bytes(),headers={'Origin':'https://testserver'}).status_code==401
        client.post('/login',data={'password':'A-Secure-Test-Password-123!'},headers={'Origin':'https://testserver'})
        result=client.post('/api/admin/import-db',content=legacy.read_bytes(),headers={'Origin':'https://testserver'})
        assert result.status_code==200, result.text
        assert result.json()['imported']['events']==1
        saved=client.get('/api/bootstrap?mode=manual')
        assert any(r['id']=='migration-test-1' for r in saved.json()['events'])
        b=client.get('/api/admin/backup-db')
        assert b.status_code==200 and b.content[:16]==b'SQLite format 3\x00'
    monkeypatch.setattr(a,'DB_PATH',original)