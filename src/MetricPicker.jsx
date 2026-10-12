import React,{useState} from 'react';
import {metricCategories,sortedMetrics,metricInfo} from './metrics.js';

export function preferredMetric(groups){return sortedMetrics(groups)[0]?.key}
export function MetricPicker({groups,current,choose}){
 const [category,C]=useState('肿瘤随访'),[search,S]=useState('');
 const metrics=sortedMetrics(groups),selected=metricInfo(current,groups[current]||[]);
 const available=metricCategories.filter(c=>metrics.some(m=>c==='本次异常'?m.abnormal:m.category===c));
 const active=available.includes(category)?category:available[0];
 const visible=metrics.filter(m=>(search?`${m.name} ${m.code} ${m.description}`.toLowerCase().includes(search.toLowerCase()):active==='本次异常'?m.abnormal:m.category===active));
 return <div className="metric-picker"><div className="metric-intro"><b>先选关注方向，再选指标</b><small>“高”表示随访阅读优先级，指标是否适合本人需由医生确认。</small></div><div className="metric-tabs" role="group" aria-label="指标分类">{available.map(c=><button key={c} className={active===c&&!search?'active':''} onClick={()=>{C(c);S('')}}>{c}<span>{metrics.filter(m=>c==='本次异常'?m.abnormal:m.category===c).length}</span></button>)}</div><label>搜索中文名称或缩写<input value={search} onChange={e=>S(e.target.value)} placeholder="例如：肿瘤、糖类抗原、CA125、中性粒细胞"/></label><div className="metric-options">{visible.map(m=><button key={m.key} aria-pressed={m.key===current} className={m.key===current?'selected':''} onClick={()=>choose(m.key)}><span className="metric-priority">{m.priority}</span><b>{m.name}</b><small>{m.code} · {m.key.split(' | ')[1]}{m.abnormal?' · 最近报告有异常标记':''}</small></button>)}</div>{!visible.length&&<p>没有符合条件的已核对指标。</p>}<div className="metric-explanation"><h3>{selected.name} <span>{selected.code}</span></h3><p>{selected.description}</p><small>每次结果的单位、参考区间、检测方法和来源见下方表格。原始结果不按优先级改写。</small></div></div>
}
