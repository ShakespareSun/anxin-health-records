"""Conservative geometry-based extraction. Every generated record stays pending."""
import re, json, datetime
from difflib import SequenceMatcher

DATE = r'(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})'
def dates_in(text):
    dates=[]
    for a,b,c in re.findall(DATE,text):
        try: dates.append(datetime.date(int(a),int(b),int(c)).isoformat())
        except ValueError:pass
    return sorted(set(dates))

def extract_report(blocks,expected=''):
    text='\n'.join(b['text'] for b in blocks); top='\n'.join(b['text'] for b in blocks[:18])
    rules=[('出院记录|出院小结','出院小结','核心资料'),('病理.{0,5}报告|病理检查|病理诊断报告','病理','核心资料'),('手术记录|手术经过|手术及操作名称','治疗记录','核心资料'),('住院病案首页','住院首页','核心资料'),('入院记录','入院记录','背景备查'),('超声.*报告|CT.*报告|放射科|磁共振','影像检查','复查关注'),('检验报告|检验.*报告|参考区间|参考范围','检验','复查关注'),('医[嘱瞩啊]单','医嘱记录','背景备查'),('诊断证明','诊断证明','核心资料'),('门[（(]急[）)]诊病历','门急诊记录','复查关注'),('体温单|体温|护理','护理记录','背景备查')]
    category,priority='其他','背景备查'
    for pattern,cat,pri in rules:
        if re.search(pattern,top) or (cat=='检验' and re.search('参考区间|参考范围',text)):
            category,priority=cat,pri;break
    if category=='其他' and '出院诊断' in text and '出院情况' in text:category,priority='出院小结（续页）','核心资料'
    if re.search('收费票据|收费据|金额合计',top+'\n'+text[:800]):category,priority='收费票据','背景备查'
    patient='';m=re.search(r'姓\s*名\s*[：:]?\s*([\u4e00-\u9fff]{2,4})(?=\s|$)',text)
    if m:patient=m[1]
    dates=dates_in(text);chosen='';source=''
    markers=['采样时间','采集时间','采样日期','检查日期','检查时间','报告日期','报告时间','签字时间','记录时间']
    if category.startswith('出院'):markers=['出院日期','签字时间']+markers
    if category=='住院首页':markers=['出院日期','入院日期']+markers
    for marker in markers:
        match=re.search(marker+r'[：:\s]*('+DATE+')',text)
        if match:
            found=dates_in(match[1])
            if found:chosen=found[0];source=marker;break
    if not chosen and len(dates)==1:chosen=dates[0];source='页面唯一日期'
    issues=[]
    if not chosen:issues.append('日期不明确：'+(' / '.join(dates) if dates else '未识别到有效日期'))
    elif len(dates)>1:issues.append('页面含多个日期，当前按'+source+'归档，请核实')
    if not patient:issues.append('本页姓名未可靠识别，可能是续页，请核对前后页')
    if patient and expected and patient!=expected:issues.append('姓名与资料主人不一致，请核实')
    if any(b['confidence']<.85 for b in blocks):issues.append('存在低置信度文字，请检查关键字段')
    summary=''
    markers=['超声印象','超声提示','检查结论','诊断意见','病理诊断','出院诊断']
    if category.startswith('出院'):markers=['诊疗经过','出院诊断']
    for marker in markers:
        if marker in text:
            summary=text[text.index(marker):]
            for stop in ['操作者','报告医生','医师签名','此意见非','cs.','扫描全能王']:
                summary=summary.split(stop)[0]
            summary=summary.strip()[:2400];break
    return dict(date=chosen,patient=patient,category=category,priority=priority,reason=f'原文类别：{category}；'+(f'日期依据：{source}' if source else '日期待核实'),summary=summary,issues=issues)

def extract_observations(blocks):
    # Report layouts may contain two parallel tables. Result headers define each table.
    result_headers=[b for b in blocks if b['text'].strip() in ['结果','检验结果','测定结果']]
    observations=[]
    for h in result_headers:
        hx=(h['box'][0]+h['box'][2])/2;hy=(h['box'][1]+h['box'][3])/2;hh=h['box'][3]-h['box'][1]
        headers=[b for b in blocks if abs((b['box'][1]+b['box'][3])/2-hy)<hh*1.4]
        names=[b for b in headers if re.search('项目名称|中文名称|检验项目|项目$',b['text']) and b['box'][0]<hx]
        if not names:continue
        nh=max(names,key=lambda b:b['box'][0]);left=nh['box'][0]-hh*2
        next_names=[b['box'][0]-hh for b in headers if re.search('项目名称|中文名称',b['text']) and b['box'][0]>hx]
        right=min(next_names) if next_names else max(b['box'][2] for b in blocks)+1
        unit_h=next((b for b in headers if b['text']=='单位' and hx<b['box'][0]<right),None)
        ref_h=next((b for b in headers if '参考' in b['text'] and hx<b['box'][0]<right),None)
        method_h=next((b for b in headers if '方法' in b['text'] and hx<b['box'][0]<right),None)
        candidates=[b for b in blocks if b['box'][1]>hy+hh*.5 and abs(b['box'][0]-h['box'][0])<hh*1.8 and re.fullmatch(r'[<>≤≥+\-]?\d+(?:\.\d+)?(?:[↑↓])?',b['text'].strip())]
        for value in candidates:
            vy=(value['box'][1]+value['box'][3])/2
            row=sorted([b for b in blocks if abs((b['box'][1]+b['box'][3])/2-vy)<hh*.6 and left<=b['box'][0]<right],key=lambda b:b['box'][0])
            before=[b for b in row if b['box'][2]<value['box'][0]+hh*.2 and re.search('[\u4e00-\u9fff]',b['text'])]
            if not before:continue
            name=' '.join(b['text'] for b in before)
            name=re.sub(r'^\s*\d+[.、]?\s*','',name);name=re.sub(r'^[▲★*\s]+','',name)
            if any(w in name for w in ['控制目','患者','地址','电话','报告','采样','时间','备注']):continue
            code=next((b['text'] for b in row if b['box'][0]>before[-1]['box'][2] and b['box'][2]<value['box'][0] and re.fullmatch('[A-Za-z0-9%#-]+',b['text'])),'')
            tail=[b for b in row if b['box'][0]>value['box'][0]+hh]
            def aligned(header):
                if not header:return ''
                center=(header['box'][0]+header['box'][2])/2
                choices=[b for b in tail if abs(b['box'][0]-header['box'][0])<hh*1.4 or b['box'][0]-hh*.3<=center<=b['box'][2]+hh*.3]
                return ' '.join(b['text'] for b in choices)
            ref=aligned(ref_h);unit=aligned(unit_h);method=aligned(method_h)
            flag='↑' if any('↑' in b['text'] for b in row) else ('↓' if any('↓' in b['text'] for b in row) else '')
            # Split joined reference + unit without absorbing powers of ten into the upper bound.
            if ref:
                ref=re.sub('[↑↓]','',ref).strip()
                ref=re.sub(r'^\d\s+(?=\d+[.-])','',ref)
                split=re.search(r'(10\^[0-9]+/[Ll]|[μuUnpfmgI]+(?:mol|g|IU|U)?/[mLdli]+|%|fL|pg)$',ref)
                if split and (not unit or unit==ref):unit=split[0];ref=ref[:split.start()].strip()
            if not unit:
                unit_candidates=[b['text'] for b in tail if re.fullmatch(r'(?:10\^\d+/L|[μuUnpfmgI]+(?:mol|g|IU|U)?/[mLdli]+|%|fL|pg)',b['text'])]
                if len(unit_candidates)==1:unit=unit_candidates[0]
            if unit_h and method_h and unit and '法' in unit:unit='';method=''
            box=[min(b['box'][0] for b in row),min(b['box'][1] for b in row),max(b['box'][2] for b in row),max(b['box'][3] for b in row)]
            observations.append(dict(name=name,code=code,value=value['text'],unit=unit,reference=ref,method=method,flag=flag,box=box))
    return observations

def normalized_text(text):
    return re.sub(r'\W+','',text.replace('扫描全能王创建',''))

def duplicate_candidates(rows):
    pairs=[]
    for i,a in enumerate(rows):
        for b in rows[:i]:
            if a['category']!=b['category']:continue
            ta,tb=normalized_text(a['raw']),normalized_text(b['raw'])
            if min(len(ta),len(tb))<80:continue
            same_date=a['date'] and a['date']==b['date']
            if not same_date and abs(len(ta)-len(tb))>max(len(ta),len(tb))*.1:continue
            ratio=SequenceMatcher(None,ta,tb,autojunk=False).ratio()
            if ratio>.94 or same_date and ratio>.86:pairs.append((a['id'],b['id'],round(ratio,3)))
    return pairs
