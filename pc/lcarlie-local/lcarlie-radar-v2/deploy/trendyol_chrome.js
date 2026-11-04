// Trendyol arama sayfasındaki ürün kartlarını okur (sahibin Chrome'unda, normal ziyaret).
// Kullanım: trendyol.com/sr?q=<arama>&prc=1000-3500&sst=BEST_SELLER açılır, bu kod sayfada çalıştırılır;
// her satır "marka|fiyat|ürün-no|ad" -> python3 -m radar trendyol-ekle <dosya.tsv>
// Doğrulama robotu çıkarsa durun; engeli aşmaya çalışmayın.
(() => {
  const F = /^\d{1,3}(?:\.\d{3})*(?:,\d{1,2})? TL$/;
  const out = [];
  const gor = new Set();
  for (const a of document.querySelectorAll('a[href*="-p-"]')) {
    const u = a.href.split('?')[0];
    if (gor.has(u)) continue;
    const L = a.innerText.split('\n').map((s) => s.trim()).filter(Boolean);
    const fi = L.findIndex((s) => F.test(s));
    const ad = L.find((s) => s.length > 25 && !F.test(s));
    const no = (u.match(/-p-(\d+)/) || [])[1];
    if (fi < 0 || !ad || !no) continue;
    gor.add(u);
    out.push([u.split('/')[3], L[fi], no, ad.slice(0, 70)].join('|'));
    if (out.length >= 24) break;
  }
  return out.join('\n');
})();
