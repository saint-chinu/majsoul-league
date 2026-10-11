(function (root) {
  'use strict';
  const combos = [], pairs = [];
  for (let a = 0; a < 6; a++) for (let b = a + 1; b < 6; b++) {
    pairs.push([a, b]);
    for (let c = b + 1; c < 6; c++) combos.push([a, b, c]);
  }
  function stats(counts) {
    if (counts.length !== 20 || counts.some(n => !Number.isInteger(n) || n < 0)) throw Error('Invalid counts');
    const people = Array(6).fill(0), together = Array(15).fill(0);
    combos.forEach((c, i) => {
      c.forEach(p => { people[p] += counts[i]; });
      pairs.forEach((pair, j) => { if (pair.every(p => c.includes(p))) together[j] += counts[i]; });
    });
    return {people, together, total: counts.reduce((a, b) => a + b, 0)};
  }
  function validate(counts, plan) {
    return plan.length === 20 && plan.every(n => Number.isInteger(n) && n >= 0) &&
      counts.every((n,i)=>n+plan[i]<=3) && stats(counts.map((n, i) => n + plan[i])).people.every(n => n === 30);
  }
  function solve(counts, solver) {
    const s = stats(counts), remaining = s.people.map(n => 30 - n), games = 60 - s.total;
    if (counts.some(n=>n>3)) return {error:'同じ3人組は3回が上限です。超過した仮登録を確認してください。'};
    if (remaining.some(n => n < 0)) return {error: '30半荘を超えている参加者がいます。対象牌譜を確認してください。'};
    if (remaining.some(n => n > games)) return {error: '現在の消化数から全員30半荘に揃えることはできません。対局数の条件を見直す必要があります。'};
    if (counts.every(n => n <= 3)) return result(counts, counts.map(n => 3 - n), true);
  }
  function result(counts, plan, exact) {
    const final = stats(counts.map((n,i) => n+plan[i]));
    return {plan, exact, final, pairGap: Math.max(...final.together.map(n => Math.abs(n-12)))};
  }
  function order(counts, plan) {
    const left = [...plan], current = [...counts], sequence = [];
    while (left.some(n => n > 0)) {
      const s = stats(current);
      const ranked = left.map((n,i) => ({i,n, score: combos[i].reduce((v,p) => v+s.people[p],0)*5 +
        pairs.reduce((v,p,j) => v+(p.every(x => combos[i].includes(x)) ? s.together[j] : 0),0)*2 + current[i]}))
        .filter(x => x.n > 0).sort((a,b) => a.score-b.score || a.i-b.i);
      const i = ranked[0].i; sequence.push(i); left[i]--; current[i]++;
    }
    return sequence;
  }
  root.Seating = {combos, pairs, stats, validate, solve, order};
  if (typeof module !== 'undefined') module.exports = root.Seating;
})(typeof self !== 'undefined' ? self : globalThis);
