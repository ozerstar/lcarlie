/* Sales and advertising decision panel. Reads existing APIs; never attributes an order to an ad. */
(() => {
  'use strict';
  const salesView = document.getElementById('viewSatislar');
  const adsView = document.getElementById('viewReklam');
  if (!salesView || !adsView) return;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function formatNumber(value) { return Number(value).toLocaleString('tr-TR'); }
  function makeCard(value, label, description) {
    const card = element('div', 'insight-card');
    card.append(element('strong', '', value), element('span', '', label), element('p', '', description));
    return card;
  }
  function createPanel(view, title, subtitle) {
    const panel = element('section', 'insight-block');
    panel.setAttribute('aria-label', title);
    const heading = element('div', 'insight-heading');
    const copy = element('div');
    copy.append(element('h2', '', title), element('p', '', subtitle));
    heading.append(copy, element('span', 'insight-source', 'Canlı kayıtlardan'));
    const grid = element('div', 'insight-grid');
    grid.append(makeCard('—', 'Sepete ekleme', 'GA4 olayı Jarvis verisine henüz bağlanmadı.'),
      makeCard('—', 'Reklam bağlantı tıklaması', 'Reklam verisi yükleniyor.'),
      makeCard('—', 'Doğrulanmış sipariş', 'Satış verisi yükleniyor.'));
    const next = element('div', 'insight-next', 'Kaynaklar yükleniyor…');
    const go = element('button', 'insight-link', view === salesView ? 'Reklam analizini aç ↗' : 'Satış kayıtlarını aç ↗');
    go.type = 'button';
    go.addEventListener('click', () => {
      if (typeof window.setView === 'function') window.setView(view === salesView ? 'reklam' : 'satislar');
    });
    panel.append(heading, grid, next, go);
    const anchor = view.querySelector(':scope > .iv-flow') || view.querySelector(':scope > .iv-hero');
    if (anchor) anchor.after(panel); else view.prepend(panel);
    return { panel, grid, next };
  }
  const sales = createPanel(salesView, 'Satış yolu ve reklam etkisi',
    'Sepetten siparişe ilerlemeyi, reklam ilgisini ve gerçek satış kaydını aynı yerde izle.');
  const ads = createPanel(adsView, 'Reklamdan satışa görünürlük',
    'Reklamın yarattığı ilgiyi gör; satışa dönüşümün ölçüm durumunu açıkça takip et.');
  let loadedAt = 0;
  let pending = null;

  async function get(path) {
    const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }
  async function refresh() {
    if (pending) return pending;
    if (Date.now() - loadedAt < 60000) return;
    pending = Promise.allSettled([get('/api/satislar'), get('/api/kreatif')]).then(([salesResult, adsResult]) => {
      loadedAt = Date.now();
      const orders = salesResult.status === 'fulfilled' && Array.isArray(salesResult.value.siparisler)
        ? salesResult.value.siparisler : null;
      const creatives = adsResult.status === 'fulfilled' && Array.isArray(adsResult.value.rows)
        ? adsResult.value.rows : null;
      const confirmed = orders ? orders.filter(row => row.ciro_sinifi === 'DOGRULANMIS').length : null;
      const clicks = creatives ? creatives.reduce((total, row) => total + (Number(row.link_tiklama) || 0), 0) : null;
      const measured = creatives ? creatives.filter(row => row.yeterli_ornek && Number(row.gosterim) >= 1000) : [];
      const leaders = measured.sort((a, b) => (Number(b.link_ctr) || 0) - (Number(a.link_ctr) || 0)).slice(0, 3);
      const report = leaders.length
        ? 'Ölçülebilir kreatiflerde bağlantı tıklama oranı en yüksek çalışmalar: ' + leaders.map(row =>
            `${String(row.ad_adi || row.baslik || 'Adsız reklam').slice(0, 70)} (%${Number(row.link_ctr || 0).toLocaleString('tr-TR', {maximumFractionDigits: 2})})`).join(' · ') + '. '
        : 'Kıyaslanabilecek reklam örneği henüz yok. ';
      for (const target of [sales, ads]) {
        target.grid.replaceChildren(
          makeCard('—', 'Sepete ekleme', 'Sitede add_to_cart olayı bulunuyor; GA4 sayısı Jarvis’e aktarılmadığı için burada sayı gösterilemiyor.'),
          makeCard(clicks === null ? '—' : formatNumber(clicks), 'Reklam bağlantı tıklaması',
            clicks === null ? 'Reklam verisi alınamadı.' : 'Kreatif performans kayıtlarındaki bağlantı tıklamalarının toplamı; sipariş atfı değildir.'),
          makeCard(confirmed === null ? '—' : formatNumber(confirmed), 'Doğrulanmış sipariş',
            confirmed === null ? 'Satış verisi alınamadı.' : 'Satış ekranına gelen son 300 sipariş kaydındaki doğrulanmış satışlar; reklam kaynaklı sayı değildir.')
        );
        target.next.replaceChildren();
        const bold = element('b', '', 'Ölçüm raporu: ');
        const detail = document.createTextNode(report +
          'Sepete ekleme sayısını göstermek için GA4 → Jarvis veri akışı kurulmalı. ' +
          'Sepet görüntüleme, ödeme başlangıcı ve satın alma olayları da doğrulanmalı. ' +
          'Bu bağlantı tamamlanmadan reklamın satış dönüşümü veya getirisi hesaplanamaz.');
        target.next.append(bold, detail);
      }
    }).finally(() => { pending = null; });
    return pending;
  }
  for (const view of [salesView, adsView]) {
    new MutationObserver(() => { if (!view.hidden) refresh(); })
      .observe(view, { attributes: true, attributeFilter: ['hidden'] });
  }
  if (!salesView.hidden || !adsView.hidden) refresh();
})();
