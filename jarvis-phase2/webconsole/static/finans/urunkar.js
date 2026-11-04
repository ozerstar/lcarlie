// L'CARLIÉ ürün maliyet / kâr tablosu (sahip, 02.11.2026): ürün ürün maliyet, satış, karşılama, kâr/zarar;
// "Gider ekle" genel maliyete ya da seçilen ürüne yazılır. Tutarlar KDV hariç (şirket KDV'yi indirir).
import {$, $$, esc, icon, tl, tlBig, qty, pct, monthLabel, dayLabel, api, post, card, filterBar, table, empty, skeleton, widths, today} from './core.js?v=13';

// sahip: "ÜGR 108 bin görünüyor, testlerin maliyeti yok" — testler ile ÜGR ayrı satır, yanında KDV dahil
// testerlar marka tanıtımı: genel maliyet (sahip: "L'CARLIÉ reklamı için harcıyorum, ürün bazlı değil")
const LAYERS = [['production', 'Üretim (kutu, etiket, ambalaj dahil)', '#3478E5'], ['general_tester', 'Tester / numune (marka tanıtımı)', '#E5A13B'],
  ['general_test', 'Laboratuvar testleri (TTS)', '#7A5AF8'], ['general_ugr', 'ÜGR raporları (Regnovis)', '#E87BA4'],
  ['general_reklam', 'Promosyon / reklam materyali', '#0EA5B7'], ['general_diger', 'Diğer genel', '#94A3B8'], ['special', 'Ürüne özel', '#16A36A']];
const kpi = (t, v, ic, col, d) => `<section class="card kpi"><div class="top-row"><span class="t">${esc(t)}</span><span class="chip-ic ${col}">${icon(ic)}</span></div><div class="v">${v}</div><div class="d">${d}</div></section>`;
const sumOf = (rows, key) => rows.reduce((s, x) => s + x[key], 0);
// sahip: "maliyet katmanlarının yanına kutucuklar koy, hepsi seçili olsun, istediğimi çıkarayım, genel toplam ona göre düşsün"
const OFF_KEY = 'urunkar.off';
const readOff = () => {try {return new Set(JSON.parse(sessionStorage.getItem(OFF_KEY) || '[]'));} catch {return new Set();}};
const saveOff = off => {try {sessionStorage.setItem(OFF_KEY, JSON.stringify([...off]));} catch { /* gizli pencere */ }};
/** seçili katmanlarla ürün maliyeti, kâr, karşılama ve başabaş yeniden (kuruşu kuruşuna, sunucunun aynı kuralı) */
function recompute(d, off) {
  const products = d.products.map(x => {
    const general = Object.entries(x.general_by || {}).reduce((s, [kind, v]) => s + (off.has('general_' + kind) ? 0 : v), 0);
    const total = (off.has('production') ? 0 : x.production) + general + (off.has('special') ? 0 : x.special);
    const price = x.sold > 0 ? x.sales_net / x.sold : 0, remaining = Math.max(0, total - x.sales_net);
    return {...x, general, total_cost: total, profit: x.sales_net - total, remaining,
      coverage: total ? Math.round(x.sales_net / total * 1000) / 10 : null,
      unit_cost: x.produced ? Math.round(total / x.produced) : null,
      units_to_breakeven: remaining ? (price > 0 ? Math.ceil(remaining / price) : null) : 0};
  });
  const t = {...d.totals};
  for (const [k] of LAYERS) t[k + '_on'] = !off.has(k);
  t.total_cost = sumOf(products, 'total_cost'); t.profit = sumOf(products, 'profit'); t.remaining = sumOf(products, 'remaining');
  t.coverage = t.total_cost ? Math.round(t.sales_net / t.total_cost * 1000) / 10 : null;
  t.in_profit = products.filter(x => x.total_cost && x.profit >= 0).length;
  return {products, totals: t};
}
// karşılama göstergesi: durum rengi + yazı (renk tek başına anlam taşımaz)
const meter = c => (c == null ? '<span class="muted">—</span>'
  : `<span class="meter"><span class="track"><i data-w="${Math.min(100, c)}" data-bg="${c >= 100 ? '#16A36A' : c >= 50 ? '#E5A13B' : '#DC5555'}"></i></span><b>%${c.toLocaleString('tr-TR')}</b></span>`);

export async function urunKar(host, c, live) {
  host.innerHTML = `<div class="card">${skeleton(5, true)}</div>`;
  let alloc = 'esit';
  try {alloc = sessionStorage.getItem('urunkar.alloc') || 'esit';} catch { /* gizli pencere */ }
  const d = await api('/api/money/product-profit', {alloc});
  if (!live()) return;
  const off = readOff(), {products, totals: t} = recompute(d, off), cov = t.coverage ?? 0;
  host.innerHTML = `
    <div class="grid g4">
      ${kpi('Toplam maliyet', tlBig(t.total_cost), 'package', 'red', off.size ? `${off.size} katman hesaba katılmıyor` : `${t.products_with_cost} ürün · bütün maliyet katmanları`)}
      ${kpi('Toplam satış', tlBig(t.sales_net), 'shopping-cart', 'green', `KDV hariç · KDV dahil ${tl(t.sales_gross)}`)}
      <section class="card kpi"><div class="top-row"><span class="t">Maliyetin karşılanan kısmı</span><span class="chip-ic blue">${icon('chart-pie')}</span></div>
        <div class="v">%${cov.toLocaleString('tr-TR')}</div>
        <div class="bars"><div class="b-row"><div class="track"><i data-w="${Math.min(100, cov)}" data-bg="${cov >= 100 ? '#16A36A' : '#E5A13B'}"></i></div></div></div>
        <div class="d">${cov >= 100 ? 'Maliyet karşılandı' : `Başabaşa kalan ${tl(t.remaining)}`}</div></section>
      ${kpi(t.profit >= 0 ? 'Kâr' : 'Henüz karşılanmayan', tlBig(t.profit, true), t.profit >= 0 ? 'trending-up' : 'trending-down', t.profit >= 0 ? 'green' : 'red',
    `${t.in_profit} / ${t.products_with_cost} ürün maliyetini çıkardı`)}
    </div>
    <div class="grid g21">${card({id: 'ukLayers', title: 'Maliyet katmanları', sub: 'Tutarlar KDV hariç; KDV dahil yanında'})}
      ${card({id: 'ukAdd', title: 'Gider ekle', sub: 'Genel maliyete (ürünlere dağıtılır) ya da tek ürüne'})}</div>
    ${card({id: 'ukTable', title: 'Ürün ürün maliyet ve kâr', sub: 'KDV hariç · bütün zamanlar · ayrıntı için satıra tıklayın'})}
    <div class="grid g2">${card({id: 'ukGeneral', title: 'Genel maliyet kalemleri', sub: 'Ürünlere dağıtılan'})}${card({id: 'ukSpecial', title: 'Ürüne özel eklenenler'})}</div>
    <div class="alert info">${icon('info')}<div><b>Bu tabloya girmeyenler</b>Reklam, kargo, pazaryeri komisyonu, personel ve ortak giderler burada yok (Şirket Analizi’nde). Ürün maliyetine saymak istediğinizi “Gider ekle” ile ekleyin.</div></div>`;
  widths(host);

  // maliyet katmanları
  const lb = $('#ukLayers .card-b');
  lb.innerHTML = `<div class="bars layers">${LAYERS.map(([k, label, color]) => `<label class="b-row layer${off.has(k) ? ' off' : ''}">
      <span><input type="checkbox" data-layer="${k}"${off.has(k) ? '' : ' checked'}> ${label} <small>${off.has(k) ? 'hesaba katılmıyor' : pct(t[k], t.total_cost)}${t[k + '_gross'] && t[k + '_gross'] !== t[k] ? ` · KDV dahil ${tl(t[k + '_gross'])}` : ''}</small></span><b class="num">${tl(t[k])}</b>
      <div class="track"><i data-w="${t.total_cost && !off.has(k) ? (t[k] / t.total_cost * 100).toFixed(1) : 0}" data-bg="${color}"></i></div></label>`).join('')}</div>
    <div class="total-line"><span>Toplam maliyet${off.size ? ` <small class="muted">(${off.size} katman çıkarıldı)</small>` : ''}</span><span class="num">${tl(t.total_cost)}</span></div>
    <p class="foot-note">Üretilen ${qty(t.produced)} adet · satılan ${qty(t.sold)} adet · tester ${qty(t.tester_qty)} adet (marka tanıtımı; genel maliyete yazıldı) · genel maliyet dağıtımı: <b>${esc(d.allocations[d.allocation])}</b></p>`;
  widths(lb);
  $$('[data-layer]', lb).forEach(box => box.addEventListener('change', () => {
    if (box.checked) off.delete(box.dataset.layer); else off.add(box.dataset.layer);
    saveOff(off);
    urunKar(host, c, live);  // veri önbellekte: yalnız hesap yenilenir
  }));

  // gider ekle
  const ab = $('#ukAdd .card-b');
  ab.innerHTML = `<form class="uk-form" id="ukForm">
    <label>Tarih<input class="ctl" type="date" name="date" value="${today()}" required></label>
    <label>Ne için<input class="ctl" name="description" maxlength="200" placeholder="ör. TTS analiz, kutu baskısı, çekim" required></label>
    <label>Tutar<input class="ctl" name="amount" inputmode="decimal" placeholder="ör. 12.500,00" required></label>
    <label>KDV<select class="ctl" name="vat_rate"><option value="20">%20</option><option value="10">%10</option><option value="1">%1</option><option value="0">Yok</option></select></label>
    <label class="chk"><input type="checkbox" name="vat_included"> Tutar KDV dahil</label>
    <div class="seg sm" role="group" aria-label="Nereye"><button type="button" data-target="genel" class="on">Genel maliyete</button><button type="button" data-target="urun">Ürüne özel</button></div>
    <label id="ukProd" hidden>Ürün<select class="ctl" name="product">${d.product_names.map(p => `<option>${esc(p)}</option>`).join('')}</select></label>
    <button type="submit" class="btn primary">${icon('hand-coins', 'sm')}Ekle</button><p class="foot-note" id="ukMsg"></p></form>`;
  let target = 'genel';
  $$('[data-target]', ab).forEach(b => b.addEventListener('click', () => {
    target = b.dataset.target;
    $$('[data-target]', ab).forEach(x => x.classList.toggle('on', x === b));
    $('#ukProd').hidden = target !== 'urun';
  }));
  $('#ukForm').addEventListener('submit', async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target)), btn = $('button[type=submit]', e.target);
    btn.disabled = true; $('#ukMsg').textContent = 'Kaydediliyor…';
    try {
      const r = await post('/api/money/product-cost', {...f, vat_included: Boolean(f.vat_included), target, product: target === 'urun' ? f.product : ''});
      $('#ukMsg').textContent = `Eklendi: ${tl(r.net_cents)} (KDV hariç).`;
      await urunKar(host, c, live);
    } catch (x) {$('#ukMsg').textContent = x.message; btn.disabled = false;}
  });

  // ürün tablosu: kendi süzgeci
  const tb = $('#ukTable .card-b'), tf = document.createElement('div'), tt = document.createElement('div');
  tb.append(tf, tt);
  const draw = st => {
    if (st.alloc !== d.allocation) {
      try {sessionStorage.setItem('urunkar.alloc', st.alloc);} catch { /* gizli pencere */ }
      urunKar(host, c, live);
      return;
    }
    const q = (st.q || '').toLocaleLowerCase('tr-TR');
    const rows = products.filter(x => (!q || x.product.toLocaleLowerCase('tr-TR').includes(q))
      && (st.state === 'all' || (st.state === 'profit' ? x.profit >= 0 && x.total_cost : x.profit < 0)));
    // ana tablo yedi sütun: ne kadar sattık, neye mal oldu, ne kadarını karşıladık, kâr mı zarar mı;
    // maliyet katmanları satıra tıklayınca açılır (sahip: "veriler karışmış, anlaşılamıyor")
    table(tt, {rows, sortKey: st.sort, limit: 60, cols: [
      {key: 'product', label: 'Ürün', fmt: x => `<b>${esc(x.product)}</b>`},
      {key: 'sold', label: 'Satılan / üretilen', right: true, sort: x => x.sold,
        fmt: x => `<span class="ratio"><span>${qty(x.sold)} <span class="muted">/ ${qty(x.produced)}</span></span><span class="track"><i data-w="${x.produced ? Math.min(100, x.sold / x.produced * 100).toFixed(1) : 0}"></i></span></span>`,
        total: rs => `${qty(sumOf(rs, 'sold'))} / ${qty(sumOf(rs, 'produced'))}`},
      {key: 'total_cost', label: 'Toplam maliyet', right: true, money: true, total: 'sum'},
      {key: 'sales_net', label: 'Satış', right: true, money: true, total: 'sum'},
      {key: 'coverage', label: 'Karşılama', right: true, sort: x => x.coverage ?? -1, fmt: x => meter(x.coverage),
        total: rs => {const cost = sumOf(rs, 'total_cost'); return meter(cost ? Math.round(sumOf(rs, 'sales_net') / cost * 1000) / 10 : null);}},
      {key: 'profit', label: 'Kâr / zarar', right: true, fmt: x => `<b class="${x.profit < 0 ? 'neg' : 'pos'}">${tl(x.profit, true)}</b>`, total: rs => tl(sumOf(rs, 'profit'), true)},
      {key: 'remaining', label: 'Başabaşa', right: true, sort: x => (x.remaining ? x.units_to_breakeven ?? 1e9 : -1),
        fmt: x => (!x.remaining ? '<span class="ok-mark">✓ karşılandı</span>' : x.units_to_breakeven ? `≈ ${qty(x.units_to_breakeven)} adet` : '<span class="muted">satış yok</span>')}],
    detail: x => `<dl class="dl">
        ${[['Üretim', tl(x.production)], ['Genel pay (tester + test + ÜGR)', tl(x.general)], ['Ürüne özel', tl(x.special)],
    ['Birim tam maliyet', x.unit_cost ? tl(x.unit_cost) : '—'], ['Birim üretim maliyeti', x.unit_production ? tl(x.unit_production) : '—'],
    ['Ortalama satış fiyatı', x.avg_price ? tl(x.avg_price) : '—'], ['Satış (KDV dahil)', tl(x.sales_gross)],
    ['Stok (üretilen − satılan)', `${qty(x.stock)} adet`], ['Başabaşa kalan', tl(x.remaining)],
    ['İlk üretim', x.first_made ? monthLabel(x.first_made, true) : 'üretim faturası yok']].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`});
  };
  draw(filterBar(tf, [{key: 'q', type: 'text', label: 'Ürün ara'},
    {key: 'state', type: 'seg', label: 'Durum', options: [['all', 'Hepsi'], ['profit', 'Kârda'], ['loss', 'Zararda']], value: 'all'},
    {key: 'sort', type: 'select', label: 'Sırala', options: [['sales_net', 'Satışa göre'], ['profit', 'Kâr / zarara göre'], ['coverage', 'Karşılamaya göre'], ['total_cost', 'Maliyete göre'], ['stock', 'Stoğa göre']], value: 'sales_net'},
    {key: 'alloc', type: 'select', label: 'Genel maliyet dağıtımı', options: Object.entries(d.allocations), value: d.allocation}], draw));

  // genel kalemler ve elle eklenenler (elle eklenen silinebilir)
  const gb = $('#ukGeneral .card-b');
  gb.innerHTML = d.general_items.length ? `<ul class="rows">${d.general_items.map(g => `<li><span class="rt"><b>${esc(g.description)}</b>
      <small>${esc(d.general_kinds[g.kind] || '')} · ${esc(g.source === 'fatura' ? `Fatura · ${g.party}` : g.source === 'elle' ? 'Elle eklendi' : 'Tester')}${g.month ? ' · ' + monthLabel(g.month, true) : ''}</small></span>
      <span class="ra num">${tl(g.net)}<small>KDV dahil ${tl(g.gross)}</small></span>${g.id ? `<button type="button" class="icon-btn" data-del="${g.id}" aria-label="Sil">${icon('x', 'sm')}</button>` : ''}</li>`).join('')}</ul>
      <div class="total-line"><span>Genel maliyet</span><span class="num">${tl(t.general)}</span></div>`
    : empty('Genel maliyet kalemi yok', 'TTS analizi ve ÜGR faturaları gelince burada görünür.');
  const sb = $('#ukSpecial .card-b'), special = d.extras.filter(e => e.target === 'urun');
  sb.innerHTML = special.length ? `<ul class="rows">${special.map(e => `<li><span class="rt"><b>${esc(e.product)} · ${esc(e.description)}</b><small>${dayLabel(e.spent_on)}</small></span>
      <span class="ra num">${tl(e.net_cents)}<small>KDV ${tl(e.vat_cents)}</small></span><button type="button" class="icon-btn" data-del="${e.cost_id}" aria-label="Sil">${icon('x', 'sm')}</button></li>`).join('')}</ul>`
    : empty('Ürüne özel gider yok', '“Gider ekle”de “Ürüne özel” seçin.');
  $$('[data-del]', host).forEach(b => b.addEventListener('click', async () => {
    b.disabled = true;
    try {await post('/api/money/product-cost-delete', {id: b.dataset.del}); await urunKar(host, c, live);} catch (x) {b.disabled = false; b.title = x.message;}
  }));
}
