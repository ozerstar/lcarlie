/* Tasarım 2026 — tema düğmesi (25.11.2026). Hiçbir veri yazmaz. */
(function () {
  'use strict';
  var dugmeler = document.querySelectorAll('[data-tema-dugme]');
  if (!dugmeler.length) return;
  var kok = document.documentElement;
  function koyuMu() { return kok.getAttribute('data-theme') === 'dark'; }
  function yansit() {
    dugmeler.forEach(function (d) {
      var koyu = koyuMu();
      d.setAttribute('aria-pressed', koyu ? 'true' : 'false');
      d.setAttribute('aria-label', koyu ? 'Açık temaya geç' : 'Koyu temaya geç');
      d.title = koyu ? 'Açık tema' : 'Koyu tema';
      d.textContent = koyu ? '☀' : '☾';
    });
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', koyuMu() ? '#121110' : '#f5f2ec');
  }
  dugmeler.forEach(function (d) {
    d.addEventListener('click', function () {
      var koyu = !koyuMu();
      if (koyu) kok.setAttribute('data-theme', 'dark'); else kok.removeAttribute('data-theme');
      try { localStorage.setItem('lcarlie.tema', koyu ? 'koyu' : 'acik'); } catch (_) { /* yalnız bu oturum */ }
      yansit();
    });
  });
  yansit();
})();
