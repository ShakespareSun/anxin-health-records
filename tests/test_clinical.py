from clinical_analysis import build_analysis,evidence_context,fingerprint,within_reference

def report(rid,date,value='8.20',status='confirmed',**extra):
    return dict(id=rid,date=date,category='检验',summary='',status=status,duplicate_of=None,updated='x',
                observations=[dict(code='CA125',name='糖类抗原125',value=value,unit='U/mL',reference='≤25',flag='',method='')],**extra)

def test_interpretation_excludes_pending_and_duplicates():
    rs=[report(1,'2024-01-15'),report(2,'2024-07-15','10.10'),report(3,'2024-07-16','900','pending'),report(4,'2024-07-17','1000')]
    rs[-1]['duplicate_of']=2
    a=build_analysis(rs);m=next(c for c in a['cards'] if c['key']=='markers')
    assert a['confirmed_count']==2 and a['pending_count']==1 and m['sources']==[1,2]
    assert '均在各自报告参考范围内' in m['meaning'] and '不能单独解释为肿瘤增长' in m['meaning']
    assert '900' not in str(a['cards']) and '1000' not in str(a['cards'])

def test_new_out_of_range_value_changes_analysis():
    rs=[report(1,'2024-01-15'),report(2,'2024-07-15','30')]
    m=build_analysis(rs)['cards'][0]
    assert '均在各自' not in m['meaning'] and '已有超界' in m['meaning']
    assert within_reference({'value':'<5','reference':'0-25'}) is None
    assert within_reference({'value':'25','reference':'<25'}) is False

def test_unrelated_pages_excluded_from_analysis_context_and_counts():
    included=report(1,'2024-01-15')
    excluded=report(2,'2024-07-15','900',relevance='unrelated')
    invoice=report(3,'','1000','pending',relevance='unrelated')
    rs=[included,excluded,invoice]
    a=build_analysis(rs)
    assert a['confirmed_count']==1 and a['pending_count']==0
    assert [r['source'] for r in evidence_context(rs)['records']]==['R1']
    assert '900' not in str(a['cards']) and '1000' not in str(a['cards'])
    digest=fingerprint(rs);excluded['relevance']='clinical'
    assert fingerprint(rs)!=digest and build_analysis(rs)['confirmed_count']==2

def test_context_minimizes_identity_and_hash_detects_edits(monkeypatch):
    monkeypatch.setattr('clinical_analysis.setting',lambda _: '母亲姓名')
    r=report(1,'2024-01-15');r['summary']='母亲姓名 病理编号1234567890';r['filename']='身份文件.pdf';r['raw']='不发送'
    ctx=evidence_context([r]);s=str(ctx)
    assert '母亲姓名' not in s and '1234567890' not in s and '身份文件' not in s and '不发送' not in s
    original=fingerprint([r]);r['observations'][0]['value']='10.10'
    assert fingerprint([r])!=original
