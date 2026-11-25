/* Tema seçimi (25.11.2026). <head> içinde ERTELENMEDEN yüklenir ki sayfa
   önce açık sonra koyu yanıp sönmesin. Tercih yalnız bu tarayıcıda tutulur;
   tarayıcı depolamaya izin vermezse açık tema kalır. */
(function () {
  try {
    if (localStorage.getItem('lcarlie.tema') === 'koyu') document.documentElement.setAttribute('data-theme', 'dark');
  } catch (_) { /* depolama kapalı: açık tema */ }
})();
