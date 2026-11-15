// Optional score chart and player heading; source tables remain authoritative.
(() => {
  'use strict';
  const num = text => { const c = String(text ?? '').replace(/[,%+]/g, '').trim(); return /^-?\d+(\.\d+)?$/.test(c) ? Number(c) : null; };
  const scoreLayout = scores => {
    const values = scores.map(s => s.value).filter(Number.isFinite);
    const min = Math.min(0, ...values), max = Math.max(0, ...values), span = max - min || 1;
    return scores.map(s => ({ ...s, rank: 1 + values.filter(v => v > s.value).length,
      zero: -min / span * 100, left: (Math.min(0, s.value) - min) / span * 100, width: Math.abs(s.value) / span * 100 }));
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = { num, scoreLayout };
  if (typeof document === 'undefined') return;
  document.addEventListener('DOMContentLoaded', () => {
    const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
    const fmt = (v, d = 1) => v.toLocaleString('ja-JP', { minimumFractionDigits: d, maximumFractionDigits: d });
    const signed = v => (v > 0 ? '+' : '') + fmt(v);
    const scope = document.querySelector('.compact-location')?.textContent.trim() || document.title.split(' | ')[0];
    const updated = document.querySelector('footer .generated-at')?.textContent.replace(/^\s*最終更新:\s*/, '').trim();
    const kicker = parts => { const p = el('p', 'report-kicker'); parts.filter(Boolean).forEach((t, i) => p.append(el(i ? 'span' : 'b', '', t))); return p; };
    const playerHref = name => {
      const prefix = location.pathname.includes('lifetime') || location.pathname.includes('old-') ? 'lifetime-player-' : 'new-player-';
      const links = [...document.querySelectorAll('a.player-tab[href]')].filter(a => a.textContent.trim() === name);
      return (links.find(a => a.getAttribute('href').startsWith(prefix)) || links[0])?.getAttribute('href');
    };
    const comparison = document.getElementById('player-comparison');
    const table = comparison?.querySelector('.comparison-table');
    if (table) {
      const names = [...table.querySelectorAll('thead .matrix-player')].map(b => b.textContent.trim());
      const metrics = new Map();
      table.querySelectorAll('tbody tr').forEach(tr => {
        const label = tr.querySelector('.matrix-metric')?.textContent.trim(); if (!label) return;
        metrics.set(label, names.map((name, i) => { const td = tr.cells[i + 1]; const text = td?.querySelector('.matrix-value')?.textContent.trim() ?? ''; return { name, text, value: num(text), rank: td?.querySelector('.matrix-rank')?.textContent.trim() || '' }; }));
      });
      const scores = (metrics.get('スコア') || []).filter(s => s.value !== null).sort((a, b) => b.value - a.value);
      if (scores.length > 1) {
        const games = new Map((metrics.get('半荘数') || []).map(g => [g.name, g.text]));
        const fold = el('details', 'stats-fold score-fold');fold.append(el('summary', '', '獲得スコアの比較'));
        const exhibit = el('figure', 'exhibit'), head = el('div', 'exhibit-head');
        head.append(el('h3', '', '獲得スコア'), el('span', '', '単位: pt'));
        exhibit.append(head);
        scoreLayout(scores).forEach(s => {
          const row = el('div', 'score-row');
          const name = el('div', 'score-name'), href = playerHref(s.name);
          if (href) { const a = el('a', '', s.name); a.href = href; name.append(a); } else name.append(el('span', '', s.name));
          if (games.get(s.name)) name.append(el('small', '', games.get(s.name) + '半荘'));
          const track = el('div', 'score-track'), bar = el('div', 'score-bar' + (s.value < 0 ? ' neg' : ''));
          track.setAttribute('aria-hidden', 'true'); track.style.setProperty('--zero', s.zero + '%');
          bar.style.left = s.left + '%'; bar.style.width = s.width + '%'; track.append(bar);
          row.append(el('span', 'score-rank', String(s.rank)), name, track, el('span', 'score-value' + (s.value < 0 ? ' neg' : ''), signed(s.value)));
          exhibit.append(row);
        });
        const rule = comparison.querySelector('.comparison-note')?.textContent.match(/率・平均[^。]*。/)?.[0];
        exhibit.append(el('figcaption', 'exhibit-note', '出所: 雀魂 大会戦牌譜。' + (rule || '')));
        fold.append(exhibit); comparison.after(fold);
      }
      const body = comparison.querySelector('.comparison-content');
      if (body) {
        const paint = () => body.querySelectorAll('[data-metric="スコア"] .matrix-value').forEach(v => v.classList.toggle('neg-value', (num(v.textContent) ?? 0) < 0));
        paint(); new MutationObserver(paint).observe(body, { childList: true });
      }
    }
    const overview = document.querySelector('.personal-overview');
    if (overview) {
      const panel = overview.closest('.tab-panel');
      const name = scope.includes(' / ') ? scope.split(' / ').pop() : document.title.split(' | ')[0];
      const ranks = new Map();
      panel.querySelectorAll('table').forEach(t => {
        const heads = [...(t.tHead?.rows[0]?.cells || [])].map(c => c.textContent.trim());
        if (heads[0] !== '項目' || !heads.includes('順位') || !t.tBodies[0]) return;
        [...t.tBodies[0].rows].forEach(r => {
          const label = r.cells[0].textContent.replace(/\s*\?\s*$/, '').trim(), m = r.cells[2]?.textContent.trim().match(/^(\d+)\s*\/\s*(\d+)$/);
          if (!ranks.has(label)) ranks.set(label, { rank: m ? Number(m[1]) : null, total: m ? Number(m[2]) : null, reference: /参考/.test(r.cells[2]?.textContent || '') });
        });
      });
      const lead = el('section', 'report-lead'); lead.setAttribute('aria-label', '集計サマリー');
      const games = overview.querySelector('.personal-stat strong')?.textContent.trim();
      lead.append(kicker([scope.split(' / ')[0], games && games + '半荘', updated && '最終更新 ' + updated]));
      lead.append(el('h2', 'report-title', name));
      overview.before(lead);
      overview.querySelectorAll('.personal-stat').forEach(b => {
        const info = ranks.get(b.querySelector('span')?.textContent.trim()), small = b.querySelector('.personal-rank');
        if (!small || !info?.rank || !info.total || info.total > 16) return;
        small.textContent = info.rank + '位'; small.title = info.total + '人中' + info.rank + '位';
        if (info.rank === 1) small.classList.add('is-top');
        const strip = el('span', 'rank-strip'); strip.setAttribute('aria-hidden', 'true');
        for (let i = 1; i <= info.total; i++) strip.append(el('i', i === info.rank ? 'on' : ''));
        small.append(strip);
      });
    }
  });
})();
