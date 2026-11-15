const assert = require('node:assert/strict');
const {num, scoreLayout} = require('../docs/league-report.js');
assert.equal(num('+1,189.2'), 1189.2);
assert.equal(num('-23.5'), -23.5);
assert.equal(num('32.10%'), 32.1);
for (const missing of ['', null, undefined, '-', '参考', '1位']) assert.equal(num(missing), null);
const layout = values => scoreLayout(values.map(value => ({value})));
const mixed = layout([100, 0, -100]);
assert.deepEqual(mixed.map(s => s.zero), [50, 50, 50]);
assert.deepEqual(mixed.map(s => [s.left, s.width]), [[50, 50], [50, 0], [0, 50]]);
assert.deepEqual(layout([10, 10, 0]).map(s => s.rank), [1, 1, 3]);
for (const values of [[0, 0], [10, 20], [-10, -20], [-1000, 3], []]) {
  for (const s of layout(values)) {
    assert.ok(Number.isFinite(s.zero) && Number.isFinite(s.width));
    assert.ok(s.left >= 0 && s.width >= 0 && s.left + s.width <= 100.000001);
  }
}
console.log('Report score layout and numeric parsing: passed');
