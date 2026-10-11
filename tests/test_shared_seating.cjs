const assert=require('node:assert/strict');
const {reconcile}=require('../docs/seating/reconcile.js');
(async()=>{
  const {mutate,default:worker}=await import('../shared-seating/worker.mjs');
  const players=[68348480,101939586,108312204], now=1791700000;
  const input={id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',action:'add',players,end:now-60};
  const rows=mutate([],input,now);
  assert.equal(rows.length,1);assert.deepEqual(mutate(rows,input,now),rows);
  assert.throws(()=>mutate(rows,{...input,id:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'},now));
  assert.throws(()=>mutate([],{...input,players:[players[0],players[0],players[1]]},now));
  assert.throws(()=>mutate([],{...input,end:now+3600},now));
  assert.equal(mutate(rows,{id:input.id,action:'cancel'},now)[0].cancelled,true);
  const data={updated:new Date(now*1000).toISOString(),records:[]};
  assert.equal(reconcile(data,rows)[0].status,'pending');
  const record={uuid:'x',players,end:input.end};
  data.records=[record];assert.equal(reconcile(data,rows)[0].status,'matched');
  data.records=[record,{...record,uuid:'y'}];assert.equal(reconcile(data,rows)[0].status,'review');
  data.records=[record];assert(reconcile(data,[...rows,{...rows[0],id:'other'}]).every(x=>x.status==='review'));
  assert.equal(reconcile(data,[{...rows[0],uuid:'missing'}])[0].status,'pending');
  assert.equal(reconcile(data,[{...rows[0],end:now-3600}])[0].status,'review');
  assert.equal(reconcile(data,[{...rows[0],cancelled:true}])[0].status,'cancelled');
  assert.equal(reconcile({...data,records:[record,record]},rows)[0].status,'matched');
  assert.equal(reconcile({...data,records:[],excluded:[record]},rows)[0].status,'excluded');
  globalThis.fetch=async()=>{throw Error('Registration must not depend on published replay data');};
  let stored={revision:0,body:'[]'};
  const env={DB:{prepare(sql){return {
    async first(){return {...stored};},
    bind(body,revision){return {async run(){if(stored.revision!==revision)return {meta:{changes:0}};stored={body,revision:revision+1};return {meta:{changes:1}};}};}
  };}}};
  const send=x=>worker.fetch(new Request('https://test/season4',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(x)}),env);
  const results=await Promise.all([send(input),send({...input,id:'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',end:input.end-120})]);
  assert(results.every(r=>r.status===200));assert.equal(JSON.parse(stored.body).length,2);
  const retryResponse=await send(input);assert.equal(retryResponse.status,200);assert.equal(JSON.parse(stored.body).length,2);
  const atLimit=await Promise.all([send({...input,id:'cccccccc-cccc-cccc-cccc-cccccccccccc',end:input.end-240}),send({...input,id:'dddddddd-dddd-dddd-dddd-dddddddddddd',end:input.end-360})]);
  assert.deepEqual(atLimit.map(r=>r.status).sort(),[200,200]);
  assert.equal(JSON.parse(stored.body).length,4);
  assert(reconcile({...data,records:[],updated:new Date((now+3600)*1000).toISOString()},JSON.parse(stored.body)).every(r=>r.status==='review'));
  const despiteReview=await send({...input,id:'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',end:input.end-720});
  assert.equal(despiteReview.status,200);
  assert.equal(JSON.parse(stored.body).length,5);
  console.log('shared seating validation, retries, cancellation and reconciliation: OK');
})();
