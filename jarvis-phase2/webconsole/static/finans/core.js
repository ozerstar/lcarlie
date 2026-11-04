// Finans Merkezi — çekirdek: veri, biçim, bileşenler (sahip, 02.11.2026)
// Sayfa salt okur; düzenleme mevcut Harcamalarım sayfasında kalır.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
export const icon = (name, cls = '') => `<svg class="ic ${cls}" aria-hidden="true"><use href="/finans/icons.svg#i-${name}"></use></svg>`;

// ------------------------------------------------------------------ biçim
const nf2 = new Intl.NumberFormat('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const nf0 = new Intl.NumberFormat('tr-TR', {maximumFractionDigits: 0});
/** kuruş → "1.234,56 ₺" (kuruşu kuruşuna; yuvarlama yok) */
export const tl = (cents, sign = false) => {
  const v = Number(cents || 0) / 100;
  return `${sign && v > 0 ? '+' : v < 0 ? '−' : ''}${nf2.format(Math.abs(v))} ₺`;
};
/** büyük kart rakamı: lira kalın, kuruş küçük */
export const tlBig = (cents, sign = false) => {
  const v = Number(cents || 0), abs = Math.abs(v);
  const lira = nf0.format(Math.floor(abs / 100)), kr = String(abs % 100).padStart(2, '0');
  return `${sign && v > 0 ? '+' : v < 0 ? '−' : ''}${lira}<small>,${kr} ₺</small>`;
};
export const tlShort = cents => {
  const v = Math.abs(Number(cents || 0) / 100);
  const s = v >= 1e6 ? `${(v / 1e6).toLocaleString('tr-TR', {maximumFractionDigits: 1})} mn` : v >= 1e3 ? `${(v / 1e3).toLocaleString('tr-TR', {maximumFractionDigits: 0})} bin` : nf0.format(v);
  return (cents < 0 ? '−' : '') + s;
};
export const qty = n => Number(n || 0).toLocaleString('tr-TR', {maximumFractionDigits: 2});
export const pct = (part, whole) => whole ? `%${(part / whole * 100).toLocaleString('tr-TR', {maximumFractionDigits: 1})}` : '—';
const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
export const monthLabel = (m, long = false) => {
  const [y, mo] = String(m).split('-').map(Number);
  return long ? `${MONTHS[mo - 1]} ${y}` : MONTHS[mo - 1].slice(0, 3);
};
export const dayLabel = d => {
  if (!d) return '—';
  const [y, m, day] = String(d).slice(0, 10).split('-').map(Number);
  return `${day} ${MONTHS[m - 1]} ${y}`;
};
export const dayShort = d => {
  if (!d) return '—';
  const [, m, day] = String(d).slice(0, 10).split('-').map(Number);
  return `${day} ${MONTHS[m - 1].slice(0, 3)}`;
};
export const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const today = () => iso(new Date());
/** Türkçe büyük/küçük harf ve aksan farkını yok say ("İ"/"ı" dahil) */
export const fold = s => String(s || '').toLocaleLowerCase('tr-TR').replace(/ı/g, 'i').normalize('NFD').replace(/[̀-ͯ]/g, '');
/** "yeni nesil, mim" → satır bu terimlerden birini içeriyor mu */
export const matcher = (text, mode) => {
  const terms = String(text || '').split(',').map(t => fold(t).trim()).filter(Boolean);
  if (!terms.length) return () => true;
  return hay => {const h = fold(hay); const hit = terms.some(t => h.includes(t)); return mode === 'except' ? !hit : hit;};
};
export const sum = (rows, key) => rows.reduce((s, r) => s + Number((typeof key === 'function' ? key(r) : r[key]) || 0), 0);
export function groupBy(rows, keyFn, init, add) {
  const map = new Map();
  for (const r of rows) {const k = keyFn(r); if (!map.has(k)) map.set(k, init(k)); add(map.get(k), r);}
  return [...map.values()];
}

// ------------------------------------------------------------------ veri
const cache = new Map();
export async function api(path, params = {}, {fresh = false} = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString();
  const url = path + (qs ? '?' + qs : '');
  if (!fresh && cache.has(url)) return cache.get(url);
  const p = fetch(url, {credentials: 'same-origin', headers: {Accept: 'application/json'}}).then(async res => {
    let body = {};
    try {body = await res.json();} catch { /* boş gövde */ }
    if (res.status === 401) throw new Error('Oturum kapalı. Jarvis’e yeniden giriş yapın.');
    if (!res.ok) throw new Error(body.error || `Sunucu ${res.status} döndü.`);
    return body;
  });
  cache.set(url, p);
  p.catch(() => cache.delete(url));
  return p;
}
export const clearCache = () => cache.clear();
let csrf = '';
export const setCsrf = token => {csrf = token || '';};
/** kayıt: oturum jetonuyla (CSRF) POST; başarıda önbellek temizlenir, sayfalar taze veri görür */
export async function post(path, body) {
  const res = await fetch(path, {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, Accept: 'application/json'}, body: JSON.stringify(body)});
  let out = {};
  try {out = await res.json();} catch { /* boş gövde */ }
  if (res.status === 401) throw new Error('Oturum kapalı. Jarvis’e yeniden giriş yapın.');
  if (!res.ok) throw new Error(out.error || `Sunucu ${res.status} döndü.`);
  cache.clear();
  return out;
}

// --------------------------------------------------------------- durumlar
export const skeleton = (lines = 4, block = false) =>
  (block ? '<div class="sk b"></div>' : '') + Array.from({length: lines}, (_, i) => `<div class="sk l" style-w="${90 - i * 12}"></div>`).join('');
export const empty = (title, text = '', ic = 'circle-alert') =>
  `<div class="empty">${icon(ic)}<b>${esc(title)}</b>${text ? `<span>${esc(text)}</span>` : ''}</div>`;
export const errorBox = msg => `<div class="alert err">${icon('circle-alert')}<div><b>Yüklenemedi</b>${esc(msg)}</div></div>`;
export function widths(root) { // CSP: satır içi stil yok — genişlikler JS ile verilir
  $$('[data-w]', root).forEach(el => {el.style.width = el.dataset.w + '%';});
  $$('[style-w]', root).forEach(el => {el.style.width = el.getAttribute('style-w') + '%';});
  $$('[data-bg]', root).forEach(el => {el.style.background = el.dataset.bg;});
}

// ------------------------------------------------------------------- kart
/** bir kart; body string ya da sonradan doldurulacak */
export function card({id = '', title, sub = '', acts = '', body = '', cls = ''}) {
  return `<section class="card ${cls}" ${id ? `id="${id}"` : ''}>
    <header class="card-h"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ''}</div>${acts ? `<div class="acts">${acts}</div>` : ''}</header>
    <div class="card-b">${body}</div></section>`;
}

// ---------------------------------------------------- kartın kendi süzgeci
/** spec: [{key, type:'text'|'select'|'mode'|'vat'|'seg', label, options:[[v,l]], value}] → çubuk + durum
 *  Sahip: "filtreleme her birimde, her analizde, her grafikte ayrı; genel yapma". */
export function filterBar(host, spec, onChange) {
  const state = Object.fromEntries(spec.map(s => [s.key, s.value ?? (s.type === 'vat' ? 'both' : s.type === 'mode' ? 'only' : '')]));
  const ctl = s => {
    if (s.type === 'text') return `<input class="ctl txt" type="search" data-k="${s.key}" placeholder="${esc(s.label)}" aria-label="${esc(s.label)}" value="${esc(state[s.key])}">`;
    if (s.type === 'mode') return `<select class="ctl" data-k="${s.key}" aria-label="Süzme biçimi"><option value="only">Yalnız bunlar</option><option value="except"${state[s.key] === 'except' ? ' selected' : ''}>Bunlar hariç</option></select>`;
    if (s.type === 'vat') return `<div class="seg sm vat" role="group" aria-label="KDV">${[['both', 'Hariç + dahil'], ['net', 'KDV hariç'], ['gross', 'KDV dahil']].map(([v, l]) => `<button type="button" data-k="${s.key}" data-v="${v}" class="${state[s.key] === v ? 'on' : ''}">${l}</button>`).join('')}</div>`;
    if (s.type === 'seg') return `<div class="seg sm" role="group" aria-label="${esc(s.label)}">${s.options.map(([v, l]) => `<button type="button" data-k="${s.key}" data-v="${v}" class="${state[s.key] === v ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>`;
    return `<select class="ctl" data-k="${s.key}" aria-label="${esc(s.label)}">${s.options.map(([v, l]) => `<option value="${esc(v)}"${String(state[s.key]) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  };
  host.innerHTML = `<div class="flt">${spec.map(ctl).join('')}</div>`;
  let t;
  $$('[data-k]', host).forEach(el => {
    const fire = () => {state[el.dataset.k] = el.dataset.v ?? el.value; onChange(state);};
    if (el.tagName === 'BUTTON') el.addEventListener('click', () => {
      $$(`[data-k="${el.dataset.k}"]`, host).forEach(b => b.classList.toggle('on', b === el)); fire();
    });
    else if (el.type === 'search') el.addEventListener('input', () => {clearTimeout(t); t = setTimeout(fire, 160);});
    else el.addEventListener('change', fire);
  });
  return state;
}

// ------------------------------------------------------------------ tablo
/** cols: [{key, label, right, money, fmt(row), sort(row), total:'sum'|fn}] — sıralanır, toplam satırı verir */
export function table(host, {cols, rows, sortKey = null, asc = false, limit = 25, totalLabel = 'Toplam', emptyText = 'Bu seçimde kayıt yok.', onRow, detail}) {
  let key = sortKey, up = asc, shown = limit;
  const val = (c, r) => (c.sort ? c.sort(r) : r[c.key]);
  const render = () => {
    if (!rows.length) {host.innerHTML = empty(emptyText); return;}
    const col = cols.find(c => c.key === key);
    const sorted = col ? [...rows].sort((a, b) => {
      const x = val(col, a), y = val(col, b);
      const r = typeof x === 'number' && typeof y === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), 'tr');
      return up ? r : -r;
    }) : rows;
    const view = sorted.slice(0, shown);
    const hasTotal = cols.some(c => c.total);
    host.innerHTML = `<div class="tbl-wrap"><table class="tbl"><thead><tr>${cols.map(c =>
      `<th class="${c.right ? 'r' : ''}${c.key === key ? ' sorted' : ''}" ${c.nosort ? '' : `data-sort="${c.key}"`} scope="col">${esc(c.label)}${c.nosort ? '' : `<span class="arr">${c.key === key ? (up ? '↑' : '↓') : '↕'}</span>`}</th>`).join('')}</tr></thead>
      <tbody>${view.map((r, i) => `<tr data-i="${i}" class="${detail ? 'has-detail' : ''}">${cols.map((c, ci) => `<td class="${c.right ? 'r num' : ''} ${c.cls || ''}">${detail && ci === 0 ? '<span class="chev" aria-hidden="true">›</span>' : ''}${c.fmt ? c.fmt(r) : c.money ? tl(r[c.key]) : esc(r[c.key])}</td>`).join('')}</tr>`).join('')}</tbody>
      ${hasTotal ? `<tfoot><tr>${cols.map((c, i) => `<td class="${c.right ? 'r num' : ''}">${i === 0 ? `${esc(totalLabel)} <span class="muted">(${rows.length})</span>` : c.total ? (typeof c.total === 'function' ? c.total(rows) : tl(sum(rows, c.sumKey || c.key))) : ''}</td>`).join('')}</tr></tfoot>` : ''}
      </table></div>${rows.length > shown ? `<div class="more"><button type="button" class="btn">${rows.length - shown} kayıt daha göster</button></div>` : ''}`;
    $$('th[data-sort]', host).forEach(th => th.addEventListener('click', () => {
      if (key === th.dataset.sort) up = !up; else {key = th.dataset.sort; up = false;}
      render();
    }));
    const more = $('.more button', host);
    if (more) more.addEventListener('click', () => {shown += 100; render();});
    if (onRow) $$('tbody tr', host).forEach(tr => {tr.style.cursor = 'pointer'; tr.addEventListener('click', () => onRow(view[Number(tr.dataset.i)]));});
    // satıra tıklayınca ayrıntı satırı açılır/kapanır (ana tabloyu sade tutmak için)
    if (detail) $$('tbody tr.has-detail', host).forEach(tr => {
      tr.tabIndex = 0;
      const toggle = () => {
        const next = tr.nextElementSibling;
        if (next && next.classList.contains('detail')) {next.remove(); tr.classList.remove('open'); return;}
        tr.insertAdjacentHTML('afterend', `<tr class="detail"><td colspan="${cols.length}">${detail(view[Number(tr.dataset.i)])}</td></tr>`);
        tr.classList.add('open'); widths(tr.nextElementSibling);
      };
      tr.addEventListener('click', toggle);
      tr.addEventListener('keydown', e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault(); toggle();}});
    });
    widths(host);
  };
  render();
}
/** KDV seçimine göre tutar sütunları */
export function moneyCols(vat, {net = 'v', gross = 'g', labelNet = 'KDV hariç', labelGross = 'KDV dahil'} = {}) {
  const cols = [];
  if (vat !== 'gross') cols.push({key: net, label: labelNet, right: true, money: true, total: 'sum'});
  if (vat !== 'net') cols.push({key: gross, label: labelGross, right: true, money: true, total: 'sum'});
  return cols;
}

// ----------------------------------------------------------------- grafik
const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs, parent) => {const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (parent) parent.appendChild(n); return n;};
function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), f = v / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}
/** labels + series [{name, color, values(kuruş)}] → sütun ya da çizgi; üzerine gelince ipucu */
export function chart(host, {labels, series, type = 'bar', height = 260, tipTitle = l => l, stacked = false}) {
  host.innerHTML = '';
  host.classList.add('chart');
  if (!labels.length || series.every(s => s.values.every(v => !v))) {host.innerHTML = empty('Bu dönemde veri yok', '', 'chart-column'); return;}
  const W = Math.max(320, host.clientWidth || 640), H = height, pad = {l: 56, r: 10, t: 12, b: 28};
  const totals = labels.map((_, i) => series.reduce((s, x) => s + Math.max(0, x.values[i] || 0), 0));
  const max = niceMax(stacked ? Math.max(...totals) : Math.max(...series.flatMap(s => s.values.map(v => Math.max(0, v || 0)))));
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': series.map(s => s.name).join(', ')}, host);
  const y = v => pad.t + (H - pad.t - pad.b) * (1 - Math.max(0, v) / max);
  for (let i = 0; i <= 4; i++) {
    const v = max / 4 * i;
    el('line', {x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), class: 'grid-l'}, svg);
    const t = el('text', {x: pad.l - 8, y: y(v) + 4, 'text-anchor': 'end', class: 'axis-t'}, svg); t.textContent = tlShort(v);
  }
  const step = (W - pad.l - pad.r) / labels.length;
  const tip = document.createElement('div'); tip.className = 'tip'; host.appendChild(tip);
  const showTip = (i, evt) => {
    tip.innerHTML = `<b>${esc(tipTitle(labels[i]))}</b>${series.map(s => `<div><span class="dot-c" data-bg="${s.color}"></span> ${esc(s.name)}: ${tl(s.values[i])}</div>`).join('')}`;
    widths(tip);
    const r = host.getBoundingClientRect();
    let x = evt.clientX - r.left + 12; if (x + 220 > r.width) x = evt.clientX - r.left - 220;
    tip.style.left = Math.max(0, x) + 'px'; tip.style.top = Math.max(0, evt.clientY - r.top - 20) + 'px'; tip.classList.add('on');
  };
  labels.forEach((lab, i) => {
    const t = el('text', {x: pad.l + i * step + step / 2, y: H - 8, 'text-anchor': 'middle', class: 'axis-t'}, svg); t.textContent = lab.length === 7 ? monthLabel(lab) : lab;
    const hit = el('rect', {x: pad.l + i * step, y: pad.t, width: step, height: H - pad.t - pad.b, fill: 'transparent'}, svg);
    hit.addEventListener('mousemove', e => showTip(i, e)); hit.addEventListener('mouseleave', () => tip.classList.remove('on'));
  });
  if (type === 'line') {
    series.forEach(s => {
      const pts = s.values.map((v, i) => [pad.l + i * step + step / 2, y(v || 0)]);
      el('path', {d: pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' '), class: 'ln', stroke: s.color}, svg);
      pts.forEach(p => el('circle', {cx: p[0], cy: p[1], r: 3.5, fill: s.color, class: 'pt'}, svg));
    });
  } else {
    const groupW = Math.min(step * 0.72, stacked ? 34 : 18 * series.length + 6);
    labels.forEach((_, i) => {
      let base = 0;
      series.forEach((s, j) => {
        const v = Math.max(0, s.values[i] || 0); if (!v) return;
        const bw = stacked ? groupW : groupW / series.length - 2;
        const x = pad.l + i * step + (step - groupW) / 2 + (stacked ? 0 : j * (bw + 2));
        const top = y(base + v), h = y(base) - top;
        const r = el('rect', {x, y: top, width: Math.max(1, bw), height: Math.max(0, stacked ? h - 1 : h), rx: 3, fill: s.color, class: 'bar'}, svg);
        r.addEventListener('mousemove', e => showTip(i, e)); r.addEventListener('mouseleave', () => tip.classList.remove('on'));
        if (stacked) base += v;
      });
    });
  }
  const lg = document.createElement('div'); lg.className = 'legend';
  lg.innerHTML = series.map(s => `<span><i class="dot-c" data-bg="${s.color}"></i>${esc(s.name)}</span>`).join('');
  host.appendChild(lg); widths(host);
}
/** yatay çubuk listesi: [{label, value, sub, color}] */
export function hbars(items, {fmt = tl, color = '#3478E5', limit = 8} = {}) {
  if (!items.length) return empty('Bu seçimde kayıt yok.');
  const max = Math.max(1, ...items.map(i => Math.abs(i.value)));
  return `<div class="bars">${items.slice(0, limit).map(i => `<div class="b-row"><span>${esc(i.label)}${i.sub ? ` <small>${esc(i.sub)}</small>` : ''}</span><b class="num">${fmt(i.value)}</b>
    <div class="track"><i data-w="${Math.max(1.5, Math.abs(i.value) / max * 100).toFixed(1)}" data-bg="${i.color || color}"></i></div></div>`).join('')}</div>`;
}
// SVG fill özniteliği CSS değişkeni kabul etmez: renkler finans.css'teki belirteçlerin aynısı
export const COLORS = {lcarlie: '#3478E5', lemos: '#16A36A', moy: '#7A5AF8', kisisel: '#E5A13B', aile: '#E87BA4', ortak: '#94A3B8',
  grup: '#CBD5E1', belirsiz: '#CBD5E1', dogrudan: '#3478E5', wix: '#0EA5B7', trendyol: '#F27A1A', in: '#16A36A', out: '#DC5555',
  primary: '#3478E5'};
