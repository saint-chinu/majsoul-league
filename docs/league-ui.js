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
      if(latest) addLink(latest, latest.textContent.includes('進行中') ? latest.textContent : latest.textContent+'（最新）');
      [['index.html','新リーグ累計'],['old-league.html','旧リーグ累計'],['lifetime.html','合算累計']].forEach(([file,title])=>addLink(links.find(a=>filename(a)===file),title));
      const tools=el('div','compact-tools');
      function menu(title, groups, isPlayers) {
        const trigger=el('button','compact-menu-button',title+' ▾');trigger.type='button';trigger.setAttribute('aria-haspopup','dialog');tools.append(trigger);
        const modal=el('dialog','drill-dialog navigation-dialog');modal.setAttribute('aria-label',title);document.body.append(modal);
        const head=el('div','drill-head'),close=el('button','drill-close','×');close.type='button';close.setAttribute('aria-label','閉じる');close.onclick=()=>modal.close();head.append(el('h2','',title),close);
        const field=el('label','nav-scope','表示対象'),scope=el('select');scope.setAttribute('aria-label',title+'のリーグ');
        groups.forEach(g=>{const o=el('option','',g.title);o.value=g.id;scope.append(o);});field.append(scope);
        if(current){const match=groups.find(g=>g.links.includes(current));if(match)scope.value=match.id;}
        const search=el('input','nav-search');search.type='search';search.placeholder='選手名で検索';search.setAttribute('aria-label','選手名で検索');
        const list=el('div','nav-choices');
        function render(){list.replaceChildren();const group=groups.find(g=>g.id===scope.value);const matches=group.links.filter(a=>!isPlayers||a.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));matches.forEach(a=>{const link=a.cloneNode(true);link.className='nav-choice';if(a===current)link.classList.add('selected');const name=el('span','',a.textContent),arrow=el('span','','→');arrow.setAttribute('aria-hidden','true');link.replaceChildren(name,arrow);list.append(link);});if(!matches.length)list.append(el('p','nav-empty','該当する選手がいません。'));}
        modal.append(head,field);if(isPlayers)modal.append(search);modal.append(list);scope.onchange=render;search.oninput=render;render();
        trigger.onclick=()=>{modal.showModal();};modal.addEventListener('close',()=>trigger.focus());modal.addEventListener('click',e=>{const r=modal.getBoundingClientRect();if(e.target===modal&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))modal.close();});
      }
      menu('シーズンを選ぶ',[
        {id:'new',title:'新リーグ',links:seasonLinks.filter(a=>filename(a).startsWith('new-'))},
        {id:'old',title:'旧リーグ',links:seasonLinks.filter(a=>filename(a).startsWith('old-'))}
      ],false);
      menu('選手を選ぶ',[
        {id:'new',title:'新リーグ個人成績',links:links.filter(a=>filename(a).startsWith('new-player-'))},
        {id:'lifetime',title:'合算個人成績',links:links.filter(a=>filename(a).startsWith('lifetime-player-'))}
      ],true);
      const location=el('p','compact-location');
      if(current){const file=filename(current); const prefix=file.startsWith('lifetime-player-')?'合算個人成績 / ':file.startsWith('new-player-')?'新リーグ個人成績 / ':'';location.textContent=prefix+(file==='index.html'?'新リーグ累計':file==='lifetime.html'?'合算累計':file==='old-league.html'?'旧リーグ累計':current.textContent);location.setAttribute('aria-label','現在のページ');}
      nav.append(primary,tools,location); legacyNav.before(nav);legacyNav.classList.add('nav-legacy');legacyNav.hidden=true;
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
  });
})();
