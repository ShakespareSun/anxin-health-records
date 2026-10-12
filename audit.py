import json,re
from store import connect
from extraction import duplicate_candidates

def audit_new_report(rid):
    with connect() as c:
        rows=[dict(r) for r in c.execute('SELECT r.*,p.raw,d.name filename FROM reports r JOIN pages p ON p.id=r.page_id JOIN documents d ON d.id=p.document_id')]
        current=next((r for r in rows if r['id']==rid),None)
        if not current:return
        issues=json.loads(current['issues'])
        prefix=re.match(r'(20\d{2})(\d{2})',current['filename'])
        if prefix and current['date'] and current['date'][:7]!=prefix[1]+'-'+prefix[2]:issues.append('原报告日期与文件名月份不同，已采用报告日期，请核实归档')
        pages=re.search(r'第\s*(\d+)\s*页\s*[/,，]?\s*共\s*(\d+)\s*页',current['raw'])
        if pages and int(pages[2])>1:issues.append(f'原报告标注第{pages[1]}/{pages[2]}页，请核对配套页；PDF页序不等于报告页序')
        for a,b,score in duplicate_candidates([r for r in rows if r['id']!=rid]+[current]):
            if a==rid:issues.append(f'疑似与报告 #{b} 重复（文字相似度 {score:.0%}），请核对后关联')
        c.execute('UPDATE reports SET issues=? WHERE id=?',(json.dumps(list(dict.fromkeys(issues)),ensure_ascii=False),rid))
