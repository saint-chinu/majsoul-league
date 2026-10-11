const MEMBERS = [101939586, 68348480, 108312204, 101665767, 102159970, 108386176];
const ORIGIN = 'https://saint-chinu.github.io';
const headers = {'Access-Control-Allow-Origin': ORIGIN, 'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Cache-Control': 'no-store', 'Vary': 'Origin'};
const reply = (body, status=200) => Response.json(body, {status, headers});
export function checkCap(rows, input, data) {
  if(input.action!=='add'||rows.some(r=>r.id===input.id))return;
  const same=(a,b)=>[...a].sort((x,y)=>x-y).join(',')===[...b].sort((x,y)=>x-y).join(',');
  const actual=[...data.records,...(data.excluded||[])];
  const matches=d=>actual.filter(r=>same(r.players,d.players)&&(d.uuid?r.uuid===d.uuid:Math.abs(r.end-d.end)<=600));
  let count=data.records.filter(r=>same(r.players,input.players)).length;
  const used=new Set();
  for(const r of rows.filter(r=>!r.cancelled)){
    const candidates=matches(r);
    if(candidates.length>1 || candidates.some(x=>used.has(x.uuid)))throw Error('要確認の仮登録を先に確認してください');
    candidates.forEach(x=>used.add(x.uuid));
    if(!candidates.length){
      if(r.end<=Date.parse(data.updated)/1000-900)throw Error('要確認の仮登録を先に確認してください');
      if(same(r.players,input.players))count++;
    }
  }
  // Three games per combination is advisory; all results remain valid.
}
export function mutate(rows, input, now) {
  if (!/^[a-f0-9-]{36}$/.test(input.id || '')) throw Error('登録IDが不正です');
  const old = rows.find(x=>x.id===input.id);
  if (input.action === 'cancel') {
    if (!old) throw Error('対象が見つかりません');
    return rows.map(x=>x.id===input.id ? {...x, cancelled:true, cancelledAt:now} : x);
  }
  if (input.action !== 'add') throw Error('操作が不正です');
  const players = input.players;
  if (!Array.isArray(players) || players.length!==3 || new Set(players).size!==3 || players.some(x=>!MEMBERS.includes(x))) throw Error('異なる参加者3名を選んでください');
  const sorted = [...players].sort((a,b)=>a-b);
  if (old) {
    if (JSON.stringify(old.players) === JSON.stringify(sorted) && old.end === input.end && old.uuid === (input.uuid || '')) return rows;
    throw Error('登録IDが重複しています');
  }
  if (rows.length >= 500) throw Error('登録上限です。管理者へ連絡してください');
  if (!Number.isInteger(input.end) || input.end < 1791388800 || input.end > now + 300) throw Error('終了日時を確認してください');
  const uuid = input.uuid || '';
  if (typeof uuid!=='string' || (uuid && !/^\d{6}-[a-f0-9-]{36}$/.test(uuid))) throw Error('牌譜IDが不正です');
  if (rows.some(x=>!x.cancelled && JSON.stringify(x.players)===JSON.stringify(sorted) && Math.abs(x.end-input.end)<60)) throw Error('同じ卓・時刻が登録済みです');
  return [...rows,{id:input.id,players:sorted,end:input.end,uuid,createdAt:now,cancelled:false}];
}
export default {
  async fetch(request, env) {
    if (request.method==='OPTIONS') return new Response(null,{status:204,headers});
    if (new URL(request.url).pathname!=='/season4') return reply({error:'Not found'},404);
    try {
      if (request.method==='GET') {
        const row=await env.DB.prepare('SELECT revision, body FROM seating WHERE id=4').first();
        return reply({season:4,revision:row.revision,rows:JSON.parse(row.body)});
      }
      if (request.method!=='POST') return reply({error:'Method not allowed'},405);
      if (request.headers.get('Origin') && request.headers.get('Origin')!==ORIGIN) return reply({error:'Origin rejected'},403);
      const reader=request.body?.getReader(); let length=0,chunks=[];
      if(reader)while(true){const {value,done}=await reader.read();if(done)break;length+=value.length;if(length>2048){await reader.cancel();return reply({error:'入力が大きすぎます'},413);}chunks.push(value);}
      const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
      let input;
      try { input=JSON.parse(new TextDecoder().decode(bytes)); } catch {return reply({error:'入力が不正です'},400);}
      if (!input || typeof input!=='object') return reply({error:'入力が不正です'},400);
      let data;
      if(input.action==='add'){
        const response=await fetch('https://saint-chinu.github.io/majsoul-league/seating/data.js',{cache:'no-store'});
        if(!response.ok)return reply({error:'牌譜データを確認できません。少し待って再試行してください'},503);
        const source=await response.text();
        if(!source.startsWith('window.SEATING_DATA = '))return reply({error:'牌譜データが不正です'},503);
        data=JSON.parse(source.slice('window.SEATING_DATA = '.length).trim().replace(/;$/,''));
        if(data.season!==4||!Array.isArray(data.records)||data.issues?.length)return reply({error:'牌譜データが未確認です'},503);
      }
      for(let attempt=0;attempt<5;attempt++) {
        const row=await env.DB.prepare('SELECT revision, body FROM seating WHERE id=4').first();
        let rows;
        try {const previous=JSON.parse(row.body);rows=mutate(previous,input,Math.floor(Date.now()/1000));checkCap(previous,input,data);} catch(e){return reply({error:e.message},400);}
        const result=await env.DB.prepare('UPDATE seating SET body=?, revision=revision+1 WHERE id=4 AND revision=?').bind(JSON.stringify(rows),row.revision).run();
        if(result.meta.changes===1) return reply({season:4,revision:row.revision+1,rows});
      }
      return reply({error:'同時更新がありました。再度お試しください'},409);
    } catch(e) {
      console.error(JSON.stringify({event:'seating_error',name:e.name}));
      return reply({error:'共有保存先に接続できません'},503);
    }
  }
};
