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
