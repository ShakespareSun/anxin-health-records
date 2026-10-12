export const aliases={
 '糖类抗原125':'CA125','糖类抗原CA-125':'CA125','CA-125':'CA125','CA125':'CA125',
 '甲胎蛋白':'AFP','癌胚抗原':'CEA','糖类抗原15-3':'CA153','糖类抗原19-9':'CA199','人附睾蛋白4':'HE4',
 '白细胞':'WBC','白细胞计数':'WBC','红细胞':'RBC','红细胞计数':'RBC','血红蛋白':'HGB',
 '血红蛋白测定':'HGB','血小板计数':'PLT','中性粒细胞绝对值':'NEUT#','淋巴细胞绝对值':'LYM#',
 '游离三碘甲状腺原氨酸':'FT3','游离甲状腺素':'FT4','促甲状腺激素':'TSH'
};
export function identity(o){let n=o.name.replace(/[（(].*?[)）]/g,'').trim();return aliases[o.code]||o.code||aliases[n]||n}
export function unit(o){return o.unit.trim().replace(/ml/gi,'mL').replace(/^u\//,'U/').replace(/[＊*×]10([0-9]+)\//,'10^$1/')}
export function groups(reports){let g={};reports.filter(r=>r.relevance!=='unrelated'&&r.status==='confirmed'&&!r.duplicate_of).forEach(r=>r.observations.forEach(o=>{let key=identity(o)+' | '+(unit(o)||'单位待确认 · '+r.id);(g[key]??=[]).push({...o,date:r.date,report:r})}));return g}
export function numeric(o){return /^[-+]?\d+(\.\d+)?$/.test(o.value)}
export function canConnect(a,b){return a.date!==b.date&&!!a.method?.trim()&&a.method.trim()===b.method?.trim()&&unit(a)&&unit(a)===unit(b)&&numeric(a)&&numeric(b)}

// A dashed chronological connector does not establish clinical comparability.
// Only adjacent records connect, so an unreadable or missing result leaves a gap.
export function trendSegments(rows){return rows.slice(1).flatMap((b,i)=>{
 const a=rows[i];
 if(!a.date||!b.date||a.date===b.date||identity(a)!==identity(b)||!unit(a)||unit(a)!==unit(b)||!numeric(a)||!numeric(b))return [];
 return [{from:i,to:i+1,style:canConnect(a,b)?'solid':'dashed'}];
})}
