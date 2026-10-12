import os, tempfile, json, io, hashlib
from pathlib import Path
import fitz
from fastapi.testclient import TestClient
from app import app
from store import *
from extraction import extract_report,extract_observations,duplicate_candidates

client=TestClient(app,headers={'X-Health-Client':'1'})

def test_01_auth_and_csrf():
    assert client.get('/api/data').status_code==401
    assert client.get('/api/pages/1/image').status_code==401
    assert client.post('/api/auth/setup',json={'password':'a'}).status_code==400
    assert client.post('/api/auth/setup',json={'password':'test-password-123','patient':'测试'}).status_code==200
    assert client.post('/api/auth/setup',json={'password':'test-password-123'}).status_code==409
    assert client.post('/api/auth/login',json={'password':'incorrect'}).status_code==401
    assert client.post('/api/auth/login',json={'password':'test-password-123'}).status_code==200
    assert client.post('/api/questions',json={'text':'x'},headers={'Origin':'https://evil.example'}).status_code==403

def test_02_import_idempotence():
    d=fitz.open();d.new_page();content=d.tobytes();d.close()
    a=client.post('/api/upload',files={'file':('sample.pdf',content,'application/pdf')}).json()
    b=client.post('/api/upload',files={'file':('sample-again.pdf',content,'application/pdf')}).json()
    assert a['new'] and not b['new'] and a['id']==b['id']
    assert len(client.get('/api/data').json()['pages'])==1
    assert client.post('/api/upload',files={'file':('bad.pdf',b'not pdf')}).status_code==400
    assert client.get('/api/pages/1/image').status_code==200

def body(**extra):
    return dict(date='2026-09-01',patient='测试',category='检验',priority='复查关注',reason='测试',status='confirmed',summary='',issues=[],observations=[dict(name='WBC',code='WBC',value='4.49',unit='10^9/L',reference='3.5-9.5',method='流式法',box=[1,2,3,4])],**extra)

def test_03_review_history_and_retry_preserve():
    with connect() as c:c.execute("INSERT INTO reports(page_id,status,updated) VALUES(1,'pending',?)",(now(),))
    invalid=body();invalid['date']='2026-99-99'
    assert client.put('/api/reports/1',json=invalid).status_code==400
    invalid=body();invalid['patient']='其他人'
    assert client.put('/api/reports/1',json=invalid).status_code==400
    assert client.put('/api/reports/1',json=body()).status_code==200
    assert len(client.get('/api/reports/1/history').json())==1
    client.post('/api/pages/1/retry',json={})
    from reprocess import reprocess
    reprocess()
    r=client.get('/api/data').json()['reports'][0]
    assert r['observations'][0]['value']=='4.49' and r['status']=='confirmed'
    assert client.put('/api/reports/1',json=body(duplicate_of=1)).status_code==400

def test_04_backup_restore_and_wrong_password():
    backup=client.post('/api/backup',json={'password':'backup-password-123'})
    assert backup.status_code==200 and backup.content.startswith(b'HEALTH1')
    assert b'4.49' not in backup.content
    bad=client.post('/api/restore',files={'file':('copy.health',backup.content)},data={'password':'wrong'})
    assert bad.status_code==400
    ok=client.post('/api/restore',files={'file':('copy.health',backup.content)},data={'password':'backup-password-123'})
    assert ok.status_code==200
    with __import__('sqlite3').connect(DATA/'restore-ready'/'records.db',factory=ClosingConnection) as c:
        assert c.execute('select value from observations').fetchone()[0]=='4.49'
    assert client.get('/api/export/csv').status_code==200

def test_05_extract_dates_and_identity():
    b=[dict(text=s,confidence=.99,box=[0,i*20,100,i*20+15]) for i,s in enumerate(['检验报告单','姓名：测试','出生日期：1975-04-17','采样时间：2026-09-01','报告时间：2026-09-02'])]
    f=extract_report(b,'另一人')
    assert f['date']=='2026-09-01' and any('不一致' in x for x in f['issues'])
    b=[dict(text='记录 2025-05-01 与 2025-05-02',confidence=.5,box=[0,0,10,10])]
    assert extract_report(b)['date']==''

def test_06_geometric_lab_and_uncertain_value():
    def b(t,x,y):return dict(text=t,confidence=.99,box=[x,y,x+50,y+20])
    blocks=[b('项目名称',0,0),b('结果',200,0),b('参考区间',300,0),b('单位',400,0),b('白细胞',0,40),b('4.49',200,40),b('3.5-9.5',300,40),b('10^9/L',400,40)]
    obs=extract_observations(blocks)
    assert len(obs)==1 and obs[0]['value']=='4.49' and obs[0]['reference']=='3.5-9.5'
    blocks[5]['text']='4?49';assert extract_observations(blocks)==[]

def test_07_duplicate_and_logout():
    rows=[dict(id=1,raw='检验报告 白细胞4.49 '*30,date='2026-09-01',category='检验'),dict(id=2,raw='检验报告 白细胞4.49 '*30,date='2026-09-01',category='检验')]
    assert duplicate_candidates(rows)[0][:2]==(2,1)
    assert client.post('/api/auth/logout',json={}).status_code==200
    assert client.get('/api/export/csv').status_code==401

def test_08_page_classification_history_restore_and_backup():
    assert client.put('/api/reports/1/classification',json={'relevance':'unrelated'}).status_code==401
    assert client.post('/api/auth/login',json={'password':'test-password-123'}).status_code==200
    current=client.get('/api/data').json()['reports'][0]
    original=(DATA/'originals'/f"{current['document_id']}.pdf").read_bytes()
    obs=current['observations']
    change={'updated':current['updated'],'relevance':'unrelated','relevance_reason':'缴费发票'}
    assert client.put('/api/reports/1/classification',json={**change,'relevance':'invalid'}).status_code==400
    assert client.put('/api/reports/1/classification',json={**change,'updated':'stale'}).status_code==409
    assert client.put('/api/reports/1/classification',json=change,headers={'Origin':'https://evil.example'}).status_code==403
    assert client.put('/api/reports/1/classification',json=change).status_code==200
    data=client.get('/api/data').json();excluded=data['reports'][0]
    assert excluded['relevance']=='unrelated' and excluded['relevance_reason']=='缴费发票'
    assert excluded['observations']==obs and excluded['status']==current['status']
    assert data['analysis']['confirmed_count']==0 and data['analysis']['pending_count']==0
    assert not client.get('/api/ai/context').json()['context']['records']
    assert '4.49' not in client.get('/api/export/csv').text
    assert (DATA/'originals'/f"{current['document_id']}.pdf").read_bytes()==original
    history=client.get('/api/reports/1/history').json()
    assert json.loads(history[0]['before_json'])['relevance']=='clinical'
    assert json.loads(history[0]['after_json'])['relevance']=='unrelated'
    backup=client.post('/api/backup',json={'password':'backup-password-123'})
    # The earlier restore test intentionally leaves a prepared restore in place.
    (DATA/'restore-ready').rename(DATA/'restore-first-test')
    assert client.post('/api/restore',files={'file':('copy.health',backup.content)},data={'password':'backup-password-123'}).status_code==200
    with __import__('sqlite3').connect(DATA/'restore-ready'/'records.db',factory=ClosingConnection) as c:
        assert c.execute('select relevance,relevance_reason from reports where id=1').fetchone()==('unrelated','缴费发票')
    # Reprocessing never undoes the user's exclusion.
    from reprocess import reprocess
    reprocess()
    excluded=next(r for r in reports() if r['id']==1)
    assert excluded['relevance']=='unrelated'
    assert client.put('/api/reports/1/classification',json={'updated':excluded['updated'],'relevance':'clinical','priority':'背景备查','relevance_reason':''}).status_code==200
    restored=next(r for r in reports() if r['id']==1)
    assert restored['status']==current['status'] and restored['observations']==obs and restored['priority']=='背景备查'
    assert client.get('/api/data').json()['analysis']['confirmed_count']==1
    assert '4.49' in client.get('/api/export/csv').text
