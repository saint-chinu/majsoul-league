(() => {
  'use strict';
  const themes = { white: 'オフホワイト', salmon: 'サーモン', navy: 'ネイビー × ゴールド', dark: 'ダーク' };
  let theme = 'white';
  try { theme = localStorage.getItem('gyogun-theme') || theme; } catch (_) {}
  document.documentElement.dataset.theme = themes[theme] ? theme : 'white';
  document.addEventListener('DOMContentLoaded', () => {
    const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
    const control = el('label', 'theme-control', 'テーマ');
    const dot = el('span', 'theme-dot'); dot.setAttribute('aria-hidden', 'true'); control.prepend(dot);
    const select = el('select'); select.setAttribute('aria-label', '表示テーマ');
    Object.entries(themes).forEach(([value, label]) => { const o = el('option', '', label); o.value = value; select.append(o); });
    select.value = document.documentElement.dataset.theme;
    select.addEventListener('change', () => { document.documentElement.dataset.theme = select.value; try { localStorage.setItem('gyogun-theme', select.value); } catch (_) {} });
    control.append(select); document.querySelector('header')?.append(control);
    const legacyNav = document.querySelector('.tab-groups');
    if (legacyNav) {
      const links = [...legacyNav.querySelectorAll('a[href]')];
      const filename = a => decodeURIComponent(a.getAttribute('href'));
      const current = links.find(a => a.getAttribute('aria-current') === 'page');
      const seasonLinks = links.filter(a => /^(new|old)-season-\d+\.html$/.test(filename(a)));
      const latest = seasonLinks.filter(a => filename(a).startsWith('new-')).sort((a,b) => Number(filename(b).match(/\d+/)[0])-Number(filename(a).match(/\d+/)[0]))[0];
      const nav = el('nav', 'compact-nav'); nav.setAttribute('aria-label','成績メニュー');
      const primary = el('div','compact-primary');
      const addLink = (a, title) => { if (!a) return; const link=a.cloneNode(true); link.className='compact-link'; link.textContent=title; if(a===current)link.classList.add('selected');primary.append(link); };
      const seasonGroups = [
        {id:'new',title:'新リーグ',links:seasonLinks.filter(a=>filename(a).startsWith('new-'))},
        {id:'old',title:'旧リーグ',links:seasonLinks.filter(a=>filename(a).startsWith('old-'))}
      ];
      seasonGroups.forEach(g=>g.links.sort((a,b)=>Number(filename(b).match(/\d+/)[0])-Number(filename(a).match(/\d+/)[0])));
      const currentFile=current ? filename(current) : '';
      const currentLeague=currentFile.startsWith('old-') ? 'old' : currentFile.startsWith('lifetime') ? 'lifetime' : 'new';
      const disclosure=el('section','league-disclosure');disclosure.id='league-seasons';disclosure.hidden=true;
      const entries=[];
      let expanded=null;
      function collapse(restoreFocus=false) {
        const previous=expanded;
        expanded=null;disclosure.hidden=true;
        entries.forEach(({button})=>button.setAttribute('aria-expanded','false'));
        if(restoreFocus)previous?.button.focus();
      }
      function choice(a, cls, text) {
        const link=a.cloneNode(true);link.className=cls;link.replaceChildren(el('span','',text));
        const marker=el('span','nav-choice-marker',a===current ? '表示中' : '→');
        if(a===current)link.classList.add('selected');else marker.setAttribute('aria-hidden','true');
        link.append(marker);return link;
      }
      function expand(entry) {
        if(expanded===entry){collapse();return;}
        nav.dispatchEvent(new CustomEvent('nav-disclosure-change',{detail:'league'}));
        expanded=entry;
        entries.forEach(e=>e.button.setAttribute('aria-expanded',String(e===entry)));
        disclosure.replaceChildren();disclosure.setAttribute('aria-labelledby',entry.button.id);
        const head=el('div','league-disclosure-head');
        head.append(choice(entry.link,'league-overview',entry.title+'を見る'));
        const close=el('button','league-disclosure-close','×');close.type='button';close.setAttribute('aria-label','シーズン一覧を閉じる');close.onclick=()=>collapse(true);head.append(close);
        disclosure.append(head);
        const groups=el('div','league-season-groups');
        entry.groups.forEach(group=>{
          const section=el('section','league-season-group');
          section.append(el('h3','',group.title+' / シーズン'));
          const list=el('div','league-season-list');
          group.links.forEach(a=>{
            const row=choice(a,'league-season-link',a.textContent);
            if(a===latest && a!==current && !a.textContent.includes('進行中'))row.querySelector('.nav-choice-marker').textContent='最新 →';
            list.append(row);
          });
          if(!group.links.length)list.append(el('p','nav-empty','シーズンデータはまだありません。'));
          section.append(list);groups.append(section);
        });
        disclosure.append(groups);disclosure.hidden=false;
      }
      [
        {id:'new',file:'index.html',title:'新リーグ累計',groups:[seasonGroups[0]]},
        {id:'old',file:'old-league.html',title:'旧リーグ累計',groups:[seasonGroups[1]]},
        {id:'lifetime',file:'lifetime.html',title:'合算累計',groups:seasonGroups}
      ].forEach(entry=>{
        entry.link=links.find(a=>filename(a)===entry.file);if(!entry.link)return;
        const button=el('button','compact-link league-trigger',entry.title);button.type='button';button.id='league-menu-'+entry.id;
        button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',disclosure.id);
        if(entry.id===currentLeague)button.classList.add('selected');
        const chevron=el('span','nav-chevron');chevron.setAttribute('aria-hidden','true');button.append(chevron);
        entry.button=button;entries.push(entry);button.onclick=()=>expand(entry);primary.append(button);
      });
      if(latest) addLink(latest, latest.textContent.includes('進行中') ? latest.textContent : latest.textContent+'（最新）');
      nav.addEventListener('keydown',e=>{if(e.key==='Escape'&&expanded){collapse(true);e.stopPropagation();}});
      document.addEventListener('click',e=>{if(expanded&&!nav.contains(e.target))collapse();});
      nav.addEventListener('nav-disclosure-change',e=>{if(e.detail!=='league')collapse();});
      const tools=el('div','compact-tools');
      function menu(title, groups, isPlayers) {
        const trigger=el('button','compact-menu-button',title+' ▾');trigger.type='button';trigger.id='player-picker-toggle';trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls','player-picker');tools.append(trigger);
        const picker=el('section','player-disclosure');picker.id='player-picker';picker.hidden=true;picker.setAttribute('aria-labelledby',trigger.id);
        const shut=(focus=false)=>{picker.hidden=true;trigger.setAttribute('aria-expanded','false');if(focus)trigger.focus();};
        const head=el('div','league-disclosure-head'),close=el('button','league-disclosure-close','×');close.type='button';close.setAttribute('aria-label','選手一覧を閉じる');close.onclick=()=>shut(true);head.append(el('h2','',title),close);
        const field=el('label','nav-scope','表示対象'),scope=el('select');scope.setAttribute('aria-label',title+'のリーグ');
        groups.forEach(g=>{const o=el('option','',g.title);o.value=g.id;scope.append(o);});field.append(scope);
        if(current){const match=groups.find(g=>g.links.includes(current));if(match)scope.value=match.id;else if(currentLeague!=='new')scope.value='lifetime';}
        const search=el('input','nav-search');search.type='search';search.placeholder='選手名で検索';search.setAttribute('aria-label','選手名で検索');
        const list=el('div','nav-choices');
        function render(){list.replaceChildren();const group=groups.find(g=>g.id===scope.value);const matches=group.links.filter(a=>!isPlayers||a.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));matches.forEach(a=>{const link=a.cloneNode(true);link.className='nav-choice';if(a===current)link.classList.add('selected');const name=el('span','',a.textContent),arrow=el('span','','→');arrow.setAttribute('aria-hidden','true');link.replaceChildren(name,arrow);list.append(link);});if(!matches.length)list.append(el('p','nav-empty','該当する選手がいません。'));}
        const filters=el('div','player-picker-filters');filters.append(field);if(isPlayers)filters.append(search);
        picker.append(head,filters,list);scope.onchange=render;search.oninput=render;render();nav.append(picker);
        trigger.onclick=()=>{if(!picker.hidden){shut();return;}nav.dispatchEvent(new CustomEvent('nav-disclosure-change',{detail:'players'}));picker.hidden=false;trigger.setAttribute('aria-expanded','true');};
        nav.addEventListener('nav-disclosure-change',e=>{if(e.detail!=='players')shut();});
        picker.addEventListener('keydown',e=>{if(e.key==='Escape'){shut(true);e.stopPropagation();}});
      }
      menu('選手を選ぶ',[
        {id:'new',title:'新リーグ個人成績',links:links.filter(a=>filename(a).startsWith('new-player-'))},
        {id:'lifetime',title:'合算個人成績',links:links.filter(a=>filename(a).startsWith('lifetime-player-'))}
      ],true);
      const location=el('p','compact-location');
      if(current){const file=filename(current); const prefix=file.startsWith('lifetime-player-')?'合算個人成績 / ':file.startsWith('new-player-')?'新リーグ個人成績 / ':'';location.textContent=prefix+(file==='index.html'?'新リーグ累計':file==='lifetime.html'?'合算累計':file==='old-league.html'?'旧リーグ累計':current.textContent);location.setAttribute('aria-label','現在のページ');}
      nav.prepend(primary,tools,location,disclosure); legacyNav.before(nav);legacyNav.classList.add('nav-legacy');legacyNav.hidden=true;
    }
    const dialog = el('dialog', 'drill-dialog'); dialog.setAttribute('aria-labelledby', 'drill-title'); document.body.append(dialog);
    let opener;
    dialog.addEventListener('close', () => opener?.focus());
    dialog.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } });
    const open = (title, trigger, context) => {
      opener = trigger; dialog.replaceChildren();
      dialog.append(el('p', 'drill-kicker', context || document.title.split(' | ')[0]));
      const head = el('div', 'drill-head'), h = el('h2', '', title), close = el('button', 'drill-close', '×');
      h.id = 'drill-title'; close.type = 'button'; close.title = '閉じる'; close.setAttribute('aria-label', '閉じる'); close.onclick = () => dialog.close();
      head.append(h, close); dialog.append(head); dialog.showModal();
    };
    const playerLink = name => {
      const links = [...document.querySelectorAll('a.player-tab')].filter(a => a.textContent.trim() === name);
      const prefix = location.pathname.includes('lifetime') || location.pathname.includes('old-') ? 'lifetime-player-' : 'new-player-';
      const a = links.find(a => a.getAttribute('href').startsWith(prefix)) || links[0];
      if (a) { const link = el('a', 'drill-link', name + 'の個人ページへ →'); link.href = a.href; dialog.append(link); }
    };
    document.querySelectorAll('.digest-cards').forEach(group => {
      const cards = [...group.querySelectorAll('.player-card')];
      const nameOf = card => card.querySelector('h3')?.textContent.trim() || '';
      cards.forEach(card => {
        const name = nameOf(card), heading = card.querySelector('h3');
        if (heading) {
          const button = el('button', 'player-open', name); button.type = 'button'; button.setAttribute('aria-label', name + 'の成績内訳'); heading.replaceChildren(button);
          button.onclick = () => {
            open(name, button);
            const panel = card.closest('.tab-panel');
            let count = 0;
            panel?.querySelectorAll('.table-wrap').forEach(wrap => {
              const table = wrap.querySelector('table');
              const row = [...(table?.querySelectorAll('tbody tr') || [])].find(r => [...r.cells].some(c => c.classList.contains('name') && c.textContent.trim() === name));
              if (!row) return;
              const headers = [...table.querySelectorAll('thead th')];
              if (headers.length !== row.cells.length) return;
              const section = el('details', 'drill-section'); section.open = count++ === 0;
              let prev = wrap.previousElementSibling;
              while (prev && !prev.matches('h2,h3')) prev = prev.previousElementSibling;
              const title = prev?.matches('h2,h3') ? prev.textContent : wrap.closest('.stat-table-panel,.ranking-panel')?.querySelector('h3')?.textContent;
              section.append(el('summary', '', title || '成績内訳 ' + count));
              const dl = el('dl'); [...row.cells].forEach((c, i) => { if (c.classList.contains('name')) return; dl.append(el('dt', '', headers[i].textContent.replace(/\s*\?\s*$/, '').trim()), el('dd', '', c.textContent.trim())); }); section.append(dl); dialog.append(section);
            });
            if (!count) { const dl = el('dl'); card.querySelectorAll('.digest-metric').forEach(m => dl.append(el('dt', '', m.querySelector('span').textContent), el('dd', '', m.querySelector('strong').textContent))); const section = el('div', 'drill-section'); section.append(dl); dialog.append(section); }
            playerLink(name);
          };
        }
        card.querySelectorAll('.digest-metric').forEach((metric, index) => {
          const strong = metric.querySelector('strong'), label = metric.querySelector('span')?.textContent;
          if (!strong) return;
          const button = el('button', 'digest-open', strong.textContent); button.type = 'button'; button.setAttribute('aria-label', name + '・' + label + 'の比較'); strong.replaceChildren(button);
          button.onclick = () => {
            open(label, button);
            const values = cards.map(c => ({name: nameOf(c), text: c.querySelectorAll('.digest-metric')[index]?.querySelector('strong')?.textContent || ''}));
            const number = text => Number(text.replace(/[^0-9.+-]/g, '')) || 0;
            const max = Math.max(1, ...values.map(v => Math.abs(number(v.text))));
            values.forEach(v => { const row = el('div', 'compare-row' + (v.name === name ? ' selected' : '')); const track = el('div', 'compare-track'), bar = el('div', 'compare-bar'); bar.style.width = Math.abs(number(v.text)) / max * 100 + '%'; if (number(v.text) < 0) bar.style.background = 'var(--danger)'; track.append(bar); row.append(el('span', '', v.name), track, el('strong', '', v.text)); dialog.append(row); });
            dialog.append(el('p', 'drill-note', '棒の長さは数値の絶対値。マイナス値は赤色で表示。'));
            playerLink(name);
          };
        });
      });
    });
    const digest=document.querySelector('.digest-cards');
    if(digest) {
      const panel=digest.closest('.tab-panel');
      const names=[...digest.querySelectorAll('.player-card h3')].map(h=>h.textContent.trim());
      const categories=new Map();
      const metricSources=new Map();
      // Compare the already-rendered values; no separate aggregation or rounding of source data.
      panel.querySelectorAll('.table-wrap').forEach(wrap=>{
        const table=wrap.querySelector('table');if(!table)return;
        let title=wrap.closest('.stat-table-panel')?.querySelector('h3')?.textContent.trim();
        if(!title){
          const heading=wrap.previousElementSibling?.textContent.trim() || '';
          title=['リーチの質','鳴きの質','放銃の質'].find(t=>heading.endsWith(t));
        }
        if(!title)return;
        const headers=[...table.querySelectorAll('thead th')];
        const rows=new Map([...table.querySelectorAll('tbody tr')].map(r=>[r.querySelector('td.name')?.textContent.trim(),r]));
        if(!names.some(name=>rows.has(name)))return;
        if(!categories.has(title))categories.set(title,new Map());
        const metrics=categories.get(title);
        headers.forEach((header,index)=>{
          const label=header.textContent.replace(/\s*\?\s*$/,'').trim();
          if(['順位','プレイヤー'].includes(label))return;
          const values=new Map(names.map(name=>[name,rows.get(name)?.cells[index]?.textContent.trim() || '—']));
          if(metrics.has(label) && names.every(name=>metrics.get(label).get(name)===values.get(name)))return;
          const key=metrics.has(label)?label+'（詳細）':label;
          metrics.set(key,values);
          if(!metricSources.has(key))metricSources.set(key,{header,cells:new Map(names.map(name=>[name,rows.get(name)?.cells[index]]))});
        });
      });
      if(names.length>1 && categories.size) {
        const allMetrics=new Map();categories.forEach(metrics=>metrics.forEach((values,label)=>{if(!allMetrics.has(label))allMetrics.set(label,values);}));
        const mainMetrics=new Map();
        ['半荘数','スコア','平均順位','1位率','2位率','3位率','和了率','放銃率','平均和了点','放銃平均打点','先制テンパイ率','テンパイ維持率','立直率','副露率'].forEach(label=>{if(allMetrics.has(label))mainMetrics.set(label,allMetrics.get(label));});
        const views=new Map([['主要指標',mainMetrics],...categories]);
        const high=new Set(['スコア','1位率','ラス回避率','トップキープ率','トップ滞在率','和了率','平均和了点','鳴き手平均打点','先制テンパイ率','テンパイ維持率','リーチ質スコア','鳴き質スコア','放銃質スコア','リーチ可率','オーラスまくり率','南場まくり率','MVP回数','チーム優勝回数','最高終了時持ち点','最低終了時持ち点']);
        const low=new Set(['平均順位','3位率','放銃率','放銃平均打点','オーラスまくられ率','南場まくられ率','ラス滞在率','リーチ空振り率','非推奨リーチ率']);
        const numeric=text=>{const clean=text.replace(/,/g,'');return /^[+-]?\d+(?:\.\d+)?%?$/.test(clean)?Number(clean.replace('%','')):null;};
        let ordering='スコア';
        const comparison=el('section','comparison-panel comparison-home');comparison.id='player-comparison';comparison.setAttribute('aria-label','全員比較');
        const firstHeading=panel.querySelector('h2');firstHeading.before(comparison);
        {
          const head=el('div','league-disclosure-head');
          head.append(el('h2','',document.querySelector('.compact-location')?.textContent+' / 全員比較'));comparison.append(head);
          const controls=el('div','matrix-controls');
          const label=el('label','','比較項目'),category=el('select');category.setAttribute('aria-label','比較項目');
          views.forEach((_,key)=>{const option=el('option','',key);option.value=key;category.append(option);});label.append(category);controls.append(label);
          const orderStatus=el('span','matrix-order');controls.append(orderStatus);
          const body=el('div','comparison-content');body.tabIndex=0;body.setAttribute('role','region');body.setAttribute('aria-label','全員比較表');
          const detail=el('section','matrix-detail');detail.id='comparison-detail';detail.hidden=true;
          let detailKey=null,detailOpener=null;
          const clearDetail=(focus=false)=>{
            const previousKey=detailKey;
            detail.hidden=true;detailKey=null;
            comparison.querySelectorAll('[aria-controls="comparison-detail"]').forEach(b=>b.setAttribute('aria-expanded','false'));
            if(focus&&detailOpener?.isConnected)detailOpener.focus({preventScroll:true});
            else if(focus)[...body.querySelectorAll('[data-detail-key]')].find(b=>b.dataset.detailKey===previousKey)?.focus({preventScroll:true});
          };
          function openDetail(key,title,trigger){
            if(detailKey===key&&!detail.hidden){clearDetail();return false;}
            clearDetail();detailKey=key;detailOpener=trigger;trigger.setAttribute('aria-expanded','true');
            detail.replaceChildren();detail.hidden=false;
            comparison.querySelectorAll('[data-detail-key]').forEach(b=>b.setAttribute('aria-expanded',String(b.dataset.detailKey===key)));
            const heading=el('div','league-disclosure-head'),h=el('h3','',title),close=el('button','league-disclosure-close','×');
            h.id='comparison-detail-title';detail.setAttribute('aria-labelledby',h.id);h.tabIndex=-1;
            close.type='button';close.setAttribute('aria-label','比較の詳細を閉じる');close.onclick=()=>clearDetail(true);heading.append(h,close);detail.append(heading);
            h.focus({preventScroll:true});detail.scrollIntoView({block:'nearest'});return true;
          }
          const drillButton=(label,cls,key,callback)=>{
            const button=el('button',cls,label);button.type='button';button.dataset.detailKey=key;button.setAttribute('aria-controls',detail.id);button.setAttribute('aria-expanded',String(detailKey===key&&!detail.hidden));button.onclick=()=>callback(button);return button;
          };
          const addRichDetail=(host,label,player)=>{
            const source=metricSources.get(label)?.cells.get(player)?.querySelector('[data-metric-html]');
            if(!source)return;
            const d=el('details','drill-section'),content=el('div','rich-metric-detail');d.append(el('summary','',label+'の分類内訳'));
            content.innerHTML=source.dataset.metricHtml;d.append(content);host.append(d);
          };
          function showPlayer(player,trigger){
            if(!openDetail('player:'+player,player+' / '+document.querySelector('.compact-location')?.textContent,trigger))return;
            const stats=el('dl','player-drill-summary');
            ['半荘数','スコア','平均順位','1位率','和了率','放銃率'].forEach(label=>{const value=allMetrics.get(label)?.get(player);if(value!==undefined){const box=el('div');box.append(el('dt','',label),el('dd','',value));stats.append(box);}});detail.append(stats);
            categories.forEach((metrics,title)=>{
              const group=el('details','drill-section');group.append(el('summary','',title));const dl=el('dl');
              metrics.forEach((values,label)=>{dl.append(el('dt','',label),el('dd','',values.get(player)));});group.append(dl);
              metrics.forEach((_,label)=>addRichDetail(group,label,player));detail.append(group);
            });
            const prefix=location.pathname.includes('lifetime')||location.pathname.includes('old-')?'lifetime-player-':'new-player-';
            const a=[...document.querySelectorAll('.nav-legacy a.player-tab')].find(a=>a.textContent.trim()===player&&a.getAttribute('href').startsWith(prefix));
            if(a){const link=el('a','drill-link',player+'の個人ページ・シーズン推移 →');link.href=a.href;detail.append(link);}
            detail.scrollIntoView({block:'start'});
          }
          function showMetric(label,trigger){
            if(!openDetail('metric:'+label,label+' / 全員の内訳',trigger))return;
            const source=metricSources.get(label)?.header.querySelector('[data-metric-title]');
            if(source?.dataset.metricBody)detail.append(el('p','metric-description',source.dataset.metricBody));
            if(source?.dataset.metricHtml){const rules=el('details','drill-section'),content=el('div','rich-metric-detail');rules.append(el('summary','','定義・採点基準'));content.innerHTML=source.dataset.metricHtml;rules.append(content);detail.append(rules);}
            const list=el('div','metric-player-list');allMetrics.get(label).forEach((text,player)=>{
              const row=el('div','metric-player-row'),button=drillButton(player,'matrix-player','player:'+player,b=>showPlayer(player,b));row.append(button,el('strong','',text));addRichDetail(row,label,player);list.append(row);
            });detail.append(list);
            const matching=[...categories].find(([,metrics])=>metrics.has(label));
            if(matching){const more=el('button','metric-category-link',matching[0]+'で全員を比較 →');more.type='button';more.onclick=()=>{category.value=matching[0];clearDetail();renderComparison();comparison.scrollIntoView({block:'start'});category.focus({preventScroll:true});};detail.append(more);}
            detail.scrollIntoView({block:'start'});
          }
          detail.addEventListener('keydown',e=>{if(e.key==='Escape'){clearDetail(true);e.stopPropagation();}});
          function renderComparison(){
            const sorted=[...names];const orderValues=allMetrics.get(ordering);
            if(orderValues)sorted.sort((a,b)=>{
              const x=numeric(orderValues.get(a)),y=numeric(orderValues.get(b));
              return x===null?(y===null?0:1):y===null?-1:(low.has(ordering)?x-y:y-x);
            });
            orderStatus.textContent=ordering+'順 / '+names.length+'人';
            const table=el('table','comparison-table'),thead=el('thead'),tr=el('tr');
            table.style.setProperty('--players',names.length);
            ['項目',...sorted].forEach((text,index)=>{const th=el('th');th.scope='col';if(index)th.append(drillButton(text,'matrix-player','player:'+text,b=>showPlayer(text,b)));else th.textContent=text;tr.append(th);});thead.append(tr);table.append(thead);
            const tbody=el('tbody');
            views.get(category.value).forEach((values,label)=>{
              const row=el('tr'),name=el('th');name.scope='row';row.append(name);
              const ranked=high.has(label)||low.has(label);
              name.append(drillButton(label,'matrix-metric','metric:'+label,b=>showMetric(label,b)));
              if(ranked){
                const button=el('button','matrix-sort',low.has(label)?'↓':'↑');button.type='button';button.title=label+'順に並べ替え';button.setAttribute('aria-label',button.title);button.setAttribute('aria-pressed',String(ordering===label));
                button.onclick=()=>{ordering=label;renderComparison();body.querySelectorAll('.matrix-sort').forEach(b=>{if(b.title===button.title)b.focus({preventScroll:true});});};name.append(button);
              }
              const numbers=sorted.map(n=>numeric(values.get(n))).filter(n=>n!==null);
              const best=low.has(label)?Math.min(...numbers):Math.max(...numbers),worst=low.has(label)?Math.max(...numbers):Math.min(...numbers);
              sorted.forEach(player=>{
                const cell=el('td'),text=values.get(player),value=numeric(text);cell.append(el('span','matrix-value',text));
                if(ranked && value!==null){
                  const rank=1+numbers.filter(n=>low.has(label)?n<value:n>value).length;
                  cell.append(el('small','matrix-rank',rank+'位'));
                  if(best!==worst)cell.classList.add(value===best?'matrix-best':value===worst?'matrix-worst':'matrix-neutral');
                }
                row.append(cell);
              });tbody.append(row);
            });
            table.append(tbody);body.replaceChildren(table);
          }
          category.onchange=()=>{clearDetail();renderComparison();};
          comparison.append(controls,el('p','comparison-note','順位は表示値で比較。↑は高い順、↓は低い順。1位を色付き、最下位を薄いグレーで表示。同値は同順位。'),body,detail);
          renderComparison();
        }
      }
    }
    // Move existing sections intact so every table, explanation and listener is retained.
    document.querySelectorAll('.tab-panel').forEach(panel=>{
      const isOverview=!!panel.querySelector('.digest-cards');
      const trend=panel.querySelector('.season-trends');
      const isPlayer=!isOverview&&!!trend;
      if(isPlayer){
        const metrics=new Map();
        const firstHeading=panel.querySelector(':scope > h2');
        for(let n=firstHeading?.nextElementSibling;n&&n.tagName!=='H2';n=n.nextElementSibling){
          n.querySelectorAll('table').forEach(table=>{
            const headers=[...table.querySelectorAll('thead th')],row=table.querySelector('tbody tr');
            if(!row)return;
            headers.forEach((h,i)=>{const label=h.querySelector('[data-metric-title]')?.dataset.metricTitle||h.textContent.replace(/\s*\?\s*$/,'').trim();if(row.cells[i])metrics.set(label,{text:row.cells[i].textContent.trim(),cell:row.cells[i]});});
          });
        }
        const overview=el('section','personal-overview');overview.setAttribute('aria-label','主要成績');overview.append(el('h2','','主要成績'));
        const grid=el('div','personal-key-stats');
        ['半荘数','スコア','平均順位','1位率','和了率','放銃率','平均和了点','放銃平均打点'].forEach(label=>{
          const metric=metrics.get(label);if(!metric)return;
          const button=el('button','personal-stat');button.type='button';button.setAttribute('aria-label',label+'の詳細を見る');button.append(el('span','',label),el('strong','',metric.text));
          button.onclick=()=>{const fold=metric.cell.closest('.stats-fold');if(fold)fold.open=true;const target=metric.cell.closest('.stat-table-panel')||metric.cell.closest('table');target.scrollIntoView({block:'start'});target.tabIndex=-1;target.focus({preventScroll:true});};grid.append(button);
        });
        overview.append(grid);trend.prepend(el('h2','','シーズン推移'));panel.prepend(overview,trend);
        const oldSummary=panel.querySelector(':scope > .summary');
        if(oldSummary){const fold=el('details','stats-fold');fold.append(el('summary','','集計概要'));oldSummary.before(fold);fold.append(oldSummary);}
      }
      [...panel.children].filter(n=>n.tagName==='H2').forEach(heading=>{
        if(!isOverview&&!isPlayer&&!/和了役スタッツ|リーチの質|鳴きの質|放銃の質/.test(heading.textContent))return;
        const nodes=[];for(let n=heading.nextElementSibling;n&&n.tagName!=='H2'&&!n.classList.contains('ranking-grid');n=n.nextElementSibling)nodes.push(n);
        const fold=el('details','stats-fold'),summary=el('summary');heading.before(fold);summary.append(heading);fold.append(summary,...nodes);
      });
      if(isOverview)panel.querySelectorAll(':scope > .ranking-grid').forEach(grid=>{const fold=el('details','stats-fold');fold.append(el('summary','','役満の被害・獲得ランキング'));grid.before(fold);fold.append(grid);});
    });
  });
})();
