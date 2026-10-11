importScripts('engine.js?v=20261011-cap');
self.onmessage = ({data}) => {
  try { self.postMessage(Seating.solve(data)); }
  catch (_) { self.postMessage({error: '計算中にエラーが発生しました。再計算してください。'}); }
};
