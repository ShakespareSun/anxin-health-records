import React from 'react';
import {numeric,trendSegments} from './comparison.js';

export default function TrendChart({rows,name}){
 const values=rows.filter(numeric).map(r=>Number(r.value));
 if(!values.length)return <p className="muted">暂无可绘制的明确数值；模糊值和带大小于号的结果保留在下方表格。</p>;
 let lo=Math.min(...values),hi=Math.max(...values);
 const padding=(hi-lo)*.15||Math.max(Math.abs(hi)*.1,1);
 lo-=padding;hi+=padding;
 const width=Math.max(800,rows.length*125),x=i=>80+i*(width-150)/Math.max(1,rows.length-1),y=v=>190-(Number(v)-lo)/(hi-lo)*150;
 const segments=trendSegments(rows),uncertain=segments.some(s=>s.style==='dashed');
 return <>
  <div className="trend-legend"><span><i/>实线：检测方法明确且相同</span><span><i className="dashed"/>虚线：检测方法待确认或不同</span></div>
  <p className="muted chart-help">折线按检查先后连接，横轴按检查次序等距排列；手机可左右滑动查看。</p>
  <div className="chart"><svg viewBox={`0 0 ${width} 265`} role="img" aria-label={name+'折线趋势图'}>
   <title>{name}历次结果折线图</title>
   <desc>实线表示检测方法明确且相同，虚线只展示时间顺序，不代表结果可以直接作医学比较。缺失或不明确的数值处不连线。</desc>
   {[0,1,2,3].map(i=><g key={i}><line x1="60" y1={40+i*50} x2={width-35} y2={40+i*50} stroke="#e5ebe7"/><text x="5" y={45+i*50}>{(hi-i*(hi-lo)/3).toFixed(2)}</text></g>)}
   {segments.map(s=><line className="trend-segment" key={s.from} x1={x(s.from)} y1={y(rows[s.from].value)} x2={x(s.to)} y2={y(rows[s.to].value)} stroke="#287660" strokeWidth="3" strokeDasharray={s.style==='dashed'?'8 5':undefined}/>)}
   {rows.map((r,i)=><g key={i}>{numeric(r)?<><circle cx={x(i)} cy={y(r.value)} r="5" fill="#287660"/><text x={x(i)} y={y(r.value)-13} textAnchor="middle" className="trend-value">{r.value}</text></>:<text x={x(i)} y="120" textAnchor="middle">数值待确认</text>}<text x={x(i)} y="225" textAnchor="middle">{r.date||'日期待确认'}</text></g>)}
  </svg></div>
  {values.length===1&&<p className="muted">目前只有一次明确数值，增加复查记录后即可形成折线。</p>}
  {uncertain&&<p className="trend-caution">虚线仅帮助观察数值随时间的变化；检测方法存在差异或尚未确认，不能仅凭连线判断病情变化。</p>}
 </>;
}
