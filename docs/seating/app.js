'use strict';
(() => {
  const d = window.SEATING_DATA, E = window.Seating, $ = id => document.getElementById(id);
  if (!d || !E) { $('notice').hidden=false; $('notice').textContent='集計データを読み込めませんでした。再読込してください。'; return; }
  const esc = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const counts=Array(20).fill(0), errors=[...d.issues], ids=new Set();
  for(const r of d.records){
    if(ids.has(r.uuid))continue;
    ids.add(r.uuid);
    const members=r.players.map(id=>d.players.findIndex(p=>p.id===id)).sort((a,b)=>a-b);
    const i=E.combos.findIndex(c=>c.join(',')===members.join(','));
    if(i<0){errors.push({reason:'対象外の参加者'});continue;}
    counts[i]++;
  }
  const state=E.stats(counts);
  const names = c => c.map(i=>'<span>'+esc(d.players[i].name)+'</span>').join('<b class="separator">·</b>');
  const simpleNames = c => c.map(i=>d.players[i].name).join(' / ');
  const date = t => new Date(t).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  let plan=null, worker=null, timer=null;
  $('played').textContent=state.total; $('remaining').textContent=Math.max(0,60-state.total);
  $('source').textContent=`公開データ更新 ${date(d.updated)} JST · 対局結果 ${state.total}件`;
  if(!d.source_available){$('notice').hidden=false; $('notice').textContent='シーズン4の牌譜は未取得です。以下は0半荘からの初期配分案です。';}
  if(errors.length){$('notice').hidden=false; $('notice').textContent=`未集計 ${errors.length}件。${errors.map(x=>x.reason).filter((x,i,a)=>a.indexOf(x)===i).join(' / ')}。推奨卓は保留中です。`;}
  $('people').innerHTML=d.players.map((p,i)=>`<div class="person ${state.people[i]>30?'over':''}"><div class="person-heading"><strong title="${esc(p.account_name)}">${esc(p.name)}</strong><span>${state.people[i]}<small> / 30</small></span></div><progress max="30" value="${Math.min(state.people[i],30)}" aria-label="${esc(p.name)}の消化数"></progress><p>${state.people[i]>30?'超過 '+(state.people[i]-30):'残り '+(30-state.people[i])}半荘</p></div>`).join('');
  function tables(){
    const final=plan?E.stats(counts.map((n,i)=>n+plan[i])):null;
    $('combinations').innerHTML=E.combos.map((c,i)=>`<tr><td class="names">${names(c)}</td><td class="count ${counts[i]<3?'low':counts[i]>3?'high':''}">${counts[i]}</td><td>${counts[i]-3>0?'+':''}${counts[i]-3}</td><td class="forecast">${plan?plan[i]:'—'}</td><td>${plan?counts[i]+plan[i]:'—'}</td></tr>`).join('');
    $('pair-table').innerHTML='<thead><tr><th>参加者</th>'+d.players.map(p=>`<th>${esc(p.name)}</th>`).join('')+'</tr></thead><tbody>'+d.players.map((p,i)=>'<tr><th>'+esc(p.name)+'</th>'+d.players.map((_,j)=>{
      if(i===j)return '<td class="diagonal">—</td>';
      const k=E.pairs.findIndex(pair=>pair.includes(i)&&pair.includes(j));
      return `<td class="${state.together[k]<12?'low':state.together[k]>12?'high':''}">${state.together[k]}<small>/ ${final?final.together[k]:'—'}</small></td>`;
    }).join('')+'</tr>').join('')+'</tbody>';
  }
  $('history-count').textContent=`${state.total}半荘`;
  $('history').innerHTML=d.records.length?[...d.records].reverse().map(r=>`<tr><td>${date(r.end*1000)}</td><td>${esc(r.players.map(id=>d.players.find(p=>p.id===id)?.name||'対象外').join(' / '))}</td><td><a href="https://game.mahjongsoul.com/?paipu=${encodeURIComponent(r.uuid)}" target="_blank" rel="noopener">開く</a></td></tr>`).join(''):'<tr><td colspan="3" class="empty">集計済みの対局はありません</td></tr>';
  function finish(result){
    clearTimeout(timer); if(worker)worker.terminate(); worker=null;
    $('recalculate').disabled=false; $('download').disabled=true;
    if(result.error){$('plan-status').textContent=result.error;return;}
    if(!E.validate(counts,result.plan)){$('plan-status').textContent='計算結果の検証に失敗しました。';return;}
    plan=result.plan; tables(); $('download').disabled=false;
    if(state.total===60){$('plan-status').textContent=`全員30半荘を消化しました。ペア同卓の最大偏差は${result.pairGap}回です。`;return;}
    $('plan-status').textContent=result.exact?'全20通りを各3回に揃えられます。以下は残り全体の配分案から選んだ候補です。':`3人組を各3回には戻せません。全員30半荘を保つ調整案です。最終ペア同卓の最大偏差：${result.pairGap}回。`;
    const order=E.order(counts,plan), candidates=[...new Set(order)].slice(0,3);
    $('suggestions').innerHTML=candidates.map((i,j)=>`<div class="suggestion"><div class="number">0${j+1}</div><div><div class="names">${names(E.combos[i])}</div><small>この3人組：消化 ${counts[i]}回 · 残り案 ${plan[i]}回</small></div><span class="right">最終 ${counts[i]+plan[i]}回</span></div>`).join('');
    for(const i of [...new Set(order)]){
      const c=E.combos.findIndex(x=>x.every(p=>!E.combos[i].includes(p)));
      if(plan[c]>0){$('two-tables').hidden=false; $('two-tables').innerHTML='<strong>6人揃う場合の2卓案</strong><div>A '+esc(simpleNames(E.combos[i]))+'</div><div>B '+esc(simpleNames(E.combos[c]))+'</div>';break;}
    }
  }
  function calculate(){
    if(worker)worker.terminate(); clearTimeout(timer); plan=null; tables();
    $('suggestions').innerHTML='';$('two-tables').hidden=true;$('download').disabled=true;
    if(errors.length){$('plan-status').textContent='不足・対象外の対局を確認後、再集計してください。';return;}
    $('recalculate').disabled=true;$('plan-status').textContent='残り全体の卓組を計算中…';
    try {worker=new Worker('seating/worker.js');worker.onmessage=e=>finish(e.data);worker.onerror=()=>finish({error:'計算機能を読み込めませんでした。再計算してください。'});worker.postMessage(counts);timer=setTimeout(()=>finish({error:'計算時間の上限に達しました。再計算してください。'}),12000);}
    catch(_){finish({error:'このブラウザでは計算機能を開始できませんでした。'});}
  }
  $('reload').onclick=()=>location.reload();$('recalculate').onclick=calculate;
  $('help').onclick=()=>$('rules').showModal();$('close-help').onclick=()=>$('rules').close();$('print').onclick=()=>window.print();
  $('download').onclick=()=>{
    if(!plan)return;
    const rows=[['残り対局番号','参加者1','参加者2','参加者3'],...E.order(counts,plan).map((i,n)=>[n+1,...E.combos[i].map(j=>d.players[j].name)])];
    const csv='\ufeff'+rows.map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'})),a=document.createElement('a');a.href=url;a.download='season4-remaining-tables.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  window.lucide?.createIcons(); tables(); calculate();
})();
