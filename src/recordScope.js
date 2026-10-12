export const isClinical=r=>r.relevance!=='unrelated';
export function filterRecords(reports,filter='',query=''){
 return reports.filter(r=>(filter==='unrelated'?!isClinical(r):filter==='all'||isClinical(r))&&(filter===''||filter==='all'||filter==='unrelated'||r.status===filter||r.priority===filter)&&JSON.stringify(r).includes(query));
}
