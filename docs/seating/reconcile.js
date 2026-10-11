'use strict';
((root)=>{
  function reconcile(data, drafts) {
    const same=(a,b)=>[...a].sort((x,y)=>x-y).join(',')===[...b].sort((x,y)=>x-y).join(',');
    const actual=[...new Map(data.records.map(r=>[r.uuid,r])).values()];
    const cutoff=Date.parse(data.updated)/1000-900;
    const rows=drafts.map(d=>{
      if(d.cancelled)return {...d,status:'cancelled',candidates:[]};
      const candidates=actual.filter(r=>same(r.players,d.players) && (d.uuid?r.uuid===d.uuid:Math.abs(r.end-d.end)<=600)).map(r=>r.uuid);
      return {...d,candidates,status:candidates.length===1?'matched':candidates.length>1?'review':d.end<=cutoff?'review':'pending'};
    });
    const used=new Map();
    for(const d of rows)if(d.status!=='cancelled')for(const uuid of d.candidates)used.set(uuid,(used.get(uuid)||0)+1);
    for(const d of rows)if(d.candidates.some(uuid=>used.get(uuid)>1))d.status='review';
    return rows;
  }
  root.SeatingReconcile={reconcile};
  if(typeof module!=='undefined')module.exports={reconcile};
})(typeof globalThis!=='undefined'?globalThis:window);
