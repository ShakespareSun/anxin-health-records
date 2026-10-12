import {test} from 'node:test';
import assert from 'node:assert/strict';
import {groups,canConnect,numeric,trendSegments} from '../src/comparison.js';
import {sortedMetrics,metricInfo} from '../src/metrics.js';
import {filterRecords,isClinical} from '../src/recordScope.js';
const obs={name:'糖类抗原125',code:'CA125',value:'8.20',unit:'u/ml',reference:'≤25',method:''};
const r=(id,status='confirmed',extra={})=>({id,date:'2024-01-15',status,observations:[obs],...extra});
test('Unreviewed and duplicates excluded',()=>{assert.equal(Object.values(groups([r(1),r(2,'pending'),r(3,'confirmed',{duplicate_of:1})]))[0].length,1)});
test('Unrelated pages hidden by default and never enter trends',()=>{
 const rows=[r(1),r(2,'pending',{relevance:'unrelated'}),r(3,'confirmed',{relevance:'unrelated'}),r(4,'pending',{priority:'背景备查'})];
 assert.deepEqual(filterRecords(rows).map(r=>r.id),[1,4]);
 assert.deepEqual(filterRecords(rows,'unrelated').map(r=>r.id),[2,3]);
 assert.equal(filterRecords(rows,'all').length,4);
 assert.deepEqual(filterRecords(rows,'pending').map(r=>r.id),[4]);
 assert.equal(Object.values(groups(rows))[0].length,1);
 rows[2].relevance='clinical';assert.ok(isClinical(rows[2]));assert.equal(Object.values(groups(rows))[0].length,2);
});
test('Equivalent unit spelling groups; incompatible units separate',()=>{let g=groups([r(1),r(2,'confirmed',{observations:[{...obs,unit:'U/mL'}]}),r(3,'confirmed',{observations:[{...obs,unit:'ng/mL'}]})]);assert.equal(Object.keys(g).length,2);assert.equal(g['CA125 | U/mL'].length,2)});
test('Unknown methods never connect; thresholds are not exact values',()=>{let a={...obs,date:'2024-01-15'},b={...obs,date:'2024-07-15'};assert.equal(!!canConnect(a,b),false);assert.ok(canConnect({...a,method:'ECLIA'},{...b,method:'ECLIA'}));assert.equal(!!canConnect({...a,method:'ECLIA'},{...b,method:'ECLIA',value:'<5'}),false);assert.equal(numeric({...obs,value:'4?49'}),false);assert.equal(numeric({...obs,value:''}),false)});
test('Chinese labels and tumor follow-up come first',()=>{let g=groups([r(1,'confirmed',{observations:[{...obs,name:'白细胞',code:'WBC'},obs,{...obs,name:'人附睾蛋白4',code:'HE4'}]})]);let items=sortedMetrics(g);assert.equal(items[0].code,'CA125');assert.equal(items[0].name,'糖类抗原125');assert.equal(items[0].category,'肿瘤随访');assert.ok(items[0].description.includes('正常也不能排除复发'));assert.equal(items[1].code,'HE4')});
test('Only latest report flags populate current abnormal group',()=>{let rows=[{...obs,date:'2024-01-15',flag:'↑'},{...obs,date:'2024-07-15',flag:''}];assert.equal(metricInfo('CA125 | U/mL',rows).abnormal,false)});

test('Chronological lines distinguish comparable methods from uncertain methods',()=>{
 const rows=['2023-07-15','2024-01-15','2024-07-15'].map(date=>({...obs,date}));
 assert.deepEqual(trendSegments(rows),[{from:0,to:1,style:'dashed'},{from:1,to:2,style:'dashed'}]);
 assert.equal(trendSegments(rows.map(r=>({...r,method:'ECLIA'})))[0].style,'solid');
 assert.equal(trendSegments([{...rows[0],method:'ECLIA'},{...rows[1],method:'ELISA'}])[0].style,'dashed');
});
test('Trend lines never bridge ambiguous results or incompatible measurements',()=>{
 const a={...obs,date:'2023-07-15'},b={...obs,date:'2024-01-15'},c={...obs,date:'2024-07-15'};
 for(const value of ['','<5','4?49'])assert.deepEqual(trendSegments([a,{...b,value},c]),[]);
 for(const altered of [{...b,unit:'ng/mL'},{...b,unit:''},{...b,code:'CEA'},{...b,date:a.date}])assert.deepEqual(trendSegments([a,altered]),[]);
});
