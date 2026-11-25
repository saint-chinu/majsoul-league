const assert = require('node:assert/strict');
const {summarize,filterEvents}=require('../docs/deal-in-review.js');
const categories=[{key:'positive',points:7},{key:'negative',points:-3},{key:'other',points:0}];
const events=[
  {id:'ron:1',categories:['positive','negative'],score:4,start_time:1,round_no:1},
  {id:'ron:2',categories:['negative'],score:-3,start_time:1,round_no:1},
  {id:'other',categories:['other'],score:0,start_time:2,round_no:2},
];
const s=summarize(events,categories);
assert.equal(s.count,3);
assert.equal(s.total,1);
assert.equal(s.negative,-6);
assert.equal(s.positive,7);
assert.equal(s.mean,1/3);
assert.equal(s.causes[0].key,'negative');
assert.equal(s.causes[0].count,2);
assert.equal(filterEvents(events,categories,'','negative','penalty').length,2);
assert.equal(filterEvents(events,categories,'positive','all','recent')[0].id,'ron:1');
assert.equal(filterEvents(events,categories,'negative','positive','recent').length,1);
assert.equal(summarize([],categories).mean,null);
console.log('PASS: overlapping conditions, double-ron entries, denominator, positive net with deductions, filtering');
