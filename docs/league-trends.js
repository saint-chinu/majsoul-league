(() => {
  'use strict';
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const number = text => { const s = text.trim().replaceAll(',', '').replace(/%$/, ''); return /^[+-]?\d+(\.\d+)?$/.test(s) ? Number(s) : null; };
  const headerName = cell => cell.querySelector('[data-metric-title]')?.dataset.metricTitle || cell.textContent.trim();
  document.querySelectorAll('.tab-panel').forEach(panel => {
    const heading = [...panel.querySelectorAll('h2')].find(h => h.textContent.endsWith('シーズン別推移'));
    if (!heading) return;
    const tables = [];
    for (let n = heading.nextElementSibling; n && n.tagName !== 'H2'; n = n.nextElementSibling) tables.push(...n.querySelectorAll('table'));
    const seasons = new Map();
    tables.forEach((table, tableIndex) => {
      const heads = [...table.querySelectorAll('thead th')];
      const seasonIndex = heads.findIndex(h => h.textContent.trim() === 'シーズン');
      if (seasonIndex < 0) return;
      let title = table.closest('.stat-table-panel')?.querySelector('h3')?.textContent;
      title ||= ['順位スタッツ', '和了・放銃スタッツ', 'リーチの質', '鳴きの質', '放銃の質'][tableIndex] || '詳細成績';
      table.querySelectorAll('tbody > tr').forEach(row => {
        const cells = [...row.cells];
        const label = cells[seasonIndex]?.textContent.trim();
        if (!label || cells.length !== heads.length) return;
        if (!seasons.has(label)) seasons.set(label, {label, groups: [], metrics: new Map()});
        const season = seasons.get(label), items = [];
        cells.forEach((cell, i) => {
          if (i === seasonIndex || headerName(heads[i]) === 'プレイヤー') return;
          const name = headerName(heads[i]), text = cell.textContent.trim();
          const item = {name, text, value: number(text), detail: cell.querySelector('[data-metric-html]')?.dataset.metricHtml};
          items.push(item); if (!season.metrics.has(name)) season.metrics.set(name, item);
        });
        season.groups.push({title, items});
      });
    });
    const order = label => [(label.startsWith('旧') ? 0 : 1), Number(label.match(/\d+/)?.[0] || 0)];
    const rows = [...seasons.values()].sort((a,b) => { const x = order(a.label), y = order(b.label); return x[0] - y[0] || x[1] - y[1]; });
    if (!rows.length) return;
    const metrics = [...new Set(rows.flatMap(r => [...r.metrics].filter(([,m]) => m.value !== null).map(([k]) => k)))];
    if (!metrics.length) return;
    const section = el('section', 'season-trends'); section.setAttribute('aria-label', 'シーズン別成績グラフ');
    const toolbar = el('div', 'trend-toolbar'), label = el('label', '', '指標'), select = el('select'); select.setAttribute('aria-label','推移グラフの指標');
    metrics.forEach(m => { const o = el('option', '', m); o.value = m; select.append(o); }); select.value = metrics.includes('スコア') ? 'スコア' : metrics[0]; label.append(select);
    const rangeLabel = el('label', '', '期間'), range = el('select'); range.setAttribute('aria-label','推移グラフの期間');
    [['all','全シーズン'],['old','旧リーグ'],['new','新リーグ']].forEach(([v,t]) => { if (v !== 'all' && !rows.some(r => (v === 'old') === r.label.startsWith('旧'))) return; const o = el('option','',t); o.value=v; range.append(o); }); rangeLabel.append(range); toolbar.append(label,rangeLabel);
    const quick = el('div','trend-presets'); quick.setAttribute('aria-label','主要指標');
    ['スコア','平均順位','和了率','放銃率','リーチ質スコア'].filter(m=>metrics.includes(m)).forEach(m=>{ const b=el('button','',m); b.type='button'; b.onclick=()=>{select.value=m;render();}; quick.append(b); });
    const stats=el('div','trend-stats'), scroll=el('div','trend-scroll'), plot=el('div','trend-plot'), note=el('p','trend-note'); scroll.append(plot);
    section.append(toolbar,quick,stats,scroll,note); heading.after(section);
    const dialog=el('dialog','drill-dialog season-dialog'); dialog.setAttribute('aria-label','シーズン成績の内訳'); document.body.append(dialog); let opener;
    dialog.addEventListener('close',()=>opener?.focus());
    dialog.addEventListener('click',e=>{const r=dialog.getBoundingClientRect();if(e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))dialog.close();});
    const openSeason=(season,trigger)=>{
      opener=trigger;dialog.replaceChildren();const head=el('div','drill-head'), title=el('h2','',season.label), close=el('button','drill-close','×'); close.type='button';close.setAttribute('aria-label','閉じる');close.onclick=()=>dialog.close();head.append(title,close);dialog.append(el('p','drill-kicker',heading.textContent.replace(' シーズン別推移','')),head);
      season.groups.forEach((group,i)=>{const d=el('details','drill-section');d.open=i===0;d.append(el('summary','',group.title));const dl=el('dl'); group.items.forEach(item=>{dl.append(el('dt','',item.name));const dd=el('dd','',item.text);dl.append(dd);if(item.detail){const detail=el('details','trend-quality');detail.append(el('summary','',item.name+'の分類内訳'));const body=el('div');body.innerHTML=item.detail;detail.append(body);dd.append(detail);}});d.append(dl);dialog.append(d);});
      const n=season.label.match(/\d+/)?.[0]; if(n){const link=el('a','drill-link','シーズン全員の成績へ →');link.href=(season.label.startsWith('旧')?'old':'new')+'-season-'+n+'.html';dialog.append(link);}dialog.showModal();
    };
    function render(){
      const chosen=rows.filter(r=>range.value==='all'||(range.value==='old')===r.label.startsWith('旧'));
      const key=select.value, values=chosen.map(r=>r.metrics.get(key)?.value ?? null), valid=values.filter(v=>v!==null);
      quick.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.textContent===key)));
      plot.replaceChildren();stats.replaceChildren();
      const last=chosen.at(-1), lastMetric=last?.metrics.get(key);
      const unit=lastMetric?.text.endsWith('%')?'pt':'';
      const prev=chosen.at(-2)?.metrics.get(key)?.value;
      const delta=lastMetric?.value!==null&&lastMetric?.value!==undefined&&prev!==null&&prev!==undefined?lastMetric.value-prev:null;
      [[last?.label||'最新',lastMetric?.text||'データなし'],['前シーズンとの差',delta===null?'—':(delta>0?'+':'')+Number(delta.toFixed(2))+unit],['表示シーズン',String(chosen.length)]].forEach(([a,b])=>{const box=el('div');box.append(el('span','',a),el('strong','',b));stats.append(box);});
      note.textContent='各点・シーズン名から内訳を表示。未参加シーズンは省略し、欠損値は線でつなぎません。';
      if(key==='平均順位')note.textContent+=' 平均順位は低いほど上位。';
      if(!valid.length){plot.append(el('p','','この期間には数値データがありません。'));return;}
      const width=Math.max(560,scroll.clientWidth-2,chosen.length*95+80),height=290,left=60,right=55,top=30,bottom=55;
      plot.style.width=width+'px'; plot.style.minWidth='0'; plot.style.height=height+'px';
      let min=Math.min(...valid),max=Math.max(...valid);const pad=(max-min)*.15||Math.max(Math.abs(max)*.1,1);min-=pad;max+=pad;
      const x=i=>chosen.length===1?width/2:left+i*(width-left-right)/(chosen.length-1), y=v=>top+(max-v)/(max-min)*(height-top-bottom);
      const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('aria-hidden','true');
      const shape=(tag,attrs)=>{const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));svg.append(n);return n;};
      for(let i=0;i<5;i++){const value=min+(max-min)*i/4, yy=y(value);shape('line',{x1:left,y1:yy,x2:width-right,y2:yy,class:'trend-grid'});shape('text',{x:left-8,y:yy+4,'text-anchor':'end',class:'trend-axis'}).textContent=Number(value.toFixed(2)).toLocaleString('ja-JP');}
      chosen.forEach((r,i)=>{if(i&&values[i]!==null&&values[i-1]!==null&&order(r.label)[0]===order(chosen[i-1].label)[0]&&order(r.label)[1]===order(chosen[i-1].label)[1]+1)shape('line',{x1:x(i-1),y1:y(values[i-1]),x2:x(i),y2:y(values[i]),class:'trend-line'});});plot.append(svg);
      chosen.forEach((r,i)=>{const v=values[i];if(v!==null){const b=el('button','trend-point');b.type='button';b.style.left=x(i)+'px';b.style.top=y(v)+'px';b.setAttribute('aria-label',r.label+' '+key+' '+r.metrics.get(key).text+' 内訳');b.title=r.label+' / '+r.metrics.get(key).text;b.onclick=()=>openSeason(r,b);plot.append(b);const text=el('span','trend-value',r.metrics.get(key).text);text.style.left=x(i)+'px';text.style.top=(y(v)-25)+'px';plot.append(text);}const b=el('button','trend-season',r.label.replace('（進行中）',' *'));b.type='button';b.style.left=x(i)+'px';b.onclick=()=>openSeason(r,b);plot.append(b);});
    }
    select.onchange=render;range.onchange=render;render();
  });
})();
