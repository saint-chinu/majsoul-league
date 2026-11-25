(() => {
  'use strict';
  const summarize = (events, categories) => {
    const points = Object.fromEntries(categories.map(c => [c.key, c.points]));
    const counts = new Map(categories.map(c => [c.key, 0]));
    let positive = 0, negative = 0;
    events.forEach(e => e.categories.forEach(k => {
      counts.set(k, (counts.get(k) || 0) + 1);
      const n = points[k] || 0;
      if (n > 0) positive += n; else negative += n;
    }));
    const total = positive + negative;
    return {count: events.length, positive, negative, total, mean: events.length ? total / events.length : null,
      causes: categories.map(c => ({...c, count: counts.get(c.key), total: counts.get(c.key) * c.points}))
        .filter(c => c.count).sort((a,b) => a.total - b.total || b.count - a.count)};
  };
  const filterEvents = (events, categories, cause, mode, sort) => {
    const points = Object.fromEntries(categories.map(c => [c.key, c.points]));
    const penalty = e => e.categories.reduce((sum,k) => sum + Math.min(0, points[k] || 0), 0);
    return events.filter(e => (!cause || e.categories.includes(cause)) &&
      (mode === 'all' || e.categories.some(k => mode === 'positive' ? points[k] > 0 : points[k] < 0)))
      .sort((a,b) => (sort === 'penalty' ? penalty(a) - penalty(b) : 0) || b.start_time - a.start_time || b.round_no - a.round_no);
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = {summarize, filterEvents};
  if (typeof document === 'undefined') return;
  const $ = id => document.getElementById(id);
  const el = (tag, cls, text) => {const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;};
  const fmt = (n,d=0) => n.toLocaleString('ja-JP',{minimumFractionDigits:d,maximumFractionDigits:d});
  const signed = (n,d=0) => (n>0?'+':'')+fmt(n,d);
  const scoreClass = n => n<0?'audit-negative':n>0?'audit-positive':'';
  const round = e => (['東','南','西','北'][e.chang] || String(e.chang+1))+(e.ju+1)+'局 '+e.honba+'本場';
  const tile = t => {if(!t)return '不明';if(t[1]==='z')return ['東','南','西','北','白','發','中'][Number(t[0])-1]||t;return (t[0]==='0'?'赤5':t[0])+({m:'萬',p:'筒',s:'索'}[t[1]]||'');};
  const date = e => new Date(e.start_time*1000).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})+' JST';
  const params = new URLSearchParams(location.search);
  let manifest, categories=[], loaded=[], own=[], cause=params.get('cause')||'', page=0, request=0;
  const pageSize=20, cache=new Map();
  const fetchJSON = async url => {const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json();};
  const saveURL = () => {
    const q=new URLSearchParams({scope:$('scope').value,player:$('player').value});
    if(cause)q.set('cause',cause);
    q.set('mode',$('mode').value);q.set('sort',$('sort').value);
    history.replaceState(null,'','?'+q.toString());
  };
  const selectedSeasons = () => manifest.seasons.filter(s => $('scope').value==='lifetime' ||
    ($('scope').value==='new-league'?s.id.startsWith('new-'):$('scope').value==='old-league'?s.id.startsWith('old-'):s.id===$('scope').value));
  const fillSelect = (select, options, value) => {
    select.replaceChildren();options.forEach(([key,label])=>{const o=el('option','',label);o.value=key;select.append(o);});
    select.value=options.some(o=>o[0]===value)?value:options[0]?.[0]||'';
  };
  function renderEvents() {
    const filtered=filterEvents(own,categories,cause,$('mode').value,$('sort').value);
    const pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,pages-1);
    $('events').replaceChildren();
    $('selected-cause').hidden=!cause;$('clear-cause').hidden=!cause;
    $('selected-cause').textContent=categories.find(c=>c.key===cause)?.label||'';
    document.querySelectorAll('.cause-row').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.cause===cause)));
    filtered.slice(page*pageSize,(page+1)*pageSize).forEach(e => {
      const details=el('details','audit-event'), summary=el('summary');
      const action=e.action==='kita'?'北抜き':e.action==='kan'?'槍槓':e.action==='unknown'?'動作不明':'';
      summary.append(el('span','event-title',round(e)+' / '+(e.turn==null?'巡目不明':e.turn+'巡目')+(action?'・'+action:'')),el('span','event-score '+scoreClass(e.score),signed(e.score)));
      summary.append(el('span','event-meta','対局開始 '+date(e)+' · '+e.season_label+' · '+e.winner+'へ '+fmt(e.payment)+'点'));
      details.append(summary);
      const body=el('div','event-body'), reasons=el('ul','event-reasons');
      e.categories.forEach(key=>{
        const c=categories.find(c=>c.key===key);if(!c)return;
        const li=el('li');li.append(el('span','',c.label),el('b',scoreClass(c.points),signed(c.points)));reasons.append(li);
      });
      body.append(reasons,el('p','', '放銃牌：'+tile(e.tile)+' / 採点の参照状態：'+(e.riichi?'リーチ':e.shanten>=8?'不明（初打牌前）':e.shanten<=0?'テンパイ':e.shanten+'シャンテン')+' / 相手：'+(e.winner_riichi?'リーチ':e.winner_melds?e.winner_melds+'副露':'ダマ')));
      if(action)body.append(el('p','audit-note',action+'放銃。既存採点のシャンテン・終盤判定は直前の打牌時点を参照します。初打牌前は不明値が2シャンテン以下扱いになるため、減点理由は要確認です。'));
      if(e.riichi_info?.riichi)body.append(el('p','audit-note','リーチ時の採点情報：'+(e.riichi_info.good_shape?'良形':'愚形')+' / ドラ評価数 '+e.riichi_info.dora_count+' / 推定打点 '+fmt(e.riichi_info.estimated_point)+'点'));
      if(e.scores_before?.length && e.scores_after?.length){
        const rank=scores=>1+scores.slice(0,3).filter(n=>n>scores[e.seat]).length;
        body.append(el('p','','自分の持ち点：'+fmt((e.actual_scores_before||e.scores_before)[e.seat])+' → '+fmt((e.actual_scores_after||e.scores_after)[e.seat])+'点'),el('p','','採点上の順位：'+rank(e.scores_before)+'位 → '+rank(e.scores_after)+'位'));
      }
      body.append(el('p','audit-note','同卓：'+e.players.join('・')),el('p','audit-note','対局ID：'+e.uuid));
      const actions=el('div','event-actions'),link=el('a','','牌譜を開く');
      link.href='https://game.mahjongsoul.com/?paipu='+encodeURIComponent(e.uuid);link.target='_blank';link.rel='noopener noreferrer';
      const copy=el('button','','局情報をコピー');copy.type='button';
      copy.onclick=async()=>{try{await navigator.clipboard.writeText(e.uuid+' / '+date(e)+' / '+round(e)+' / '+e.turn+'巡目 / '+e.player+' → '+e.winner+' / '+tile(e.tile)+' / '+e.payment+'点');copy.textContent='コピー済み';}catch(_){copy.textContent='コピーできませんでした';}};
      actions.append(link,copy);body.append(actions);details.append(body);$('events').append(details);
    });
    if(!filtered.length)$('events').append(el('p','audit-note','該当する放銃はありません。'));
    $('previous').disabled=page===0;$('next').disabled=page>=pages-1;
    $('page-status').textContent=filtered.length?fmt(filtered.length)+'件中 '+(page*pageSize+1)+'–'+Math.min(filtered.length,(page+1)*pageSize)+'件':'0件';
    saveURL();
  }
  function renderPlayer() {
    own=loaded.flatMap(d=>d.events).filter(e=>e.player===$('player').value);
    const s=summarize(own,categories), warnings=[];
    const missing=loaded.reduce((n,d)=>n+d.missing_games.length,0);
    if(missing)warnings.push(missing+'半荘の元牌譜がないため、内訳は取得済み分のみです。');
    const special=own.filter(e=>e.action && e.action!=='discard').length;
    if(special)warnings.push('北抜き・槍槓などの放銃を'+special+'件含みます。既存採点が直前の打牌状態を参照するため、該当局に注意事項を表示しています。');
    const expected=manifest.expected[$('scope').value]?.[$('player').value];
    if(expected!==undefined && s.mean!==null && Math.abs(Number(expected)-s.mean)>0.011)warnings.push('成績表のスコア '+expected+' と、該当局からの再現値 '+fmt(s.mean,2)+' に差があります。ここは現行の採点処理による内訳です。');
    const mismatch=loaded.some(d=>{
      const target=d.expected[$('player').value]?.breakdown;if(target===undefined)return false;
      const expectedCounts=Object.fromEntries(target.split('|').filter(Boolean).map(p=>{const [k,v]=p.split(':');return [k,Number(v)];}));
      const actual=summarize(d.events.filter(e=>e.player===$('player').value),categories).causes;
      return categories.some(c=>(expectedCounts[c.key]||0)!==(actual.find(a=>a.key===c.key)?.count||0));
    });
    if(mismatch)warnings.push('保存済みの分類件数と再現件数が異なるシーズンを含みます。元の成績表は変更していません。');
    $('warning').hidden=!warnings.length;$('warning').textContent=warnings.join(' ');
    $('totals').replaceChildren();
    [['平均スコア',s.mean===null?'—':signed(s.mean,2),s.mean],['ロン放銃',fmt(s.count)+'件',0],['減点合計',signed(s.negative),s.negative],['加点合計',signed(s.positive),s.positive]].forEach(([label,value,n])=>{
      const d=el('div');d.append(el('dt','',label),el('dd',scoreClass(n),value));$('totals').append(d);
    });
    $('causes').replaceChildren();
    s.causes.forEach(c=>{
      const b=el('button','cause-row');b.type='button';b.dataset.cause=c.key;b.setAttribute('aria-controls','events');b.setAttribute('aria-pressed',String(cause===c.key));
      const name=el('span'),count=el('span'),points=el('span',scoreClass(c.total));
      name.append(el('strong','',c.label),el('small','',signed(c.points)+'点 / 回'));
      count.append(el('strong','',fmt(c.count)+'件'),el('small','',fmt(c.count/s.count*100,1)+'%'));
      points.append(el('strong','',signed(c.total)),el('small','',signed(c.total/s.count,2)+' / 放銃'));
      b.append(name,count,points);b.onclick=()=>{cause=cause===c.key?'':c.key;$('mode').value='all';page=0;renderEvents();$('rounds-title').scrollIntoView({block:'start'});};$('causes').append(b);
    });
    if(!s.causes.length)$('causes').append(el('p','audit-note','放銃の記録はありません。'));
    page=0;renderEvents();
    $('status').textContent=$('player').value+' / '+$('scope').selectedOptions[0].textContent;
    $('back-link').href=$('scope').value==='new-league'?'index.html':$('scope').value+'.html';
  }
  async function loadScope(player) {
    const token=++request;
    $('audit-content').hidden=true;$('warning').hidden=true;$('retry').hidden=true;$('player').disabled=true;$('status').textContent='該当局を読み込み中…';
    const seasons=selectedSeasons();
    fillSelect($('player'),[...new Set(seasons.flatMap(s=>s.players))].sort().map(p=>[p,p]),player);
    try{
      const data=await Promise.all(seasons.map(async s=>{
        if(!cache.has(s.id))cache.set(s.id,fetchJSON('deal-in-audit/'+s.file).catch(e=>{cache.delete(s.id);throw e;}));
        const d=await cache.get(s.id);return {...d,events:d.events.map(e=>({...e,season_label:s.label}))};
      }));
      if(token!==request)return;
      loaded=data;$('player').disabled=false;$('audit-content').hidden=false;renderPlayer();
    }catch(e){if(token!==request)return;$('status').textContent='該当局を読み込めませんでした。通信を確認して再読み込みしてください。';$('retry').hidden=false;}
  }
  $('retry').onclick=()=>location.reload();
  $('player').onchange=()=>{cause='';renderPlayer();};
  $('scope').onchange=()=>{cause='';loadScope($('player').value);};
  $('mode').onchange=$('sort').onchange=()=>{page=0;renderEvents();};
  $('clear-cause').onclick=()=>{cause='';page=0;renderEvents();};
  $('previous').onclick=()=>{page--;renderEvents();$('rounds-title').scrollIntoView({block:'start'});};
  $('next').onclick=()=>{page++;renderEvents();$('rounds-title').scrollIntoView({block:'start'});};
  if(['all','negative','positive'].includes(params.get('mode')))$('mode').value=params.get('mode');
  if(['recent','penalty'].includes(params.get('sort')))$('sort').value=params.get('sort');
  fetchJSON('deal-in-audit/index.json').then(data=>{
    manifest=data;categories=data.categories;
    if(!categories.some(c=>c.key===cause))cause='';
    const seasons=[...manifest.seasons].sort((a,b)=>a.id.startsWith('new-')!==b.id.startsWith('new-')?(a.id.startsWith('new-')?-1:1):Number(b.id.split('-').pop())-Number(a.id.split('-').pop()));
    fillSelect($('scope'),[...seasons.map(s=>[s.id,s.label]),['new-league','新リーグ累計'],['old-league','旧リーグ累計'],['lifetime','合算累計']],params.get('scope'));
    $('scope').disabled=false;return loadScope(params.get('player'));
  }).catch(()=>{$('status').textContent='データを読み込めませんでした。';$('retry').hidden=false;});
})();
