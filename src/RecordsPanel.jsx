import React from 'react';
import {filterRecords,isClinical} from './recordScope.js';

export default function RecordsPanel({reports,filter,setFilter,query,setQuery,render}){
 const unrelated=reports.filter(r=>!isClinical(r)).length,visible=filterRecords(reports,filter,query);
 return <>
  <section className="records-guide"><h2>先留下与病情有关的资料</h2><p>发票、缴费凭证等可移为“无关页”，从默认列表和待核对计数中隐藏；仍需备查的医疗资料可移为“背景备查”。原件保留，分类可以恢复。</p><button onClick={()=>{setFilter(filter==='unrelated'?'':'unrelated');setQuery('')}}>{filter==='unrelated'?'返回病历资料':`查看无关页（${unrelated}）`}</button></section>
  <div className="toolbar"><div className="search"><input aria-label="搜索资料" placeholder="搜索文件、结论、类别或姓名" value={query} onChange={e=>setQuery(e.target.value)}/></div><select aria-label="资料分类筛选" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">病历资料（隐藏无关页）</option><option value="pending">待核对</option><option value="confirmed">已核对</option><option value="conflict">存在冲突</option><option value="核心资料">核心资料</option><option value="复查关注">复查关注</option><option value="背景备查">背景备查</option><option value="unrelated">无关页</option><option value="all">全部页面（含无关页）</option></select></div>
  <p className="muted">当前显示 {visible.length} 页 · 无关页 {unrelated} 页。背景备查仍属于病历资料，不会自动确认核对状态。</p>
  <div className="record-grid">{visible.map(render)}</div>
  {!visible.length&&<section><p className="muted">{reports.length?'当前筛选下没有资料，请调整筛选或搜索。':'正在识别扫描页，可在上传与备份查看进度。'}</p></section>}
 </>;
}
