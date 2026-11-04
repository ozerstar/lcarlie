// Finans Merkezi — kabuk: menü, kurum, dönem, sayfa geçişi (sahip, 02.11.2026)
// sahip, 03.11.2026: "şahsımı, MOY'u, Lemos'u ve L'CARLIÉ'yi 4 farklı başlık, 4 farklı kurum gibi yap; şu anki hâlde
// her şey birbirine giriyor" — seçili kurum her sayfanın tek konusudur; karşılaştırma sayfaları ayrı bölümdedir.
import {$, $$, api, esc, icon, iso, today, dayLabel, monthLabel, tl, errorBox, clearCache, setCsrf} from './core.js?v=13';
import {PAGES, KURUM} from './pages.js?v=13';

const saved = (() => {try {return localStorage.getItem('finans-kurum');} catch {return null;}})();
const state = {page: 'genel', scope: KURUM[saved] ? saved : 'sahsi', view: 'month', day: today(), start: '', end: '', q: ''};
const allowed = (page, kurum) => !PAGES[page].kurums || PAGES[page].kurums.includes(kurum);

function readUrl() {
  const [path, query] = location.hash.replace(/^#\/?/, '').split('?');
  const p = new URLSearchParams(query || '');
  const kurum = p.get('kurum') || p.get('scope');
  if (KURUM[kurum]) state.scope = kurum;
  state.page = PAGES[path] && allowed(path, state.scope) ? path : 'genel';
  state.view = ['day', 'week', 'month', 'year', 'range'].includes(p.get('view')) ? p.get('view') : state.view;
  if (/^\d{4}-\d{2}-\d{2}$/.test(p.get('day') || '')) state.day = p.get('day');
  if (/^\d{4}-\d{2}-\d{2}$/.test(p.get('start') || '')) state.start = p.get('start');
  if (/^\d{4}-\d{2}-\d{2}$/.test(p.get('end') || '')) state.end = p.get('end');
  state.q = p.get('q') || '';
}
export function go(page, extra = {}) {
  Object.assign(state, extra);
  const p = new URLSearchParams({kurum: state.scope, view: state.view, day: state.day});
  if (state.view === 'range') {p.set('start', state.start); p.set('end', state.end);}
  if (state.q) p.set('q', state.q);
  const target = page || state.page;
  const hash = `#/${allowed(target, state.scope) ? target : 'genel'}?${p}`;
  if (location.hash === hash) render(); else location.hash = hash;
}

/** dönemin sınırları (sayfaların fatura satırlarını süzmesi için) */
export function periodBounds() {
  const d = new Date(state.day + 'T12:00:00');
  if (state.view === 'day') return {start: state.day, end: state.day, label: dayLabel(state.day)};
  if (state.view === 'week') {
    const s = new Date(d); s.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const e = new Date(s); e.setDate(s.getDate() + 6);
    return {start: iso(s), end: iso(e), label: `${dayLabel(iso(s))} – ${dayLabel(iso(e))}`};
  }
  if (state.view === 'month') {
    const s = new Date(d.getFullYear(), d.getMonth(), 1), e = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    return {start: iso(s), end: iso(e), label: monthLabel(state.day.slice(0, 7), true)};
  }
  if (state.view === 'year') return {start: `${d.getFullYear()}-01-01`, end: `${d.getFullYear()}-12-31`, label: `${d.getFullYear()} yılı`};
  return {start: state.start, end: state.end, label: `${dayLabel(state.start)} – ${dayLabel(state.end)}`};
}

function shift(n) {
  if (state.view === 'range') return;
  const d = new Date(state.day + 'T12:00:00');
  if (state.view === 'day') d.setDate(d.getDate() + n);
  else if (state.view === 'week') d.setDate(d.getDate() + 7 * n);
  else if (state.view === 'month') d.setMonth(d.getMonth() + n, 1);
  else d.setFullYear(d.getFullYear() + n, 0, 1);
  go(null, {day: iso(d)});
}

function syncChrome() {
  const page = PAGES[state.page];
  $$('.nav a').forEach(a => {
    a.classList.toggle('on', a.dataset.page === state.page);
    a.href = `#/${a.dataset.page}?` + location.hash.split('?')[1];
    a.closest('li').hidden = !allowed(a.dataset.page, state.scope);
  });
  $$('.kurum [data-kurum]').forEach(b => {const on = b.dataset.kurum === state.scope; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on));});
  $('#kurumName').textContent = KURUM[state.scope];
  document.body.dataset.kurum = page.cross ? 'cross' : state.scope;
  $$('[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === state.view));
  const range = state.view === 'range';
  $('#dayIn').hidden = range; $('#startIn').hidden = !range; $('#endIn').hidden = !range;
  $('#prevP').hidden = range; $('#nextP').hidden = range;
  $('#dayIn').value = state.day; $('#startIn').value = state.start; $('#endIn').value = state.end;
  $('#pageKurum').textContent = page.cross ? 'Kurumlar arası' : KURUM[state.scope];
  $('#pageTitle').textContent = page.title;
  $('#pageSub').textContent = page.sub;
  document.title = `${page.cross ? '' : KURUM[state.scope] + ' · '}${page.title} · Finans Merkezi`;
  $('#periodBar').hidden = page.noPeriod === true;
  $('#globalSearch').value = state.page === 'islemler' ? state.q : '';
}

let renderSeq = 0;
let authed = false;  // hashchange can fire before the session check: nothing is drawn until it passes
async function render() {
  if (!authed) return;
  readUrl();
  if (state.view === 'range' && (!state.start || !state.end)) {
    const b = new Date(state.day + 'T12:00:00');
    state.start = iso(new Date(b.getFullYear(), b.getMonth(), 1)); state.end = state.day;
  }
  syncChrome();
  closeMenu();
  const seq = ++renderSeq, host = $('#view');
  try {
    await PAGES[state.page].render(host, ctx(), () => seq === renderSeq);
  } catch (x) {
    if (seq === renderSeq) host.innerHTML = errorBox(x.message);
  }
}

/** sayfaların ortak verisi: hepsi önbellekli, aynı istek bir kez gider */
function ctx() {
  const b = periodBounds();
  const years = [];
  for (let y = Number(b.start.slice(0, 4)); y <= Number(b.end.slice(0, 4)); y++) years.push(y);
  return {
    state: {...state}, bounds: b, go,
    overview: () => api('/api/money/overview', {ws: state.scope, view: state.view, day: state.day,
      start: state.view === 'range' ? state.start : '', end: state.view === 'range' ? state.end : ''}),
    /** fatura satırları (Lemos + MOY) dönemin yıllarından; kart süzgeçleri bunları süzer */
    analysis: async () => {
      const all = await Promise.all(years.map(y => api('/api/money/invoice-analysis', {book: 'lemos', year: y})));
      const first = all[0];
      return {...first, rows: all.flatMap(a => a.rows || []), years};
    },
    ledger: () => api('/api/money/report', {book: 'kisisel', view: 'month', day: today()}),
    invoices: (book, month) => api('/api/money/invoices', {book, month}),
  };
}

// --------------------------------------------------------------- olaylar
function closeMenu() {$('#side').classList.remove('open'); $('#overlay').classList.remove('open');}
function wire() {
  $('#dateLine').textContent = new Date().toLocaleDateString('tr-TR', {weekday: 'long', day: '2-digit', month: 'long', year: 'numeric'}).toLocaleUpperCase('tr-TR');
  $$('.kurum [data-kurum]').forEach(b => b.addEventListener('click', () => {
    try {localStorage.setItem('finans-kurum', b.dataset.kurum);} catch { /* kurum hatırlanmazsa yine çalışır */ }
    go(PAGES[state.page].cross ? 'genel' : null, {scope: b.dataset.kurum});
  }));
  $$('[data-view]').forEach(b => b.addEventListener('click', () => go(null, {view: b.dataset.view})));
  $('#dayIn').addEventListener('change', e => e.target.value && go(null, {day: e.target.value}));
  $('#startIn').addEventListener('change', e => e.target.value && go(null, {start: e.target.value}));
  $('#endIn').addEventListener('change', e => e.target.value && go(null, {end: e.target.value}));
  $('#prevP').addEventListener('click', () => shift(-1));
  $('#nextP').addEventListener('click', () => shift(1));
  $('#menuBtn').addEventListener('click', () => {$('#side').classList.add('open'); $('#overlay').classList.add('open');});
  $('#overlay').addEventListener('click', closeMenu);
  // sahip: "finans bölümüne girince bir önceki bölüme geçemiyorum" — finans içinde geri, değilse Jarvis'e
  const entry = history.length;
  $('#backBtn').addEventListener('click', () => {if (history.length > entry || document.referrer.startsWith(location.origin)) history.back(); else location.href = '/';});
  $('#globalSearch').addEventListener('keydown', e => {if (e.key === 'Enter') go('islemler', {q: e.target.value.trim()});});
  const toggle = (btn, pop, fill) => btn.addEventListener('click', async ev => {
    ev.stopPropagation();
    const open = pop.hidden;
    $$('.pop').forEach(p => {p.hidden = true;});
    if (open) {pop.hidden = false; btn.setAttribute('aria-expanded', 'true'); await fill(pop);} else btn.setAttribute('aria-expanded', 'false');
  });
  toggle($('#bellBtn'), $('#bellPop'), fillBell);
  toggle($('#meBtn'), $('#mePop'), pop => {
    pop.innerHTML = `<a href="/harcamalar.html">${icon('wallet', 'sm')}Harcamalarım (düzenleme ve yükleme)</a>
      <a href="/">${icon('layout-dashboard', 'sm')}Jarvis ana sayfa</a>
      <a href="#" id="refreshAll">${icon('arrow-up-down', 'sm')}Verileri tazele</a>`;
    $('#refreshAll').addEventListener('click', e => {e.preventDefault(); clearCache(); render();});
  });
  document.addEventListener('click', e => {if (!e.target.closest('.pop')) $$('.pop').forEach(p => {p.hidden = true;});});
  document.addEventListener('keydown', e => {if (e.key === 'Escape') {$$('.pop').forEach(p => {p.hidden = true;}); closeMenu();}});
  window.addEventListener('hashchange', render);
  let rt; window.addEventListener('resize', () => {clearTimeout(rt); rt = setTimeout(() => {if (PAGES[state.page].redraw) render();}, 250);});
}
async function fillBell(pop) {
  pop.innerHTML = '<div class="row"><small>Yükleniyor…</small></div>';
  try {
    const r = await ctx().ledger();
    const owed = (r.agreements || []).filter(a => a.owed_closed_months > 0);
    const q = r.report?.unknown_all || {count: 0, total: 0};
    const items = [
      ...owed.map(a => `<a href="#/odemeler">${icon('clock', 'sm')}<span><b>${esc(a.party)}</b><br><small>Borç ${tl(a.owed_closed_months)}</small></span></a>`),
      q.count ? `<a href="/harcamalar.html">${icon('circle-alert', 'sm')}<span><b>${q.count} hareketin açıklaması eksik</b><br><small>${tl(q.total)} · “Bu ne için?”</small></span></a>` : '',
    ].filter(Boolean);
    pop.innerHTML = items.length ? items.join('') : '<div class="row"><small>Bekleyen bildirim yok.</small></div>';
  } catch (x) {pop.innerHTML = `<div class="row"><small>${esc(x.message)}</small></div>`;}
}
async function bellCount() {
  try {
    const r = await ctx().ledger();
    const n = (r.agreements || []).filter(a => a.owed_closed_months > 0).length + ((r.report?.unknown_all?.count || 0) ? 1 : 0);
    if (n) $('#bellBtn').insertAdjacentHTML('beforeend', `<span class="dot">${n}</span>`);
  } catch { /* bildirim sayısı yoksa sayfa yine açılır */ }
}

async function init() {
  wire();
  try {
    const s = await api('/api/session');
    if (!s.authenticated) {
      $('#view').innerHTML = errorBox('Finans Merkezi’ni görmek için önce Jarvis’e giriş yapın.') + '<p><a class="btn primary" href="/giris.html">Giriş yap</a></p>';
      $('#periodBar').hidden = true;
      return;
    }
    $('#meName').textContent = s.username === 'operator' ? 'Yönetici' : s.username;
    setCsrf(s.csrf_token);
    authed = true;
  } catch (x) {$('#view').innerHTML = errorBox(x.message); return;}
  if (!location.hash) go('genel'); else render();
  bellCount();
}
init();
