// Finans Merkezi — sayfalar. Her kartın kendi süzgeci var (sahip: "her birimde, her analizde, her
// grafikte ayrı"); fatura kaynaklı tutarlar KDV hariç ve dahil yan yana (sahip: "KDV dahil de göreyim").
import {$, $$, api, esc, icon, tl, tlBig, qty, pct, monthLabel, dayLabel, dayShort, fold, matcher, sum, groupBy,
  card, filterBar, table, moneyCols, chart, hbars, empty, skeleton, widths, COLORS} from './core.js?v=13';
import {urunKar} from './urunkar.js?v=13';

// ------------------------------------------------------------ yardımcılar
const ENTITY = {lcarlie: "L'CARLIÉ", lemos: 'Lemos (muayenehane)', moy: 'MOY', ortak: 'Ortak gider', belirsiz: 'Belirsiz', grup: 'Grup içi'};
// sahip, 03.11.2026: "şahsımı, MOY'u, Lemos'u ve L'CARLIÉ'yi 4 farklı kurum gibi yap" — her sayfa yalnız seçili kurumu gösterir
export const KURUM = {sahsi: 'Şahsım', moy: 'MOY', lemos: 'Lemos', lcarlie: "L'CARLIÉ"};
const AGREEMENT_SCOPES = {sahsi: ['kisisel', 'aile', ''], moy: ['moy'], lemos: ['lemos'], lcarlie: ['lcarlie']};
/** fatura satırının sahibi: MOY defteri MOY'dur; Lemos defterinde iş (L'CARLIÉ / Lemos / ortak) */
// MOY → Lemos faturası (27.03.2026, 36.000 TL) grup içidir: MOY faturalarında konu etiketi yok, karşı taraftan anlaşılır
const entityOf = r => (r.z === 'grup' || (r.k === 'moy' && fold(r.f).includes('lemos')) || (r.k === 'lemos' && fold(r.f).startsWith('moy dan')) ? 'grup'
  : r.k === 'moy' ? 'moy' : r.z);
const SRC_INV = 'Kaynak: faturalar + Wix + Trendyol siparişleri';
const SRC_BANK = 'Kaynak: banka ve kart hareketleri (ödenen tutar)';

function chg(cur, prev, cost = false, short = false) {
  // önceki dönemin verisi eksikse (dökümler 2025 sonunda başlıyor) yüzde yanıltır: söylenir, hesaplanmaz
  if (!prev || (Math.abs(cur) > 0 && Math.abs(prev) < Math.abs(cur) * 0.1)) return '<span class="chg flat">Önceki dönemde yeterli veri yok</span>';
  const d = (cur - prev) / Math.abs(prev) * 100;
  const dir = Math.abs(d) < 0.05 ? 'flat' : d > 0 ? 'up' : 'down';
  return `<span class="chg ${cost ? 'cost ' : ''}${dir}">${icon(d > 0 ? 'arrow-up-right' : 'arrow-down-right', 'sm')}%${Math.abs(d).toLocaleString('tr-TR', {maximumFractionDigits: 1})}${short ? '' : ' <span class="muted">önceki döneme göre</span>'}</span>`;
}
/** dönemdeki bütün fatura satırları; gün/hafta görünümünde fatura ayı gösterilir (satırlar ay bazında) */
function allInvoiceRows(a, c) {
  const s = c.bounds.start.slice(0, 7), e = c.bounds.end.slice(0, 7);
  return (a.rows || []).filter(r => r.m >= s && r.m <= e);
}
/** seçili kurumun fatura satırları. L'CARLIÉ ile Lemos'un ortak giderleri satış payıyla bölünür: her kurum yalnız kendi payını görür */
function invoiceRows(a, c) {
  const k = c.state.scope, all = allInvoiceRows(a, c);
  if (k === 'moy') return all.filter(r => r.k === 'moy');
  if (k !== 'lemos' && k !== 'lcarlie') return [];
  const share = companyResult(all, 'net').list.find(x => x.k === k)?.share ?? 0.5;
  return all.filter(r => r.k === 'lemos' && r.z === k).concat(all.filter(r => r.k === 'lemos' && r.z === 'ortak' && entityOf(r) !== 'grup')
    .map(r => ({...r, v: Math.round(r.v * share), g: Math.round(r.g * share), n: `${r.n || r.f} · ortak gider payı ${pct(share, 1)}`})));
}
const sells = c => c.state.scope === 'lemos' || c.state.scope === 'lcarlie';
/** hareketin parasının çıktığı hesabın sahibi (kurum başka kurumun hesabından ödendiyse o) */
const src = (ov, x) => ov.book_labels[x.paid_from || x.book] || '';
const bookOpts = ov => [...new Set(ov.accounts.map(a => a.book))].map(k => [k, ov.book_labels[k]]);
function periodNote(c) {
  const v = c.state.view;
  if (v === 'day' || v === 'week') return `Fatura verisi ay bazında tutulur: ${monthLabel(c.bounds.start.slice(0, 7), true)} gösteriliyor.`;
  return '';
}
const vatVal = (vat, r) => (vat === 'gross' ? r.g : r.v);
const vatCell = (vat, net, gross) => vat === 'net' ? tl(net) : vat === 'gross' ? tl(gross) : `${tl(net)}<span class="sub">KDV dahil ${tl(gross)}</span>`;
const noCompany = c => c.state.scope === 'sahsi'
  ? empty('Şahsım’da fatura yok', 'Faturalar kurumlara ait: MOY, Lemos ve L’CARLIÉ. Soldan bir kurum seçin.', 'building-2') : '';
const noSales = () => empty('Bu kurumun kanal satışı yok', 'Satış ve ürün analizi Lemos ile L’CARLIÉ içindir. Soldan birini seçin.', 'shopping-cart');
const months = rows => [...new Set(rows.map(r => r.m))].sort();
const monthOpts = rows => [['', 'Bütün aylar'], ...months(rows).map(m => [m, monthLabel(m, true)])];
const kindOf = m => (m.internal || ['ic_transfer', 'aracilik', 'haric'].includes(m.category) ? 'ic' : m.direction);
const counted = ov => ov.movements.filter(m => kindOf(m) !== 'ic');
function agreementsFor(list, scope) {
  const allow = AGREEMENT_SCOPES[scope];
  return (list || []).filter(a => !allow || allow.includes(a.scope || ''));
}
function csv(name, header, rows) {
  const cell = v => {const s = String(v ?? ''); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;};
  const text = '﻿' + [header, ...rows].map(r => r.map(cell).join(';')).join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], {type: 'text/csv;charset=utf-8'}));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
const money = c => (Number(c || 0) / 100).toFixed(2).replace('.', ',');  // Excel TR: virgüllü ondalık
const loading = (host, n = 4) => {host.innerHTML = `<div class="grid g4">${('<div class="card">' + skeleton(3) + '</div>').repeat(4)}</div><div class="card">${skeleton(n, true)}</div>`;};

// ----------------------------------------------------------- GENEL BAKIŞ
async function genel(host, c, live) {
  loading(host);
  const [ov, a, led] = await Promise.all([c.overview(), c.state.scope === 'sahsi' ? null : c.analysis(), c.ledger()]);
  if (!live()) return;
  const ags = agreementsFor(led.agreements, c.state.scope);
  const pending = sum(ags, x => x.owed_closed_months + (x.this_month?.open || 0));
  const late = sum(ags, 'owed_closed_months');
  const nets = ov.net, prevNet = ov.prev_in_total - ov.prev_out_total;
  const flow = ov.owner_flow || {};
  // sahip 02.11.2026 sordu: uyarı nedenini söylesin — eksik döküm mü, Jarvis'te olmayan banka mı, ödeyen hesap mı
  const gapSum = k => (flow[k] || []).reduce((s, g) => s + g.total, 0);
  const missing = gapSum('no_statement') + gapSum('other_bank') + gapSum('unmatched');
  const gap = c.state.scope === 'tumu' && (missing > 100 || (flow.no_company_side || []).length);
  const gapLines = [
    ...(flow.no_statement || []).map(g => `<li><b>${tl(g.total)}</b> ${esc(g.bank)} hesabınıza gitmiş (${g.count} transfer, ${dayShort(g.first)} – ${dayShort(g.last)}). ${esc(g.bank)} dökümü Jarvis’te <b>${dayLabel(g.statement_from)}</b>’dan başlıyor — <b>bu dönemin dökümünü yükleyin.</b></li>`),
    ...(flow.other_bank || []).map(g => `<li><b>${tl(g.total)}</b> ${esc(g.bank)} hesabınıza gitmiş (${g.count} transfer) — <b>bu hesap Jarvis’te yok;</b> dökümünü yükleyin.</li>`),
    ...(flow.unmatched || []).map(g => `<li><b>${tl(g.total)}</b> ${esc(g.bank || 'bilinmeyen bankaya')} gitmiş (${g.count} transfer) ama dökümde karşılığı bulunamadı.</li>`),
    ...(flow.no_company_side || []).map(g => `<li><b>${tl(g.total)}</b> ${esc(g.party)}’dan size gelmiş (${g.count} ödeme) — ödeyen şirket hesabı Jarvis’te yok.</li>`)];
  host.innerHTML = `
    ${c.state.scope === 'lcarlie' ? `<div class="alert info">${icon('info')}<div><b>L’CARLIÉ’nin kendi banka hesabı yok.</b> Buradaki banka rakamları, hesap başlığı “L’CARLIÉ” verilmiş ödemelerdir (çoğu şahsi kartından). Satışları <a href="#/satis?${location.hash.split('?')[1]}">Satış Analizi</a>’nde, ürün kârını <a href="#/urunkar?${location.hash.split('?')[1]}">Ürün Kârlılığı</a>’nda görürsün.</div></div>` : ''}
    ${gap ? `<div class="alert warn">${icon('triangle-alert')}<div><b>Şirketle aranızdaki paranın bir kısmı Jarvis’te tek taraflı görünüyor</b>
      Şirketlerden size giden ${tl(flow.company_to_owner)}’nin ${tl(flow.matched)}’si şahsi hesaplarınızda birebir eşleşti${missing ? `; ${tl(missing)} eşleşmedi` : ''}:
      <ul class="gap-list">${gapLines.join('')}</ul>Eksik dökümler yüklenince bu uyarı kendiliğinden kalkar; o zamana kadar o paranın harcanışı toplamlarda yok.</div></div>` : ''}
    <div class="grid g21">
      <section class="card hero"><div><div class="lbl">Dönem net sonucu · ${esc(c.bounds.label)}</div>
        <div class="big ${nets < 0 ? 'neg' : ''}">${tlBig(nets, true)}</div>${chg(nets, prevNet)}</div>
        <span class="badge">${icon('wallet', 'lg')}</span>
        <div class="trio"><div><span>Gelir</span><b class="num pos">${tl(ov.in_total)}</b></div><div><span>Gider</span><b class="num neg">${tl(ov.out_total)}</b></div><div><span>Net</span><b class="num">${tl(nets, true)}</b></div></div>
        <p class="foot-note">${SRC_BANK}. ${ov.internal_count ? `${ov.internal_count} iç aktarım (${tl(ov.internal_total)}) iki kez sayılmasın diye ayrı tutuldu — <a href="#/islemler?${location.hash.split('?')[1]}">göster</a>.` : ''}</p></section>
      <div class="grid g2">
        ${c.state.scope === 'lcarlie' && a ? kpi('Satış (KDV hariç)', tlBig(sum(invoiceRows(a, c).filter(r => r.b === 'out' && entityOf(r) !== 'grup'), 'v')), 'shopping-cart', 'green', 'Faturalar + Wix + Trendyol · banka değil')
          : kpi('Toplam tahsilat', tlBig(ov.in_total), 'hand-coins', 'green', chg(ov.in_total, ov.prev_in_total, false, true))}
        ${kpi('Toplam ödeme', tlBig(ov.out_total), 'credit-card', 'red', chg(ov.out_total, ov.prev_out_total, true, true))}
        ${kpi('Bekleyen ödemeler', tlBig(pending), 'clock', 'orange', late ? `<span class="chg cost up">${tl(late)} gecikmiş</span>` : 'Anlaşmalar: bu ay + geçmiş borç')}
        ${kpi('Kullanılan hesaplar', String(ov.accounts.length), 'wallet', 'blue', esc([...new Set(ov.accounts.map(x => x.book_label))].join(' · ') || '—'))}
      </div>
    </div>
    ${card({id: 'cMonthly', title: 'Gelir – gider analizi', sub: `Son 12 ay · ${SRC_BANK}`})}
    <div class="grid g2">${card({id: 'cBetween', title: 'Kurumlar arası para', sub: 'Öteki kurumlarla ve onlar adına giden / gelen · gelir ya da gider sayılmaz'})}${sells(c) ? card({id: 'cChannels', title: 'Satış kanalları', sub: SRC_INV}) : card({id: 'cCost', title: 'En yüksek giderler', sub: 'Kategoriye göre'})}</div>
    ${card({id: 'cRecent', title: 'Son finansal hareketler', sub: SRC_BANK, acts: `<a class="btn" href="#/islemler?${location.hash.split('?')[1]}">${icon('list', 'sm')}Tüm işlemler</a>`})}
    ${sells(c) ? `<div class="grid g2">${card({id: 'cTop', title: 'En çok satan ürünler', sub: SRC_INV})}${card({id: 'cCost', title: 'En yüksek giderler', sub: 'Kategoriye göre'})}</div>` : ''}`;

  // aylık gelir-gider: kendi süzgeci
  const mBody = $('#cMonthly .card-b'), mf = document.createElement('div'), mc = document.createElement('div');
  mBody.append(mf, mc);
  const drawM = st => chart(mc, {labels: ov.monthly.map(m => m.month), type: st.type, tipTitle: m => monthLabel(m, true),
    series: [st.show !== 'out' && {name: 'Gelir', color: COLORS.in, values: ov.monthly.map(m => m.in)},
      st.show !== 'in' && {name: 'Gider', color: COLORS.out, values: ov.monthly.map(m => m.out)}].filter(Boolean)});
  drawM(filterBar(mf, [{key: 'type', type: 'seg', label: 'Grafik', options: [['bar', 'Sütun'], ['line', 'Çizgi']], value: 'bar'},
    {key: 'show', type: 'seg', label: 'Seri', options: [['both', 'Gelir + gider'], ['in', 'Gelir'], ['out', 'Gider']], value: 'both'}], drawM));

  betweenCard($('#cBetween .card-b'), ov);
  if (a && sells(c)) {
    const rows = invoiceRows(a, c).filter(r => r.b === 'out' && entityOf(r) !== 'grup');
    const note = periodNote(c);
    channelCard($('#cChannels .card-b'), rows.filter(r => r.k === 'lemos'), note);
    topProducts($('#cTop .card-b'), rows, note);
  }
  recentCard($('#cRecent .card-b'), ov);
  costCard($('#cCost .card-b'), ov, a ? invoiceRows(a, c).filter(r => r.b === 'in' && entityOf(r) !== 'grup') : null);
}
const kpi = (t, v, ic, col, d) => `<section class="card kpi"><div class="top-row"><span class="t">${esc(t)}</span><span class="chip-ic ${col}">${icon(ic)}</span></div><div class="v">${v}</div><div class="d">${d}</div></section>`;

function betweenCard(body, ov) {
  const g = ov.between || [];
  body.innerHTML = g.length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Kiminle</th><th class="r">Gelen</th><th class="r">Giden</th><th class="r">Hareket</th></tr></thead><tbody>
    ${g.map(x => `<tr><td>${esc(x.label)}</td><td class="r num pos">${x.in ? tl(x.in) : '—'}</td><td class="r num neg">${x.out ? tl(x.out) : '—'}</td><td class="r">${x.count}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td>Toplam</td><td class="r num">${tl(sum(g, 'in'))}</td><td class="r num">${tl(sum(g, 'out'))}</td><td class="r">${sum(g, 'count')}</td></tr></tfoot></table></div>
    <p class="foot-note">“… adına ödeme”: bu kurumun hesabından başka bir kurumun işi ödendi; o gider o kurumda sayılır. Ayrıntısı İşlemler’de “İç aktarım” türünde.</p>`
    : empty('Bu dönemde öteki kurumlarla para hareketi yok.');
}
function channelCard(body, rows, note) {
  const f = document.createElement('div'), out = document.createElement('div');
  body.append(f, out);
  const draw = st => {
    const m = matcher(st.q, st.mode);
    const sel = rows.filter(r => (!st.ent || entityOf(r) === st.ent) && m(`${r.p} ${r.n}`));
    const ch = ['dogrudan', 'wix', 'trendyol'].map(k => ({k, label: {dogrudan: 'Doğrudan', wix: 'Wix (web sitesi)', trendyol: 'Trendyol'}[k],
      v: sum(sel.filter(r => r.c === k), 'v'), g: sum(sel.filter(r => r.c === k), 'g')}));
    out.innerHTML = (note ? `<p class="flt-note">${esc(note)}</p>` : '') + `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Kanal</th>${st.vat !== 'gross' ? '<th class="r">KDV hariç</th>' : ''}${st.vat !== 'net' ? '<th class="r">KDV dahil</th>' : ''}<th class="r">Pay</th></tr></thead><tbody>
      ${ch.map(x => `<tr><td><i class="dot-c" data-bg="${COLORS[x.k]}"></i> ${x.label}</td>${st.vat !== 'gross' ? `<td class="r num">${tl(x.v)}</td>` : ''}${st.vat !== 'net' ? `<td class="r num">${tl(x.g)}</td>` : ''}<td class="r num">${pct(st.vat === 'gross' ? x.g : x.v, sum(ch, st.vat === 'gross' ? 'g' : 'v'))}</td></tr>`).join('')}</tbody>
      <tfoot><tr><td>Toplam satış</td>${st.vat !== 'gross' ? `<td class="r num">${tl(sum(ch, 'v'))}</td>` : ''}${st.vat !== 'net' ? `<td class="r num">${tl(sum(ch, 'g'))}</td>` : ''}<td class="r num">%100</td></tr></tfoot></table></div>
      <p class="foot-note">Faturası olan sipariş faturadan sayılır, olmayan siparişten eklenir; iade, indirim ve kuponlar düşülür. Seçili kurumun satışları (MOY’un kanal satışı yok).</p>`;
    widths(out);
  };
  draw(filterBar(f, [{key: 'q', type: 'text', label: 'Ürün ara'}, {key: 'mode', type: 'mode'}, {key: 'vat', type: 'vat'}], draw));
}
function productAgg(rows) {
  return groupBy(rows.filter(r => r.p), r => r.p, k => ({name: k, q: 0, v: 0, g: 0}), (x, r) => {x.q += r.q; x.v += r.v; x.g += r.g;});
}
function topProducts(body, rows, note) {
  const f = document.createElement('div'), out = document.createElement('div');
  body.append(f, out);
  const draw = st => {
    const m = matcher(st.q, st.mode);
    const items = productAgg(rows.filter(r => (!st.ent || entityOf(r) === st.ent) && m(r.p))).sort((x, y) => vatVal(st.vat, y) - vatVal(st.vat, x));
    if (note) out.innerHTML = `<p class="flt-note">${esc(note)}</p>`; else out.innerHTML = '';
    const t = document.createElement('div'); out.appendChild(t);
    table(t, {rows: items, limit: 5, sortKey: st.vat === 'gross' ? 'g' : 'v', cols: [
      {key: 'name', label: 'Ürün'}, {key: 'q', label: 'Adet', right: true, fmt: r => qty(r.q), total: rs => qty(sum(rs, 'q'))},
      ...moneyCols(st.vat, {labelNet: 'Ciro (KDV hariç)', labelGross: 'Ciro (KDV dahil)'}),
      {key: 'unit', label: 'Birim fiyat', right: true, sort: r => (r.q ? vatVal(st.vat, r) / r.q : 0), fmt: r => (r.q ? tl(Math.round((st.vat === 'gross' ? r.g : r.v) / r.q)) : '—')}]});
  };
  draw(filterBar(f, [{key: 'q', type: 'text', label: 'Ürün ara'}, {key: 'mode', type: 'mode'}, {key: 'vat', type: 'seg', label: 'KDV', options: [['net', 'KDV hariç'], ['gross', 'KDV dahil']], value: 'net'}], draw));
}
function recentCard(body, ov) {
  const f = document.createElement('div'), out = document.createElement('div');
  body.append(f, out);
  const draw = st => {
    const m = matcher(st.q, 'only');
    const list = ov.movements.filter(x => (st.dir === 'all' || kindOf(x) === st.dir) && m(`${x.party} ${x.description || ''} ${ov.categories[x.category] || ''}`)).slice(0, 8);
    out.innerHTML = list.length ? `<ul class="rows">${list.map(x => moveRow(x, ov)).join('')}</ul>` : empty('Bu seçimde hareket yok.');
  };
  draw(filterBar(f, [{key: 'q', type: 'text', label: 'Hareket ara'}, {key: 'dir', type: 'seg', label: 'Tür', options: [['all', 'Hepsi'], ['in', 'Gelir'], ['out', 'Gider'], ['ic', 'İç aktarım']], value: 'all'}], draw));
}
function moveRow(x, ov) {
  const k = kindOf(x);
  const ic = k === 'in' ? ['arrow-down-right', 'green'] : k === 'out' ? ['arrow-up-right', 'red'] : ['arrow-left-right', 'blue'];
  return `<li><span class="ri chip-ic ${ic[1]}">${icon(ic[0])}</span><span class="rt"><b>${esc(x.party)}</b><small>${esc(src(ov, x))} · ${esc(x.internal || ov.categories[x.category] || 'Kategorisiz')} · ${dayShort(x.tx_date)}</small></span>
    <span class="ra num ${k === 'in' ? 'pos' : k === 'out' ? 'neg' : 'muted'}">${k === 'in' ? '+' : k === 'out' ? '−' : ''}${tl(x.amount_cents)}<small>${esc(x.account)}</small></span></li>`;
}
function costCard(body, ov, invRows) {
  const f = document.createElement('div'), out = document.createElement('div');
  body.append(f, out);
  const draw = st => {
    if (st.src === 'bank') {
      const items = ov.by_category.map(x => ({label: x.label, value: x.total, sub: pct(x.total, ov.out_total)}));
      out.innerHTML = hbars(items, {limit: st.all ? 50 : 5}) + `<p class="foot-note">${SRC_BANK}</p>`;
    } else if (!invRows) out.innerHTML = empty('Şahsi görünümde fatura yok.');
    else {
      const g = groupBy(invRows, r => r.t, k => ({label: THEMES[k] || k, v: 0, g: 0}), (x, r) => {x.v += r.v; x.g += r.g;}).sort((x, y) => vatVal(st.vat, y) - vatVal(st.vat, x));
      const tot = sum(g, st.vat === 'gross' ? 'g' : 'v');
      out.innerHTML = hbars(g.map(x => ({label: x.label, value: vatVal(st.vat, x), sub: pct(vatVal(st.vat, x), tot)})), {limit: st.all ? 50 : 5}) + `<p class="foot-note">${SRC_INV} · ${st.vat === 'gross' ? 'KDV dahil' : 'KDV hariç'}</p>`;
    }
    out.insertAdjacentHTML('beforeend', `<div class="more"><button type="button" class="btn ghost">${st.all ? 'İlk 5' : 'Tüm kategoriler'}</button></div>`);
    $('.more button', out).addEventListener('click', () => {st.all = !st.all; draw(st);});
    widths(out);
  };
  draw(filterBar(f, [{key: 'src', type: 'seg', label: 'Kaynak', options: [['bank', 'Banka hareketleri'], ['inv', 'Faturalar']], value: 'bank'},
    {key: 'vat', type: 'seg', label: 'KDV', options: [['net', 'KDV hariç'], ['gross', 'KDV dahil']], value: 'net'}], draw));
}
const THEMES = {lcarlie_urun: "L'CARLIÉ ürünü", takviye_ilac: 'Takviye / ilaç', promosyon_matbaa: 'Promosyon / matbaa / baskı', ambalaj: 'Ambalaj / kutu',
  pazaryeri: 'Pazaryeri', kargo: 'Kargo / kurye', reklam: 'Reklam', etkinlik_ikram: 'Etkinlik / ikram', saglik_hizmeti: 'Sağlık hizmeti',
  grup_ici: 'Grup içi', numune_tester: 'Tester / numune (ücretsiz)', iletisim: 'Telefon / internet', arac: 'Araç / bakım', ofis_demirbas: 'Ofis / demirbaş', yazilim: 'Yazılım', danismanlik: 'Danışmanlık', giyim: 'Giyim', diger: 'Diğer'};

// ------------------------------------------------------------- HESAPLARIM
async function hesaplar(host, c, live) {
  loading(host);
  const ov = await c.overview(); if (!live()) return;
  const inS = sum(ov.accounts, 'in'), outS = sum(ov.accounts, 'out');
  host.innerHTML = `<div class="grid g4">${kpi('Hesap', String(ov.accounts.length), 'wallet', 'blue', 'Dökümü yüklenmiş banka ve kartlar')}
    ${kpi('Dönemde giren', tlBig(inS), 'arrow-down-right', 'green', 'İç aktarımlar hariç')}${kpi('Dönemde çıkan', tlBig(outS), 'arrow-up-right', 'red', 'İç aktarımlar hariç')}
    ${kpi('Hesaplar arası', tlBig(ov.internal_total), 'arrow-left-right', 'orange', `${ov.internal_count} hareket · gelir/gider sayılmadı`)}</div>
    ${card({id: 'cAcc', title: 'Hesaplar', sub: 'Bakiye: dökümlerde her bankanın bakiye satırı yok; bakiye takibi henüz kurulmadı, hareketler tam.'})}`;
  const b = $('#cAcc .card-b'), f = document.createElement('div'), t = document.createElement('div'); b.append(f, t);
  const draw = st => {
    const m = matcher(st.q, 'only');
    table(t, {rows: ov.accounts.filter(x => (!st.book || x.book === st.book) && m(`${x.name} ${x.book_label}`)), sortKey: 'out', limit: 50, cols: [
      {key: 'name', label: 'Hesap', fmt: x => `<b>${esc(x.name)}</b>`}, {key: 'book_label', label: 'Sahibi'},
      {key: 'count', label: 'Hareket', right: true, total: rs => String(sum(rs, 'count'))}, {key: 'last', label: 'Son işlem', fmt: x => dayLabel(x.last)},
      {key: 'in', label: 'Dönemde giren', right: true, money: true, total: 'sum'}, {key: 'out', label: 'Dönemde çıkan', right: true, money: true, total: 'sum'}],
    onRow: x => c.go('islemler', {q: x.name})});
  };
  draw(filterBar(f, [{key: 'q', type: 'text', label: 'Hesap ara'}, {key: 'book', type: 'select', label: 'Sahibi', options: [['', 'Bütün defterler'], ...bookOpts(ov)]}], draw));
}

// --------------------------------------------------------- GELİR / GİDER
function flowPage(direction) {
  return async (host, c, live) => {
    loading(host);
    const ov = await c.overview(); if (!live()) return;
    const list = counted(ov).filter(m => m.direction === direction);
    const total = direction === 'in' ? ov.in_total : ov.out_total, prev = direction === 'in' ? ov.prev_in_total : ov.prev_out_total;
    const cats = direction === 'in' ? ov.in_by_category : ov.by_category;
    const biggest = [...list].sort((x, y) => y.amount_cents - x.amount_cents)[0];
    const word = direction === 'in' ? 'gelir' : 'gider';
    host.innerHTML = `<div class="grid g4">${kpi(`Toplam ${word}`, tl(total), direction === 'in' ? 'trending-up' : 'trending-down', direction === 'in' ? 'green' : 'red', chg(total, prev, direction === 'out'))}
      ${kpi('Hareket', String(list.length), 'list', 'blue', c.bounds.label)}
      ${kpi('En büyük kategori', cats[0] ? esc(cats[0].label) : '—', 'chart-pie', 'orange', cats[0] ? `${tl(cats[0].total)} · ${pct(cats[0].total, total)}` : '')}
      ${kpi('En büyük hareket', biggest ? tl(biggest.amount_cents) : '—', 'receipt', 'blue', biggest ? `${esc(biggest.party)} · ${dayShort(biggest.tx_date)}` : '')}</div>
      <div class="grid g21">${card({id: 'cList', title: `${direction === 'in' ? 'Gelir' : 'Gider'} hareketleri`, sub: SRC_BANK + '; iç aktarımlar hariç'})}
      ${card({id: 'cCats', title: 'Kategoriye göre', sub: c.bounds.label})}</div>`;
    const lb = $('#cList .card-b'), lf = document.createElement('div'), lt = document.createElement('div'); lb.append(lf, lt);
    const drawL = st => {
      const m = matcher(st.q, st.mode);
      table(lt, {rows: list.filter(x => (!st.cat || x.category === st.cat) && (!st.book || (x.paid_from || x.book) === st.book) && (!st.acc || x.account === st.acc) && m(`${x.party} ${x.description || ''} ${x.note || ''}`)),
        sortKey: 'tx_date', limit: 30, cols: [
          {key: 'tx_date', label: 'Tarih', fmt: x => dayShort(x.tx_date)}, {key: 'party', label: 'Açıklama', cls: 'clip', fmt: x => `<b>${esc(x.party)}</b>${x.note ? `<span class="sub">${esc(x.note)}</span>` : ''}`},
          {key: 'book', label: 'Ödeyen hesap', fmt: x => `${esc(src(ov, x))}<span class="sub">${esc(x.account)}</span>`},
          {key: 'category', label: 'Kategori', fmt: x => (x.category ? esc(ov.categories[x.category] || x.category) : '<span class="tag orange">Belirlenmedi</span>') + (x.subcategory ? `<span class="sub">${esc(x.subcategory)}</span>` : '')},
          {key: 'amount_cents', label: 'Tutar', right: true, fmt: x => `<span class="${direction === 'in' ? 'pos' : 'neg'}">${tl(x.amount_cents)}</span>`, total: 'sum'}]});
    };
    const catOpts = [['', 'Bütün kategoriler'], ...cats.map(x => [x.key, `${x.label} (${x.count})`])];
    drawL(filterBar(lf, [{key: 'q', type: 'text', label: 'Kişi, firma, açıklama · virgülle birden çok'}, {key: 'mode', type: 'mode'},
      {key: 'cat', type: 'select', label: 'Kategori', options: catOpts}, {key: 'book', type: 'select', label: 'Ödeyen hesap', options: [['', 'Bütün hesap sahipleri'], ...bookOpts(ov)]},
      {key: 'acc', type: 'select', label: 'Hesap', options: [['', 'Bütün hesaplar'], ...[...new Set(list.map(x => x.account))].map(a => [a, a])]}], drawL));
    const cb = $('#cCats .card-b'), cf = document.createElement('div'), co = document.createElement('div'); cb.append(cf, co);
    const drawC = st => {
      const sel = list.filter(x => !st.scope || (x.scope || 'none') === st.scope);
      const g = groupBy(sel, x => x.category || '', k => ({label: ov.categories[k] || 'Belirlenmedi', value: 0, n: 0}), (x, r) => {x.value += r.amount_cents; x.n += 1;}).sort((x, y) => y.value - x.value);
      co.innerHTML = hbars(g.map(x => ({...x, sub: `${pct(x.value, sum(g, 'value'))} · ${x.n}`})), {limit: 30, color: direction === 'in' ? COLORS.in : COLORS.out}) + `<div class="total-line"><span>Toplam</span><span class="num">${tl(sum(g, 'value'))}</span></div>`;
      widths(co);
    };
    drawC(filterBar(cf, [{key: 'scope', type: 'select', label: 'Hesap başlığı', options: [['', 'Bütün başlıklar'], ...Object.entries(ov.scopes), ['none', 'Belirsiz']]}], drawC));
  };
}

// --------------------------------------------------------------- ÖDEMELER
async function odemeler(host, c, live) {
  loading(host);
  const [led, ov] = await Promise.all([c.ledger(), c.overview()]); if (!live()) return;
  const ags = agreementsFor(led.agreements, c.state.scope);
  const rec = (led.report?.recurring || []);
  const late = ags.filter(x => x.owed_closed_months > 0), open = sum(ags, x => x.this_month?.open || 0);
  host.innerHTML = `${late.length ? `<div class="alert warn">${icon('triangle-alert')}<div><b>Gecikmiş ödeme: ${tl(sum(late, 'owed_closed_months'))}</b>${late.map(x => `${esc(x.party)} ${tl(x.owed_closed_months)}`).join(' · ')}</div></div>` : ''}
    <div class="grid g4">${kpi('Gecikmiş', tlBig(sum(ags, 'owed_closed_months')), 'triangle-alert', 'red', `${late.length} anlaşma`)}
      ${kpi('Bu ay bekleyen', tlBig(open), 'clock', 'orange', 'Anlaşmaların bu ayki kalanı')}
      ${kpi('Bu ay ödenen', tlBig(sum(ags, x => x.this_month?.paid || 0)), 'circle-check', 'green', 'Anlaşmalara')}
      ${kpi('Aylık taahhüt', tlBig(sum(ags.filter(x => !x.ended), 'monthly')), 'calendar', 'blue', `${ags.filter(x => !x.ended).length} süren anlaşma`)}</div>
    <div class="grid g21">${card({id: 'cAg', title: 'Anlaşmalar ve durumları', sub: 'Aylık ödemeler sırayla aylara dağıtılır; çalışma olmayan ay borç yazmaz'})}${card({id: 'cCal', title: 'Ödeme takvimi', sub: 'Bu ay · yeşil: ödendi, turuncu: beklenen (son ödemeye göre tahmin)'})}</div>
    ${card({id: 'cRec', title: 'Düzenli ödemeler', sub: 'Anlaşmalar + iki ayda tekrar eden ödemeler'})}`;
  const status = x => x.owed_closed_months > 0 ? '<span class="tag red">Gecikti</span>' : x.this_month?.open > 0 ? (x.this_month.paid ? '<span class="tag orange">Kısmi ödendi</span>' : '<span class="tag orange">Bekliyor</span>')
    : x.ended ? '<span class="tag">Bitti</span>' : '<span class="tag green">Ödendi</span>';
  const ab = $('#cAg .card-b'), af = document.createElement('div'), at = document.createElement('div'); ab.append(af, at);
  const drawA = st => table(at, {rows: ags.filter(x => !st.st || (st.st === 'late' ? x.owed_closed_months > 0 : st.st === 'open' ? (x.this_month?.open || 0) > 0 : !x.owed_closed_months && !(x.this_month?.open))), limit: 20, cols: [
    {key: 'party', label: 'Ödeme', fmt: x => `<b>${esc(x.party)}</b><span class="sub">${esc(led.categories?.[x.category] || x.category)}${x.note ? ' · ' + esc(x.note) : ''}</span>`},
    {key: 'scope', label: 'Hesap', fmt: x => esc(led.scopes?.[x.scope] || '—')}, {key: 'monthly', label: 'Aylık', right: true, money: true},
    {key: 'owed', label: 'Gecikmiş', right: true, sort: x => x.owed_closed_months, fmt: x => (x.owed_closed_months ? `<span class="neg">${tl(x.owed_closed_months)}</span>` : '—'), total: rs => tl(sum(rs, 'owed_closed_months'))},
    {key: 'now', label: 'Bu ay kalan', right: true, sort: x => x.this_month?.open || 0, fmt: x => tl(x.this_month?.open || 0), total: rs => tl(sum(rs, x => x.this_month?.open || 0))},
    {key: 'st', label: 'Durum', nosort: true, fmt: status}]});
  drawA(filterBar(af, [{key: 'st', type: 'seg', label: 'Durum', options: [['', 'Hepsi'], ['late', 'Gecikti'], ['open', 'Bekliyor'], ['ok', 'Ödendi']], value: ''}], drawA));
  // takvim: gerçek ödeme günleri + tahmini sonraki ödeme
  const now = new Date(), y = now.getFullYear(), mo = now.getMonth(), first = new Date(y, mo, 1), days = new Date(y, mo + 1, 0).getDate();
  const ym = `${y}-${String(mo + 1).padStart(2, '0')}`, events = {};
  const add = (d, html) => {(events[d] = events[d] || []).push(html);};
  ags.forEach(x => (x.payments || []).filter(p => p.date.startsWith(ym)).forEach(p => add(Number(p.date.slice(8, 10)), `<span class="ev paid" title="${esc(x.party)} ${tl(p.amount)}">${esc(x.party.split(' ')[0])} ${tl(p.amount)}</span>`)));
  rec.filter(r => r.last_date && !r.last_date.startsWith(ym)).forEach(r => {
    const d = Number(r.last_date.slice(8, 10)); if (d <= days) add(d, `<span class="ev" title="${esc(r.party)} · tahmini ${tl(r.monthly_estimate)}">${esc(r.party.split(' ')[0])} ~${tl(r.monthly_estimate)}</span>`);
  });
  const lead = (first.getDay() + 6) % 7;
  $('#cCal .card-b').innerHTML = `<div class="cal">${['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'].map(d => `<div class="h">${d}</div>`).join('')}
    ${'<div class="d out"></div>'.repeat(lead)}${Array.from({length: days}, (_, i) => `<div class="d${i + 1 === now.getDate() ? ' today' : ''}"><span class="n">${i + 1}</span>${(events[i + 1] || []).join('')}</div>`).join('')}</div>`;
  const rb = $('#cRec .card-b'), rf = document.createElement('div'), rt = document.createElement('div'); rb.append(rf, rt);
  const drawR = st => table(rt, {rows: rec.filter(r => !st.kind || (st.kind === 'decl' ? r.declared : !r.declared)), limit: 20, cols: [
    {key: 'party', label: 'Ödeme', fmt: r => `<b>${esc(r.party)}</b>${r.declared ? ' <span class="tag blue">anlaşma</span>' : ''}`},
    {key: 'category', label: 'Kategori', fmt: r => esc(led.categories?.[r.category] || '—')},
    {key: 'monthly_estimate', label: 'Aylık', right: true, money: true, total: 'sum'},
    {key: 'last_date', label: 'Son ödeme', fmt: r => (r.last_date ? dayLabel(r.last_date) : '—')},
    {key: 'next', label: 'Sonraki (tahmini)', sort: r => r.last_date || '', fmt: r => {if (!r.last_date) return '—'; const d = new Date(r.last_date + 'T12:00:00'); d.setMonth(d.getMonth() + 1); return dayLabel(d.toISOString().slice(0, 10));}}]});
  drawR(filterBar(rf, [{key: 'kind', type: 'seg', label: 'Tür', options: [['', 'Hepsi'], ['decl', 'Anlaşmalar'], ['guess', 'Tekrar eden']], value: ''}], drawR));
  void ov;
}

// -------------------------------------------------------------- FATURALAR
async function faturalar(host, c, live) {
  if (c.state.scope === 'sahsi') {host.innerHTML = card({title: 'Faturalar', body: noCompany(c)}); return;}
  const books = c.state.scope === 'moy' ? ['moy'] : ['lemos'];
  const month = c.bounds.start.slice(0, 7);
  host.innerHTML = card({id: 'cInv', title: 'Faturalar', sub: c.state.scope === 'moy' ? 'e-Fatura / e-Arşiv · Uyumsoft' : 'Lemos defteri (L’CARLIÉ ile Lemos aynı vergi kimliğinde) · kalemler L’CARLIÉ / Lemos / ortak diye ayrılır'}) + '<div id="invDetail"></div>';
  const body = $('#cInv .card-b'), f = document.createElement('div'), sumHost = document.createElement('div'), t = document.createElement('div');
  body.append(f, sumHost, t);
  t.innerHTML = skeleton(6);
  const st0 = {book: books[0], month};
  const load = async st => {
    t.innerHTML = skeleton(6);
    const d = await c.invoices(st.book, st.month); if (!live()) return;
    const m = matcher(st.q, st.mode);
    const paid = i => Boolean(i.movement_id);
    const rows = d.invoices.filter(i => !['Canceled', 'Declined', 'Draft'].includes(i.status))
      .filter(i => !st.tab ? true : st.tab === 'in' ? i.box === 'in' : st.tab === 'out' ? i.box === 'out' : st.tab === 'paid' ? paid(i) : !paid(i))
      .filter(i => m(`${i.party} ${i.number} ${(i.lines || []).map(l => l.name).join(' ')}`))
      .map(i => ({...i, net: i.payable_cents - (i.tax_cents || 0)}));
    sumHost.innerHTML = `<div class="grid g4">${[['Gelen (alış)', rows.filter(i => i.box === 'in')], ['Giden (satış)', rows.filter(i => i.box === 'out')]].map(([l, rs]) =>
      `<div class="card kpi"><span class="t">${l} · ${rs.length}</span><div class="v num">${tl(sum(rs, 'net'))}</div><div class="d">KDV hariç · KDV dahil ${tl(sum(rs, 'payable_cents'))}</div></div>`).join('')}
      <div class="card kpi"><span class="t">Ödemesi bulunamayan</span><div class="v num">${rows.filter(i => !paid(i)).length}</div><div class="d">Bankada eşleşen hareket yok</div></div>
      <div class="card kpi"><span class="t">KDV toplamı</span><div class="v num">${tl(sum(rows, 'tax_cents'))}</div><div class="d">${esc(monthLabel(st.month, true))}</div></div></div>`;
    table(t, {rows, sortKey: 'issue_date', limit: 40, cols: [
      {key: 'issue_date', label: 'Tarih', fmt: i => dayShort(i.issue_date)}, {key: 'number', label: 'Fatura no', fmt: i => `<span class="num">${esc(i.number || '—')}</span>`},
      {key: 'party', label: 'Firma / kişi', cls: 'clip', fmt: i => `<b>${esc(i.party || '—')}</b><span class="sub">${i.box === 'in' ? 'Gelen' : 'Giden'} · ${i.scenario === 'eArchive' ? 'e-Arşiv' : 'e-Fatura'}</span>`},
      {key: 'net', label: 'KDV hariç', right: true, money: true, total: 'sum'}, {key: 'tax_cents', label: 'KDV', right: true, money: true, total: 'sum'},
      {key: 'payable_cents', label: 'KDV dahil', right: true, money: true, total: 'sum'},
      {key: 'pay', label: 'Durum', sort: i => (paid(i) ? 1 : 0), fmt: i => (paid(i) ? `<span class="tag green">${i.box === 'out' ? 'Tahsil edildi' : 'Ödendi'}</span><span class="sub">${esc(i.pay_label || '')} ${i.pay_date ? dayShort(i.pay_date) : ''}</span>` : `<span class="tag orange">${i.box === 'out' ? 'Tahsilat bulunamadı' : 'Ödeme bulunamadı'}</span>`)}],
    onRow: i => {
      $('#invDetail').innerHTML = card({title: `${i.number || 'Fatura'} · ${i.party}`, sub: `${dayLabel(i.issue_date)} · ${i.box === 'in' ? 'Gelen' : 'Giden'}`,
        body: `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Kalem</th><th class="r">Miktar</th><th class="r">KDV hariç</th><th class="r">KDV %</th><th class="r">KDV</th></tr></thead><tbody>
          ${(i.lines || []).map(l => `<tr><td>${esc(l.name)}</td><td class="r num">${qty(l.quantity)} ${esc(l.unit || '')}</td><td class="r num">${tl(l.net_cents)}</td><td class="r num">${l.vat_percent == null ? '—' : '%' + qty(l.vat_percent)}</td><td class="r num">${tl(l.vat_cents)}</td></tr>`).join('') || '<tr><td colspan="5">Kalem okunamadı; fatura toplamı kullanılır.</td></tr>'}</tbody>
          <tfoot><tr><td>Fatura</td><td></td><td class="r num">${tl(i.net)}</td><td></td><td class="r num">${tl(i.tax_cents)}</td></tr><tr><td>Ödenecek (KDV dahil)</td><td></td><td class="r num" colspan="3">${tl(i.payable_cents)}</td></tr></tfoot></table></div>`});
      $('#invDetail').scrollIntoView({behavior: 'smooth', block: 'start'});
    }});
  };
  const monthsOpt = [];
  const base = new Date(c.bounds.end + 'T12:00:00');
  for (let i = 0; i < 14; i++) {const d = new Date(base.getFullYear(), base.getMonth() - i, 1); const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; monthsOpt.push([k, monthLabel(k, true)]);}
  const st = filterBar(f, [{key: 'book', type: 'select', label: 'Şirket', options: books.map(b => [b, b === 'lemos' ? 'Lemos' : 'MOY']), value: st0.book},
    {key: 'month', type: 'select', label: 'Ay', options: monthsOpt, value: c.bounds.end.slice(0, 7)},
    {key: 'tab', type: 'seg', label: 'Sekme', options: [['', 'Tümü'], ['in', 'Gelen'], ['out', 'Giden'], ['paid', 'Ödenenler'], ['wait', 'Bekleyenler']], value: ''},
    {key: 'q', type: 'text', label: 'Firma, numara, kalem ara'}, {key: 'mode', type: 'mode'}], s => load(s).catch(x => {t.innerHTML = `<div class="alert err">${esc(x.message)}</div>`;}));
  await load(st);
}

// --------------------------------------------------------------- İŞLEMLER
async function islemler(host, c, live) {
  loading(host);
  const ov = await c.overview(); if (!live()) return;
  host.innerHTML = card({id: 'cTx', title: 'Bütün finansal hareketler', sub: `${c.bounds.label} · ${SRC_BANK} · iç aktarımlar etiketli`,
    acts: `<button type="button" class="btn" id="txCsv">${icon('download', 'sm')}Excel’e aktar</button>`});
  const b = $('#cTx .card-b'), f = document.createElement('div'), s = document.createElement('div'), t = document.createElement('div'); b.append(f, s, t);
  let current = [];
  const draw = st => {
    const m = matcher(st.q, st.mode);
    current = ov.movements.filter(x => (st.kind === 'all' || kindOf(x) === st.kind) && (!st.book || (x.paid_from || x.book) === st.book) && (!st.cat || (x.category || '__') === st.cat)
      && (!st.acc || x.account === st.acc) && m(`${x.party} ${x.description || ''} ${x.note || ''} ${ov.categories[x.category] || ''} ${x.account}`));
    const inT = sum(current.filter(x => kindOf(x) === 'in'), 'amount_cents'), outT = sum(current.filter(x => kindOf(x) === 'out'), 'amount_cents');
    s.innerHTML = `<p class="flt-note">${current.length} hareket · gelir <b class="pos">${tl(inT)}</b> · gider <b class="neg">${tl(outT)}</b> · net <b>${tl(inT - outT, true)}</b>${st.kind !== 'in' && st.kind !== 'out' ? ` · iç aktarım ${tl(sum(current.filter(x => kindOf(x) === 'ic'), 'amount_cents'))} (toplama girmez)` : ''}</p>`;
    table(t, {rows: current, sortKey: 'tx_date', limit: 50, cols: [
      {key: 'tx_date', label: 'Tarih', fmt: x => dayShort(x.tx_date)},
      {key: 'party', label: 'İşlem', cls: 'clip', fmt: x => `<b>${esc(x.party)}</b>${x.description ? `<span class="sub">${esc(String(x.description).slice(0, 80))}</span>` : ''}`},
      {key: 'book', label: 'Ödeyen hesap', fmt: x => `${esc(src(ov, x))}<span class="sub">${esc(x.account)}</span>`},
      {key: 'category', label: 'Kategori', fmt: x => (x.category ? esc(ov.categories[x.category] || x.category) : '<span class="tag orange">Belirlenmedi</span>') + (x.scope ? `<span class="sub">${esc(ov.scopes[x.scope] || '')}</span>` : '')},
      {key: 'kind', label: 'Tür', sort: kindOf, fmt: x => {const k = kindOf(x); return k === 'in' ? '<span class="tag green">Gelir</span>' : k === 'out' ? '<span class="tag red">Gider</span>' : `<span class="tag blue">${esc(x.internal || ov.categories[x.category] || 'İç aktarım')}</span>`;}},
      {key: 'amount_cents', label: 'Tutar', right: true, sort: x => (x.direction === 'in' ? 1 : -1) * x.amount_cents,
        fmt: x => {const k = kindOf(x); return `<span class="${k === 'in' ? 'pos' : k === 'out' ? 'neg' : 'muted'}">${x.direction === 'in' ? '+' : '−'}${tl(x.amount_cents)}</span>`;},
        total: rs => tl(sum(rs.filter(x => kindOf(x) === 'in'), 'amount_cents') - sum(rs.filter(x => kindOf(x) === 'out'), 'amount_cents'), true)}]});
  };
  const cats = [...new Set(ov.movements.map(x => x.category || '__'))].map(k => [k, k === '__' ? 'Belirlenmedi' : ov.categories[k] || k]).sort((x, y) => x[1].localeCompare(y[1], 'tr'));
  draw(filterBar(f, [{key: 'q', type: 'text', label: 'Kişi, firma, açıklama, hesap · virgülle birden çok', value: c.state.q},
    {key: 'mode', type: 'mode'}, {key: 'kind', type: 'seg', label: 'Tür', options: [['all', 'Hepsi'], ['in', 'Gelir'], ['out', 'Gider'], ['ic', 'İç aktarım']], value: 'all'},
    {key: 'book', type: 'select', label: 'Ödeyen hesap', options: [['', 'Bütün hesap sahipleri'], ...bookOpts(ov)]},
    {key: 'cat', type: 'select', label: 'Kategori', options: [['', 'Bütün kategoriler'], ...cats]},
    {key: 'acc', type: 'select', label: 'Hesap', options: [['', 'Bütün hesaplar'], ...ov.accounts.map(a => [a.name, a.name])]}], draw));
  $('#txCsv').addEventListener('click', () => csv(`islemler-${c.bounds.start}-${c.bounds.end}.csv`,
    ['Tarih', 'İşlem', 'Açıklama', 'Defter', 'Hesap', 'Kategori', 'Alt kalem', 'Hesap başlığı', 'Tür', 'Tutar (TL)'],
    current.map(x => [x.tx_date, x.party, x.description || '', src(ov, x), x.account, ov.categories[x.category] || '', x.subcategory || '', ov.scopes[x.scope] || '',
      kindOf(x) === 'in' ? 'Gelir' : kindOf(x) === 'out' ? 'Gider' : (x.internal || 'İç aktarım'), money((x.direction === 'in' ? 1 : -1) * x.amount_cents)])));
}

// --------------------------------------------------------- ŞİRKET ANALİZİ
/** satış / doğrudan gider / ortak gider payı / kalan — sunucudaki iki iş hesabının aynısı, satırlardan */
function companyResult(rows, vat) {
  const val = r => (vat === 'gross' ? r.g : r.v);
  // grup içi (Lemos ↔ MOY) her iki tarafta da dışarıda: Genel Bakış ile aynı kural (entityOf)
  const le = rows.filter(r => r.k === 'lemos' && entityOf(r) !== 'grup'), mo = rows.filter(r => r.k === 'moy' && entityOf(r) !== 'grup');
  const sales = k => sum(le.filter(r => r.b === 'out' && r.z === k), val), cost = k => sum(le.filter(r => r.b === 'in' && r.z === k), val);
  const sl = sales('lcarlie'), sm = sales('lemos'), clear = sl + sm, shared = cost('ortak');
  const share = {lcarlie: clear ? sl / clear : 0.5, lemos: clear ? sm / clear : 0.5};
  const out = ['lcarlie', 'lemos'].map(k => {
    const s = sales(k), d = cost(k), sh = Math.round(shared * share[k]);
    return {k, sales: s, direct: d, shared: sh, share: share[k], result: s - d - sh};
  });
  if (mo.length) {
    const s = sum(mo.filter(r => r.b === 'out'), val), d = sum(mo.filter(r => r.b === 'in'), val);
    out.push({k: 'moy', sales: s, direct: d, shared: 0, share: null, result: s - d});
  }
  return {list: out, shared, unclear: sum(le.filter(r => r.b === 'out' && r.z === 'belirsiz'), val), group: sum(rows.filter(r => entityOf(r) === 'grup'), val)};
}
async function sirket(host, c, live) {
  loading(host);
  const a = await c.analysis(); if (!live()) return;
  const all = allInvoiceRows(a, c);
  host.innerHTML = (periodNote(c) ? `<div class="alert info">${icon('info')}<div>${esc(periodNote(c))}</div></div>` : '') +
    card({id: 'cCmp', title: "Şirket karşılaştırması: L'CARLIÉ · Lemos · MOY", sub: `${SRC_INV} · ortak giderler L'CARLIÉ ve Lemos arasında satış payına göre bölüştürülür`}) +
    card({id: 'cCmpM', title: 'Aylık satış karşılaştırması', sub: SRC_INV});
  const b = $('#cCmp .card-b'), f = document.createElement('div'), o = document.createElement('div'); b.append(f, o);
  const draw = st => {
    const m = matcher(st.q, st.mode);
    const res = companyResult(all.filter(r => (!st.month || r.m === st.month) && m(`${r.p} ${r.n} ${r.f}`)), st.vat === 'both' ? 'net' : st.vat);
    const resG = st.vat === 'both' ? companyResult(all.filter(r => (!st.month || r.m === st.month) && m(`${r.p} ${r.n} ${r.f}`)), 'gross') : null;
    const cell = (x, key) => (resG ? `${tl(x[key])}<span class="sub">KDV dahil ${tl(resG.list.find(y => y.k === x.k)[key])}</span>` : tl(x[key]));
    o.innerHTML = `<div class="grid g3">${res.list.map(x => `<section class="card"><div class="split"><h2 class="card-title"><i class="dot-c" data-bg="${COLORS[x.k]}"></i> ${esc(ENTITY[x.k])}</h2>${x.share != null ? `<span class="tag">satış payı ${pct(x.share, 1)}</span>` : ''}</div>
      <dl class="kv"><dt>Satış</dt><dd class="num">${cell(x, 'sales')}</dd><dt>Doğrudan gider</dt><dd class="num">−${cell(x, 'direct')}</dd>
      ${x.k !== 'moy' ? `<dt>Ortak gider payı</dt><dd class="num">−${cell(x, 'shared')}</dd>` : ''}
      <dt class="sum">Net sonuç</dt><dd class="sum num ${x.result < 0 ? 'neg' : 'pos'}">${tl(x.result, true)}</dd>
      <dt>Kâr marjı</dt><dd class="num ${x.result < 0 ? 'neg' : ''}">${x.sales ? pct(x.result, x.sales) : '—'}</dd></dl></section>`).join('')}</div>
      <p class="foot-note">Bölüştürülen ortak gider ${tl(res.shared)}${res.group ? ` · Lemos ↔ MOY grup içi faturalar (${tl(res.group)}) iki kez sayılmasın diye dışarıda` : ''}${res.unclear ? ` · işi belli olmayan satış ${tl(res.unclear)}` : ''}. ${st.vat === 'gross' ? 'KDV dahil tutarlar.' : 'Net sonuç KDV hariç tutarlarla hesaplanır.'}</p>`;
    widths(o);
  };
  draw(filterBar(f, [{key: 'month', type: 'select', label: 'Ay', options: monthOpts(all)}, {key: 'q', type: 'text', label: 'Kalem / ürün / firma · ör. vireon'},
    {key: 'mode', type: 'mode', value: 'except'}, {key: 'vat', type: 'vat'}], draw));
  const mb = $('#cCmpM .card-b'), mf = document.createElement('div'), mc = document.createElement('div'); mb.append(mf, mc);
  const drawM = st => {
    const m = matcher(st.q, st.mode), rows = all.filter(r => r.b === 'out' && entityOf(r) !== 'grup' && m(`${r.p} ${r.n}`));
    const ms = months(all);
    chart(mc, {labels: ms, type: st.type, tipTitle: x => monthLabel(x, true), series: ['lcarlie', 'lemos', 'moy'].filter(k => rows.some(r => entityOf(r) === k))
      .map(k => ({name: ENTITY[k], color: COLORS[k], values: ms.map(mm => sum(rows.filter(r => r.m === mm && entityOf(r) === k), r => vatVal(st.vat, r)))}))});
  };
  drawM(filterBar(mf, [{key: 'type', type: 'seg', label: 'Grafik', options: [['bar', 'Sütun'], ['line', 'Çizgi']], value: 'bar'},
    {key: 'q', type: 'text', label: 'Ürün ara'}, {key: 'mode', type: 'mode'}, {key: 'vat', type: 'seg', label: 'KDV', options: [['net', 'KDV hariç'], ['gross', 'KDV dahil']], value: 'net'}], drawM));
}

// ---------------------------------------------------------- SATIŞ ANALİZİ
async function satis(host, c, live) {
  if (!sells(c)) {host.innerHTML = card({title: 'Satış analizi', body: noSales()}); return;}
  loading(host);
  const a = await c.analysis(); if (!live()) return;
  const all = invoiceRows(a, c).filter(r => r.b === 'out' && entityOf(r) !== 'grup');
  host.innerHTML = (periodNote(c) ? `<div class="alert info">${icon('info')}<div>${esc(periodNote(c))}</div></div>` : '') +
    card({id: 'cCh', title: 'Kanal karşılaştırması', sub: `${SRC_INV} · iade, indirim, kupon düşülmüş net satış`}) +
    card({id: 'cChM', title: 'Aylık satış (kanala göre)', sub: SRC_INV});
  const CH = {dogrudan: 'Doğrudan (muayenehane / etkinlik / kurumsal)', wix: 'Wix (web sitesi)', trendyol: 'Trendyol'};
  const b = $('#cCh .card-b'), f = document.createElement('div'), t = document.createElement('div'); b.append(f, t);
  const draw = st => {
    const m = matcher(st.q, st.mode), sel = all.filter(r => r.k === 'lemos' && (!st.ent || entityOf(r) === st.ent) && (!st.month || r.m === st.month) && m(`${r.p} ${r.n}`));
    const rows = Object.keys(CH).map(k => {
      const rs = sel.filter(r => r.c === k), pos = rs.filter(r => r.v > 0), neg = rs.filter(r => r.v < 0);
      return {k, name: CH[k], qty: sum(rs.filter(r => r.p), 'q'), lines: pos.length, gross_sales: sum(pos, 'v'), returns: sum(neg, 'v'), v: sum(rs, 'v'), g: sum(rs, 'g'),
        avg: pos.length ? Math.round(sum(pos, 'v') / pos.length) : 0};
    });
    table(t, {rows, sortKey: 'v', limit: 10, cols: [{key: 'name', label: 'Kanal', fmt: r => `<i class="dot-c" data-bg="${COLORS[r.k]}"></i> ${esc(r.name)}`},
      {key: 'qty', label: 'Satış adedi', right: true, fmt: r => qty(r.qty), total: rs => qty(sum(rs, 'qty'))},
      {key: 'avg', label: 'Ort. satır tutarı', right: true, money: true}, {key: 'gross_sales', label: 'Brüt satış', right: true, money: true, total: 'sum'},
      {key: 'returns', label: 'İade / indirim', right: true, money: true, total: 'sum'}, ...moneyCols(st.vat, {labelNet: 'Net (KDV hariç)', labelGross: 'Net (KDV dahil)'}),
      {key: 'p', label: 'Pay', right: true, sort: r => r.v, fmt: r => pct(r.v, sum(rows, 'v'))}]});
    widths(t);
  };
  draw(filterBar(f, [{key: 'month', type: 'select', label: 'Ay', options: monthOpts(all)}, {key: 'q', type: 'text', label: 'Ürün ara · ör. vireon'}, {key: 'mode', type: 'mode'}, {key: 'vat', type: 'vat'}], draw));
  const mb = $('#cChM .card-b'), mf = document.createElement('div'), mc = document.createElement('div'); mb.append(mf, mc);
  const drawM = st => {
    const m = matcher(st.q, st.mode), rows = all.filter(r => r.k === 'lemos' && (!st.ent || entityOf(r) === st.ent) && m(`${r.p} ${r.n}`)), ms = months(all);
    chart(mc, {labels: ms, type: st.type, stacked: st.type === 'bar', tipTitle: x => monthLabel(x, true),
      series: Object.keys(CH).map(k => ({name: CH[k].split(' (')[0], color: COLORS[k], values: ms.map(mm => sum(rows.filter(r => r.m === mm && r.c === k), r => vatVal(st.vat, r)))}))});
  };
  drawM(filterBar(mf, [{key: 'type', type: 'seg', label: 'Grafik', options: [['bar', 'Yığılmış sütun'], ['line', 'Çizgi']], value: 'bar'},
    {key: 'q', type: 'text', label: 'Ürün ara'}, {key: 'mode', type: 'mode'}, {key: 'vat', type: 'seg', label: 'KDV', options: [['net', 'KDV hariç'], ['gross', 'KDV dahil']], value: 'net'}], drawM));
}

// ----------------------------------------------------------- ÜRÜN ANALİZİ
async function urun(host, c, live) {
  if (!sells(c)) {host.innerHTML = card({title: 'Ürün analizi', body: noSales()}); return;}
  loading(host);
  const a = await c.analysis(); if (!live()) return;
  const all = invoiceRows(a, c).filter(r => r.b === 'out' && r.p && entityOf(r) !== 'grup');
  host.innerHTML = (periodNote(c) ? `<div class="alert info">${icon('info')}<div>${esc(periodNote(c))}</div></div>` : '') +
    card({id: 'cPr', title: 'Ürün performansı', sub: `${SRC_INV} · iadeler adet ve cirodan düşülmüş`}) +
    card({id: 'cPrC', title: 'Ciroya göre ilk 12 ürün', sub: SRC_INV});
  const costs = a.product_costs || {};
  const b = $('#cPr .card-b'), f = document.createElement('div'), t = document.createElement('div'); b.append(f, t);
  const sel = st => {const m = matcher(st.q, st.mode); return all.filter(r => (!st.ent || entityOf(r) === st.ent) && (!st.ch || r.c === st.ch) && (!st.month || r.m === st.month) && m(r.p));};
  const draw = st => {
    // maliyet: ürünün en son üretim faturasındaki birim fiyat (KDV hariç); faturası yoksa boş — tahmin yok
    const items = productAgg(sel(st)).map(r => {const c = costs[r.name]; const cost = c ? Math.round(c.unit * r.q) : null;
      return {...r, unit_cost: c ? c.unit : null, cost, profit: cost == null ? null : r.v - cost, cost_src: c};});
    const tot = sum(items, st.vat === 'gross' ? 'g' : 'v'), known = items.filter(r => r.cost != null);
    t.innerHTML = '';
    const note = document.createElement('p'); note.className = 'flt-note';
    note.innerHTML = `Maliyet: ürünün en son üretim faturası (KDV hariç; testerlar dahil değil). ${known.length} / ${items.length} ürünün faturası var — bu ürünler cironun ${pct(sum(known, 'v'), sum(items, 'v'))}’i. Kâr ve marj yalnız faturası olan ürünlerde hesaplanır.`;
    const tt = document.createElement('div'); t.append(note, tt);
    table(tt, {rows: items, sortKey: st.vat === 'gross' ? 'g' : 'v', limit: 40, cols: [{key: 'name', label: 'Ürün', fmt: r => `<b>${esc(r.name)}</b>`},
      {key: 'q', label: 'Adet', right: true, fmt: r => qty(r.q), total: rs => qty(sum(rs, 'q'))}, ...moneyCols(st.vat, {labelNet: 'Ciro (KDV hariç)', labelGross: 'Ciro (KDV dahil)'}),
      {key: 'u', label: 'Ort. birim fiyat', right: true, sort: r => (r.q ? r.v / r.q : 0), fmt: r => (r.q ? vatCell(st.vat, Math.round(r.v / r.q), Math.round(r.g / r.q)) : '—')},
      {key: 'unit_cost', label: 'Birim maliyet', right: true, sort: r => r.unit_cost ?? -1, fmt: r => (r.unit_cost == null ? '<span class="tag">fatura yok</span>' : `${tl(r.unit_cost)}<span class="sub">${esc(r.cost_src.supplier.split(' ')[0])} · ${dayShort(r.cost_src.date)}</span>`)},
      {key: 'cost', label: 'Maliyet', right: true, sort: r => r.cost ?? -1, fmt: r => (r.cost == null ? '—' : tl(r.cost)), total: rs => tl(sum(rs.filter(r => r.cost != null), 'cost'))},
      {key: 'profit', label: 'Brüt kâr (KDV hariç)', right: true, sort: r => r.profit ?? -1e15, fmt: r => (r.profit == null ? '—' : `<span class="${r.profit < 0 ? 'neg' : 'pos'}">${tl(r.profit)}</span>`), total: rs => tl(sum(rs.filter(r => r.profit != null), 'profit'))},
      {key: 'margin', label: 'Marj', right: true, sort: r => (r.profit == null || !r.v ? -1e9 : r.profit / r.v), fmt: r => (r.profit == null || !r.v ? '—' : pct(r.profit, r.v)),
        total: rs => {const k = rs.filter(r => r.profit != null); return pct(sum(k, 'profit'), sum(k, 'v'));}},
      {key: 'p', label: 'Ciro payı', right: true, sort: r => r.v, fmt: r => pct(vatVal(st.vat, r), tot)}]});
  };
  const spec = [{key: 'ch', type: 'select', label: 'Kanal', options: [['', 'Bütün kanallar'], ['dogrudan', 'Doğrudan'], ['wix', 'Wix'], ['trendyol', 'Trendyol']]},
    {key: 'month', type: 'select', label: 'Ay', options: monthOpts(all)}, {key: 'q', type: 'text', label: 'Ürün ara · virgülle birden çok'}, {key: 'mode', type: 'mode'}];
  draw(filterBar(f, [...spec, {key: 'vat', type: 'vat'}], draw));
  const cb = $('#cPrC .card-b'), cf = document.createElement('div'), co = document.createElement('div'); cb.append(cf, co);
  const drawC = st => {
    const items = productAgg(sel(st)).sort((x, y) => vatVal(st.vat, y) - vatVal(st.vat, x));
    co.innerHTML = hbars(items.map(x => ({label: x.name, value: vatVal(st.vat, x), sub: `${qty(x.q)} adet`})), {limit: 12, color: COLORS.lcarlie}); widths(co);
  };
  drawC(filterBar(cf, [...spec, {key: 'vat', type: 'seg', label: 'KDV', options: [['net', 'KDV hariç'], ['gross', 'KDV dahil']], value: 'net'}], drawC));
}

// ----------------------------------------------------------- GİDER ANALİZİ
// sahip, 02.11.2026: "harcama" adı Harcamalarım sayfasınındır; Finans Merkezi'nde "gider"
async function harcama(host, c, live) {
  loading(host);
  const [ov, a] = await Promise.all([c.overview(), c.state.scope === 'sahsi' ? null : c.analysis()]); if (!live()) return;
  const out = counted(ov).filter(m => m.direction === 'out');
  host.innerHTML = `<div class="grid g21">${card({id: 'hCat', title: 'Kategoriye göre gider', sub: `${c.bounds.label} · ${SRC_BANK}`})}${card({id: 'hScope', title: 'Kime ait', sub: 'Hesap başlığına göre'})}</div>
    ${card({id: 'hTrend', title: 'Aylık gider trendi', sub: `Son 12 ay · ${SRC_BANK}`})}
    ${card({id: 'hInv', title: 'Fatura giderleri: konu, tedarikçi, kalem', sub: `${SRC_INV} · KDV hariç ve dahil`})}
    ${card({id: 'hTop', title: 'En yüksek gider kalemleri', sub: `${c.bounds.label} · tek tek hareketler`})}`;
  const mk = id => {const b = $(`#${id} .card-b`), f = document.createElement('div'), o = document.createElement('div'); b.append(f, o); return [f, o];};
  const [cf, co] = mk('hCat');
  const drawCat = st => {
    const m = matcher(st.q, st.mode), sel = out.filter(x => (!st.scope || (x.scope || 'none') === st.scope) && (!st.book || (x.paid_from || x.book) === st.book) && m(`${x.party} ${x.note || ''}`));
    const g = groupBy(sel, x => x.category || '', k => ({label: ov.categories[k] || 'Belirlenmedi', value: 0, n: 0}), (x, r) => {x.value += r.amount_cents; x.n += 1;}).sort((x, y) => y.value - x.value);
    co.innerHTML = hbars(g.map(x => ({...x, sub: `${pct(x.value, sum(g, 'value'))} · ${x.n} hareket`})), {limit: 40, color: COLORS.out}) + `<div class="total-line"><span>Toplam gider</span><span class="num">${tl(sum(g, 'value'))}</span></div>`;
    widths(co);
  };
  drawCat(filterBar(cf, [{key: 'book', type: 'select', label: 'Ödeyen hesap', options: [['', 'Bütün hesap sahipleri'], ...bookOpts(ov)]},
    {key: 'scope', type: 'select', label: 'Hesap başlığı', options: [['', 'Bütün başlıklar'], ...Object.entries(ov.scopes), ['none', 'Belirsiz']]},
    {key: 'q', type: 'text', label: 'Kişi / firma ara'}, {key: 'mode', type: 'mode'}], drawCat));
  const [sf, so] = mk('hScope');
  const drawScope = st => {
    const sel = out.filter(x => !st.cat || x.category === st.cat);
    const g = groupBy(sel, x => x.scope || 'none', k => ({label: ov.scopes[k] || 'Belirsiz', value: 0, k}), (x, r) => {x.value += r.amount_cents;}).sort((x, y) => y.value - x.value);
    so.innerHTML = hbars(g.map(x => ({...x, color: COLORS[x.k] || '#94A3B8', sub: pct(x.value, sum(g, 'value'))})), {limit: 10}); widths(so);
  };
  drawScope(filterBar(sf, [{key: 'cat', type: 'select', label: 'Kategori', options: [['', 'Bütün kategoriler'], ...ov.by_category.map(x => [x.key, x.label])]}], drawScope));
  const [tf, tc] = mk('hTrend');
  const drawT = st => chart(tc, {labels: ov.monthly.map(m => m.month), type: st.type, tipTitle: m => monthLabel(m, true), series: [{name: 'Gider', color: COLORS.out, values: ov.monthly.map(m => m.out)}, ...(st.cmp ? [{name: 'Gelir', color: COLORS.in, values: ov.monthly.map(m => m.in)}] : [])]});
  drawT(filterBar(tf, [{key: 'type', type: 'seg', label: 'Grafik', options: [['bar', 'Sütun'], ['line', 'Çizgi']], value: 'line'}, {key: 'cmp', type: 'seg', label: 'Karşılaştır', options: [['', 'Yalnız gider'], ['1', 'Gelirle birlikte']], value: ''}], drawT));
  const [inf, ino] = mk('hInv');
  if (!a) ino.innerHTML = noCompany(c);
  else {
    const inv = invoiceRows(a, c).filter(r => r.b === 'in' && entityOf(r) !== 'grup');
    const drawI = st => {
      const m = matcher(st.q, st.mode), sel = inv.filter(r => (!st.ent || entityOf(r) === st.ent) && (!st.theme || r.t === st.theme) && (!st.month || r.m === st.month) && m(`${r.n} ${r.f}`));
      const key = st.by === 'party' ? r => r.f || '—' : st.by === 'item' ? r => r.n || r.f || '—' : r => THEMES[r.t] || r.t;
      const g = groupBy(sel, key, k => ({name: k, v: 0, g: 0, n: 0}), (x, r) => {x.v += r.v; x.g += r.g; x.n += 1;});
      ino.innerHTML = ''; const t = document.createElement('div'); ino.appendChild(t);
      table(t, {rows: g, sortKey: st.vat === 'gross' ? 'g' : 'v', limit: 15, cols: [{key: 'name', label: st.by === 'party' ? 'Tedarikçi' : st.by === 'item' ? 'Kalem' : 'Konu', cls: 'clip'},
        {key: 'n', label: 'Kalem', right: true, total: rs => String(sum(rs, 'n'))}, ...moneyCols(st.vat), {key: 'p', label: 'Pay', right: true, sort: r => r.v, fmt: r => pct(vatVal(st.vat, r), sum(g, st.vat === 'gross' ? 'g' : 'v'))}]});
    };
    drawI(filterBar(inf, [{key: 'by', type: 'seg', label: 'Grupla', options: [['theme', 'Konu'], ['party', 'Tedarikçi'], ['item', 'Kalem']], value: 'theme'},
      {key: 'theme', type: 'select', label: 'Konu', options: [['', 'Bütün konular'], ...Object.entries(THEMES).filter(([k]) => inv.some(r => r.t === k))]},
      {key: 'month', type: 'select', label: 'Ay', options: monthOpts(inv)}, {key: 'q', type: 'text', label: 'Tedarikçi / kalem · ör. yeni nesil, mim'}, {key: 'mode', type: 'mode'}, {key: 'vat', type: 'vat'}], drawI));
  }
  const [pf, po] = mk('hTop');
  const drawP = st => {
    const m = matcher(st.q, st.mode);
    table(po, {rows: out.filter(x => (!st.cat || x.category === st.cat) && m(x.party)), sortKey: 'amount_cents', limit: 10, cols: [
      {key: 'tx_date', label: 'Tarih', fmt: x => dayShort(x.tx_date)}, {key: 'party', label: 'Kime', cls: 'clip', fmt: x => `<b>${esc(x.party)}</b>`},
      {key: 'category', label: 'Kategori', fmt: x => esc(ov.categories[x.category] || 'Belirlenmedi')}, {key: 'book', label: 'Ödeyen hesap', fmt: x => esc(src(ov, x))},
      {key: 'amount_cents', label: 'Tutar', right: true, money: true, total: 'sum'}]});
  };
  drawP(filterBar(pf, [{key: 'cat', type: 'select', label: 'Kategori', options: [['', 'Bütün kategoriler'], ...ov.by_category.map(x => [x.key, x.label])]}, {key: 'q', type: 'text', label: 'Ara'}, {key: 'mode', type: 'mode'}], drawP));
}

// --------------------------------------------------------------- RAPORLAR
async function raporlar(host, c, live) {
  host.innerHTML = card({id: 'rp', title: 'Rapor oluştur', sub: 'Dönem üstteki seçimden gelir · Excel (CSV) ve yazdır / PDF',
    acts: `<button type="button" class="btn" id="rpCsv">${icon('download', 'sm')}Excel’e aktar</button><button type="button" class="btn primary" id="rpPrint">${icon('printer', 'sm')}Yazdır / PDF</button>`});
  const b = $('#rp .card-b'), f = document.createElement('div'), o = document.createElement('div'); b.append(f, o);
  let last = {name: 'rapor', header: [], rows: []};
  const build = async st => {
    o.innerHTML = skeleton(6);
    const ov = await c.overview(); if (!live()) return;
    const a = st.type === 'sales' || st.type === 'company' || st.type === 'products' ? (c.state.scope === 'sahsi' ? null : await c.analysis()) : null;
    let header = [], rows = [], view = '';
    if (st.type === 'pl') {
      header = ['Ay', 'Gelir (TL)', 'Gider (TL)', 'Net (TL)'];
      rows = ov.monthly.map(m => [monthLabel(m.month, true), money(m.in), money(m.out), money(m.in - m.out)]);
      view = `<table class="tbl"><thead><tr><th>Ay</th><th class="r">Gelir</th><th class="r">Gider</th><th class="r">Net</th></tr></thead><tbody>${ov.monthly.map(m => `<tr><td>${monthLabel(m.month, true)}</td><td class="r num pos">${tl(m.in)}</td><td class="r num neg">${tl(m.out)}</td><td class="r num">${tl(m.in - m.out, true)}</td></tr>`).join('')}</tbody>
        <tfoot><tr><td>Son 12 ay</td><td class="r num">${tl(sum(ov.monthly, 'in'))}</td><td class="r num">${tl(sum(ov.monthly, 'out'))}</td><td class="r num">${tl(sum(ov.monthly, 'in') - sum(ov.monthly, 'out'), true)}</td></tr></tfoot></table>`;
    } else if (st.type === 'spend') {
      header = ['Kategori', 'Hareket', 'Tutar (TL)', 'Pay'];
      rows = ov.by_category.map(x => [x.label, x.count, money(x.total), pct(x.total, ov.out_total)]);
      view = `<table class="tbl"><thead><tr><th>Kategori</th><th class="r">Hareket</th><th class="r">Tutar</th><th class="r">Pay</th></tr></thead><tbody>${ov.by_category.map(x => `<tr><td>${esc(x.label)}</td><td class="r">${x.count}</td><td class="r num">${tl(x.total)}</td><td class="r">${pct(x.total, ov.out_total)}</td></tr>`).join('')}</tbody><tfoot><tr><td>Toplam</td><td></td><td class="r num">${tl(ov.out_total)}</td><td></td></tr></tfoot></table>`;
    } else if (!a) {view = noCompany(c);}
    else {
      const all = st.type === 'company' ? allInvoiceRows(a, c) : invoiceRows(a, c);
      if (st.type === 'sales') {
        const g = groupBy(all.filter(r => r.b === 'out' && entityOf(r) !== 'grup'), r => `${ENTITY[entityOf(r)] || r.z}|${r.c || '—'}`, k => ({k, v: 0, g: 0}), (x, r) => {x.v += r.v; x.g += r.g;});
        header = ['İş', 'Kanal', 'KDV hariç (TL)', 'KDV dahil (TL)']; rows = g.map(x => [...x.k.split('|'), money(x.v), money(x.g)]);
      } else if (st.type === 'products') {
        const g = productAgg(all.filter(r => r.b === 'out' && entityOf(r) !== 'grup')).sort((x, y) => y.v - x.v);
        header = ['Ürün', 'Adet', 'KDV hariç (TL)', 'KDV dahil (TL)']; rows = g.map(x => [x.name, qty(x.q), money(x.v), money(x.g)]);
      } else {
        const r1 = companyResult(all, 'net').list, r2 = companyResult(all, 'gross').list;
        header = ['Şirket / iş', 'Satış KDV hariç', 'Satış KDV dahil', 'Doğrudan gider (KDV hariç)', 'Ortak gider payı (KDV hariç)', 'Net sonuç (KDV hariç)', 'Kâr marjı'];
        rows = r1.map((x, i) => [ENTITY[x.k], money(x.sales), money(r2[i].sales), money(x.direct), money(x.shared), money(x.result), x.sales ? pct(x.result, x.sales) : '—']);
      }
      view = `<table class="tbl"><thead><tr>${header.map((h, i) => `<th class="${i > 0 ? 'r' : ''}">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((v, i) => `<td class="${i > 0 ? 'r num' : ''}">${esc(i > 0 && /^-?\d+,\d{2}$/.test(v) ? v.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' ₺' : v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    }
    o.innerHTML = `<p class="flt-note">${esc(c.bounds.label)} · ${esc(st.type === 'company' ? 'Kurumlar arası karşılaştırma' : KURUM[c.state.scope])}</p><div class="tbl-wrap">${view}</div>`;
    last = {name: `${st.type}-${c.bounds.start}-${c.bounds.end}.csv`, header, rows};
  };
  const st = filterBar(f, [{key: 'type', type: 'select', label: 'Rapor türü', options: [['pl', 'Gelir – gider raporu (aylık)'], ['spend', 'Gider raporu (kategori)'],
    ['company', 'Şirket raporu (L’CARLIÉ · Lemos · MOY)'], ['sales', 'Satış raporu (iş × kanal)'], ['products', 'Ürün raporu']], value: 'pl'}], s => build(s).catch(x => {o.innerHTML = `<div class="alert err">${esc(x.message)}</div>`;}));
  await build(st);
  $('#rpCsv').addEventListener('click', () => last.rows.length && csv(last.name, last.header, last.rows));
  $('#rpPrint').addEventListener('click', () => window.print());
}

// ---------------------------------------------------------------- AYARLAR
async function ayarlar(host, c, live) {
  loading(host, 2);
  const ov = await c.overview(); if (!live()) return;
  host.innerHTML = `<div class="grid g2">
    ${card({title: 'Dört kurum', sub: 'Şahsım, MOY, Lemos ve L’CARLIÉ ayrı şirketler gibi gösterilir', body: `<ul class="rows"><li><span class="rt"><b>Kimin parası</b><small>Banka hareketi, hesabın sahibine ait sayılır. Hesap başlığı başka bir kurum verilmişse (ör. şahsi kartla ödenen MOY vergisi) o kurumun geliri ya da gideri olur.</small></span></li>
      <li><span class="rt"><b>L’CARLIÉ</b><small>Resmî olarak Lemos’un içinde bir iş ve kendi banka hesabı yok. Faturalar içeriğine göre L’CARLIÉ / Lemos / ortak diye ayrılır; ortak giderler ikisine satış payıyla bölünür. Banka tarafında hesap başlığı “L’CARLIÉ” olan ödemeler L’CARLIÉ’nindir.</small></span></li>
      <li><span class="rt"><b>Kurumlar arası para</b><small>Kurumdan kuruma giden para (ortaktan, şirketten, grup içi, bir kurum adına ödeme) hiçbir kurumda gelir ya da gider sayılmaz; Genel Bakış’ta “Kurumlar arası para” kartında görünür.</small></span></li></ul>`})}
    ${card({title: 'Sayım kuralları', body: `<ul class="rows"><li><span class="rt"><b>Kurumlar arası</b><small>Hiçbir kurumda gelir de gider de sayılmaz; İşlemler’de “İç aktarım” etiketiyle görünür. Özet’teki “Tümü” satırında da sayılmaz.</small></span></li>
      <li><span class="rt"><b>Kendi hesaplar arası, aracılık, hesaba katılmasın</b><small>Hiçbir görünümde sayılmaz.</small></span></li>
      <li><span class="rt"><b>Fatura tutarları</b><small>Her fatura kendi tutarı kadar sayılır (ödenecek − KDV); KDV dahil ayrıca gösterilir.</small></span></li></ul>`})}
    ${card({title: 'Gider kategorileri', body: `<div class="legend">${Object.values(ov.out_categories).map(v => `<span class="tag">${esc(v)}</span>`).join('')}</div>`})}
    ${card({title: 'Gelir kategorileri ve hesap başlıkları', body: `<div class="legend">${Object.values(ov.in_categories).map(v => `<span class="tag green">${esc(v)}</span>`).join('')}</div><div class="legend">${Object.values(ov.scopes).map(v => `<span class="tag blue">${esc(v)}</span>`).join('')}</div>`})}
  </div>
  ${card({title: 'Düzenleme, yükleme ve anlaşmalar', sub: 'Bu sayfa yalnız okur; değiştirme işleri mevcut sayfada', body: `<p>Banka dökümü yükleme, hareketlere kategori verme (“Bu ne için?”), kurallar, anlaşma ekleme ve bütçeler <b>Harcamalarım</b> sayfasında.</p><a class="btn primary" href="/harcamalar.html">${icon('external-link', 'sm')}Harcamalarım’ı aç</a>`})}
  ${card({title: 'Tema ve görünüm', body: '<p class="muted">Açık tema. Masaüstünde sabit sol menü; tablet ve telefonda menü düğmesiyle açılır.</p>'})}`;
}

// ------------------------------------------------------------------ ÖZET
// sahip, 02.11.2026: "detay ağırdıkça kayboluyoruz … şirket gelir giderleri, benim şahsi gelir
// giderlerim, araları, nereye harcadığımız, ne kadar kazandığımız, Lemos'un MOY'un ödemeleri
// gelirleri, düzenli ödemeler, L'CARLIÉ'nin durumu, mali işler, muhasebe".
// Sonra: "her şeyi ay ay parçalaman gerekiyor … gelir gider bizde aylık hesaplanır; raporlamaları
// haftalık, aylık, yıllık ve genel sunacaksın". Banka hareketi gün gün tarihli: istenen döneme bölünür.
// Fatura, KDV ve anlaşmalar ay bazında tutulur: haftalık görünümde o haftaların ayları gösterilir.
const OZET_BOOKS = [['sahsi', 'Şahsım'], ['moy', 'MOY'], ['lemos', 'Lemos'], ['lcarlie', "L'CARLIÉ"]];
const OZ_GRAINS = [['hafta', 'Haftalık'], ['ay', 'Aylık'], ['yil', 'Yıllık'], ['genel', 'Genel']];
const OZ_UNIT = {hafta: 'önceki haftaya göre', ay: 'önceki aya göre', yil: 'önceki yıla göre'};
const ozIso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const ozMonday = d => {const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x;};
const ozState = (() => {
  let g = 'ay', y = new Date().getFullYear();
  try {g = sessionStorage.getItem('ozet.g') || g; y = Number(sessionStorage.getItem('ozet.y')) || y;} catch { /* gizli pencere */ }
  return {g: OZ_GRAINS.some(([v]) => v === g) ? g : 'ay', y};
})();
// Özet'te kuruş yok, sıfır "—" (sahip: okunurluk); kuruşu kuruşuna rakam ayrıntı sayfalarında
const tl0 = (v, sign = false) => {
  const n = Math.round(Number(v || 0) / 100);
  return n ? `${sign && n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toLocaleString('tr-TR')} ₺` : '<span class="muted">—</span>';
};
const signed = v => `<span class="num ${v <= -100 ? 'neg' : v >= 100 ? 'pos' : ''}">${tl0(v, true)}</span>`;

/** veri penceresi: en fazla üç yıl (sunucu sınırı 1100 gün) */
function ozWindow() {
  const now = new Date(), floor = new Date(now); floor.setDate(floor.getDate() - 1095);
  const jan = new Date(now.getFullYear() - 2, 0, 1);
  return {start: ozIso(jan > floor ? jan : floor), end: ozIso(now), now};
}
/** sütunlar: bank → banka hareketinin tarihine göre; monthly → ay bazındaki veri (fatura, KDV, anlaşma) */
function ozColumns(st, w, firstYear) {
  const now = w.now, cy = now.getFullYear(), cm = `${cy}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const monthsOf = y => Array.from({length: y === cy ? now.getMonth() + 1 : 12}, (_, i) => `${y}-${String(i + 1).padStart(2, '0')}`);
  const years = Array.from({length: cy - firstYear + 1}, (_, i) => String(firstYear + i));
  if (st.g === 'hafta') {
    const mons = Array.from({length: 8}, (_, i) => {const d = ozMonday(now); d.setDate(d.getDate() - 7 * (7 - i)); return d;});
    const bank = mons.map(d => ({key: ozIso(d), label: dayShort(ozIso(d)), now: ozIso(d) === ozIso(ozMonday(now))}));
    const months = [...new Set(mons.flatMap(d => {const e = new Date(d); e.setDate(e.getDate() + 6); return [ozIso(d).slice(0, 7), ozIso(e).slice(0, 7)];}))].filter(m => m <= cm);
    return {bank, bankKey: iso => ozIso(ozMonday(new Date(iso + 'T12:00:00'))),
      monthly: months.map(m => ({key: m, label: monthLabel(m), now: m === cm, months: [m]})), monthKey: m => m};
  }
  if (st.g === 'ay') {
    const ms = monthsOf(st.y).map(m => ({key: m, label: monthLabel(m), now: m === cm, months: [m]}));
    return {bank: ms, bankKey: iso => iso.slice(0, 7), monthly: ms, monthKey: m => m};
  }
  if (st.g === 'yil') {
    const ys = years.map(y => ({key: y, label: y, now: y === String(cy), months: monthsOf(Number(y))}));
    return {bank: ys, bankKey: iso => iso.slice(0, 4), monthly: ys, monthKey: m => m.slice(0, 4)};
  }
  const all = [{key: 'genel', label: 'Genel', now: false, months: years.flatMap(y => monthsOf(Number(y)))}];
  return {bank: all, bankKey: () => 'genel', monthly: all, monthKey: () => 'genel'};
}
/** satır × dönem tablosu. Toplam; üç ve daha çok sütunda tamamlanmış dönemlerin ortalaması;
 *  "şimdi" sütunu vurgulu, ilk sütun yana kaydırırken sabit (CSS). */
function ozTable(cols, rows, {total = true, avg = true} = {}) {
  const withTotal = total && cols.length > 1;
  const done = cols.map((c, i) => (c.now ? -1 : i)).filter(i => i >= 0);
  const withAvg = avg && cols.length > 2 && done.length > 1;
  const cell = (r, v) => (r.kind === 'net' ? signed(v) : r.fmt ? r.fmt(v) : tl0(v));
  const nowc = i => (cols[i].now ? ' nowc' : '');
  return `<div class="tbl-wrap"><table class="tbl oz"><thead><tr><th scope="col"></th>${cols.map((c, i) => `<th class="r${nowc(i)}" scope="col">${esc(c.label)}${c.now ? ' <small>(şimdi)</small>' : ''}</th>`).join('')}${withAvg ? '<th class="r" scope="col">Ortalama</th>' : ''}${withTotal ? '<th class="r" scope="col">Toplam</th>' : ''}</tr></thead>
    <tbody>${rows.map(r => `<tr class="${r.kind === 'net' ? 'sumrow' : ''}"><td>${r.label}</td>${r.vals.map((v, i) => `<td class="r num${nowc(i)}">${cell(r, v)}</td>`).join('')}${withAvg ? `<td class="r num muted-c">${r.noAvg ? '' : cell(r, Math.round(done.reduce((s, i) => s + r.vals[i], 0) / done.length))}</td>` : ''}${withTotal ? `<td class="r num"><b>${r.total !== undefined ? r.total : cell(r, r.vals.reduce((s, v) => s + v, 0))}</b></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
}

async function ozet(host, c, live) {
  loading(host, 6);
  const w = ozWindow();
  const years = [];
  for (let y = Number(w.start.slice(0, 4)); y <= w.now.getFullYear(); y++) years.push(y);
  const [books, tumu, inv, led, pp] = await Promise.all([
    Promise.all(OZET_BOOKS.map(([ws]) => api('/api/money/overview', {ws, view: 'range', start: w.start, end: w.end}))),
    api('/api/money/overview', {ws: 'tumu', view: 'range', start: w.start, end: w.end}),
    Promise.all(years.map(y => api('/api/money/invoice-analysis', {book: 'lemos', year: y}))).then(all => all.flatMap(a => a.rows || [])),
    c.ledger(),
    api('/api/money/product-profit', {alloc: 'esit'}).catch(() => null)]);
  if (!live()) return;
  const ov = Object.fromEntries(OZET_BOOKS.map(([ws], i) => [ws, books[i]]));
  // gerçek veri başlangıcı: Genel ve Yıllık görünümde boş yıllar gösterilmez
  const firstDay = OZET_BOOKS.flatMap(([k]) => ov[k].movements.map(m => m.tx_date)).concat(inv.map(r => `${r.m}-01`)).sort()[0] || w.start;
  const firstYear = Number(firstDay.slice(0, 4));
  if (ozState.y < firstYear || ozState.y > w.now.getFullYear()) ozState.y = w.now.getFullYear();
  const P = ozColumns(ozState, w, firstYear);
  const bankCols = P.bank, monCols = P.monthly, cm = ozIso(w.now).slice(0, 7);

  // banka: kendi hesapların arası ve hesaba katılmayanlar dışarıda (öteki sayfalarla aynı kural)
  const moves = Object.fromEntries(OZET_BOOKS.map(([k]) => [k, counted(ov[k])]));
  moves.tumu = counted(tumu);
  const bucket = (k, dir, pred = () => true) => {
    const out = Object.fromEntries(bankCols.map(x => [x.key, 0]));
    for (const m of moves[k]) if (m.direction === dir && pred(m)) {const b = P.bankKey(m.tx_date); if (b in out) out[b] += m.amount_cents;}
    return bankCols.map(x => out[x.key]);
  };
  // kurumlar arası para (03.11.2026'dan beri) her kurumda sayılmayan hareket: o kartlar bütün hareketlerden okur
  const bucketAll = (k, dir, pred) => {
    const out = Object.fromEntries(bankCols.map(x => [x.key, 0]));
    for (const m of ov[k].movements) if (m.direction === dir && pred(m)) {const b = P.bankKey(m.tx_date); if (b in out) out[b] += m.amount_cents;}
    return bankCols.map(x => out[x.key]);
  };
  const flow = Object.fromEntries([...OZET_BOOKS.map(([k]) => k), 'tumu'].map(k => [k, {in: bucket(k, 'in'), out: bucket(k, 'out')}]));
  const diff = k => flow[k].in.map((v, i) => v - flow[k].out[i]);

  // fatura: ay bazında satırlar → dönem
  const monIdx = Object.fromEntries(monCols.map((x, i) => [x.key, i]));
  const invRows = inv.filter(r => P.monthKey(r.m) in monIdx);
  const res = monCols.map(x => companyResult(invRows.filter(r => P.monthKey(r.m) === x.key), 'net'));
  const pick = (i, k) => res[i]?.list.find(x => x.k === k) || {sales: 0, direct: 0, shared: 0, result: 0};

  // anlaşmalar: aylık ödenen / kalan → dönem; 50 TL altı kalan (yuvarlama, EFT masrafı) borç sayılmaz
  const ags = (led.agreements || []).map(a => ({...a, owed_closed_months: a.owed_closed_months < 5000 ? 0 : a.owed_closed_months}));
  const agBucket = (a, key) => monCols.map(x => sum((a.months || []).filter(m => P.monthKey(m.month) === x.key), key));
  const dueNow = sum(ags, x => x.owed_closed_months + (x.this_month?.open || 0));

  // gösterge kartları: son TAMAMLANMIŞ dönem, bir öncekine göre (yarım ay tam ayla kıyaslanmaz)
  const unit = OZ_UNIT[ozState.g];
  const bi = Math.max(0, bankCols.length - (bankCols[bankCols.length - 1]?.now ? 2 : 1));
  const mi = Math.max(0, monCols.length - (monCols[monCols.length - 1]?.now ? 2 : 1));
  const kpiCmp = (arr, i) => {
    if (!unit || i < 1) return '';
    const ch = chg(arr[i], arr[i - 1], false, true);
    return ch.includes('yeterli veri') ? ch : `${ch} <span class="muted">${unit}</span>`;
  };
  const shirket = bankCols.map((_, i) => diff('lemos')[i] + diff('moy')[i]);
  const lcRes = monCols.map((_, i) => pick(i, 'lcarlie').result);
  const nowNote = (arr, cols, i) => (cols[cols.length - 1]?.now && i !== cols.length - 1 ? ` · şimdiye kadar ${tl0(arr[arr.length - 1], true)}` : '');

  host.innerHTML = `
    <div class="oz-bar" id="ozBar"></div>
    <div class="grid g4">
      ${kpi(`Şahsi fark · ${bankCols[bi]?.label || ''}`, tlBig(diff('sahsi')[bi] || 0, true), 'user', (diff('sahsi')[bi] || 0) < 0 ? 'red' : 'green', kpiCmp(diff('sahsi'), bi) + nowNote(diff('sahsi'), bankCols, bi))}
      ${kpi(`Şirketler fark · ${bankCols[bi]?.label || ''}`, tlBig(shirket[bi] || 0, true), 'building-2', (shirket[bi] || 0) < 0 ? 'red' : 'green', kpiCmp(shirket, bi) + nowNote(shirket, bankCols, bi))}
      ${kpi(`L'CARLIÉ sonucu · ${monCols[mi]?.label || ''}`, tlBig(lcRes[mi] || 0, true), 'shopping-cart', (lcRes[mi] || 0) < 0 ? 'red' : 'green', `Satış ${tl0(pick(mi, 'lcarlie').sales)} · faturadan`)}
      ${kpi('Ödenecek (düzenli, şu an)', tlBig(dueNow), 'clock', dueNow ? 'orange' : 'green', `${ags.filter(x => (x.this_month?.open || 0) + x.owed_closed_months > 0).length} ödeme bekliyor`)}
    </div>
    ${card({id: 'oNext', title: 'Önümüzdeki 30 gün', sub: 'Ödenecekler, tarih sırasıyla'})}
    ${card({id: 'oFlow', title: 'Gelir – gider', sub: 'Banka ve kart hareketleri · kendi hesapların arası sayılmaz'})}
    ${card({id: 'oCat', title: 'Nereden geldi, nereye gitti', sub: 'Kategoriye göre · banka ve kart hareketleri'})}
    ${card({id: 'oBetween', title: 'Şirketler ↔ sen', sub: 'Şirketten sana, senden şirkete · banka hareketleri'})}
    ${card({id: 'oPay', title: 'Düzenli ödemeler', sub: 'Ödenen tutar; kırmızı: o dönemde kalan · ay bazında'})}
    ${card({id: 'oBiz', title: "İşler: L'CARLIÉ · Lemos · MOY", sub: 'Faturalara göre, KDV hariç · ay bazında · ortak giderler satış payına göre bölüştürülür'})}
    ${card({id: 'oLc', title: "L'CARLIÉ: maliyetin geri dönüşü", sub: 'Dönem satışı ve o döneme kadar biriken satışın toplam ürün maliyetine oranı'})}
    ${card({id: 'oVat', title: 'Muhasebe: KDV', sub: 'Faturalardan hesaplanan tahmini · devreden KDV aydan aya taşınır · beyanname muhasebecide'})}`;

  // dönem seçimi: Haftalık / Aylık (yıl seçilir) / Yıllık / Genel
  const yearOpts = Array.from({length: w.now.getFullYear() - firstYear + 1}, (_, i) => String(w.now.getFullYear() - i)).map(y => [y, y]);
  filterBar($('#ozBar'), [{key: 'g', type: 'seg', label: 'Dönem', options: OZ_GRAINS, value: ozState.g},
    ...(ozState.g === 'ay' ? [{key: 'y', type: 'select', label: 'Yıl', options: yearOpts, value: String(ozState.y)}] : [])], st => {
    ozState.g = st.g; ozState.y = Number(st.y || ozState.y);
    try {sessionStorage.setItem('ozet.g', ozState.g); sessionStorage.setItem('ozet.y', String(ozState.y));} catch { /* gizli pencere */ }
    ozet(host, c, live);
  });
  if (ozState.g === 'genel') $('#ozBar').insertAdjacentHTML('beforeend', `<p class="foot-note">Genel: ${dayLabel(firstDay)} – bugün (Jarvis’teki ilk kayıttan).</p>`);
  if (ozState.g === 'hafta') $('#ozBar').insertAdjacentHTML('beforeend', '<p class="foot-note">Son 8 hafta (Pazartesi başlar). Fatura, KDV ve düzenli ödemeler ay bazında: bu haftaların ayları gösterilir.</p>');
  widths(host);

  // önümüzdeki 30 gün: anlaşmaların kalanı + tekrar eden ödemelerin tahmini sonraki günü
  const today = ozIso(w.now), lim = new Date(w.now); lim.setDate(lim.getDate() + 30);
  const next = [];
  for (const a of ags) {
    const open = (a.this_month?.open || 0) + a.owed_closed_months;
    if (open < 5000) continue;
    const lastPay = (a.payments || []).map(p => p.date).sort().pop();
    const day = lastPay ? Math.min(Number(lastPay.slice(8, 10)), 28) : 1;
    const due = `${cm}-${String(day).padStart(2, '0')}`;
    next.push({date: due < today ? today : due, late: a.owed_closed_months > 0 || due < today, party: a.party, amount: open,
      note: a.owed_closed_months ? `${tl0(a.owed_closed_months)} gecikmiş` : 'anlaşma'});
  }
  const declared = new Set(ags.map(a => fold(a.party).split(' ')[0]));
  for (const r of led.report?.recurring || []) {
    if (r.declared || !r.last_date || r.last_date.slice(0, 7) === cm || declared.has(fold(r.party).split(' ')[0])) continue;
    const d = new Date(r.last_date + 'T12:00:00'); d.setMonth(d.getMonth() + 1);
    const due = ozIso(d);
    if (due <= ozIso(lim)) next.push({date: due < today ? today : due, late: due < today, party: r.party, amount: r.monthly_estimate, note: 'tekrar eden, tahmini'});
  }
  next.sort((a, b) => a.date.localeCompare(b.date));
  $('#oNext .card-b').innerHTML = next.length ? `<ul class="rows">${next.map(x => `<li><span class="ri chip-ic ${x.late ? 'red' : 'orange'}">${icon(x.late ? 'triangle-alert' : 'calendar')}</span>
      <span class="rt"><b>${esc(x.party)}</b><small>${x.late ? 'gecikti / bugün' : dayLabel(x.date)} · ${esc(x.note)}</small></span><span class="ra num">${tl0(x.amount)}</span></li>`).join('')}</ul>
    <div class="total-line"><span>Toplam</span><span class="num">${tl0(sum(next, 'amount'))}</span></div>
    <p class="foot-note">Kart ekstrelerinin son ödeme günü dökümlerden okunmuyor; kart borçları bu listede yok.</p>` : empty('Önümüzdeki 30 günde bilinen ödeme yok', '', 'circle-check');

  // gelir – gider: grafik (konsolide) + tablo; telefonda dönem kartları
  const fb = $('#oFlow .card-b'), fc = document.createElement('div'), ft = document.createElement('div'), fm = document.createElement('div');
  fm.className = 'oz-cards'; fb.append(fc, ft, fm);
  chart(fc, {labels: bankCols.map(x => x.label), height: 220, series: [
    {name: 'Gelir (tümü)', color: COLORS.in, values: flow.tumu.in}, {name: 'Gider (tümü)', color: COLORS.out, values: flow.tumu.out}]});
  ft.innerHTML = ozTable(bankCols, [
    {label: '<b>Tümü</b> gelir', vals: flow.tumu.in}, {label: '<b>Tümü</b> gider', vals: flow.tumu.out}, {label: 'Tümü fark', vals: diff('tumu'), kind: 'net'},
    ...OZET_BOOKS.flatMap(([k, label]) => [
      {label: `<b>${label}</b> gelir`, vals: flow[k].in}, {label: `<b>${label}</b> gider`, vals: flow[k].out},
      {label: `${label} fark`, vals: diff(k), kind: 'net'}])]) +
    '<p class="foot-note">Tümü: şirketlerle aranızdaki para iki kez sayılmaz, bu yüzden üç satırın toplamından küçüktür.</p>';
  fm.innerHTML = bankCols.map((x, i) => i).reverse().map(i => `<section class="oz-c${bankCols[i].now ? ' now' : ''}"><h3>${esc(bankCols[i].label)}${bankCols[i].now ? ' <small>(şimdi)</small>' : ''}</h3>
    <dl class="kv">${[['tumu', 'Tümü'], ...OZET_BOOKS].map(([k, label]) => `<dt><b>${label}</b> gelir</dt><dd>${tl0(flow[k].in[i])}</dd><dt>${label} gider</dt><dd>${tl0(flow[k].out[i])}</dd><dt class="sum">${label} fark</dt><dd class="sum">${signed(diff(k)[i])}</dd>`).join('')}</dl></section>`).join('');

  // kategoriler: defter seçilir, gelen ve giden ayrı tablo
  const cb = $('#oCat .card-b'), cf = document.createElement('div'), ct = document.createElement('div'); cb.append(cf, ct);
  const catLabel = (o, key) => (key ? o.categories?.[key] || key : 'Belirlenmedi');
  const drawCat = st => {
    const o = ov[st.book];
    const block = dir => {
      const keys = [...new Set(moves[st.book].filter(m => m.direction === dir).map(m => m.category || ''))];
      const rows = keys.map(key => ({label: esc(catLabel(o, key)), vals: bucket(st.book, dir, m => (m.category || '') === key)}))
        .filter(r => r.vals.some(v => Math.abs(v) >= 100)).sort((a, b) => sum(b.vals, v => v) - sum(a.vals, v => v));
      return rows.length ? ozTable(bankCols, rows) : empty('Bu dönemde kayıt yok.');
    };
    ct.innerHTML = `<h3 class="mini">Gelen</h3>${block('in')}<h3 class="mini">Giden</h3>${block('out')}`;
  };
  drawCat(filterBar(cf, [{key: 'book', type: 'seg', label: 'Hesap', options: OZET_BOOKS, value: 'sahsi'}], drawCat));

  // şirketler ↔ sen
  const toOwner = bucketAll('sahsi', 'in', m => m.category === 'sirketten');
  const salary = bucketAll('sahsi', 'in', m => m.category === 'gelir');
  const ortL = bucketAll('lemos', 'in', m => m.category === 'ortaktan'), ortM = bucketAll('moy', 'in', m => m.category === 'ortaktan');
  const fromOwner = bankCols.map((_, i) => ortL[i] + ortM[i]);
  $('#oBetween .card-b').innerHTML = ozTable(bankCols, [
    {label: 'Şirketlerden sana gelen', vals: toOwner}, {label: 'Maaş / ücret (Lemos)', vals: salary},
    {label: 'Senden şirketlere giden', vals: fromOwner},
    {label: 'Şirketlerden sana net', vals: bankCols.map((_, i) => toOwner[i] + salary[i] - fromOwner[i]), kind: 'net'}]) +
    '<p class="foot-note">Bu aktarımlar hiçbir kurumda gelir ya da gider sayılmaz; para yalnız yer değiştirir.</p>';

  // düzenli ödemeler
  const payRows = ags.filter(a => !a.ended || a.owed_closed_months).map(a => ({a, paid: agBucket(a, 'paid'), open: agBucket(a, 'open')}));
  const nowp = i => (monCols[i].now ? ' nowc' : '');
  $('#oPay .card-b').innerHTML = payRows.length ? `<div class="tbl-wrap"><table class="tbl oz"><thead><tr><th scope="col"></th>${monCols.map((x, i) => `<th class="r${nowp(i)}" scope="col">${esc(x.label)}${x.now ? ' <small>(şimdi)</small>' : ''}</th>`).join('')}</tr></thead>
    <tbody>${payRows.map(r => `<tr><td><b>${esc(r.a.party)}</b><span class="sub">${esc(led.scopes?.[r.a.scope] || '')} · aylık ${tl0(r.a.monthly)}</span></td>${r.paid.map((v, i) => `<td class="r num${nowp(i)}">${tl0(v)}${r.open[i] >= 5000 ? `<span class="sub neg">kalan ${tl0(r.open[i])}</span>` : ''}</td>`).join('')}</tr>`).join('')}
    <tr class="sumrow"><td>Toplam ödenen</td>${monCols.map((_, i) => `<td class="r num${nowp(i)}">${tl0(sum(payRows, r => r.paid[i]))}</td>`).join('')}</tr></tbody></table></div>` : empty('Anlaşma yok');

  // işler
  $('#oBiz .card-b').innerHTML = ozTable(monCols, ['lcarlie', 'lemos', 'moy'].flatMap(k => [
    {label: `<i class="dot-c" data-bg="${COLORS[k]}"></i> <b>${esc(ENTITY[k])}</b> satış`, vals: monCols.map((_, i) => pick(i, k).sales)},
    {label: `${esc(ENTITY[k])} gider`, vals: monCols.map((_, i) => pick(i, k).direct + pick(i, k).shared)},
    {label: `${esc(ENTITY[k])} sonuç`, vals: monCols.map((_, i) => pick(i, k).result), kind: 'net'}])) +
    `<p class="foot-note"><a href="#/sirket">Şirket Analizi</a> · <a href="#/satis">Satış Analizi</a> · <a href="#/urun">Ürün Analizi</a></p>`;
  widths($('#oBiz'));

  // L'CARLIÉ: dönem satışı + o döneme kadar biriken satış / toplam ürün maliyeti
  const t = pp?.totals;
  const lcSale = r => r.k === 'lemos' && r.b === 'out' && r.z === 'lcarlie' && entityOf(r) !== 'grup';
  const endOf = x => x.months.filter(m => m <= cm).sort().pop() || cm;
  const cum = monCols.map(x => sum(inv.filter(r => lcSale(r) && r.m <= endOf(x)), 'v'));
  const pctFmt = v => (t?.total_cost ? `%${(v / t.total_cost * 100).toLocaleString('tr-TR', {maximumFractionDigits: 1})}` : '—');
  $('#oLc .card-b').innerHTML = t ? ozTable(monCols, [
    {label: 'Dönem satışı (KDV hariç)', vals: monCols.map((_, i) => pick(i, 'lcarlie').sales)},
    {label: 'Biriken satış (dönem sonuna kadar)', vals: cum, noAvg: true, total: tl0(cum[cum.length - 1])},
    {label: '<b>Maliyetin karşılanan kısmı</b>', vals: cum, kind: 'pct', fmt: pctFmt, noAvg: true, total: pctFmt(cum[cum.length - 1])}]) +
    `<p class="foot-note">Toplam ürün maliyeti ${tl0(t.total_cost)} (üretim, test, ÜGR, tester, reklam) · üretilen ${qty(t.produced)}, satılan ${qty(t.sold)} adet · <a href="#/urunkar">Ürün Kârlılığı</a></p>`
    : empty('Ürün kârlılığı okunamadı');

  // muhasebe: KDV — giden faturada hesaplanan, gelen faturada indirilecek; devreden aydan aya taşınır
  const allMonths = [...new Set(inv.map(r => r.m))].filter(m => m <= cm).sort();
  const vatChain = k => {
    let carry = 0;
    const out = {};
    for (const m of allMonths) {
      const o = sum(inv.filter(r => r.k === k && r.m === m && r.b === 'out'), r => (r.g || 0) - (r.v || 0));
      const n = sum(inv.filter(r => r.k === k && r.m === m && r.b === 'in'), r => (r.g || 0) - (r.v || 0));
      const net = o - n - carry;
      out[m] = {o, n, carryIn: carry, pay: Math.max(net, 0), carryOut: Math.max(-net, 0)};
      carry = out[m].carryOut;
    }
    return out;
  };
  const vatRows = ['lemos', 'moy'].flatMap(k => {
    const ch = vatChain(k), name = k === 'lemos' ? 'Lemos' : 'MOY';
    const ms = x => x.months.filter(m => ch[m]).sort();
    const s = key => monCols.map(x => sum(ms(x), m => ch[m][key]));
    const first = monCols.map(x => (ms(x).length ? ch[ms(x)[0]].carryIn : 0));
    const lastC = monCols.map(x => (ms(x).length ? ch[ms(x).pop()].carryOut : 0));
    return [{label: `<b>${name}</b> satıştan KDV`, vals: s('o')}, {label: `${name} alıştan KDV (indirilir)`, vals: s('n')},
      {label: `${name} önceki aydan devreden`, vals: first, noAvg: true, total: ''},
      {label: `<b>${name} ödenecek KDV</b>`, vals: s('pay'), fmt: v => (Math.round(v / 100) ? `<span class="neg">${tl0(v)}</span>` : tl0(v)), kind: 'pay'},
      {label: `${name} sonraki aya devreden`, vals: lastC, noAvg: true, total: ''}];
  });
  $('#oVat .card-b').innerHTML = ozTable(monCols, vatRows) +
    `<p class="foot-note">Devir Jarvis’teki ilk faturadan (${allMonths.length ? monthLabel(allMonths[0], true) : '—'}) başlar; öncesinden gelen devir ve tevkifat bu hesaba girmez. Kesin rakam muhasebecinin beyannamesidir. <a href="#/faturalar">Faturalar</a></p>`;
}

export const PAGES = {
  genel: {title: 'Genel Bakış', sub: 'Kurumun gelir, gider ve öteki kurumlarla para hareketi', render: genel, redraw: true, kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  hesaplar: {title: 'Hesaplarım', sub: 'Kurumun parasının geçtiği banka ve kart hesapları', render: hesaplar, kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  gelirler: {title: 'Gelirler', sub: 'Gelen paralar ve tahsilatlar', render: flowPage('in'), kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  giderler: {title: 'Giderler', sub: 'Giden paralar ve ödemeler', render: flowPage('out'), kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  odemeler: {title: 'Ödemeler', sub: 'Anlaşmalar, gecikenler, takvim', render: odemeler, kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  faturalar: {title: 'Faturalar', sub: 'Gelen ve giden faturalar', render: faturalar, kurums: ['moy', 'lemos', 'lcarlie']},
  islemler: {title: 'İşlemler', sub: 'Bütün finansal hareketler', render: islemler, kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  satis: {title: 'Satış Analizi', sub: 'Doğrudan, Wix ve Trendyol', render: satis, redraw: true, kurums: ['lemos', 'lcarlie']},
  urun: {title: 'Ürün Analizi', sub: 'Ürün bazında adet ve ciro', render: urun, kurums: ['lemos', 'lcarlie']},
  urunkar: {title: 'Ürün Kârlılığı', sub: 'Ürün ürün maliyet, satış, karşılama ve kâr/zarar', render: urunKar, noPeriod: true, kurums: ['lcarlie']},
  harcama: {title: 'Gider Analizi', sub: 'Kategoriler, tedarikçiler, trend', render: harcama, redraw: true, kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  raporlar: {title: 'Raporlar', sub: 'Dönem raporu, Excel ve PDF', render: raporlar, kurums: ['sahsi', 'moy', 'lemos', 'lcarlie']},
  ozet: {title: 'Özet', sub: 'Dört kurum yan yana: haftalık, aylık, yıllık ve genel', render: ozet, noPeriod: true, cross: true},
  sirket: {title: 'Şirket Karşılaştırması', sub: "L'CARLIÉ, Lemos ve MOY yan yana · faturalardan", render: sirket, redraw: true, cross: true},
  ayarlar: {title: 'Ayarlar', sub: 'Kurumlar, kategoriler, kurallar', render: ayarlar, noPeriod: true, cross: true},
};
