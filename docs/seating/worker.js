importScripts('vendor/solver-1.0.3.js', 'engine.js?v=20261011-advisory');
self.onmessage = ({data}) => {
  try { self.postMessage(Seating.solve(data, solver)); }
  catch (_) { self.postMessage({error: '計算中にエラーが発生しました。再計算してください。'}); }
};
