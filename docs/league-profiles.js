(() => {
  'use strict';
  const axes = [
    {key:'1位率', label:'トップ率', low:false},
    {key:'和了率', label:'和了率', low:false},
    {key:'平均和了点', label:'和了打点', low:false},
    {key:'放銃率', label:'放銃抑制', low:true},
    {key:'放銃平均打点', label:'失点の軽さ', low:true},
    {key:'平均順位', label:'順位安定', low:true}
  ];
  const number = text => {
    const s=String(text??'').trim().replaceAll(',','').replace(/%$/,'');
    return /^[+-]?\d+(\.\d+)?$/.test(s)?Number(s):null;
  };
  function position(value, values, low=false) {
    const valid=values.filter(v=>v!==null&&Number.isFinite(v));
    if(value===null||!Number.isFinite(value)||!valid.length)return {score:null,rank:null,total:valid.length};
    const better=valid.filter(v=>low?v<value:v>value).length;
    const tied=valid.filter(v=>v===value).length;
    const rank=better+1;
    // Midranks keep ties symmetric; a fully tied population is 50, not 100.
    const score=valid.length<2?null:100*(valid.length-rank-(Math.max(tied,1)-1)/2)/(valid.length-1);
    return {score,rank,total:valid.length};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={position,number};
  if(typeof document==='undefined')return;
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  const svgEl=(tag,attrs)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));return n;};
  const header=c=>c.querySelector('[data-metric-title]')?.dataset.metricTitle||c.textContent.replace(/\s*\?\s*$/,'').trim();
  function readScope(doc) {
    const players=new Map();
    doc.querySelectorAll('.table-wrap > table').forEach(t=>{
      const heads=[...t.querySelectorAll('thead th')].map(header),nameCol=heads.indexOf('プレイヤー');
      if(nameCol<0)return;
      t.querySelectorAll('tbody > tr').forEach(r=>{
        const name=r.cells[nameCol]?.textContent.trim();if(!name)return;
        if(!players.has(name))players.set(name,{name,metrics:new Map()});
        const p=players.get(name);
        heads.forEach((h,i)=>{if(!p.metrics.has(h)&&r.cells[i])p.metrics.set(h,r.cells[i].textContent.trim());});
      });
    });
    let ratio=.3;try{ratio=JSON.parse(doc.querySelector('#league-meta')?.textContent||'{}').minGamesRatio??ratio;}catch(_){}
    const people=[...players.values()].filter(p=>number(p.metrics.get('半荘数'))>0);
    const minimum=Math.ceil(Math.max(0,...people.map(p=>number(p.metrics.get('半荘数'))))*ratio);
    const qualified=people.filter(p=>number(p.metrics.get('半荘数'))>=minimum);
    people.forEach(p=>{
      p.games=number(p.metrics.get('半荘数'));p.eligible=p.games>=minimum;
      p.axes=axes.map(a=>{
        const text=p.metrics.get(a.key)??'—',value=number(text);
        const result=p.eligible?position(value,qualified.map(q=>number(q.metrics.get(a.key))),a.low):{score:null,rank:null,total:qualified.length};
        return {...a,...result,text};
      });
    });
    return {people,minimum};
  }
  const loads=new Map();
  async function fetchScope(file) {
    if(!loads.has(file))loads.set(file,fetch(file).then(r=>{if(!r.ok)throw Error('load');return r.text();}).then(text=>{
      const data=readScope(new DOMParser().parseFromString(text,'text/html'));
      if(!data.people.length)throw Error('empty');return data;
    }).catch(e=>{loads.delete(file);throw e;}));
    return loads.get(file);
  }
  function chart(p, activate) {
    const wrap=el('div','profile-chart'),svg=svgEl('svg',{viewBox:'0 0 360 300','aria-hidden':'true'});
    const point=(i,scale)=>{const angle=-Math.PI/2+i*Math.PI/3;return [180+96*scale*Math.cos(angle),150+96*scale*Math.sin(angle)];};
    const points=scale=>axes.map((_,i)=>point(i,scale).join(',')).join(' ');
    [.25,.5,.75,1].forEach(scale=>svg.append(svgEl('polygon',{points:points(scale),class:scale===.5?'profile-ring profile-median':'profile-ring'})));
    axes.forEach((_,i)=>{const [x,y]=point(i,1);svg.append(svgEl('line',{x1:180,y1:150,x2:x,y2:y,class:'profile-spoke'}));});
    const complete=p.axes.every(a=>a.score!==null);
    if(complete){
      svg.append(svgEl('polygon',{points:p.axes.map((a,i)=>point(i,a.score/100).join(',')).join(' '),class:'profile-area'}));
      p.axes.forEach((a,i)=>{const [cx,cy]=point(i,a.score/100);svg.append(svgEl('circle',{cx,cy,r:3,class:'profile-dot'}));});
    }else{
      const text=svgEl('text',{x:180,y:154,'text-anchor':'middle',class:'profile-empty'});text.textContent=p.eligible?'比較データ不足':'参考';svg.append(text);
    }
    wrap.append(svg);
    const positions=[[50,7],[86,30],[86,70],[50,93],[14,70],[14,30]];
    p.axes.forEach((a,i)=>{
      const button=el('button','profile-axis',a.label);button.type='button';button.style.left=positions[i][0]+'%';button.style.top=positions[i][1]+'%';
      button.setAttribute('aria-label',p.name+' '+a.key+'の内訳');button.onclick=()=>activate(p,i);wrap.append(button);
    });
    return wrap;
  }
  function createPanel(host, personal, playerName, scopeOptions) {
    const fold=el('details','stats-fold parameter-fold');fold.id='parameter-profile';fold.open=personal||location.hash==='#parameter-profile';
    const summary=el('summary'),title=el('h2','','パラメータ図');summary.append(title);fold.append(summary);
    const bar=el('div','profile-toolbar'),intro=el('div');
    intro.append(el('p','profile-kicker','PERFORMANCE PROFILE'),el('p','profile-subtitle','6つの指標で見る、成績のバランス'));
    bar.append(intro);
    const scope=el('select');scope.setAttribute('aria-label','パラメータ図の集計範囲');
    scopeOptions.forEach(o=>{const n=el('option','',o.label);n.value=o.file;scope.append(n);});
    if(personal){const label=el('label','','集計範囲');label.append(scope);bar.append(label);}
    const legend=el('div','profile-legend');legend.append(el('span','profile-self','本人'),el('span','profile-baseline','中位の目安 50'),el('span','','外側ほど上位 / 0–100'));
    const grid=el('div','profile-grid'+(personal?' profile-single':''));
    const detail=el('section','profile-detail');detail.hidden=true;detail.setAttribute('aria-live','polite');
    const method=el('details','profile-method');method.append(el('summary','','算出基準'));
    method.append(el('p','','同じ集計範囲の規定半荘以上の選手を対象に、各指標の順位を0〜100へ換算。単独1位は100、単独最下位は0。同率は同順位の占める位置の平均とし、全員同率なら50。放銃率・放銃平均打点・平均順位は低いほど外側。能力の絶対評価や、異なるシーズン間での実力差を表すものではありません。'));
    const population=el('p','profile-population');method.append(population);
    fold.append(bar,legend,grid,detail,method);host(fold);
    let data=null,started=false,request=0,opener=null;
    function show(p, selected=0) {
      opener=document.activeElement;detail.replaceChildren();detail.hidden=false;
      grid.querySelectorAll('.profile-player').forEach(n=>n.classList.toggle('is-active',n.dataset.player===p.name));
      const cards=[...grid.querySelectorAll('.profile-player')],index=cards.findIndex(n=>n.dataset.player===p.name);
      const columns=getComputedStyle(grid).gridTemplateColumns.split(' ').length;
      cards[Math.min(cards.length-1,Math.floor(index/columns)*columns+columns-1)]?.after(detail);
      const head=el('div','profile-detail-head'),h=el('h3','',p.name+' / '+scope.selectedOptions[0].textContent),close=el('button','league-disclosure-close','×');
      close.type='button';close.setAttribute('aria-label','パラメータ内訳を閉じる');close.onclick=()=>{detail.hidden=true;grid.querySelectorAll('.is-active').forEach(n=>n.classList.remove('is-active'));opener?.focus({preventScroll:true});};head.append(h,close);detail.append(head);
      const rows=el('div','profile-breakdown');
      p.axes.forEach((a,i)=>{
        const row=el('div','profile-breakdown-row'+(i===selected?' is-selected':''));row.tabIndex=-1;
        const name=el('div','profile-metric-name');name.append(el('strong','',a.label),el('span','',a.key+' · '+(a.low?'低いほど上位':'高いほど上位')));
        const actual=el('div','profile-actual');actual.append(el('strong','',a.text),el('small','',a.rank?a.rank+'位 / '+a.total+'人':p.eligible?'比較対象なし':'規定未満・参考'));
        const track=el('div','profile-track'),fill=el('span');fill.style.width=(a.score??0)+'%';track.append(fill);
        row.append(name,actual,track,el('span','profile-score',a.score===null?'—':a.score.toFixed(1)));rows.append(row);
      });detail.append(rows);
      const note=el('p','profile-detail-note','相対位置は同じ集計範囲内での比較。成績の実数値は右欄に表示。');detail.append(note);
      h.tabIndex=-1;h.focus({preventScroll:true});detail.scrollIntoView({block:'nearest'});
    }
    detail.addEventListener('keydown',e=>{if(e.key==='Escape')detail.querySelector('button').click();});
    function render() {
      grid.replaceChildren();detail.hidden=true;
      method.before(detail);
      const people=personal?data.people.filter(p=>p.name===playerName):data.people;
      population.textContent='規定 '+data.minimum+'半荘以上 / 対象 '+data.people.filter(p=>p.eligible).length+'人。規定未満は実数値のみを参考表示。';
      if(!people.length){grid.append(el('p','profile-status','この集計範囲には参加記録がありません。'));return;}
      people.forEach(p=>{
        const item=el('article','profile-player');item.dataset.player=p.name;
        const heading=el('div','profile-player-head'),button=el('button','profile-player-name',p.name);button.type='button';button.onclick=()=>show(p);
        heading.append(button,el('span','profile-games',p.games+'半荘'+(!p.eligible?' · 参考':'')));item.append(heading,chart(p,show));
        const metrics=el('div','profile-foot');metrics.append(el('span','','トップ率 '+(p.metrics.get('1位率')||'—')),el('span','','放銃率 '+(p.metrics.get('放銃率')||'—')));item.append(metrics);grid.append(item);
      });
    }
    async function load() {
      const token=++request;grid.replaceChildren(el('p','profile-status','読み込み中…'));detail.hidden=true;fold.setAttribute('aria-busy','true');
      try{const result=personal?await fetchScope(scope.value):readScope(document);if(token!==request)return;data=result;render();}
      catch(_){if(token!==request)return;grid.replaceChildren(el('p','profile-status','データを読み込めませんでした。'));const retry=el('button','profile-retry','再読み込み');retry.type='button';retry.onclick=load;grid.append(retry);}
      finally{if(token===request)fold.removeAttribute('aria-busy');}
    }
    fold.addEventListener('toggle',()=>{if(fold.open&&!started){started=true;load();}});scope.onchange=load;
    if(fold.open){started=true;load();}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const file=decodeURIComponent(location.pathname.split('/').pop()||'index.html');
    const player=file.match(/^(new|lifetime)-player-(.+)\.html$/);
    const panel=document.querySelector('.tab-panel');if(!panel)return;
    const comparison=panel.querySelector('.comparison-home');
    if(comparison){createPanel(n=>comparison.after(n),false,null,[{file,label:document.querySelector('.compact-location')?.textContent||document.title}]);return;}
    if(!player)return;
    const links=[...document.querySelectorAll('.nav-legacy a[href]')],options=[{file:player[1]==='new'?'index.html':'lifetime.html',label:player[1]==='new'?'新リーグ累計':'合算累計'}];
    links.forEach(a=>{const href=decodeURIComponent(a.getAttribute('href'));if(/^(new|old)-season-\d+\.html$/.test(href)&&(player[1]==='lifetime'||href.startsWith('new-')))options.push({file:href,label:a.textContent.trim()});});
    const trend=panel.querySelector('.season-trends');if(trend)createPanel(n=>trend.after(n),true,player[2],options);
  });
})();
