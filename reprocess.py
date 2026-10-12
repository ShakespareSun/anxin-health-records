"""Rebuild untouched OCR drafts only; never overwrite reviewed or edited records."""
from store import *
from extraction import *

def reprocess():
    with connect() as c:
        rows=c.execute("SELECT r.id,p.blocks FROM reports r JOIN pages p ON p.id=r.page_id WHERE r.status='pending' AND NOT EXISTS(SELECT 1 FROM revisions v WHERE v.report_id=r.id)").fetchall()
        for row in rows:
            blocks=json.loads(row['blocks']);f=extract_report(blocks,setting('patient_name'))
            c.execute('UPDATE reports SET date=?,patient=?,category=?,priority=?,reason=?,summary=?,issues=?,updated=? WHERE id=?',(*[f[k] for k in ['date','patient','category','priority','reason','summary']],json.dumps(f['issues'],ensure_ascii=False),now(),row['id']))
            c.execute('DELETE FROM observations WHERE report_id=?',(row['id'],))
            if f['category']=='检验':
                for o in extract_observations(blocks):
                    c.execute('INSERT INTO observations(report_id,name,code,value,unit,reference,method,flag,box) VALUES(?,?,?,?,?,?,?,?,?)',(row['id'],*[o[k] for k in ['name','code','value','unit','reference','method','flag']],json.dumps(o['box'])))
        rows=[dict(r) for r in c.execute('SELECT r.*,p.raw FROM reports r JOIN pages p ON p.id=r.page_id')]
        for a,b,score in duplicate_candidates(rows):
            for rid,other in [(a,b),(b,a)]:
                row=c.execute('SELECT issues FROM reports WHERE id=?',(rid,)).fetchone();issues=json.loads(row[0]);message=f'疑似与报告 #{other} 重复（文字相似度 {score:.0%}），请核对后关联'
                if message not in issues:issues.append(message)
                c.execute('UPDATE reports SET issues=? WHERE id=?',(json.dumps(issues,ensure_ascii=False),rid))
    print('Reprocessed',len(rows),'reports')

if __name__=='__main__':reprocess()
