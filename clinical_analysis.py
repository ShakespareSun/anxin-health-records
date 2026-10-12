"""Local, source-linked interpretations. No network calls or inferred diagnoses."""
import hashlib, json, re
from store import reports, setting, now, is_clinical

REFERENCES = [
    {'id':'esgo','title':'ESGO / ESMO / ESP 卵巢癌共识（2024，2025 口袋版）','url':'https://www.esgo.org/media/2025/08/Pocket-Guidelines_Ovarian-cancer-consensus.pdf'},
    {'id':'nci','title':'美国国家癌症研究所：常用肿瘤标志物','url':'https://www.cancer.gov/about-cancer/diagnosis-staging/diagnosis/tumor-markers-list'},
    {'id':'thyroid','title':'美国甲状腺协会：甲状腺功能检查','url':'https://www.thyroid.org/thyroid-function-tests/'},
    {'id':'liver','title':'美国肝病研究学会：肝胆检验异常的评估','url':'https://www.aasld.org/liver-fellow-network/core-series/back-basics/how-approach-elevated-liver-enzymes'},
]

def redacted(text):
    name=setting('patient_name')
    if name:text=text.replace(name,'患者')
    # Do not send scan IDs, phone numbers or national IDs from reviewed summaries.
    return re.sub(r'(?<!\d)\d{7,18}[Xx]?(?!\d)','[编号已省略]',str(text))

def evidence_context(rs=None):
    rs=reports() if rs is None else rs
    approved=sorted([r for r in rs if is_clinical(r) and r['status']=='confirmed' and not r.get('duplicate_of')],key=lambda r:(r['date'],r['id']))
    entries=[]
    for r in approved:
        entries.append({'source':'R'+str(r['id']),'date':r['date'],'category':redacted(r['category']),
                        'summary':redacted(r['summary']),
                        'observations':[{k:redacted(str(o.get(k,''))) for k in ['name','code','value','unit','reference','method','flag']} for o in r['observations']]})
    return {'scope':'仅已核对且未关联为重复的资料；没有原始 PDF、OCR 全文、姓名、文件名或住院号字段。用户问题和历史对话可能包含用户自行输入的身份信息。',
            'pending_count':sum(is_clinical(r) and r['status']!='confirmed' and not r.get('duplicate_of') for r in rs),
            'records':entries}

def fingerprint(rs):
    # Revision timestamp changes invalidate previously generated AI reports too.
    payload=[{k:r.get(k) for k in ['id','date','status','duplicate_of','relevance','summary','observations','updated']} for r in sorted(rs,key=lambda r:r['id'])]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def within_reference(o):
    try:value=float(o['value'])
    except (ValueError,TypeError):return None
    ref=o.get('reference','').strip().replace('–','-').replace('—','-')
    m=re.fullmatch(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)',ref)
    if m:return float(m[1])<=value<=float(m[2])
    m=re.fullmatch(r'([<≤]|<=)\s*(\d+(?:\.\d+)?)',ref)
    if m:return value<float(m[2]) if m[1]=='<' else value<=float(m[2])
    return None

def build_analysis(rs=None):
    rs=reports() if rs is None else rs
    approved=sorted([r for r in rs if is_clinical(r) and r['status']=='confirmed' and not r.get('duplicate_of')],key=lambda r:(r['date'],r['id']))
    series={}
    for r in approved:
        for o in r['observations']:
            code=o.get('code','') or o['name']
            series.setdefault(code,[]).append({**o,'date':r['date'],'report_id':r['id']})
    def vals(code):return series.get(code,[])
    def latest(code):return vals(code)[-1] if vals(code) else None
    def fact(o):return f"{o['date']}：{o['name']} {o['value']} {o['unit']}（参考 {o['reference'] or '未记录'}{('；原报告 '+o['flag']) if o.get('flag') else ''}）"
    cards=[]
    def card(key,title,level,facts,meaning,next_step,source_ids,refs=()):
        cards.append(dict(key=key,title=title,level=level,facts=facts,meaning=meaning,next_step=next_step,
                          sources=sorted(set(source_ids)),references=list(refs)))
    pathology=[r for r in approved if '病理' in r['category']]
    discharge=[r for r in approved if '出院' in r['category']]
    diagnosis=pathology+discharge
    if diagnosis:
        descriptions=' '.join(r['summary'] for r in diagnosis)
        differing=all(word in descriptions for word in ['上皮内癌','腺癌','IC'])
        card('diagnosis','优先核实最终病理诊断与分期','优先确认',
             [f"{r['date']} {r['category']}：{r['summary']}" for r in diagnosis],
             '现有病理与出院诊断的用词存在差异。“交界性肿瘤伴上皮内癌”和“浸润性癌”的含义、随访依据可能不同；IC 分期还需相应手术与病理证据。仅凭这些摘录不能替主治医生确定最终病理类型和分期。' if differing else '诊断依据应优先采用完整病理、手术记录及医生最终结论；出院摘要不能替代完整病理复核。',
             '带齐完整病理、病理补充报告和两次出院记录，请妇科肿瘤医生明确：最终病理类型、是否有间质浸润、FIGO 分期及其依据，以及适合本人的复查项目。',
             [r['id'] for r in diagnosis],['esgo'])
    markers=[o for code in ['CA125','HE4','CEA','CA199'] for o in vals(code)]
    if markers:
        ca=vals('CA125'); last_markers=[latest(code) for code in ['HE4','CEA','CA199'] if latest(code)]
        ca_interpretation='已核对的 CA‑125 各次结果均在各自报告参考范围内；这提供了本次标志物未超出报告界限的证据。' if ca and all(within_reference(o) is True for o in ca) else '当前 CA‑125 应逐次对照各自参考区间；已有超界或范围无法确认的结果，需先核实再解读。'
        if len(ca)>1 and all(re.fullmatch(r'\d+(\.\d+)?',o['value']) for o in ca[-2:]) and float(ca[-1]['value'])>float(ca[-2]['value']):
            ca_interpretation+=f"最近记录由 {ca[-2]['value']} 到 {ca[-1]['value']}；由于方法/医院可比性未完整确认，这个变化不能单独解释为肿瘤增长。"
        card('markers','肿瘤随访：先看连续结果，再结合影像与症状','肿瘤随访',
             [fact(o) for o in ca]+[fact(o) for o in last_markers],
             ca_interpretation+'CA‑125 是卵巢肿瘤随访的重要辅助指标。现有资料缺少完整术前基线，无法确定它对本人的敏感程度，正常也不能排除复发。CEA、CA19‑9 可与主治医生讨论在黏液性肿瘤中的个人随访价值；HE4 对不同病理类型的适用性不同，均不能单独确诊。',
             '确认术前哪些标志物曾升高、固定哪家医院和方法复查；结合持续腹胀、腹痛、早饱、体重变化及医生安排的影像综合判断。不要据正常范围内的一次上升自行认定复发或加做治疗。',
             [o['report_id'] for o in markers],['esgo','nci'])
    pelvic=[r for r in approved if '影像' in r['category'] and ('附件区' in r['summary'] or '盆腔' in r['summary'])]
    if pelvic:
        r=pelvic[-1]
        card('pelvic','盆腔影像：报告所见与检查覆盖范围','肿瘤随访',[r['summary']],
             '该超声原文没有描述附件区包块或液性暗区，这是本次检查范围内的记录。盆腔超声覆盖范围有限，不能代表全身、腹膜或微小病灶均已排除，也不能代替医生的复发评估。',
             '向主治医生确认本人的随访影像范围是否足够，以及是否需要结合其他部位影像；由症状、病理和连续资料决定。',[r['id']],['esgo'])
    neut=vals('NEUT#')
    if neut:
        recent=neut[-3:]; last=recent[-1]
        unit=lambda o:o.get('unit','').replace(' ','')
        low_then_normal=len(recent)>1 and any(o.get('flag')=='↓' for o in recent[:-1]) and not last.get('flag') and all(unit(o)==unit(last) for o in recent)
        meaning='较早报告标记中性粒细胞绝对值偏低，最新记录未再标记降低。数值回到报告区间提示本次血细胞状态较此前记录改善，但不能据此认定肿瘤改善，也不能在缺乏用药与症状资料时归因于化疗。' if low_then_normal else '中性粒细胞绝对值用于了解感染防御相关的血细胞状态。需结合当次参考范围、感染症状和治疗时间；不属于肿瘤复发的直接指标。'
        card('blood','血常规：优先关注中性粒细胞、血红蛋白、血小板','治疗与身体状态',
             [fact(o) for o in recent]+[fact(latest(code)) for code in ['HGB','PLT'] if latest(code)],meaning,
             '就诊时补充近期用药、化疗时间和感染情况；若发热且正在接受化疗或医生告知存在中性粒细胞减少，应及时联系治疗团队，不等待聊天解读。',[o['report_id'] for o in recent]+[latest(code)['report_id'] for code in ['HGB','PLT'] if latest(code)])
    thyroid=[latest(code) for code in ['TSH','FT3','FT4','TGAb','TPOAb'] if latest(code)]
    if thyroid:
        tsi=latest('TSH'); normal_free=all(latest(c) and not latest(c).get('flag') for c in ['FT3','FT4'])
        same_date=tsi and all(o['date']==tsi['date'] for o in thyroid)
        pattern=tsi and tsi.get('flag')=='↓' and normal_free and same_date
        thyroid_us=[r for r in approved if '影像' in r['category'] and '甲状腺' in r['summary']]
        card('thyroid','甲状腺：独立于肿瘤指标，需要单独随访','其他重点关注',
             [fact(o) for o in thyroid]+([thyroid_us[-1]['summary']] if thyroid_us else []),
             '同次资料显示 TSH 低于参考下限，FT3、FT4 未被报告标记异常，两项甲状腺抗体升高。这属于需要复核的低 TSH / 游离激素未升高的检验模式，可能涉及亚临床甲亢状态、甲状腺炎阶段、药物或检测干扰；单次结果不足以确定病因。抗体升高支持进一步评估自身免疫背景，不能直接确定桥本病或格雷夫斯病。' if pattern else '需将同次 TSH、FT3、FT4 与甲状腺抗体、超声和症状一起解释；不同日期或缺测结果不能拼成同一次完整甲功结论。',
             '可带甲功和超声到内分泌科；说明有无心悸、手抖、体重变化，以及甲状腺药物、保健品或生物素使用，由医生决定复查和进一步检查。',
             [o['report_id'] for o in thyroid]+[r['id'] for r in thyroid_us[-1:]],['thyroid'])
    liver=[o for c in ['TBIL','DBIL','IBIL','ALP'] for o in vals(c)[-2:]]
    if liver:
        support=[latest(c) for c in ['ALT','AST','GGT'] if latest(c)]
        card('liver','肝胆检验：持续异常需查原因，不能直接归为肿瘤','其他重点关注',
             [fact(o) for o in liver]+[fact(o) for o in support],
             '胆红素应区分直接和间接部分，碱性磷酸酶还可能来自肝胆或骨组织。当前应结合各次异常幅度、转氨酶、GGT、用药和影像查原因；资料不足以确定胆道问题、药物影响、Gilbert 综合征或其他病因，不能据此判断肝转移。肝囊肿超声结论也不能自动解释检验异常。',
             '与医生讨论复查肝胆检验、必要时评估胆红素分型和 ALP 来源；补充既往基线、用药、黄疸或深色尿等情况，由医生选择进一步检查。',[o['report_id'] for o in liver+support],['liver'])
    lipid=[o for c in ['TC','LDL-C'] for o in vals(c)[-2:]]
    if lipid:
        card('lipids','血脂：影响长期健康，单独评估','常规健康关注',[fact(o) for o in lipid],
             '血脂属于心血管风险相关项目。应结合空腹状态、血压、糖尿病、吸烟和既往心血管病等判断个人目标，不能用肿瘤随访结论替代血脂管理。',
             '就诊时核实是否空腹及个人风险；由医生讨论复查、饮食运动和是否需要治疗。',[o['report_id'] for o in lipid])
    pending=sum(is_clinical(r) and r['status']!='confirmed' and not r.get('duplicate_of') for r in rs)
    ca=vals('CA125')
    headlines=['最先需要明确的是最终病理类型与分期，这决定个人随访依据。'] if diagnosis else []
    if ca:
        readings=' → '.join(o['value'] for o in ca[-4:])
        range_note='各自在原报告参考范围内' if all(within_reference(o) is True for o in ca) else '需逐次核实参考范围及超界情况'
        headlines.append(f'CA‑125：{readings}，{range_note}；最近一次变化不能单独判断复发。')
    if thyroid or liver:headlines.append('甲状腺与肝胆异常需要单独随访；请优先补充近期症状、用药及医生意见。')
    if not approved:headlines=['尚无已核对资料，暂不能形成病历解读。']
    return dict(title='基于病历的分析报告',version='2026-10-04.1',fingerprint=fingerprint(rs),generated_at=now(),
                data_through=max([r['date'] for r in approved] or ['']),confirmed_count=len(approved),pending_count=pending,
                summary=headlines,cards=cards,references=REFERENCES,
                limitations=[f'还有 {pending} 条记录未核对，本报告不使用其中的草稿结论。',
                             '尚未建立完整术前标志物基线、全部治疗周期、当前症状和用药资料；缺失资料不能视为不存在。',
                             '这是 AI 辅助资料解读和就诊沟通材料；最终诊断、分期、复查安排和用药由接诊医生确认。'])
