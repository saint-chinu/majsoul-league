'use strict';
(() => {
  const API='https://majsoul-seating.doppel-tag.workers.dev/season4';
  let d=window.SEATING_DATA;
  const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stamp=t=>new Date(t*1000).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  let rows=[], online=false, revision=-1, loading=false, saving=false, retry=null;
  let key='';try{key=localStorage.getItem('seating-editor')||'';}catch{}
  $('draft-members').innerHTML=d.players.map(p=>`<label><input type="checkbox" value="${p.id}">${esc(p.name)}</label>`).join('');
  function now(){ $('draft-end').value=new Date(Date.now()+9*3600000).toISOString().slice(0,16); }
  now();
  function render(){
    const checked=window.SeatingReconcile.reconcile(d,rows), include=$('include-drafts').checked;
    const pending=checked.filter(x=>x.status==='pending'), review=checked.filter(x=>x.status==='review');
    const additions=include?pending.map(x=>({...x,uuid:'draft:'+x.id,temporary:true})):[];
    const issues=[...d.issues];
    if(include&&!online)issues.push({reason:'共有仮登録が未確認'});
    if(include&&review.length)issues.push({reason:`仮登録の要確認 ${review.length}件`});
    window.renderSeating({...d,records:[...d.records,...additions],issues,confirmedCount:d.records.length,provisionalCount:additions.length});
    const labels={pending:'仮・牌譜待ち',matched:'一致・計上済み',review:'要確認',cancelled:'取消済み'};
    $('draft-rows').innerHTML=checked.length?[...checked].reverse().map(x=>`<tr><td>${stamp(x.end)}</td><td>${esc(x.players.map(id=>d.players.find(p=>p.id===id)?.name||'対象外').join(' / '))}</td><td class="draft-${x.status}">${labels[x.status]}${x.status==='matched'?` <a href="https://game.mahjongsoul.com/?paipu=${encodeURIComponent(x.candidates[0])}" target="_blank" rel="noopener">牌譜</a>`:''}</td><td>${x.status==='cancelled'?'—':`<button data-cancel="${esc(x.id)}" title="仮登録を取り消す" aria-label="仮登録を取り消す" ${!key||!online?'disabled':''}><i data-lucide="trash-2"></i></button>`}</td></tr>`).join(''):'<tr><td colspan="4" class="empty">仮登録はありません</td></tr>';
    $('draft-submit').disabled=!key||!online||saving;
    $('shared-status').textContent=online?`共有済み · 仮 ${pending.length}件 / 一致 ${checked.filter(x=>x.status==='matched').length}件 / 要確認 ${review.length}件${key?'':' · 閲覧モード'}`:'共有データ未確認。通信を確認してください。';
    window.lucide?.createIcons();
  }
  async function request(body){
    const response=await fetch(API,{method:body?'POST':'GET',cache:'no-store',headers:body?{'Content-Type':'application/json',Authorization:'Bearer '+key}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(12000)});
    const value=await response.json();if(!response.ok)throw Error(value.error||'通信に失敗しました');
    if(value.season!==4||!Array.isArray(value.rows)||!Number.isInteger(value.revision))throw Error('共有データが不正です');
    return value;
  }
  function accept(value){if(value.revision>=revision){revision=value.revision;rows=value.rows;}online=true;render();}
  async function sync(){
    if(loading||saving)return;loading=true;
    try{
      const response=await fetch('seating/data.js?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw Error('牌譜データを取得できません');
      const source=await response.text(), prefix='window.SEATING_DATA = ';
      if(!source.startsWith(prefix))throw Error('牌譜データが不正です');
      const latest=JSON.parse(source.slice(prefix.length).trim().replace(/;$/,''));
      if(latest.season!==4||!Array.isArray(latest.records)||!Array.isArray(latest.issues))throw Error('牌譜データが不正です');
      const changed=latest.updated!==d.updated;
      if(Date.parse(latest.updated)>=Date.parse(d.updated))d=latest;
      const v=await request();if(changed||v.revision!==revision||!online)accept(v);
    }catch{online=false;render();}finally{loading=false;}
  }
  async function save(body){saving=true;render();try{accept(await request(body));retry=null;$('draft-result').textContent='共有保存しました';return true;}catch(e){$('draft-result').textContent=e.message+'。入力は残っています。';return false;}finally{saving=false;render();}}
  $('draft-form').onsubmit=async e=>{
    e.preventDefault();const players=[...$('draft-members').querySelectorAll('input:checked')].map(x=>Number(x.value));
    if(players.length!==3){$('draft-result').textContent='参加者を3名選んでください';return;}
    const values={action:'add',players,end:Math.floor(Date.parse($('draft-end').value+':00+09:00')/1000),uuid:$('draft-uuid').value.trim()};
    const signature=JSON.stringify(values);
    if(!retry||retry.signature!==signature)retry={signature,id:crypto.randomUUID()};
    if(await save({...values,id:retry.id})){now();$('draft-uuid').value='';}
  };
  $('draft-rows').onclick=async e=>{const b=e.target.closest('[data-cancel]');if(b&&confirm('この仮登録を取り消しますか？ 取得済み牌譜は削除されません。'))await save({action:'cancel',id:b.dataset.cancel});};
  $('edit-key').onclick=()=>{$('key-value').value='';$('key-dialog').showModal();};
  $('save-key').onclick=()=>{key=$('key-value').value.trim();try{localStorage.setItem('seating-editor',key);}catch{}$('key-dialog').close();render();};
  $('forget-key').onclick=()=>{key='';try{localStorage.removeItem('seating-editor');}catch{}$('key-dialog').close();render();};
  $('include-drafts').onchange=render;$('sync-drafts').onclick=sync;
  render();sync();setInterval(()=>{if(!document.hidden)sync();},15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
})();
