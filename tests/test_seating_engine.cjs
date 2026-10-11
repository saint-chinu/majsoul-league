const assert=require('node:assert/strict');
const fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const E=require('../docs/seating/engine.js');
const ctx={}; vm.createContext(ctx); vm.runInContext(fs.readFileSync(path.join(__dirname,'../docs/seating/vendor/solver-1.0.3.js'),'utf8'),ctx);
assert.equal(E.combos.length,20); assert.equal(E.pairs.length,15);
function check(c){const r=E.solve(c,ctx.solver); assert(!r.error,r.error);assert(E.validate(c,r.plan));const order=E.order(c,r.plan);assert.equal(order.length,60-E.stats(c).total);const next=[...c];order.forEach(i=>next[i]++);assert(E.stats(next).people.every(n=>n===30));return r;}
const blank=check(Array(20).fill(0));assert(blank.exact);assert(blank.plan.every(n=>n===3));assert(blank.final.together.every(n=>n===12));
const early=Array.from({length:20},(_,i)=>i%4);assert(check(early).exact);
const skew=Array(20).fill(0);skew[0]=4;const adjusted=check(skew);assert(!adjusted.exact);assert.equal(adjusted.pairGap,0);
skew[0]=20;check(skew);
const late=Array(20).fill(0);late[0]=30;late[19]=29;const end=check(late);assert.equal(end.plan[19],1);
late[19]=30;check(late);late[0]=31;assert(E.solve(late,ctx.solver).error);
const impossible=Array(20).fill(3);[0,7,9].forEach(i=>impossible[i]--);[11,19].forEach(i=>impossible[i]++);
assert(E.stats(impossible).people.every(n=>n<=30));assert(E.solve(impossible,ctx.solver).error);
assert.throws(()=>E.stats([0]));assert.throws(()=>E.stats(Array(20).fill(-1)));
console.log('Engine: exact balance, biased recovery, pair parity, 30/person, finish, overflow passed');
