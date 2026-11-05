/* Ürün görsel işleri: önce görsel, sonra uyarı; uzun metin kapalı durur (sahip 05.11.2026). */
let csrf = '', current = null, job = null, visual = {}, product = '';
const $ = id => document.getElementById(id);
const STATUS = {QUEUED: ['Sırada', 'orta'], RUNNING: ['Denetleniyor', 'orta'], REVIEW_PENDING: ['Ekip görüşü bekliyor', 'orta'],
  CHANGES_REQUIRED: ['Düzeltme istendi', 'kotu'], READY_FOR_OWNER: ['Senin onayına hazır', 'orta'],
  PUBLISHED: ['Sitede yayında', 'ok'], FAILED: ['Denetim başarısız', 'kotu']};
const SLOT = {'01-KAPAK.jpg': 'Kapak', '02-FAYDA.jpg': 'Fayda', '03-ICERIK.jpg': 'İçerik', '04-KULLANIM.jpg': 'Kullanım', '05-RUTIN.jpg': 'Rutin'};
const DEPT = {WEB: 'Web ve dönüşüm', TASARIM: 'Tasarım ve üretim'};
const DECISION = {APPROVE: 'Onay', CHANGES_REQUIRED: 'Düzeltme gerekli'};
const productName = p => p.replace(/^\d+-/, '').replace(/-/g, ' ').toLocaleUpperCase('tr-TR');
const imageUrl = (id, p, slot, small) => `/api/image-jobs/${id}/images/${p}/${slot}${small ? '?boy=kucuk' : ''}`;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v; else if (k.startsWith('on')) node[k] = v; else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c.nodeType ? c : document.createTextNode(String(c)));
  return node;
}
// Ekip görüşleri model çıktısıdır: biçim işaretleri (**, ##, ---) temizlenir, ilk cümle özet olur.
function plain(text) {
  return String(text || '').replace(/\*\*|__|`/g, '').replace(/^#+\s*/gm, '').replace(/^\s*-{3,}\s*$/gm, '')
    .replace(/\s+##\s*/g, '\n').replace(/\s-\s(?=\S)/g, '\n• ').replace(/\n{3,}/g, '\n\n').trim();
}
function firstSentence(text) {
  const t = plain(text).replace(/\n+/g, ' ');
  const m = t.match(/^(.{20,220}?[.!?])(\s|$)/);
  return m ? m[1] : t.slice(0, 200) + (t.length > 200 ? '…' : '');
}
async function api(url, options = {}) {
  const r = await fetch(url, {credentials: 'same-origin', ...options});
  const v = await r.json();
  if (!r.ok) throw Error(v.error || `İşlem tamamlanamadı (${r.status}).`);
  return v;
}
function badge(status) {
  const [text, tone] = STATUS[status] || [status || 'Bilinmiyor', 'orta'];
  return el('span', {class: `ij-rozet ij-${tone}`}, text);
}
function issuesOf(key) {
  const x = visual[key]?.result?.vision || {};
  return [...(x.web_issues || []).map(t => ['Web', t]), ...(x.design_issues || []).map(t => ['Tasarım', t]),
    ...(x.needs_human_check || []).map(t => ['Kontrol et', t])];
}

async function init() {
  try {
    const s = await api('/api/session');
    if (!s.authenticated) { location.href = '/'; return; }
    csrf = s.csrf_token; await refresh();
  } catch (e) { $('uploadStatus').textContent = e.message; }
}
async function refresh() {
  const data = await api('/api/image-jobs');
  const list = $('jobs'); list.replaceChildren();
  for (const j of data.jobs) {
    const first = Object.keys(j.report.products || {}).sort()[0];
    list.append(el('button', {type: 'button', 'data-id': j.id, class: 'ij-is' + (j.id === current ? ' is-secili' : ''), 'aria-pressed': j.id === current, onclick: () => show(j.id)},
      first ? el('img', {src: imageUrl(j.id, first, '01-KAPAK.jpg', true), alt: '', loading: 'lazy'}) : el('span', {class: 'ij-bos'}),
      el('span', {class: 'ij-is-metin'},
        el('strong', {}, `${j.report.product_count ?? 0} ürün · ${j.report.image_count ?? 0} görsel`),
        el('small', {}, new Date(j.created * 1000).toLocaleString('tr-TR', {dateStyle: 'medium', timeStyle: 'short'}))),
      badge(j.status)));
  }
  if (!data.jobs.length) list.append(el('p', {class: 'muted'}, 'Henüz görsel paketi yok.'));
  if (!current && data.jobs.length) await show(data.jobs[0].id);
}

async function show(id) {
  const changed = id !== current;
  current = id;
  document.querySelectorAll('.ij-is').forEach(b => { b.classList.toggle('is-secili', b.dataset.id === id); b.setAttribute('aria-pressed', String(b.dataset.id === id)); });
  job = await api('/api/image-jobs/' + id);
  const v = await api(`/api/image-jobs/${id}/visual-review`);
  visual = v.observations || {};
  $('detail').hidden = false;
  renderSummary(v.summary || {});
  renderWarnings();
  if (changed) { product = ''; renderProducts(); renderProduct(); }
  renderTeam();
}

function renderSummary(s) {
  const r = job.report, m = job.media_stage || {};
  $('jobTitle').replaceChildren(`${r.product_count ?? 0} ürün · ${r.image_count ?? 0} görsel `, badge(job.status));
  const lines = [];
  if (m.complete) lines.push(`Wix'e yüklendi: ${m.uploaded}/${m.total} görsel${job.status === 'PUBLISHED' ? ', ürün galerilerine bağlandı' : ''}.`);
  else lines.push('Wix aktarımı henüz tamamlanmadı.');
  lines.push(s.complete ? `${s.done || 0} görselin içeriği tek tek incelendi${s.failed ? `, ${s.failed} inceleme yapılamadı` : ''}.` : `İçerik incelemesi sürüyor: ${s.done || 0}/${r.image_count || 195}.`);
  $('jobState').textContent = lines.join(' ');
  const links = $('reports'); links.replaceChildren();
  if (s.decision_ready) links.append(el('a', {href: `/api/image-jobs/${current}/visual-decision`, target: '_blank', rel: 'noopener'}, 'Doğrulanmış karar'));
  if (s.complete) links.append(el('a', {href: `/api/image-jobs/${current}/visual-report`, target: '_blank', rel: 'noopener'}, 'Tüm görsellerin raporu'));
}

function renderWarnings() {
  const box = $('warnings'); box.replaceChildren();
  const problems = [job.error, ...(job.report.problems || [])].filter(Boolean);
  const flagged = Object.keys(visual).filter(k => issuesOf(k).length).sort();
  if (!problems.length && !flagged.length) { box.append(el('p', {class: 'ij-temiz'}, '✓ Uyarı yok: paket yapısı ve görsel incelemesi sorun bulmadı.')); return; }
  box.append(el('h3', {}, `Dikkat isteyen ${flagged.length} görsel` + (problems.length ? ` · ${problems.length} paket sorunu` : '')));
  for (const p of problems) box.append(el('p', {class: 'ij-sorun'}, p));
  const list = el('ul', {class: 'ij-uyari-liste'});
  for (const key of flagged.slice(0, 40)) {
    const [p, slot] = key.split('/'), first = issuesOf(key)[0];
    list.append(el('li', {}, el('button', {type: 'button', onclick: () => { product = p; renderProducts(); renderProduct(); $('product').scrollIntoView({behavior: 'smooth'}); }},
      el('strong', {}, `${productName(p)} · ${SLOT[slot] || slot}`), el('span', {}, `${first[0]}: ${first[1]}`))));
  }
  box.append(list);
  if (flagged.length > 40) box.append(el('p', {class: 'muted'}, `+${flagged.length - 40} görsel daha; ürün ızgarasında kırmızı noktayla işaretli.`));
}

function renderProducts() {
  const grid = $('products'); grid.replaceChildren();
  const names = Object.keys(job.report.products || {}).sort();
  if (!product || !names.includes(product)) product = names[0] || '';
  for (const p of names) {
    const warn = Object.keys(job.report.products[p] || {}).some(slot => issuesOf(`${p}/${slot}`).length);
    grid.append(el('button', {type: 'button', class: 'ij-urun' + (p === product ? ' is-secili' : ''), 'aria-pressed': p === product, onclick: () => { product = p; renderProducts(); renderProduct(); }},
      el('img', {src: imageUrl(current, p, '01-KAPAK.jpg', true), alt: '', loading: 'lazy'}),
      el('span', {}, productName(p)), warn ? el('i', {class: 'ij-nokta', title: 'Dikkat isteyen görsel var'}) : null));
  }
}

function renderProduct() {
  const box = $('product'); box.replaceChildren();
  if (!product) return;
  box.append(el('h3', {}, productName(product)));
  const row = el('div', {class: 'ij-slotlar'});
  for (const slot of Object.keys(job.report.products[product] || {}).sort()) {
    const key = `${product}/${slot}`, obs = visual[key], issues = issuesOf(key), x = obs?.result?.vision || {};
    row.append(el('figure', {class: 'ij-slot' + (issues.length ? ' is-uyari' : '')},
      el('a', {href: imageUrl(current, product, slot), target: '_blank', rel: 'noopener', 'aria-label': `${productName(product)} ${SLOT[slot] || slot} görselini tam boy aç`},
        el('img', {src: imageUrl(current, product, slot, true), alt: `${productName(product)} ${SLOT[slot] || slot}`, loading: 'lazy'})),
      el('figcaption', {},
        el('strong', {}, SLOT[slot] || slot),
        ...issues.map(([kind, text]) => el('p', {class: 'ij-not'}, el('b', {}, kind + ': '), text)),
        obs?.status === 'DONE' && (x.visual_description || x.visible_text)
          ? el('details', {}, el('summary', {}, 'Görselde ne var?'), x.visual_description ? el('p', {}, x.visual_description) : null, x.visible_text ? el('p', {class: 'muted'}, 'Okunan yazı: ' + x.visible_text) : null)
          : obs && obs.status !== 'DONE' ? el('p', {class: 'muted'}, obs.status === 'PENDING' ? 'İnceleme sırasını bekliyor.' : 'İnceleme yapılamadı.') : null)));
  }
  box.append(row);
}

function renderTeam() {
  const box = $('teamNotes'); box.replaceChildren();
  for (const n of job.team_notes || []) {
    const text = n.comment || n.error || '';
    box.append(el('details', {class: 'ij-gorus'},
      el('summary', {}, el('strong', {}, DEPT[n.department] || n.department), ' · ', firstSentence(text)),
      el('div', {class: 'ij-gorus-metin'}, plain(text))));
  }
  if (!(job.team_notes || []).length) box.append(el('p', {class: 'muted'}, 'Henüz ekip görüşü yok.'));
  const reviews = $('reviews'); reviews.replaceChildren();
  for (const r of job.reviews || []) reviews.append(el('p', {}, el('strong', {}, `${DEPT[r.department] || r.department} · ${DECISION[r.decision] || r.decision}`), ` — ${r.reviewer}: ${r.comment}`));
  if (!(job.reviews || []).length) reviews.append(el('p', {class: 'muted'}, 'Henüz insan değerlendirmesi yok.'));
}

$('upload').onclick = async () => {
  const f = $('file').files[0]; if (!f) return;
  $('upload').disabled = true; $('uploadStatus').textContent = 'Yükleniyor…';
  try {
    const j = await api('/api/image-jobs/upload', {method: 'POST', headers: {'X-CSRF-Token': csrf, 'X-Filename': f.name, 'Content-Type': 'application/zip'}, body: f});
    $('uploadStatus').textContent = 'Paket alındı, denetleniyor.'; current = null; await refresh(); await show(j.id);
  } catch (e) { $('uploadStatus').textContent = e.message; } finally { $('upload').disabled = false; }
};
$('save').onclick = async () => {
  if (!current) return;
  try {
    await api(`/api/image-jobs/${current}/review`, {method: 'POST', headers: {'X-CSRF-Token': csrf, 'Content-Type': 'application/json'},
      body: JSON.stringify({department: $('department').value, decision: $('decision').value, comment: $('comment').value})});
    $('reviewStatus').textContent = 'Görüş kaydedildi.'; await show(current);
  } catch (e) { $('reviewStatus').textContent = e.message; }
};
$('askTeam').onclick = async () => {
  if (!current) return;
  $('askTeam').disabled = true; $('teamStatus').textContent = 'Jarvis ekip görüşü isteniyor…';
  try {
    await api(`/api/image-jobs/${current}/team-review`, {method: 'POST', headers: {'X-CSRF-Token': csrf, 'Content-Type': 'application/json'}, body: JSON.stringify({department: $('department').value})});
    $('teamStatus').textContent = 'Görüş kaydedildi.'; await show(current);
  } catch (e) { $('teamStatus').textContent = e.message; } finally { $('askTeam').disabled = false; }
};
init();
// Yalnız iş sürerken özet tazelenir; galeri yeniden çizilmez (görseller her 10 sn'de baştan yüklenmesin).
setInterval(async () => {
  if (!current || !job || !['QUEUED', 'RUNNING'].includes(job.status) && job.visual_review?.complete) return;
  try {
    job = await api('/api/image-jobs/' + current);
    const v = await api(`/api/image-jobs/${current}/visual-review`); visual = v.observations || {};
    renderSummary(v.summary || {}); renderWarnings();
  } catch (e) { /* bir sonraki turda yeniden denenir */ }
}, 15000);
