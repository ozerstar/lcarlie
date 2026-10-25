'use strict';
/* L'CARLIE OS -- Web Console frontend.
 *
 * No secrets stored in localStorage/sessionStorage: only the CSRF token is
 * kept in memory (a JS variable), the session id lives in an HttpOnly
 * cookie the browser sends automatically and this code never reads.
 *
 * Every value rendered here comes from an endpoint that already exists
 * (/api/session, /api/status, /api/activity, /api/proposals, /api/plan,
 * /api/chat/stream). Where the backend has no measurement -- host CPU, RAM
 * and disk utilisation -- the UI prints N/A rather than a plausible number;
 * an operator console that invents a percentage is worse than one that
 * admits the gap.
 */

const state = {
  csrfToken: null,
  username: null,
  statusPollTimer: null,
  activityPollTimer: null,
  view: 'home',
  lastActivity: { audit: [], findings: [] },
  // Last plan and, when the backend ever returns one, the run record that
  // went with it. Both start null: nothing on the execution surface is
  // rendered from a default.
  lastPlan: null,
  lastRun: null,
  planInFlight: false,
  lastVisualState: null,
  // Sesli konuşma durumu: idle | listening | thinking | speaking.
  // Burada duruyor çünkü applyLoopCoreState() -- dosyanın çok yukarısında --
  // ses ekrandayken çekirdeği geri almamalı; `voice` nesnesi orada henüz
  // tanımlı olmadığı için ona bakamaz.
  voiceMode: 'idle',
};

function qs(id) { return document.getElementById(id); }

function chatId() {
  const key = 'jarvis-work-chat-id';
  let id = sessionStorage.getItem(key);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id || '')) {
    id = crypto.randomUUID();
    sessionStorage.setItem(key, id);
  }
  return id;
}

qs('newChatBtn').addEventListener('click', () => {
  if (activeStreamController) return;
  sessionStorage.setItem('jarvis-work-chat-id', crypto.randomUUID());
  qs('chatLog').replaceChildren();
  qs('chatLog').hidden = true;
  qs('chatInput').value = '';
  qs('chatInput').focus();
});

async function api(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  if (state.csrfToken && options.method && options.method !== 'GET') {
    headers['X-CSRF-Token'] = state.csrfToken;
  }
  const res = await fetch(path, Object.assign({ credentials: 'same-origin' }, options, { headers }));
  let body = null;
  try { body = await res.json(); } catch (_) { /* no body */ }
  // A 401 means the session lapsed (idle 30 min / absolute 12 h). Drop straight
  // back to the login card instead of letting polls and POSTs keep firing
  // against a dead session. /api/session never 401s -- it answers
  // {authenticated:false} with 200 -- so this cannot loop.
  if (res.status === 401 && state.csrfToken) {
    state.csrfToken = null;
    showLogin();
  }
  return { ok: res.ok, status: res.status, body };
}


/* 🔴 BU İKİSİ YOKTU. TASARIM ve ASİSTAN kodu getJSON/postJSON çağırıyordu;
 * kod tabanında yalnız api(path, options) var ve {ok,status,body} dönüyor.
 * Sözdizimi denetimi tanımsız fonksiyonu yakalamaz -- hata ancak o satır
 * çalışınca çıkar. İnce bir sarmalayıcı ile kapatıyoruz. */
async function getJSON(path) {
  const { ok, status, body } = await api(path);
  if (!ok) throw new Error((body && body.error) || ('HTTP ' + status));
  return body || {};
}

async function postJSON(path, veri) {
  const { ok, status, body } = await api(path, {
    method: 'POST', body: JSON.stringify(veri || {}) });
  if (!ok) throw new Error((body && body.error) || ('HTTP ' + status));
  return body || {};
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  return isNaN(d.getTime()) ? '' : d.toLocaleString('tr-TR');
}

/* ---------------- auth ---------------- */
async function checkSession() {
  const { body } = await api('/api/session');
  if (body && body.authenticated) {
    state.csrfToken = body.csrf_token;
    state.username = body.username;
    showApp();
  } else {
    showLogin();
  }
}

function showLogin() {
  qs('loginView').hidden = false;
  qs('appView').hidden = true;
  stopPolling();
}

function showApp() {
  qs('loginView').hidden = true;
  qs('appView').hidden = false;
  const name = state.username || '—';
  qs('opName').textContent = name;
  qs('opAvatar').textContent = name.slice(0, 2).toLocaleUpperCase('tr-TR');
  startPolling();
  refreshAll();
  const requestedView = new URLSearchParams(window.location.search).get('view');
  if (requestedView && Object.hasOwn(VIEWS, requestedView)) {
    const navButton = document.querySelector(`.nav-item[data-view="${requestedView}"]`);
    if (navButton && !navButton.disabled) setView(requestedView);
  }
}

function refreshAll() {
  refreshStatus();
  refreshActivity();
  refreshProposals();
}

qs('loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const username = qs('loginUser').value.trim();
  const password = qs('loginPass').value;
  qs('loginError').hidden = true;
  const { ok, status, body } = await api('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) });
  if (ok && body && body.ok) {
    state.csrfToken = body.csrf_token;
    state.username = body.username;
    qs('loginPass').value = '';
    showApp();
  } else {
    const msg = status === 429
      ? `Çok fazla deneme. ${body && body.retry_after_s ? body.retry_after_s + ' sn sonra tekrar deneyin.' : ''}`
      : 'Giriş bilgileri hatalı.';
    qs('loginError').textContent = msg;
    qs('loginError').hidden = false;
  }
});

qs('logoutBtn').addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' });
  state.csrfToken = null;
  showLogin();
});

/* ---------------- navigation ----------------
 * Only views backed by an endpoint that already exists are reachable.
 * VERİ / AJANLAR / RAPORLAR / AYARLAR carry the disabled attribute in the
 * markup: they are placeholders for capabilities the backend does not have
 * yet, and clicking them must not pretend otherwise. */
const VIEWS = {
  satislar: 'viewSatislar', kargo: 'viewKargo', musteri: 'viewMusteri',
  tasarim: 'viewTasarim',
  asistan: 'viewAsistan',
  kreatifParti: 'viewKreatifParti', home: 'viewHome', analiz: 'viewAnaliz', gorevler: 'viewGorevler',
                veri: 'viewVeri', ajanlar: 'viewAjanlar', fiyat: 'viewFiyat',
                raporlar: 'viewRaporlar', ayarlar: 'viewAyarlar',
                eticaret: 'viewEticaret', reklam: 'viewReklam',
                hafiza: 'viewHafiza', ekip: 'viewEkip',
                sistem: 'viewSistem', isler: 'viewIsler',
                saha: 'viewSaha', katalog: 'viewKatalog',
                uretilenler: 'viewUretilenler',
                gelenkutusu: 'viewGelenKutusu' };

function setView(name) {
  if (!VIEWS[name]) return;
  state.view = name;
  Object.entries(VIEWS).forEach(([key, id]) => { qs(id).hidden = key !== name; });
  navAktifGrubuAc(name);
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.view === name);
  });
  if (name === 'gorevler') { refreshActivity(); refreshProposals(); refreshOrchestration(); }
  if (name === 'fiyat') loadFiyatMatrisi();
  if (name === 'eticaret') loadUrunAlanlari();
  if (name === 'satislar') loadSatislar();
  if (name === 'kargo') loadKargo();
  if (name === 'musteri') loadMusteri();
  if (name === 'reklam') loadKreatif();
  if (name === 'sistem') loadSistem();
  if (name === 'isler') loadIsler();
  if (name === 'saha') loadSaha();
  if (name === 'katalog') { loadKatalog(); loadIgPlan(); }
  if (name === 'uretilenler') loadUretilenler();
  if (name === 'gelenkutusu') loadGelenKutusu();
  if (name === 'kreatifParti') loadKreatifParti();
  if (name === 'tasarim') tasarimYukle();
  if (name === 'asistan') asistanYukle();
  if (name === 'home') anaHaberYukle();
  if (name === 'hafiza') loadHafiza();
  if (PANEL_SECTIONS[name]) loadSection(name);
}

function renderViewSearch() {
  const query = qs('viewSearchInput').value.trim().toLocaleLowerCase('tr-TR');
  const results = qs('viewSearchResults');
  results.replaceChildren();
  const matches = [...document.querySelectorAll('#mainNav .nav-item:not(:disabled)')]
    .filter((button) => button.textContent.toLocaleLowerCase('tr-TR').includes(query));
  for (const navButton of matches) {
    const option = document.createElement('button');
    option.type = 'button';
    option.textContent = navButton.textContent.trim();
    option.addEventListener('click', () => {
      setView(navButton.dataset.view);
      qs('viewSearchDialog').close();
    });
    results.append(option);
  }
  if (!matches.length) {
    const empty = document.createElement('p');
    empty.textContent = 'Bu adla bir bölüm bulunamadı.';
    results.append(empty);
  }
}

qs('quickSearch').addEventListener('click', () => {
  if (qs('viewSearchDialog').open) {
    qs('viewSearchInput').focus();
    return;
  }
  qs('viewSearchInput').value = '';
  renderViewSearch();
  qs('viewSearchDialog').showModal();
  qs('viewSearchInput').focus();
});
qs('viewSearchClose').addEventListener('click', () => qs('viewSearchDialog').close());
qs('viewSearchInput').addEventListener('input', renderViewSearch);
qs('viewSearchInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    qs('viewSearchResults').querySelector('button')?.click();
  }
});
document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !qs('appView').hidden) {
    event.preventDefault();
    qs('quickSearch').click();
  }
});
qs('quickChat').addEventListener('click', () => qs('chatInput').focus());
qs('quickApprovals').addEventListener('click', () => setView('gorevler'));

qs('mainNav').addEventListener('click', (event) => {
  const btn = event.target.closest('.nav-item');
  if (!btn || btn.disabled) return;
  setView(btn.dataset.view);
});

/* "N öneri onay bekliyor" sayacı tıklanabilir.
 * Sayıyı görmek yetmiyordu: sahip sayıyı görüp nereye bakacağını
 * aramak zorunda kalıyordu. Gösterge kendi hedefine götürmezse
 * bilgi değil, ek iştir.
 * CSP inline onclick'e izin vermiyor; bağlama burada yapılır.
 * div olduğu için klavyeyle ulaşım ayrıca eklenir -- role=button
 * tek başına tuşları çalıştırmaz, yalnız ekran okuyucuya söyler. */
(() => {
  const onayKart = qs('statApprovalsKart');
  if (!onayKart) return;
  const gorevlereGit = () => setView('gorevler');
  onayKart.addEventListener('click', gorevlereGit);
  onayKart.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      gorevlereGit();
    }
  });
})();

/* ---------------- polling ---------------- */
function startPolling() {
  stopPolling();
  state.statusPollTimer = setInterval(refreshStatus, 12000);
  state.activityPollTimer = setInterval(() => { refreshActivity(); refreshProposals(); }, 15000);
}
function stopPolling() {
  if (state.statusPollTimer) clearInterval(state.statusPollTimer);
  if (state.activityPollTimer) clearInterval(state.activityPollTimer);
}
document.addEventListener('visibilitychange', () => {
  document.body.classList.toggle('tab-hidden', document.hidden);
  if (document.hidden) { stopPolling(); } else if (!qs('appView').hidden) { startPolling(); refreshStatus(); }
});

/* ---------------- clock ---------------- */
function tickClock() {
  const now = new Date();
  qs('tbTime').textContent = now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  qs('tbDate').textContent = now.toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' }).toLocaleUpperCase('tr-TR');
}
setInterval(tickClock, 1000);
tickClock();

/* ---------------- status: core state + right panel ---------------- */
const CORE_STATE_TEXT = {
  IDLE: 'HAZIR',
  PROPOSING: 'ANALİZLİYOR',
  WAITING_APPROVAL: 'ONAY BEKLİYOR',
  OFFLINE: 'ÇEVRİMDIŞI',
};

/* While a request is being planned or a run record is on screen, the core
 * shows that instead of the idle loop state. The override is cleared as soon
 * as the execution surface has nothing live to say, so /api/status goes back
 * to driving the core. */
function applyCoreState(key, label) {
  const core = qs('jarvisCore');
  if (!core) return;
  core.setAttribute('class', 'core-svg core-state-' + key);
  qs('coreStateLabel').textContent = label;
}

/* Puts the core back on the last real /api/status reading.
 * Ses açıkken (dinliyor/düşünüyor/konuşuyor) çekirdek onu gösterir; 12
 * saniyelik durum yoklaması araya girip etiketi geri almasın. */
function applyLoopCoreState() {
  if (state.voiceMode !== 'idle') return;
  const visual = state.lastVisualState || 'IDLE';
  applyCoreState(visual.toLowerCase(), CORE_STATE_TEXT[visual] || visual.replace(/_/g, ' '));
}

function flag(value, onText, offText, onCls, offCls) {
  if (value === null || value === undefined) return ['BİLİNMİYOR', 's-warn'];
  return value ? [onText, onCls] : [offText, offCls];
}

function renderServices(body) {
  const health = (body.company_memory && body.company_memory.health) || null;
  const memoryOk = !!(body.company_memory && body.company_memory.healthy);
  const contract = body.action_firewall ? body.action_firewall.contract_valid : null;
  const rows = [
    ['Şirket verileri', memoryOk ? ['SAĞLIKLI', 's-ok'] : ['HATA', 's-error']],
    ['İşlem güvenliği', contract === null || contract === undefined
      ? ['BİLİNMİYOR', 's-warn'] : (contract ? ['SÖZLEŞME GEÇERLİ', 's-ok'] : ['GEÇERSİZ', 's-error'])],
    ['Yapay zekâ hizmeti', flag(health && health.ai_worker_enabled, 'AÇIK', 'KAPALI', 's-ok', 's-off')],
    ['İşlem hizmeti', flag(health && health.action_worker_enabled, 'AÇIK', 'KAPALI', 's-ok', 's-off')],
    ['Dış İşlem Önerileri', body.external_proposals_enabled ? ['ONAYA AÇIK', 's-warn'] : ['KAPALI', 's-off']],
    ['Otomatik Dış İşlem', body.external_actions_enabled ? ['AÇIK', 's-error'] : ['KAPALI', 's-ok']],
  ];
  qs('svcList').innerHTML = rows.map(([label, [text, cls]]) =>
    `<li><span>${escapeHtml(label)}</span><span class="svc-state ${cls}">${escapeHtml(text)}</span></li>`
  ).join('');
}

function renderQueue(health) {
  const rows = [
    ['Açık görev', 'open_tasks', false],
    ['Kiralanmış görev', 'leased_tasks', false],
    ['Açık yürütme', 'open_executions', false],
    ['Başarısız yürütme', 'failed_executions', true],
    ['Onaylanmış eylem', 'approved_actions', false],
  ];
  qs('queueList').innerHTML = rows.map(([label, key, alertIfPositive]) => {
    const raw = health ? health[key] : null;
    const shown = (raw === null || raw === undefined) ? '—' : String(raw);
    const cls = alertIfPositive && raw > 0 ? ' kv-alert' : '';
    return `<li><span>${escapeHtml(label)}</span><span class="kv-val${cls}">${escapeHtml(shown)}</span></li>`;
  }).join('');
}

/* ---------------- host kaynak kullanımı ----------------
 * Üç sayı da /api/status'un `host` nesnesinden gelir. Burada hiçbir değer
 * hesaplanmaz, yuvarlanmaz, tahmin edilmez: backend ölçemediyse alan null
 * gelir ve kutu N/A kalır, altında da SEBEBİ yazar. Panelin iki yönde de
 * yalan söylememesi kuralı (CR-001) burada da geçerli. */
function trNum(value) {
  return (value === null || value === undefined) ? '?' : String(value).replace('.', ',');
}

function renderMetric(valueId, subId, percent, sub) {
  const box = qs(valueId);
  if (!box) return;
  const known = percent !== null && percent !== undefined;
  box.textContent = known ? ('%' + trNum(percent)) : 'N/A';
  box.classList.toggle('m-na', !known);
  const subBox = qs(subId);
  if (subBox) subBox.textContent = sub || '';
}

function renderHostMetrics(host, reason) {
  const note = qs('mNote');
  if (!host) {
    renderMetric('mCpu', 'mCpuSub', null, '');
    renderMetric('mRam', 'mRamSub', null, '');
    renderMetric('mDisk', 'mDiskSub', null, '');
    if (note) note.textContent = reason || 'Kaynak ölçümü alınamadı.';
    return;
  }
  const cpu = host.cpu || {};
  const ram = host.ram || {};
  const disk = host.disk || {};

  const cpuSub = (cpu.percent === null || cpu.percent === undefined)
    ? (cpu.error || '')
    : trNum(cpu.cores) + ' çekirdek'
      + (cpu.load ? ' · yük ' + trNum(cpu.load[0]) : '');
  renderMetric('mCpu', 'mCpuSub', cpu.percent, cpuSub);

  const ramSub = (ram.used_gib === null || ram.used_gib === undefined)
    ? (ram.error || '')
    : trNum(ram.used_gib) + ' / ' + trNum(ram.total_gib) + ' GiB';
  renderMetric('mRam', 'mRamSub', ram.percent, ramSub);

  const diskSub = (disk.used_gib === null || disk.used_gib === undefined)
    ? (disk.error || '')
    : trNum(disk.used_gib) + ' / ' + trNum(disk.total_gib) + ' GiB';
  renderMetric('mDisk', 'mDiskSub', disk.percent, diskSub);

  if (!note) return;
  const at = typeof host.measured_at === 'string' ? host.measured_at.slice(11, 16) : '—';
  const window = cpu.window_s ? (trNum(cpu.window_s) + ' sn') : '—';
  note.textContent = 'Sunucunun kendi sayaçlarından okundu (' + at + '). '
    + 'CPU ' + window + ' aralıkta ölçüldü (/proc/stat), RAM MemAvailable\'a, '
    + 'disk ' + (disk.mount || '/') + ' bölümüne göre.';
}

function setBigStat(id, value) {
  const el = qs(id);
  const known = value !== null && value !== undefined;
  el.textContent = known ? String(value) : '—';
  el.classList.toggle('is-zero', known && Number(value) === 0);
}

async function refreshStatus() {
  const { ok, body } = await api('/api/status');
  const live = qs('tbLive');
  if (!ok || !body) {
    qs('tbLiveText').textContent = 'BAĞLANTI YOK';
    live.className = 'tb-live is-error';
    qs('quickApprovalCount').textContent = '—';
    qs('quickApprovals').classList.remove('has-pending');
    // Eski sayılar ekranda kalıp güncelmiş gibi durmasın.
    renderHostMetrics(null, 'Ölçüm alınamadı — sunucuya ulaşılamıyor.');
    return;
  }

  const visual = body.visual_state || 'IDLE';
  state.lastVisualState = visual;
  // The execution surface borrows the core only while something is in motion.
  if (!execOverride()) applyLoopCoreState();

  if (visual === 'OFFLINE') {
    qs('tbLiveText').textContent = 'ÇEVRİMDIŞI';
    live.className = 'tb-live is-error';
  } else if (visual === 'WAITING_APPROVAL') {
    qs('tbLiveText').textContent = 'ONAY BEKLİYOR';
    live.className = 'tb-live is-warn';
  } else {
    qs('tbLiveText').textContent = 'SİSTEM AKTİF';
    live.className = 'tb-live';
  }

  renderServices(body);
  renderHostMetrics(body.host, 'Bu sürüm kaynak ölçümü göndermiyor.');
  renderQueue((body.company_memory && body.company_memory.health) || null);
  setBigStat('statApprovals', body.pending_proposals);
  const pendingCount = Number(body.pending_proposals);
  qs('quickApprovalCount').textContent = Number.isFinite(pendingCount) ? String(pendingCount) : '—';
  qs('quickApprovals').classList.toggle('has-pending', Number.isFinite(pendingCount) && pendingCount > 0);
  const health = (body.company_memory && body.company_memory.health) || null;
  setBigStat('statProposals', health ? health.pending_actions : null);
}

/* ---------------- live intelligence stream ----------------
 * Findings carry a real observed_at; audit rows do not (the loop records a
 * cycle number, not a timestamp), so those are labelled by cycle instead of
 * being given an invented time. Consecutive no-change cycles are collapsed
 * into one line -- a presentation-only fold, nothing is dropped from
 * state/audit.jsonl. */
const SIGNAL_TAG = {
  red_team_objection: ['KARAR RİSKİ', 'f-redteam'],
  approval_backlog: ['ONAY BEKLİYOR', 'f-onay'],
  open_work_aging: ['GECİKEN İŞLER', 'f-operasyon'],
  open_work_concentration: ['İŞ YÜKÜ', 'f-operasyon'],
  agenda_aging: ['GÜNDEM', 'f-onay'],
  site_erisim: ['SİTE ERİŞİMİ', 'f-operasyon'],
  site_gerileme: ['SİTE HIZI', 'f-operasyon'],
  site_seo: ['ARAMA GÖRÜNÜRLÜĞÜ', 'f-onay'],
};
const AUDIT_TAG = {
  PROPOSED: ['ÖNERİ', 'f-oneri'],
  FIREWALL_REJECTED: ['HATA', 'f-hata'],
  CLAIM_FAILED: ['HATA', 'f-hata'],
  CODING_TASK_DENIED: ['HATA', 'f-hata'],
  SKIPPED_NOT_MINE: ['SİSTEM', 'f-sistem'],
  NOOP: ['SİSTEM', 'f-sistem'],
};

function auditText(row) {
  const detail = row.task_detail || {};
  switch (row.result) {
    case 'PROPOSED': return 'İncelemeniz için yeni bir öneri hazırlandı; henüz uygulanmadı.';
    case 'SKIPPED_NOT_MINE': return 'Bu iş farklı bir ekibe ait olduğu için işlem yapılmadı.';
    case 'FIREWALL_REJECTED': return 'Güvenlik kuralı bu işlemi durdurdu; işlem uygulanmadı.';
    case 'CLAIM_FAILED': return 'İş alınamadı; yeniden kontrol edilmesi gerekiyor.';
    case 'CODING_TASK_DENIED': return 'Kod değişikliği yetki sınırına takıldı; uygulanmadı.';
    default: return 'Bir sistem işlemi kaydedildi.';
  }
}
function auditSub(row) {
  const detail = row.task_detail || {};
  const bits = [];
  if (detail.task_id) bits.push(`İş #${detail.task_id}`);
  if (detail.proposal_id) bits.push(`Öneri #${detail.proposal_id}`);
  return bits.join(' · ');
}

function findingText(finding) {
  const evidence = finding.evidence || {};
  const address = evidence.url ? String(evidence.url).replace(/^https?:\/\//, '') : '';
  if (finding.signal_code === 'red_team_objection' && evidence.red_team_itirazi) {
    return `${evidence.red_team_itirazi} denetim itirazı açık; ilgili kararlar bu itirazlar incelenmeden uygulanmamalı.`;
  }
  if (finding.signal_code === 'approval_backlog' && evidence.insan_onayi_bekleyen) {
    return `${evidence.insan_onayi_bekleyen} karar sizin onayınızı bekliyor. Onaylanmadan dışarı dönük işlem yapılmayacak.`;
  }
  if (finding.signal_code === 'open_work_aging' && evidence.stale_count) {
    return `${evidence.stale_count} iş bir haftadan uzun süredir açık. En eskisi yaklaşık ${Math.round(Number(evidence.oldest_days) || 0)} gündür bekliyor.`;
  }
  if (finding.signal_code === 'agenda_aging' && evidence.stale_count) {
    return `${evidence.stale_count} gündem maddesi iki haftadan uzun süredir açık; karar verilmesi gerekebilir.`;
  }
  if (finding.signal_code === 'site_gerileme' && address) {
    const current = Number(evidence.sure);
    const previous = Number(evidence.onceki_sure);
    if (Number.isFinite(current) && Number.isFinite(previous)) {
      return `${address} sayfası yavaşladı: açılış süresi ${Math.round(previous * 10) / 10} saniyeden ${Math.round(current * 10) / 10} saniyeye çıktı.`;
    }
  }
  if (finding.signal_code === 'site_erisim' && address) {
    if (String(finding.reason || '').startsWith('Önceki HTTP hatası kapandı')) {
      return `${address} sayfası yeniden açılıyor; önceki erişim hatası giderilmiş görünüyor.`;
    }
    return `${address} sayfasına erişimde hata görüldü; bağlantı kontrol edilmeli.`;
  }
  if (finding.signal_code === 'site_seo' && address) {
    if (evidence.meta_refresh !== undefined) {
      return `${address} adresi kalıcı yönlendirme yerine sayfa içi yönlendirme kullanıyor; arama görünürlüğü etkilenebilir.`;
    }
    if (String(finding.reason || '').includes('meta description')) {
      return `${address} sayfasının arama sonuçlarında görünen açıklaması eksik.`;
    }
  }
  if (finding.signal_code === 'open_work_concentration') {
    const count = Number(evidence.count);
    const kinds = {
      CEVAPSIZ_MESAJ: 'yanıt bekleyen mesajlarda',
      URUN_GORSELSIZ: 'görseli eksik ürünlerde',
      ODENMEMIS_SIPARIS: 'ödenmemiş siparişlerde',
      FILIGRANLI_KARANTINA: 'inceleme bekleyen görsellerde',
      SINIFI_BILINMEYEN_GONDERI: 'sınıflandırılmamış gönderilerde',
    };
    const area = kinds[evidence.kind] || 'tek bir alanda';
    if (Number.isFinite(count) && count > 0) return `${count} açık iş ${area} birikmiş; görev dağılımı gözden geçirilmeli.`;
  }
  return String(finding.reason || 'Yeni bir bulgu kaydedildi.').replace(/red-team/gi, 'denetim ekibi');
}

function findingSub(finding) {
  const importance = { CRITICAL: 'Acil', WARN: 'Dikkat', WARNING: 'Dikkat', INFO: 'Bilgi' };
  return importance[finding.severity] ? `Önem: ${importance[finding.severity]}` : '';
}

function feedItem({ cls, tag, meta, text, sub, kind, index }) {
  return `<li class="${cls}"><button class="f-open" type="button" data-feed-kind="${kind}" data-feed-index="${index}" aria-label="${escapeHtml(tag)} konusunu incele: ${escapeHtml(text)}">
    <span class="f-head"><span class="f-tag">${escapeHtml(tag)}</span><span class="f-time">${escapeHtml(meta)}</span></span>
    <span class="f-text">${escapeHtml(text)}${sub ? `<span class="f-sub">${escapeHtml(sub)}</span>` : ''}</span>
    <span class="f-open-hint">Konuyu aç <span aria-hidden="true">↗</span></span>
  </button></li>`;
}

function buildFindingItems(findings) {
  const seen = new Set();
  let slowPages = 0;
  let seoIssues = 0;
  state.feedFindings = findings.slice().reverse().filter((finding) => {
    const code = finding.signal_code === 'site_seo'
      ? `${finding.signature}:${String(finding.reason).includes('meta description') ? 'description' : 'redirect'}`
      : ['site_erisim', 'site_gerileme'].includes(finding.signal_code)
        ? finding.signature || finding.reason
        : finding.signal_code || finding.signature || finding.reason;
    if (seen.has(code)) return false;
    seen.add(code);
    if (finding.signal_code === 'site_erisim'
        && String(finding.reason || '').startsWith('Önceki HTTP hatası kapandı')) return false;
    if (finding.signal_code === 'site_gerileme' && ++slowPages > 3) return false;
    if (finding.signal_code === 'site_seo' && ++seoIssues > 2) return false;
    return true;
  }).slice(0, 15);
  return state.feedFindings.map((f, index) => {
    const [tag, cls] = SIGNAL_TAG[f.signal_code]
      || [f.severity === 'CRITICAL' ? 'ACİL BULGU' : 'YENİ BULGU', f.severity === 'CRITICAL' ? 'f-redteam' : 'f-onay'];
    return feedItem({
      cls, tag,
      meta: fmtDateTime(f.observed_at),
      text: findingText(f),
      sub: findingSub(f), kind: 'finding', index,
    });
  });
}

function buildAuditItems(audit) {
  state.feedAudit = audit.slice().reverse().filter((row) => row.result !== 'NOOP').slice(0, 5);
  return state.feedAudit.map((row, index) => {
    const [tag, cls] = AUDIT_TAG[row.result] || ['SİSTEM', 'f-sistem'];
    return feedItem({
      cls, tag,
      meta: `DÖNGÜ #${row.cycle}`,
      text: auditText(row),
      sub: auditSub(row), kind: 'audit', index,
    });
  });
}

async function refreshActivity() {
  const { ok, body } = await api('/api/activity?limit=200');
  if (!ok || !body) return;
  state.lastActivity = body;

  const findingItems = buildFindingItems(body.findings || []);
  const auditItems = buildAuditItems(body.audit || []);
  const all = findingItems.concat(auditItems);

  const feed = qs('activityFeed');
  feed.innerHTML = all.length ? all.join('') : '<li class="f-sistem"><div class="f-text">Şu anda dikkat gerektiren yeni bir bulgu yok.</div></li>';
  qs('feedCount').textContent = `${findingItems.length} konu`;

  const cycleList = qs('taskCycleList');
  if (cycleList) {
    cycleList.innerHTML = auditItems.length ? auditItems.join('')
      : '<li class="f-sistem"><div class="f-text">Son kontrollerde işlem gerektiren kayıt yok.</div></li>';
    qs('taskCycleCount').textContent = `${auditItems.length} işlem`;
  }
}

/* A finding is a work entry, not just a status line. External edits still go
 * through their own approval path; the action here creates a traceable work
 * item in the existing improvement ledger. */
const FINDING_GUIDE = {
  open_work_aging: { title: 'Geciken işler', view: 'gelenkutusu', domain: 'operations', metric: 'stale_open_work', unit: 'iş', steps: ['Açık işleri ve en eski kaydı incele.', 'Sorumluyu ve bir sonraki somut adımı belirle.', 'Tamamlandığında sonucu ilgili işte doğrula.'] },
  open_work_concentration: { title: 'İş yükü', view: 'gelenkutusu', domain: 'operations', metric: 'concentrated_open_work', unit: 'iş', steps: ['Biriken iş türünü ve ilgili kayıtları incele.', 'İşleri uygun sorumlulara dağıt.', 'Kuyruğun azaldığını güncel veride doğrula.'] },
  site_seo: { title: 'Arama görünürlüğü', view: 'eticaret', domain: 'ecommerce', metric: 'seo_findings', unit: 'bulgu', steps: ['Etkilenen adresi ve sayfanın güncel açıklamasını kontrol et.', 'Eksik meta açıklamasını veya yönlendirmeyi ilgili site yönetiminde düzelt.', 'Yayın sonrası sayfayı ve arama görünürlüğünü yeniden doğrula.'] },
  site_gerileme: { title: 'Site hızı', view: 'eticaret', domain: 'ecommerce', metric: 'slow_pages', unit: 'sayfa', steps: ['Sayfanın ölçümünü yeniden yap.', 'Görsel, üçüncü taraf kodu ve sunucu gecikmesini karşılaştır.', 'Değişiklikten sonra açılış süresini tekrar ölç.'] },
  site_erisim: { title: 'Site erişimi', view: 'eticaret', domain: 'ecommerce', metric: 'inaccessible_pages', unit: 'sayfa', steps: ['Adresi şimdi yeniden aç ve hatanın sürüp sürmediğini doğrula.', 'Yönlendirme ve sunucu yanıtını incele.', 'Düzeltmeden sonra erişimi tekrar kontrol et.'] },
  approval_backlog: { title: 'Bekleyen onaylar', view: 'gorevler', domain: 'operations', metric: 'pending_approvals', unit: 'karar', steps: ['Onay kuyruğundaki her önerinin içerik ve etkisini incele.', 'Uygun olanları kendi onay ekranından karara bağla.', 'Dış işlemin gerçekten yapıldığını ayrıca doğrula.'] },
  agenda_aging: { title: 'Gündem', view: 'asistan', domain: 'strategy', metric: 'stale_agenda', unit: 'madde', steps: ['Eski gündem maddelerini ve karar sahiplerini incele.', 'Her madde için karar veya takip tarihi belirle.', 'Alınan kararı kayda geçir.'] },
  red_team_objection: { title: 'Karar riski', view: 'gorevler', domain: 'strategy', metric: 'open_objections', unit: 'itiraz', steps: ['İtirazın dayandığı kanıtı incele.', 'Eksik doğrulamayı tamamla.', 'Kararı ancak itiraz çözüldükten sonra onayla.'] },
};
let selectedFeedCase = null;

function feedEvidence(evidence) {
  const labels = { url: 'Adres', stale_count: 'Geciken kayıt', checked: 'Kontrol edilen iş', by_kind: 'Biriken iş türleri', oldest_days: 'En eski kayıt (gün)', oldest_key: 'En eski iş anahtarı', count: 'Kayıt', total: 'Toplam', sure: 'Güncel süre (sn)', onceki_sure: 'Önceki süre (sn)', kind: 'İş türü', meta_refresh: 'Sayfa içi yönlendirme' };
  const kinds = { CEVAPSIZ_MESAJ: 'Yanıt bekleyen mesaj', URUN_GORSELSIZ: 'Görseli eksik ürün', ODENMEMIS_SIPARIS: 'Ödenmemiş sipariş', FILIGRANLI_KARANTINA: 'İncelemede olan görsel', SINIFI_BILINMEYEN_GONDERI: 'Sınıflandırılmamış gönderi' };
  const rows = Object.entries(evidence || {}).map(([key, value]) => {
    const shown = key === 'by_kind' && value && typeof value === 'object'
      ? Object.entries(value).map(([type, count]) => `${kinds[type] || type}: ${count}`).join(' · ')
      : typeof value === 'object' ? JSON.stringify(value) : String(value);
    return `<div><dt>${escapeHtml(labels[key] || key.replace(/_/g, ' '))}</dt><dd>${escapeHtml(shown)}</dd></div>`;
  });
  return rows.length ? `<dl class="finding-evidence">${rows.join('')}</dl>` : '<p>Ek kanıt alanı kaydedilmemiş.</p>';
}

function openFeedCase(kind, index) {
  const row = (kind === 'finding' ? state.feedFindings : state.feedAudit)?.[index];
  if (!row) return;
  const guide = FINDING_GUIDE[row.signal_code] || { title: kind === 'audit' ? 'Sistem işlemi' : 'Yeni bulgu', view: 'gorevler', domain: 'operations', metric: 'open_findings', unit: 'bulgu', steps: ['Kaydı ve kanıtı incele.', 'Gerekli adımı bir takip işi olarak belirle.', 'Sonucu güncel veride doğrula.'] };
  const title = kind === 'finding' ? guide.title : (AUDIT_TAG[row.result] || ['Sistem işlemi'])[0];
  const summary = kind === 'finding' ? findingText(row) : auditText(row);
  const evidence = kind === 'finding' ? feedEvidence(row.evidence) : feedEvidence(row.task_detail);
  const url = row.evidence?.url;
  let sourceLink = '';
  try {
    const parsed = new URL(url);
    if (['http:', 'https:'].includes(parsed.protocol)) sourceLink = `<a href="${escapeHtml(parsed.href)}" target="_blank" rel="noopener noreferrer">Etkilenen sayfayı aç ↗</a>`;
  } catch (_) { /* no external address */ }
  selectedFeedCase = { kind, row, guide, title, summary };
  qs('findingTitle').textContent = title;
  qs('findingMeta').textContent = kind === 'finding' ? `${findingSub(row)} · ${fmtDateTime(row.observed_at)}` : `Döngü #${row.cycle || '—'} · ${auditSub(row)}`;
  qs('findingBody').innerHTML = `<p class="finding-summary">${escapeHtml(summary)}</p><h3>Kaydedilen kanıt</h3>${evidence}${sourceLink}<h3>Önerilen adımlar</h3><ol>${guide.steps.map(step => `<li>${escapeHtml(step)}</li>`).join('')}</ol>`;
  qs('findingInstruction').value = `${title}: ${summary} ${guide.steps[0]}`.slice(0, 1000);
  qs('findingQuestion').value = '';
  qs('findingStatus').textContent = '';
  qs('findingView').textContent = guide.view === 'eticaret' ? 'E-ticaret bölümünü aç' : 'İlgili bölümü aç';
  qs('findingDialog').showModal();
}

for (const id of ['activityFeed', 'taskCycleList']) {
  qs(id).addEventListener('click', (event) => {
    const button = event.target.closest('[data-feed-kind]');
    if (button) openFeedCase(button.dataset.feedKind, Number(button.dataset.feedIndex));
  });
}
qs('findingClose').addEventListener('click', () => qs('findingDialog').close());
qs('findingView').addEventListener('click', () => {
  if (!selectedFeedCase) return;
  qs('findingDialog').close();
  setView(selectedFeedCase.guide.view);
});
qs('findingAsk').addEventListener('click', () => {
  if (!selectedFeedCase) return;
  const question = qs('findingQuestion').value.trim() || 'Bu konunun nedenini, kaynaklarını ve yapmam gereken ilk adımı açıkla.';
  const message = `${selectedFeedCase.title}: ${selectedFeedCase.summary}\nSorum: ${question}`;
  qs('findingDialog').close();
  setView('asistan');
  sendMessage(message);
});
qs('findingRun').addEventListener('click', () => {
  if (!selectedFeedCase) return;
  const instruction = qs('findingInstruction').value.trim();
  if (!instruction) { qs('findingStatus').textContent = 'Önce ne inceleneceğini yazın.'; return; }
  qs('findingDialog').close();
  setView('analiz');
  qs('analizInput').value = instruction;
  analizCalistir(true);
});
qs('findingTask').addEventListener('click', async () => {
  if (!selectedFeedCase) return;
  const objective = qs('findingInstruction').value.trim();
  if (!objective) { qs('findingStatus').textContent = 'Önce yapılacak işi yazın.'; return; }
  const button = qs('findingTask');
  button.disabled = true;
  qs('findingStatus').textContent = 'Takip işi kaydediliyor…';
  const { row, guide } = selectedFeedCase;
  try {
    const { ok, body } = await api('/api/improvement', { method: 'POST', body: JSON.stringify({
      operation: 'work', source_key: `operator:finding:${crypto.randomUUID()}`,
      domain: guide.domain, objective, owner: state.username || 'operator',
      metric: guide.metric, unit: guide.unit, target: 0,
      source: `${selectedFeedCase.kind === 'audit' ? 'audit' : 'findings'}.jsonl:${String(row.signature || row.signal_code || row.result || 'audit').slice(0, 180)}`,
    }) });
    if (!ok || !body?.ok) throw new Error(body?.error || 'Takip işi kaydedilemedi.');
    qs('findingStatus').textContent = `Takip işi #${body.id} kaydedildi. Raporlar bölümündeki Gelişim Döngüsü'nde izlenebilir; dış değişiklik uygulanmadı.`;
  } catch (error) {
    qs('findingStatus').textContent = error.message || 'Takip işi kaydedilemedi.';
  } finally { button.disabled = false; }
});

const ORCHESTRATION_STATUS = {
  RUNNING: 'Çalışıyor', COMPLETED: 'Tamamlandı', COMPLETED_DEGRADED: 'Eksik veriye rağmen tamamlandı',
  UNVERIFIED: 'Kanıt doğrulanamadı',
  FAILED: 'Hata', INTERRUPTED: 'Yarım kalmış olabilir', PROPOSED: 'Öneri hazır; gönderilmedi',
  SUCCEEDED: 'Tamam', DATA_UNAVAILABLE: 'Veri yok', BLOCKED_CAPABILITY: 'Yetenek engeli',
  BLOCKED_UPSTREAM: 'Önceki adım engeli', REQUIRES_HUMAN_ORIGINATION: 'İnsan başlatmalı',
};

const ACCEPTANCE_TEXT = {
  read_only_completed: 'Okuma adımı tamamlandı',
  source_traceable: 'Kaynağı izlenebilir', result_shape: 'Çıktı biçimi geçerli',
  fusion_shape: 'Birleştirme kaydı geçerli', objections_recorded: 'İtirazlar kaydedildi',
  clean_flag_consistent: 'Denetim sonucu tutarlı', validated_envelope: 'Öneri zarfı doğrulandı',
  not_submitted: 'Dış eylem gönderilmedi', human_origination_required: 'İnsan başlatmalı',
  external_capability_required: 'Dış yetenek gerekir',
};

const ORCHESTRATION_STEP_TEXT = {
  internal_data_analysis: 'Şirket verileri incelendi', sales_analysis: 'Satışlar incelendi',
  advertising_analysis: 'Reklam sonuçları incelendi', evidence_fusion: 'Bulgular karşılaştırıldı',
  ecommerce_analysis: 'E-ticaret verileri incelendi', crm_analysis: 'Müşteri ilişkileri incelendi',
  operations_analysis: 'Operasyon verileri incelendi', finance_analysis: 'Finans verileri incelendi',
  red_team_review: 'Bulguların zayıf yönleri kontrol edildi',
  human_review_proposal: 'İnsan incelemesi için öneri hazırlandı',
  action_plan: 'Yapılacaklar için öneri hazırlandı',
  capability_analysis: 'Sistemin yapabildikleri kontrol edildi',
  system_status: 'Sistem durumu kontrol edildi',
  problem_opportunity_analysis: 'Sorunlar ve fırsatlar incelendi',
};
function orchestrationStepName(code) {
  return ORCHESTRATION_STEP_TEXT[code] || (String(code || '').endsWith('_analysis')
    ? 'İlgili veriler incelendi' : 'Çalışma adımı');
}
function orchestrationDate(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleString('tr-TR') : 'Tarih belirtilmemiş';
}

async function refreshOrchestration() {
  const list = qs('orchestrationList');
  if (!list) return;
  const { ok, body, status } = await api('/api/orchestration');
  if (!ok || !body) {
    qs('orchestrationCount').textContent = 'okunamadı';
    list.innerHTML = '<li class="f-sistem">Çalışmalar şu anda yüklenemedi. Biraz sonra tekrar deneyin.</li>';
    return;
  }
  qs('orchestrationCount').textContent = `son ${body.total} çalışma · ${body.needs_attention} inceleme`;
  list.innerHTML = (body.runs || []).map((run) => {
    const steps = (run.steps || []).map((step) => {
      const evidence = step.evidence_state === 'MISSING' ? ' · Kanıt eksik' :
        step.evidence_state === 'PRESENT' ? ` · ${step.evidence_count} kaynak` : '';
      const acceptance = step.acceptance_status === 'PASSED' ? ' · Teslim doğrulandı' :
        step.acceptance_status === 'FAILED' ? ` · Kabul edilmedi: ${(step.failed_criteria || []).map((criterion) => ACCEPTANCE_TEXT[criterion] || 'Kontrol koşulu sağlanmadı').join(', ')}` : '';
      return `<li>${escapeHtml(orchestrationStepName(step.capability) || 'Çalışma adımı')}: `
        + `${escapeHtml(ORCHESTRATION_STATUS[step.status] || 'Durum belirlenemedi')}${escapeHtml(evidence)}`
        + escapeHtml(acceptance)
        + `${step.reason ? ` — ${escapeHtml(yonetimAciklama(step.reason))}` : ''}</li>`;
    }).join('');
    return `<li class="f-sistem"><div class="f-text"><strong>${escapeHtml(JarvisMetin.safeTitle(run.request, 'Planlı çalışma'))}</strong>`
      + `<div>${escapeHtml(ORCHESTRATION_STATUS[run.status] || 'Durum belirlenemedi')}`
      + ` · ${escapeHtml(orchestrationDate(run.started_at))}</div>`
      + `<details><summary>${(run.steps || []).length} adımın durumu</summary><ol>${steps}</ol></details></div></li>`;
  }).join('') || '<li class="f-sistem">Henüz kayıtlı planlı çalışma yok.</li>';
}

/* ---------------- proposals ---------------- */

/* ==================================================================
   ÖNERİ GÖVDESİ — okunabilir karar ekranı

   🔴 ÖNCEDEN HAM JSON BASILIYORDU:
       escapeHtml(JSON.stringify(body.payload, null, 2))
   Yani onaylayacak kişi şunu görüyordu:
       {"reason": "KREATİF ONAYI — HYDRAVIE\n~ 01-1x1.jpg (1:1) DUZELT\n..."}
   Satır sonları "\n" olarak, içerik tek blok halinde, görseller sadece
   yol metni olarak. Bu ekranda verilen "onay" gerçekte okunmamış bir
   onaydır.

   Artık gövde AYRIŞTIRILIYOR: başlık, etiketli satırlar, uyarı kutusu,
   karar rozetleri ve GERÇEK GÖRSEL ÖNİZLEMELERİ. Ham JSON silinmedi,
   kapalı bir <details> altına alındı -- gerektiğinde bakılabilsin.
   ================================================================== */

const ONERI_ROZET = {
  '+': ['o-ok', 'GEÇER'], '~': ['o-orta', 'DÜZELT'], 'x': ['o-kotu', 'RED'],
  '✔': ['o-ok', 'GEÇER'], '✘': ['o-kotu', 'RED'],
};

function oneriBaslik(reason) {
  const ilk = String(reason || '').split('\n')[0] || '';
  if (ilk.startsWith('CodingExecutor')) return 'Kod değişikliğini incele';
  return JarvisMetin.safeTitle(ilk.replace(/^[A-ZÇĞİÖŞÜ ]+—\s*/, '').trim() || ilk.trim(), 'İncelenecek yeni karar');
}

function oneriRisk(risk) {
  return {LOW: 'Düşük risk', MEDIUM: 'Orta risk', HIGH: 'Yüksek risk', CRITICAL: 'Kritik risk'}[risk] || 'Risk belirtilmedi';
}

function oneriGovdesi(payload) {
  const reason = String((payload && payload.reason) || '');
  if (!reason.trim()) {
    return '<p class="o-bos">Bu önerinin gövdesi boş. Onaylamayın: ' +
      'neyi onayladığınız görünmüyor.</p>';
  }
  const satirlar = reason.split('\n');
  const parcalar = [];
  let liste = [];
  const listeyiBosalt = () => {
    if (liste.length) {
      parcalar.push('<ul class="o-liste">' + liste.join('') + '</ul>');
      liste = [];
    }
  };

  satirlar.forEach((ham, i) => {
    const s = ham.trim();
    if (!s) { listeyiBosalt(); return; }

    // Görsel yolu -> gerçek önizleme
    const gorsel = s.match(/^(\/kreatif\/\S+\.(?:jpg|jpeg|png))$/i);
    if (gorsel) {
      listeyiBosalt();
      parcalar.push(`<a class="o-gorsel" href="${escapeHtml(gorsel[1])}"
        target="_blank" rel="noopener">
        <img src="${escapeHtml(gorsel[1])}" alt="kreatif önizleme" loading="lazy">
        <span>büyüt</span></a>`);
      return;
    }
    // Klasör / belge bağlantısı
    const bag = s.match(/(\/kreatif\/\S+)$/);
    if (bag && !/\.(jpg|jpeg|png)$/i.test(bag[1])) {
      listeyiBosalt();
      const on = s.slice(0, s.length - bag[1].length).trim();
      parcalar.push(`<p class="o-satir">${escapeHtml(on)}
        <a class="o-link" href="${escapeHtml(bag[1])}" target="_blank"
           rel="noopener">${escapeHtml(bag[1])}</a></p>`);
      return;
    }
    // ONAY / RET sonucu -- kararin NE ANLAMA GELDIGI
    // 🔴 Bu satir duz paragraf olarak basilirsa goz onu atliyordu. Karari
    // veren kisi "onaylarsam ne olur" sorusunun cevabini gormeden
    // tiklamamali.
    if (/^ONAY\s*=/.test(s)) {
      listeyiBosalt();
      const yarim = s.split(/\s(?=RET\s*=)/);
      parcalar.push(`<p class="o-sonuc">` +
        yarim.map((y) => `<span>${escapeHtml(y.trim())}</span>`).join('') +
        `</p>`);
      return;
    }
    // Uyarı
    if (s.startsWith('🔴')) {
      listeyiBosalt();
      parcalar.push(`<p class="o-uyari">${escapeHtml(s.replace(/^🔴\s*/, ''))}</p>`);
      return;
    }
    // Karar rozetli satır:  ~ 01-1x1.jpg (1:1) DUZELT [ÖLÇÜM: ...]
    const rozet = ONERI_ROZET[s[0]];
    if (rozet && s.length > 2) {
      listeyiBosalt();
      const govde = s.slice(1).trim();
      const olcum = govde.match(/\[([^\]]+)\]/);
      const temiz = govde.replace(/\[[^\]]+\]/, '').trim();
      parcalar.push(`<p class="o-karar">
        <span class="o-rozet ${rozet[0]}">${rozet[1]}</span>
        <span>${escapeHtml(temiz)}</span>
        ${olcum ? `<em class="o-olcum">${escapeHtml(olcum[1])}</em>` : ''}</p>`);
      return;
    }
    // Madde
    if (s.startsWith('·') || s.startsWith('-') || s.startsWith('•')) {
      liste.push(`<li>${escapeHtml(s.replace(/^[·\-•]\s*/, ''))}</li>`);
      return;
    }
    // Etiketli satır:  alan   : Satış fiyatı
    const et = s.match(/^([A-Za-zÇĞİÖŞÜçğıöşü _]{2,18})\s*:\s*(.+)$/);
    if (et && i > 0) {
      listeyiBosalt();
      parcalar.push(`<p class="o-alan"><span class="o-et">${escapeHtml(et[1].trim())}</span>
        <span class="o-dg">${escapeHtml(et[2].trim())}</span></p>`);
      return;
    }
    // İlk satır = başlık
    listeyiBosalt();
    parcalar.push(i === 0
      ? `<h4 class="o-baslik${/\?\s*$/.test(s) ? ' o-soru' : ''}">${escapeHtml(s)}</h4>`
      : `<p class="o-satir">${escapeHtml(s)}</p>`);
  });
  listeyiBosalt();
  return '<div class="o-govde">' + parcalar.join('') + '</div>';
}

function oneriGorseller(payload) {
  const reason = String((payload || {}).reason || '');
  const yollar = [...reason.matchAll(/\/kreatif\/[\w./-]+\.(?:jpe?g|png)/gi)].map((m) => m[0]);
  const tekil = [...new Set(yollar)];
  if (!tekil.length) return '';
  return `<section class="o-gorseller"><h4>Görseller</h4>${tekil.map((url) =>
    `<a class="o-gorsel" href="${escapeHtml(url)}" target="_blank" rel="noopener">
      <img src="${escapeHtml(url)}" alt="Onaylanacak reklam görseli" loading="lazy"><span>Görseli büyüt</span></a>`).join('')}</section>`;
}

function disaDonukOneri(proposal) {
  return ['WHATSAPP_SEND_TEMPLATE', 'META_CAMPAIGN_CHANGE', 'PRICE_CHANGE', 'WIX_PUBLISH',
    'calendar.create', 'gmail.send', 'drive.upload']
    .includes(String(proposal.action_type || ''));
}

function proposalCardHtml(p) {
  // 🔴 Liste kartinda artik ONERININ KONUSU var. Eskiden yalniz
  // "REQUEST_HUMAN_REVIEW #28" yaziyordu; ayni tipte on oneri yan yana
  // durunca hangisinin ne oldugu ANLASILMIYORDU.
  const baslik = oneriBaslik((p.payload || {}).reason);
  const external = disaDonukOneri(p);
  return `<div class="p-type">${p.status === 'UNCERTAIN' ? 'Sonucu kontrol edin' : 'Onay bekliyor'} <span class="risk-badge risk-${escapeHtml(p.risk_class)}">${escapeHtml(oneriRisk(p.risk_class))}</span></div>
    ${external ? '<div class="external-approval-warning">🔴 DIŞA DÖNÜK İŞLEM · SİZ ONAYLAMADAN UYGULANMAZ</div>' : ''}
    ${baslik ? `<div class="p-konu">${escapeHtml(baslik)}</div>` : ''}
    <div class="p-meta">${escapeHtml(fmtDateTime(p.proposed_at))}</div>
    <span class="p-open">Öneriyi incele</span>`;
}

function fillProposalList(listEl, emptyEl, pending) {
  if (!listEl) return;
  listEl.innerHTML = '';
  if (emptyEl) emptyEl.hidden = pending.length > 0;
  pending.forEach((p) => {
    const li = document.createElement('li');
    li.className = 'proposal-card';
    li.innerHTML = proposalCardHtml(p);
    li.tabIndex = 0;
    li.setAttribute('role', 'button');
    li.addEventListener('click', () => openProposal(p.key));
    li.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openProposal(p.key); }
    });
    listEl.appendChild(li);
  });
}

async function refreshProposals() {
  const { ok, body } = await api('/api/actions');
  if (!ok || !body) {
    for (const id of ['proposalEmpty', 'taskProposalEmpty']) {
      const notice = qs(id);
      if (notice) { notice.textContent = 'Onaylar şu anda yüklenemedi.'; notice.hidden = false; }
    }
    return;
  }
  const pending = body.pending || [];
  fillProposalList(qs('proposalList'), qs('proposalEmpty'), pending);
  fillProposalList(qs('taskProposalList'), qs('taskProposalEmpty'), pending);
  const count = qs('taskPropCount');
  if (count) count.textContent = `${pending.length} kayıt`;
}

async function openProposal(actionId) {
  const { ok, body } = await api('/api/actions/' + actionId);
  if (!ok || !body) return;
  qs('modalBody').innerHTML = `
    <h3>${escapeHtml(oneriBaslik((body.payload || {}).reason) || 'Öneriyi incele')}</h3>
    <p><span class="risk-badge risk-${escapeHtml(body.risk_class)}">${escapeHtml(oneriRisk(body.risk_class))}</span> · Son karar tarihi: ${escapeHtml(fmtDateTime(body.expires_at))}</p>
    ${disaDonukOneri(body) ? '<div class="external-approval-warning">🔴 DIŞA DÖNÜK İŞLEM · Alıcı, içerik ve etkiyi kontrol edin. Onay, tek başına gönderim kanıtı değildir.</div>' : ''}
    ${oneriGovdesi(body.payload)}
    ${oneriGorseller(body.payload)}
    <label class="reason-label">Karar notu (isteğe bağlı)
      <input id="decisionReason" type="text" class="reason-input">
    </label>
    <div class="modal-actions">
      <button class="btn-approve" id="btnApprove" type="button">Öneriyi onayla</button>
      <button class="btn-reject" id="btnReject" type="button">Öneriyi reddet</button>
    </div>
  `;
  qs('btnApprove').disabled = body.status !== 'AWAITING_APPROVAL';
  qs('btnReject').disabled = body.status !== 'AWAITING_APPROVAL';
  qs('btnApprove').addEventListener('click', () => decide(actionId, 'APPROVED', body.fingerprint));
  qs('btnReject').addEventListener('click', () => decide(actionId, 'REJECTED', body.fingerprint));
  qs('proposalModal').hidden = false;
}

async function decide(actionId, decision, fingerprint) {
  const reason = qs('decisionReason').value.trim() || (decision === 'APPROVED' ? 'Operatör onayı' : 'Operatör reddi');
  const { ok, body } = await api(`/api/actions/${actionId}/decide`, {
    method: 'POST', body: JSON.stringify({ decision, reason, fingerprint }),
  });
  qs('proposalModal').hidden = true;
  if (ok) {
    addChatMessage('jarvis', `Öneri ${escapeHtml(String(actionId))} ${decision === 'APPROVED' ? 'onaylandı' : 'reddedildi'}.`);
    refreshProposals();
    refreshActivity();
    refreshStatus();
  } else {
    addChatMessage('jarvis', `Karar kaydedilemedi: ${escapeHtml((body && body.error) || 'bilinmeyen hata')}`);
  }
}

/* ---------------- execution plan: REQUEST -> PLAN -> DISPLAY ----------------
 * Shows what Jarvis WOULD do. There is deliberately no execute control here:
 * the endpoint plans and returns, and every step that could ever act is gated
 * behind the existing human-approval path (or, for a coding task, behind a
 * human running `jarvis-operator create-coding-task` themselves).
 */
const PLAN_STATUS_TEXT = {
  PLANNED: 'Plan hazır',
  BLOCKED_CAPABILITY: 'Plan hazır ancak bazı adımlar yetenek eksikliğinden bloke',
  BLOCKED_EXTERNAL_ACTION: 'Dış iş aksiyonu planlanmaz — insan kararına yönlendirildi',
  REJECTED_AMBIGUOUS: 'Talep planlanamadı',
};

function planChip(label, value, cls) {
  return `<span class="plan-chip ${cls || ''}"><span class="plan-chip-label">${escapeHtml(label)}</span>`
       + `<span class="plan-chip-value">${escapeHtml(String(value))}</span></span>`;
}

const PLAN_MODE_TEXT = {FAST:'Hızlı', SMART:'Ayrıntılı', DEEP:'Derinlemesine'};
const PLAN_RISK_TEXT = {LOW:'Düşük', MEDIUM:'Orta', HIGH:'Yüksek'};
const PLAN_CLASS_TEXT = {
  LOCAL_DETERMINISTIC:'Yerel işlem', MODEL_ASSISTED:'Yapay zekâ destekli',
  CODING_SANDBOX:'Denetimli kod çalışması',
};

function renderPlanSteps(plan) {
  if (!plan.steps.length) return '<p class="empty-note">Bu talep için adım üretilmedi.</p>';
  return plan.parallel_groups.map((group, index) => {
    const rows = group.map((stepId) => {
      const step = plan.steps.find((s) => s.step_id === stepId);
      const blocked = step.blocked_by && step.blocked_by.length;
      const marks = [];
      if (step.capability_status === 'DATA_UNAVAILABLE') {
        const why = (step.arguments && step.arguments.unavailable_reason) || '';
        marks.push('<span class="plan-flag plan-flag-blocked">VERİ YOK</span>'
                 + (why ? `<span class="plan-unavailable">${escapeHtml(yonetimAciklama(why))}</span>` : ''));
      } else if (blocked) {
        marks.push('<span class="plan-flag plan-flag-blocked">Gerekli bağlantı hazır değil</span>');
      }
      if (step.requires_human_origination) marks.push('<span class="plan-flag plan-flag-human">İNSAN BAŞLATIR</span>');
      if (step.produces_action) marks.push('<span class="plan-flag">ONAY GEREKİR</span>');
      const deps = step.depends_on.length ? ' · Önceki adıma bağlı' : '';
      return `<li class="plan-step${blocked ? ' is-blocked' : ''}">
        <div class="plan-step-head"><strong>${escapeHtml(orchestrationStepName(step.capability))}</strong><span class="plan-deps">${deps}</span></div>
        <div class="plan-step-desc">${escapeHtml(JarvisMetin.safeTitle(step.description, 'Bu adım için ayrıntı hazırlanıyor.'))}</div>
        ${(step.acceptance_criteria || []).length ? `<div class="plan-step-target">Teslim koşulları: ${step.acceptance_criteria.map((criterion) => escapeHtml(ACCEPTANCE_TEXT[criterion] || 'Sonuç kontrolü')).join(' · ')}</div>` : ''}
        ${marks.length ? `<div class="plan-flags">${marks.join(' ')}</div>` : ''}
      </li>`;
    }).join('');
    const parallel = group.length > 1 ? ' · paralel' : '';
    return `<div class="plan-group"><div class="plan-group-title">GRUP ${index + 1}${parallel}</div><ol class="plan-steps">${rows}</ol></div>`;
  }).join('');
}

function renderPlan(plan) {
  const blockedCaps = [...new Set(plan.steps.flatMap((s) => s.blocked_by || []))];
  const statusText = PLAN_STATUS_TEXT[plan.status] || 'Planın durumu belirlenemedi';
  const chips = [
    planChip('ÇALIŞMA TÜRÜ', PLAN_MODE_TEXT[plan.mode] || 'Belirlenemedi', `plan-mode-${plan.mode}`),
    planChip('RİSK', PLAN_RISK_TEXT[plan.risk] || 'Belirlenemedi', `risk-badge risk-${plan.risk}`),
    planChip('KONU', orchestrationStepName(String(plan.intent || '').replace(/^DIAGNOSE_/, '').toLowerCase())),
    planChip('İŞLEM TÜRÜ', PLAN_CLASS_TEXT[plan.estimated_execution_class] || 'Belirlenemedi'),
    planChip('TAZE ARAŞTIRMA', plan.requires_fresh_research ? 'GEREKLİ' : 'GEREKMİYOR'),
    planChip('ONAY', plan.approval_required ? 'GEREKLİ' : 'GEREKMİYOR'),
  ].join('');
  return `
    <h3>Çalışma planı <span class="risk-badge risk-${escapeHtml(plan.risk)}">${escapeHtml(statusText)}</span></h3>
    <p class="plan-request">${escapeHtml(JarvisMetin.safeTitle(plan.request, 'Planlı çalışma'))}</p>
    <p class="plan-status-text">${escapeHtml(statusText)}${plan.reason ? ' — ' + escapeHtml(yonetimAciklama(plan.reason)) : ''}</p>
    <div class="plan-chips">${chips}</div>
    ${renderPlanSteps(plan)}
    <dl class="plan-meta">
      <dt>Gerekli bağlantılar</dt><dd>${plan.required_capabilities.length ? `${plan.required_capabilities.length} bağlantı` : 'Ek bağlantı gerekmiyor'}</dd>
      <dt>Hazır olmayanlar</dt><dd>${blockedCaps.length ? `${blockedCaps.length} bağlantı hazır değil` : 'Yok'}</dd>
      <dt>Gerekli şirket verileri</dt><dd>${plan.required_internal_data.length ? `${plan.required_internal_data.length} veri kaynağı` : 'Ek veri gerekmiyor'}</dd>
    </dl>
    <p class="plan-note">Bu yalnızca bir plandır. Hiçbir adım çalıştırılmadı.</p>
  `;
}

/* İki uç, tek akış:
 *   /api/plan  yalnız PLANLAR   -> yanıtta `run` yok, yüzey iskelet kalır
 *   /api/run   PLANLAR + ÇALIŞTIRIR -> yanıta `run` eklenir ve aynı yüzey
 *              (akış rayı, domain kartları, kanıt tablosu, YÖNETİM ANALİZİ)
 *              kendiliğinden dolar; tek satır çizim kodu değişmedi.
 *
 * ÇALIŞTIR yalnız OKUMA analizi yapar. Eylem üreten adım çalıştırılmaz;
 * PROPOSED zarfına dönüşür ve gerçek eyleme ancak mevcut insan onayı
 * hattından geçerek döner. Sınır backend'de (jarvis/execution_runtime.py)
 * ve testlerinde duruyor, burada değil -- bu dosya onu yalnızca gösterir. */
async function requestPlan(message, execute) {
  state.planInFlight = true;
  renderExecutionSurface();
  let result;
  try {
    const yol = execute ? '/api/run' : '/api/plan';
    const { ok, body } = await api(yol, { method: 'POST', body: JSON.stringify({ message }) });
    if (!ok || !body) {
      state.lastPlan = null;
      state.lastRun = null;
      result = { error: (body && body.error) || 'bilinmeyen hata' };
    } else {
      state.lastPlan = body;
      // Yalnızca backend gerçekten bir RunRecord iliştirdiyse dolar;
      // extractRun şeklini denetler, uydurma bir kabuk kabul etmez.
      state.lastRun = extractRun(body);
      result = { plan: body };
    }
  } finally {
    state.planInFlight = false;
    renderExecutionSurface();
  }
  return result;
}

async function openPlan() {
  const message = qs('chatInput').value.trim();
  if (!message) return;
  const result = await requestPlan(message);
  if (result.error) {
    addChatMessage('jarvis', `Plan üretilemedi: ${escapeHtml(result.error)}`);
    return;
  }
  qs('modalBody').innerHTML = renderPlan(result.plan);
  qs('proposalModal').hidden = false;
}

qs('planBtn').addEventListener('click', openPlan);

async function analizCalistir(execute) {
  const message = qs('analizInput').value.trim();
  if (!message) return;
  const target = qs('analizResult');
  const btn = qs('analizRunBtn');
  target.innerHTML = execute
    ? '<p class="empty-note">Adımlar çalıştırılıyor…</p>'
    : '<p class="empty-note">Plan üretiliyor…</p>';
  if (btn) btn.disabled = true;
  try {
    const result = await requestPlan(message, execute);
    target.innerHTML = result.error
      ? `<p class="empty-note">${execute ? 'Çalıştırılamadı' : 'Plan üretilemedi'}: ${escapeHtml(result.error)}</p>`
      : renderPlan(result.plan);
  } finally {
    if (btn) btn.disabled = false;
  }
}

qs('analizForm').addEventListener('submit', (event) => {
  event.preventDefault();
  analizCalistir(false);
});

qs('analizRunBtn').addEventListener('click', () => { analizCalistir(true); });

qs('modalClose').addEventListener('click', () => { qs('proposalModal').hidden = true; });
qs('proposalModal').addEventListener('click', (e) => { if (e.target.id === 'proposalModal') qs('proposalModal').hidden = true; });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !qs('proposalModal').hidden) qs('proposalModal').hidden = true;
});

/* ---------------- chat: minimal, dependency-free Markdown ----------------
 * Escapes HTML first (XSS-safe), then applies a small set of transforms.
 * Deliberately not a full CommonMark implementation -- covers what Jarvis's
 * grounded answers actually produce: headings, bold, inline code, code
 * blocks, lists, simple tables. */
function renderMarkdownLite(raw) {
  const escaped = escapeHtml(raw);
  const lines = escaped.split('\n');
  let html = '';
  let inList = false;
  let inCode = false;
  for (const line of lines) {
    if (line.trim().startsWith('```')) { inCode = !inCode; html += inCode ? '<pre><code>' : '</code></pre>'; continue; }
    if (inCode) { html += line + '\n'; continue; }
    if (/^#{1,3}\s/.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      const level = line.match(/^#+/)[0].length;
      html += `<h${level + 3}>${line.replace(/^#+\s*/, '')}</h${level + 3}>`;
      continue;
    }
    if (/^-\s+/.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inlineMd(line.replace(/^-\s+/, ''))}</li>`;
      continue;
    }
    if (inList) { html += '</ul>'; inList = false; }
    if (line.trim()) html += `<p>${inlineMd(line)}</p>`;
  }
  if (inList) html += '</ul>';
  if (inCode) html += '</code></pre>';
  return html;
}
function inlineMd(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

/* ---------------- proposal / evidence cards in chat ---------------- */
function renderProposalCard(p) {
  return `<div class="chat-card">
    ${proposalCardHtml(p)}
    ${p.payload ? oneriGovdesi(p.payload) : ''}
  </div>`;
}
/* Ozetin arkasindaki satirlar. Native <details> kullaniliyor: mobilde
 * dokunmatik hedefi tarayicidan gelir, JS gerektirmez, klavye ve ekran
 * okuyucu ile calisir. "16 acik dosya" artik acilip 16 satirin kendisini
 * gosterir. */
function renderDetailBlocks(details) {
  if (!Array.isArray(details) || !details.length) return '';
  return details.map((block) => {
    const rows = (block.rows || []).map(
      (row) => `<li>${escapeHtml(String(row))}</li>`).join('');
    if (!rows) return '';
    const total = Number(block.total);
    const shown = (block.rows || []).length;
    const more = Number.isFinite(total) && total > shown
      ? `<p class="detail-more">${total - shown} kayıt daha var</p>` : '';
    const head = escapeHtml(block.summary || block.ref || 'kayıtlar');
    return `<details class="detail-block">
      <summary>${head}</summary>
      <ul class="detail-rows">${rows}</ul>
      ${more}
      <p class="detail-ref">kaynak: ${escapeHtml(block.ref || '')}</p>
    </details>`;
  }).join('');
}

function renderAnswerBody(body) {
  if (body.source === 'operator.list_pending' && Array.isArray(body.data) && body.data.length) {
    return `<p>${escapeHtml(body.text)}</p>` + body.data.map(renderProposalCard).join('');
  }
  if (body.source === 'operator.inspect' && body.data) {
    return renderProposalCard(body.data);
  }
  return renderMarkdownLite(body.text || '(boş yanıt)') + renderDetailBlocks(body.details);
}

/* ---------------- chat: send / stream / stop / retry / copy ----------------
 * sendMessage(text) is the single entry point for producing a user turn --
 * the form handler calls it, and a future microphone/voice input can call
 * the exact same function with transcribed text, with no other UI change. */
let activeStreamController = null;
let lastUserMessage = null;

function addChatMessage(role, html, cls) {
  const log = qs('chatLog');
  log.hidden = false;
  const div = document.createElement('div');
  div.className = 'chat-msg ' + role + (cls ? ' ' + cls : '');
  div.innerHTML = html;
  if (role === 'jarvis') {
    // Ekip kararı: 7 satırı geçen cevap kısaltılır (bkz. devaminiGor).
    requestAnimationFrame(() => devaminiGor(div));
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.type = 'button';
    copyBtn.textContent = 'KOPYALA';
    copyBtn.addEventListener('click', () => {
      navigator.clipboard?.writeText(div.innerText).catch(() => {});
    });
    div.appendChild(copyBtn);
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

/* Ekrana basılanın DÜZ METİN hâlini döndürür -- sesli konuşma bunu okutur.
 * Ayrı bir "sesli cevap" yolu açılmadı bilerek: sesli ve yazılı akış aynı
 * /api/chat/stream turundan çıkıyor, yani kullanıcının duyduğu şey ekranda
 * yazanın aynısı. */
async function sendMessage(message) {
  let spoken = '';
  message = (message || '').trim();
  if (!message) return spoken;
  lastUserMessage = message;
  addChatMessage('user', escapeHtml(message));

  const stageDiv = addChatMessage('jarvis', '…', 'stage');
  qs('stopBtn').hidden = false;
  qs('sendBtn').disabled = true;

  const controller = new AbortController();
  activeStreamController = controller;

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST', credentials: 'same-origin', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrfToken || '' },
      body: JSON.stringify({ message, chat_id: chatId() }),
    });
    if (!res.ok || !res.body) {
      stageDiv.innerHTML = 'Bağlantı hatası.';
      spoken = 'Bağlantı hatası.';
      return spoken;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let streamed = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === 'token') {
          streamed += event.delta;
          stageDiv.className = 'chat-msg jarvis';
          stageDiv.innerHTML = renderMarkdownLite(streamed);
          log_scroll();
        } else if (event.type === 'stage') {
          stageDiv.innerHTML = `<span class="stage-dot"></span> ${escapeHtml(event.label)}…`;
        } else if (event.type === 'done') {
          const result = event.result;
          if (result.kind === 'REQUIRES_REASONING_CAPABILITY') {
            stageDiv.className = 'chat-msg jarvis reasoning';
            stageDiv.innerHTML = escapeHtml(result.message);
            spoken = result.message || '';
          } else if (result.kind === 'ERROR') {
            stageDiv.className = 'chat-msg jarvis';
            stageDiv.innerHTML = 'Anlaşılamadı: ' + escapeHtml(result.message);
            spoken = 'Anlaşılamadı. ' + (result.message || '');
          } else {
            stageDiv.className = 'chat-msg jarvis';
            stageDiv.innerHTML = renderAnswerBody(result);
            spoken = result.text || streamed || '';
          }
        } else if (event.type === 'error') {
          stageDiv.innerHTML = 'Hata: ' + escapeHtml(event.message);
          spoken = 'Hata. ' + (event.message || '');
        }
      }
      log_scroll();
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      stageDiv.innerHTML = 'Bağlantı kesildi.';
      spoken = 'Bağlantı kesildi.';
    } else {
      stageDiv.innerHTML = '(durduruldu)';
      spoken = '';
    }
  } finally {
    qs('stopBtn').hidden = true;
    qs('sendBtn').disabled = false;
    qs('retryBtn').hidden = false;
    activeStreamController = null;
    refreshActivity();
  }
  return spoken;
}
function log_scroll() { const log = qs('chatLog'); log.scrollTop = log.scrollHeight; }

qs('chatForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const input = qs('chatInput');
  const message = input.value;
  input.value = '';
  sendMessage(message);
});

qs('stopBtn').addEventListener('click', () => {
  if (activeStreamController) activeStreamController.abort();
});

qs('retryBtn').addEventListener('click', () => { if (lastUserMessage) sendMessage(lastUserMessage); });

/* ---------------- quick actions ----------------
 * Every entry here maps onto an endpoint that already exists: a refresh of
 * the three GET endpoints, or a chat turn through /api/chat/stream. No
 * button invents a capability the backend does not have. */
qs('qaRefresh').addEventListener('click', refreshAll);
document.querySelectorAll('.qa-btn[data-ask]').forEach((btn) => {
  btn.addEventListener('click', () => {
    setView('home');
    sendMessage(btn.dataset.ask);
  });
});
document.addEventListener('click', (event) => {
  const button = event.target.closest('.lead-ask[data-ask]');
  if (!button) return;
  setView('home');
  sendMessage(button.dataset.ask);
});
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-team-filter]');
  if (!button) return;
  const desk = button.closest('.lead-members');
  desk.querySelectorAll('[data-team-filter]').forEach(item =>
    item.setAttribute('aria-pressed', String(item === button)));
  desk.querySelectorAll('[data-team-state]').forEach(item => {
    item.hidden = button.dataset.teamFilter !== 'HEPSİ' &&
      item.dataset.teamState !== button.dataset.teamFilter;
  });
});

function ekipDizininiFiltrele() {
  const dizin = qs('ekipDizin');
  if (!dizin) return;
  const query = (qs('ekipArama').value || '').trim().toLocaleLowerCase('tr-TR');
  const aile = qs('ekipAileSec').value;
  const durum = qs('ekipDurumSec').value;
  let visible = 0;
  const groups = document.querySelectorAll('#ekipBody .ek-aile');
  groups.forEach((group) => {
    let groupVisible = 0;
    group.querySelectorAll('.ek-dep').forEach((department) => {
      const matches = (!aile || group.dataset.teamFamily === aile)
        && (!durum || department.dataset.teamState === durum)
        && (!query || department.textContent.toLocaleLowerCase('tr-TR').includes(query));
      department.hidden = !matches;
      if (matches) { visible += 1; groupVisible += 1; }
    });
    group.hidden = groupVisible === 0;
  });
  qs('ekipGorunen').textContent = `${visible} / ${document.querySelectorAll('#ekipBody .ek-dep').length} departman gösteriliyor`;
  qs('ekipBos').hidden = visible !== 0;
}

document.addEventListener('input', (event) => {
  if (event.target.id === 'ekipArama') ekipDizininiFiltrele();
});
document.addEventListener('change', (event) => {
  if (event.target.id === 'ekipAileSec' || event.target.id === 'ekipDurumSec') ekipDizininiFiltrele();
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('[data-team-members]')) return;
  const directory = qs('ekipUyeler');
  if (!directory) return;
  directory.open = true;
  directory.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

/* ==================================================================
 * EXECUTION SURFACE
 * ------------------------------------------------------------------
 * Renders the execution pipeline from what the backend actually says.
 *
 * Available today (/api/plan -> ExecutionPlan.to_dict()):
 *   plan.status, plan.steps[].{step_id, capability, capability_status,
 *   blocked_by, produces_action, requires_human_origination, arguments}
 *   arguments.domain / .memory_queries / .data_available / .unavailable_reason
 *
 * Not exposed over HTTP yet: the run itself. jarvis/execution_runtime.py
 * already serialises one (RunRecord.to_dict: run_id, plan_id, status, steps
 * keyed by step_id, each with status / output / evidence_refs / error /
 * block_reason). extractRun() below reads exactly that shape off the plan
 * response if it is ever attached; nothing here invents a route, and no
 * request is made to an endpoint that does not exist.
 *
 * Rule enforced throughout: a field the backend did not send is printed as
 * an em dash. No percentage is computed anywhere -- the backend reports a
 * per-step status, never a completion ratio.
 * ================================================================== */

const DOMAIN_CARDS = [
  { id: 'sales', label: 'SATIŞ' },
  { id: 'ecommerce', label: 'E-TİCARET' },
  { id: 'advertising', label: 'REKLAM' },
  { id: 'crm', label: 'MÜŞTERİ' },
  { id: 'operations', label: 'OPERASYON' },
];
const DOMAIN_CAPS = DOMAIN_CARDS.map((d) => `${d.id}_analysis`);

const EXEC_STAGES = [
  { id: 'plan', label: 'PLAN', caps: [] },
  { id: 'domains', label: '5 İŞ ALANI', caps: DOMAIN_CAPS.concat(['internal_data_analysis']) },
  { id: 'fusion', label: 'KANIT BİRLEŞTİRME', caps: ['evidence_fusion'] },
  { id: 'signals', label: 'PROBLEM / FIRSAT', caps: ['problem_opportunity_analysis'] },
  { id: 'redteam', label: 'KANIT DENETİMİ', caps: ['red_team_review'] },
  { id: 'proposal', label: 'YÖNETİM ÖNERİSİ', caps: ['human_review_proposal', 'action_plan'] },
];

/* The backend's own step vocabulary (execution_runtime.py) mapped to the
 * operator-facing words. RUNNING / IN_PROGRESS are accepted but no executor
 * emits them today, so ÇALIŞIYOR only ever appears if the backend really
 * reports a step in flight. */
const STEP_STATE = {
  PENDING: ['BEKLİYOR', 'st-wait'],
  RUNNING: ['ÇALIŞIYOR', 'st-run'],
  IN_PROGRESS: ['ÇALIŞIYOR', 'st-run'],
  SUCCEEDED: ['TAMAMLANDI', 'st-done'],
  COMPLETED: ['TAMAMLANDI', 'st-done'],
  PROPOSED: ['ÖNERİ HAZIR', 'st-done'],
  FAILED: ['HATA', 'st-error'],
  DATA_UNAVAILABLE: ['VERİ YOK', 'st-nodata'],
  BLOCKED_CAPABILITY: ['BLOKE', 'st-blocked'],
  BLOCKED_UPSTREAM: ['BLOKE', 'st-blocked'],
  REQUIRES_HUMAN_ORIGINATION: ['İNSAN BAŞLATIR', 'st-blocked'],
};
function stepState(status) {
  return STEP_STATE[status] || [String(status || '—'), 'st-blocked'];
}

function extractRun(body) {
  const run = body && body.run;
  if (!run || typeof run !== 'object' || !run.steps || typeof run.steps !== 'object') return null;
  return run;
}
function runStep(stepId) {
  return (state.lastRun && state.lastRun.steps && state.lastRun.steps[stepId]) || null;
}
function planSteps() {
  return (state.lastPlan && Array.isArray(state.lastPlan.steps)) ? state.lastPlan.steps : [];
}
/* The core belongs to /api/status. The execution surface borrows it only
 * while something is genuinely in motion -- a plan request in flight, or a
 * run record on screen. A plan that finished rendering hands it straight
 * back, so the home screen keeps showing the live loop state. */
function execOverride() {
  return state.planInFlight || !!state.lastRun;
}

/* -- 1. execution state ------------------------------------------------ */
function deriveExecState() {
  if (state.planInFlight) return ['PLANLANIYOR', 'st-run', 'proposing'];
  const plan = state.lastPlan;
  if (!plan) return ['HAZIR', 'st-ready', 'idle'];
  if (plan.status === 'REJECTED_AMBIGUOUS') return ['HATA', 'st-error', 'error'];

  const steps = planSteps();
  const run = state.lastRun;
  if (!run) {
    // Plan only. The pipeline has not been executed, so no progress state is
    // claimed -- only what the plan itself already decided.
    const domainSteps = steps.filter((s) => DOMAIN_CAPS.includes(s.capability));
    const unavailable = domainSteps.filter((s) => s.capability_status === 'DATA_UNAVAILABLE');
    if (domainSteps.length && unavailable.length === domainSteps.length) {
      return ['VERİ YOK', 'st-nodata', 'no_data'];
    }
    if (plan.status === 'BLOCKED_CAPABILITY' || plan.status === 'BLOCKED_EXTERNAL_ACTION') {
      return ['VERİ YOK', 'st-nodata', 'no_data'];
    }
    return ['PLANLANDI', 'st-ready', 'idle'];
  }

  if (run.status === 'FAILED') return ['HATA', 'st-error', 'error'];
  const statusOf = (caps) => steps.filter((s) => caps.includes(s.capability))
    .map((s) => (runStep(s.step_id) || {}).status).filter(Boolean);
  const anyPending = (caps) => statusOf(caps).some((v) => v === 'PENDING');
  const anyRunning = (caps) => statusOf(caps).some((v) => v === 'RUNNING' || v === 'IN_PROGRESS');

  if (anyRunning(DOMAIN_CAPS.concat(['internal_data_analysis'])) || anyPending(DOMAIN_CAPS.concat(['internal_data_analysis']))) {
    return ['VERİ TOPLANIYOR', 'st-run', 'proposing'];
  }
  if (anyRunning(['evidence_fusion', 'problem_opportunity_analysis'])
      || anyPending(['evidence_fusion', 'problem_opportunity_analysis'])) {
    return ['ANALİZ EDİLİYOR', 'st-run', 'proposing'];
  }
  if (anyRunning(['red_team_review']) || anyPending(['red_team_review'])) {
    return ['KANIT DENETİMİ', 'st-run', 'proposing'];
  }
  if (statusOf(['human_review_proposal', 'action_plan']).includes('PROPOSED')) {
    return ['ONAY BEKLİYOR', 'st-wait', 'waiting_approval'];
  }
  const all = Object.values(run.steps || {}).map((s) => s.status);
  if (all.length && all.every((v) => v === 'DATA_UNAVAILABLE')) return ['VERİ YOK', 'st-nodata', 'no_data'];
  if (run.status === 'COMPLETED' || run.status === 'COMPLETED_DEGRADED') {
    return ['TAMAMLANDI', 'st-done', 'done'];
  }
  return [String(run.status || '—'), 'st-blocked', 'idle'];
}

/* -- 2. stage rail ------------------------------------------------------ */
function stageCell(stage) {
  const plan = state.lastPlan;
  let label = stage.label;
  let text = 'PLANDA YOK';
  let cls = 'st-absent';
  let meta = '';

  if (stage.id === 'plan') {
    if (state.planInFlight) { text = 'PLANLANIYOR'; cls = 'st-run'; }
    else if (plan) { text = 'HAZIR'; cls = 'st-ready'; meta = 'İncelemeye hazır'; }
    else { text = 'PLAN YOK'; cls = 'st-absent'; }
    return { label, text, cls, meta };
  }
  if (!plan) return { label, text: 'PLAN YOK', cls: 'st-absent', meta: '' };

  const steps = planSteps().filter((s) => stage.caps.includes(s.capability));
  if (!steps.length) return { label, text: 'PLANDA YOK', cls: 'st-absent', meta: '' };
  if (stage.id === 'domains') label = `${steps.length} İŞ ALANI`;
  meta = `${steps.length} adım`;

  const runStatuses = steps.map((s) => runStep(s.step_id)).filter(Boolean).map((r) => r.status);
  if (runStatuses.length) {
    const rank = ['FAILED', 'RUNNING', 'IN_PROGRESS', 'PENDING', 'BLOCKED_CAPABILITY',
                  'BLOCKED_UPSTREAM', 'REQUIRES_HUMAN_ORIGINATION', 'DATA_UNAVAILABLE',
                  'PROPOSED', 'SUCCEEDED'];
    const worst = rank.find((value) => runStatuses.includes(value)) || runStatuses[0];
    [text, cls] = stepState(worst);
    return { label, text, cls, meta };
  }

  // Plan only: report what planning already determined, nothing more.
  const blocked = steps.filter((s) => (s.blocked_by || []).length);
  const noData = steps.filter((s) => s.capability_status === 'DATA_UNAVAILABLE');
  if (noData.length === steps.length) { text = 'VERİ YOK'; cls = 'st-nodata'; }
  else if (blocked.length) { text = 'BLOKE'; cls = 'st-blocked'; }
  else if (steps.some((s) => s.requires_human_origination)) { text = 'İNSAN BAŞLATIR'; cls = 'st-blocked'; }
  else { text = 'PLANLANDI'; cls = 'st-ready'; }
  return { label, text, cls, meta };
}

function renderRail() {
  qs('execRail').innerHTML = EXEC_STAGES.map((stage) => {
    const cell = stageCell(stage);
    return `<li class="exec-stage ${cell.cls}">
      <span class="exec-stage-label">${escapeHtml(cell.label)}</span>
      <span class="exec-stage-state">${escapeHtml(cell.text)}</span>
      ${cell.meta ? `<span class="exec-stage-meta">${escapeHtml(cell.meta)}</span>` : ''}
    </li>`;
  }).join('');
}

/* -- 3. domain cards + right-panel strip -------------------------------- */
function domainCell(domain) {
  const plan = state.lastPlan;
  if (!plan) return { text: 'PLAN YOK', cls: 'st-absent', meta: '' };
  const step = planSteps().find((s) => s.capability === `${domain.id}_analysis`
    || (s.arguments && s.arguments.domain === domain.id));
  if (!step) return { text: 'PLANDA YOK', cls: 'st-absent', meta: '' };

  const record = runStep(step.step_id);
  if (record) {
    const [text, cls] = stepState(record.status);
    const output = record.output || {};
    const bits = [];
    if (output.records !== undefined) bits.push(`${output.records} kayıt`);
    if (record.block_reason) bits.push(record.block_reason);
    if (record.error) bits.push(record.error);
    return { text, cls, meta: bits.join(' · ') };
  }

  const args = step.arguments || {};
  if (step.capability_status === 'DATA_UNAVAILABLE' || args.data_available === false) {
    return { text: 'VERİ YOK', cls: 'st-nodata', meta: args.unavailable_reason || '' };
  }
  if ((step.blocked_by || []).length) {
    return { text: 'BLOKE', cls: 'st-blocked', meta: step.blocked_by.join(', ') };
  }
  return {
    text: 'BEKLİYOR', cls: 'st-wait',
    meta: (args.memory_queries || []).join(', '),
  };
}

function renderDomains() {
  const cells = DOMAIN_CARDS.map((domain) => ({ domain, cell: domainCell(domain) }));
  qs('domainGrid').innerHTML = cells.map(({ domain, cell }) => `
    <div class="dom-card ${cell.cls}">
      <span class="dom-name">${escapeHtml(domain.label)}</span>
      <span class="dom-state">${escapeHtml(cell.text)}</span>
      ${cell.meta ? `<span class="dom-meta">${escapeHtml(cell.meta)}</span>` : ''}
    </div>`).join('');

  const strip = qs('domainStrip');
  if (strip) {
    strip.innerHTML = cells.map(({ domain, cell }) =>
      `<li><span>${escapeHtml(domain.label)}</span>`
      + `<span class="svc-state ${cell.cls === 'st-done' ? 's-ok' : cell.cls === 'st-error' ? 's-error'
         : cell.cls === 'st-wait' || cell.cls === 'st-run' ? 's-warn' : 's-off'}">`
      + `${escapeHtml(cell.text)}</span></li>`).join('');
  }
}

/* -- 4. evidence -------------------------------------------------------- */
/* One normaliser for every evidence shape the backend may produce: the
 * internal `evidence_refs` strings the runtime emits today, and richer
 * objects (web research rows, for instance) if a later step returns them.
 * An alias that is absent stays absent -- it is never substituted. */
function pick(source, names) {
  for (const name of names) {
    if (source && source[name] !== undefined && source[name] !== null && source[name] !== '') {
      return source[name];
    }
  }
  return undefined;
}
function normalizeEvidence(raw, ctx) {
  if (typeof raw === 'string') {
    // Internal refs are "publisher:query" (e.g. postgres:sales_orders). Split
    // so the source column names the publisher and the reference column keeps
    // the whole ref; a ref without a colon is shown whole in both.
    const publisher = raw.includes(':') ? raw.slice(0, raw.indexOf(':')) : raw;
    return { source: publisher, reference: raw, domain: ctx.domain, finding: ctx.finding,
             freshness: ctx.freshness, confidence: ctx.confidence,
             contradiction: ctx.contradiction, independent: ctx.independent };
  }
  return {
    source: pick(raw, ['source', 'publisher', 'origin', 'host']),
    url: pick(raw, ['url', 'link', 'href']),
    title: pick(raw, ['title', 'headline', 'name']),
    domain: pick(raw, ['domain', 'entity']) || ctx.domain,
    finding: pick(raw, ['claim', 'finding', 'summary', 'text']) || ctx.finding,
    reference: pick(raw, ['reference', 'evidence_ref', 'source_id', 'id']),
    freshness: pick(raw, ['freshness', 'observed_at', 'retrieved_at', 'published_at']) || ctx.freshness,
    confidence: pick(raw, ['confidence']) !== undefined ? pick(raw, ['confidence']) : ctx.confidence,
    contradiction: pick(raw, ['contradiction']) !== undefined ? pick(raw, ['contradiction']) : ctx.contradiction,
    independent: pick(raw, ['independent_sources', 'independent_source']) !== undefined
      ? pick(raw, ['independent_sources', 'independent_source']) : ctx.independent,
  };
}

function collectEvidence() {
  const run = state.lastRun;
  if (!run) return [];
  const rows = [];
  Object.entries(run.steps || {}).forEach(([stepId, record]) => {
    const output = record.output || {};
    const ctx = {
      domain: output.domain || record.capability || stepId,
      finding: output.records !== undefined ? `${output.records} kayıt` : (output.summary || ''),
      freshness: pick(output, ['observed_at', 'retrieved_at']),
      confidence: output.confidence,
      contradiction: output.contradiction,
      independent: output.independent_sources,
    };
    if (Array.isArray(output.evidence)) {
      output.evidence.forEach((item) => rows.push(normalizeEvidence(item, ctx)));
    }
    (record.evidence_refs || []).forEach((ref) => rows.push(normalizeEvidence(ref, ctx)));
  });
  return rows;
}

/* Evidence rows are backend data, not operator input, but a URL that ends up
 * in an href is still the one place a poisoned record could become script.
 * Only http(s) survives; anything else is rendered as plain text. */
function safeUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const parsed = new URL(value, window.location.origin);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') ? parsed.href : null;
  } catch (_) {
    return null;
  }
}

function evCell(value, mono) {
  if (value === undefined || value === null || value === '') return '<td class="ev-na">—</td>';
  return `<td${mono ? ' class="ev-mono"' : ''}>${escapeHtml(String(value))}</td>`;
}

function renderEvidence() {
  const wrap = qs('evidenceWrap');
  const rows = collectEvidence();
  if (!rows.length) {
    wrap.innerHTML = '<p class="pr-empty">Kanıt bulunamadı.</p>';
    return;
  }
  const body = rows.map((row) => {
    const href = safeUrl(row.url);
    const sourceCell = href
      ? `<td><a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.title || row.source || href)}</a></td>`
      : evCell(row.title || row.source || row.url);
    const contradiction = row.contradiction === undefined || row.contradiction === null
      ? '<td class="ev-na">—</td>'
      : (row.contradiction ? '<td class="ev-flag">VAR</td>' : '<td class="ev-ok">YOK</td>');
    return `<tr>
      ${sourceCell}
      ${evCell(row.domain)}
      ${evCell(row.finding)}
      ${evCell(row.reference, true)}
      ${evCell(row.freshness, true)}
      ${evCell(row.confidence)}
      ${contradiction}
      ${evCell(row.independent)}
    </tr>`;
  }).join('');
  wrap.innerHTML = `<table class="ev-table">
    <thead><tr>
      <th>KAYNAK</th><th>İŞ ALANI</th><th>BULGU</th><th>DAYANAK</th>
      <th>TAZELİK</th><th>GÜVEN</th><th>ÇELİŞKİ</th><th>BAĞIMSIZ KAYNAK</th>
    </tr></thead><tbody>${body}</tbody></table>`;
}

/* -- 5. management analysis (advisory, never applied) ------------------- */
function outputsByCapability(capability) {
  const run = state.lastRun;
  if (!run) return [];
  return planSteps()
    .filter((s) => s.capability === capability)
    .map((s) => (runStep(s.step_id) || {}).output)
    .filter(Boolean);
}

function listBlock(title, items, emptyText) {
  const body = items.length
    ? `<ul>${items.join('')}</ul>`
    : `<p class="pr-empty">${escapeHtml(emptyText)}</p>`;
  return `<div class="pr-block"><h4>${escapeHtml(title)}</h4>${body}</div>`;
}

function yonetimKodu(code) {
  return ({ approval_backlog: 'Onay birikimi', decision_stall: 'Karar gecikmesi',
    red_team_objection: 'Denetim itirazı', agenda_aging: 'Eski gündem',
    agenda_without_source_plan: 'Kaynağı belirsiz gündem', open_work_aging: 'Geciken iş',
    open_work_concentration: 'İş yükü yoğunluğu', EVIDENCE_MISSING: 'Kanıt eksik',
    CONTRADICTION: 'Çelişkili veri', THIN_SOURCING: 'Az kaynak',
    INPUT_UNAVAILABLE: 'Veri alınamadı', REQUEST_HUMAN_REVIEW: 'İnsan incelemesi',
    WHATSAPP_SEND_TEMPLATE: 'WhatsApp gönderim önerisi',
    META_CAMPAIGN_CHANGE: 'Reklam kampanyası değişikliği',
    PRICE_CHANGE: 'Fiyat değişikliği', WIX_PUBLISH: 'Site yayını',
    DATA_UNAVAILABLE: 'Veri yok', SKIPPED: 'Değerlendirilemedi' })[code] || 'Diğer teknik kayıt';
}

function yonetimAciklama(raw) {
  const value = String(raw || '');
  const plan = value.match(/^Execution plan .+ completed read-only analysis; (\d+) red-team objection\(s\)\. Advisory only, awaiting human approval\. No action was taken\.$/);
  if (plan) return `Yalnızca okuma ve analiz tamamlandı. ${plan[1]} kanıt itirazı var. İnsan kararı bekleniyor; hiçbir işlem yapılmadı.`;
  const sources = value.match(/^independent sources = (\d+)$/);
  if (sources) return `Bağımsız kaynak sayısı: ${sources[1]}.`;
  if (value === 'fused evidence contradicts itself') return 'Birleştirilen kanıtlar birbiriyle çelişiyor.';
  if (value.startsWith('no Company Memory data contract')) return 'Bu alan için bağlı şirket verisi yok.';
  if (value.startsWith('live capability status blocks step')) return 'Gerekli bağlantı hazır olmadığı için bu adım çalışmadı.';
  if (value === 'no rows returned') return 'Kaynakta kayıt bulunamadı.';
  if (value.startsWith('value is not a number')) return 'Gerekli sayısal değer okunamadı.';
  if (value === 'agenda is empty') return 'Gündem kaydı yok.';
  if (value === 'no open work rows') return 'Açık iş kaydı yok.';
  return JarvisMetin.safeTitle(value, 'Bu adımın teknik ayrıntıları inceleniyor.');
}

function renderProposed() {
  const target = qs('proposedBody');
  if (!state.lastRun) {
    target.innerHTML = '<p class="pr-empty">Yürütme sonucu henüz yok — '
      + 'bu bölüm yalnız gerçek bir yürütme kaydı geldiğinde dolar.</p>';
    return;
  }

  const signals = outputsByCapability('problem_opportunity_analysis')
    .flatMap((output) => output.signals || []);
  // The detector has no problem/opportunity field today, only a severity.
  // If one is ever added it is used; until then the split is by severity and
  // the heading says so, rather than silently reclassifying signals.
  const hasKind = signals.some((s) => s.kind || s.type);
  const isOpportunity = (s) => (hasKind
    ? String(s.kind || s.type).toUpperCase().includes('OPPORT')
    : s.severity === 'INFO');
  const signalItem = (s) => `<li><span class="pr-sev sev-${escapeHtml(s.severity || 'INFO')}">`
    + `${escapeHtml(({ CRITICAL: 'ACİL', WARN: 'UYARI', INFO: 'BİLGİ' })[s.severity] || 'BİLGİ')}</span><span class="pr-code">${escapeHtml(yonetimKodu(s.code))}</span>`
    + `${escapeHtml(s.summary || '')}</li>`;

  const objections = outputsByCapability('red_team_review')
    .flatMap((output) => output.objections || [])
    .map((o) => `<li><span class="pr-code">${escapeHtml(yonetimKodu(o.code))}</span>`
      + `${escapeHtml(yonetimAciklama(o.detail))}</li>`);

  const actions = ['human_review_proposal', 'action_plan']
    .flatMap((cap) => outputsByCapability(cap))
    .map((output) => {
      const payload = output.payload || {};
      const applied = output.submitted === true;
      return `<li><span class="pr-code">${escapeHtml(yonetimKodu(output.action_type || output.internal_intent))}</span>`
        + `${escapeHtml(yonetimAciklama(payload.reason))}`
        + `<span class="dom-meta">${applied ? 'gönderildi' : 'ÖNERİ — uygulanmadı, gönderilmedi'}`
        + '</span></li>';
    });

  const gaps = [];
  outputsByCapability('evidence_fusion').forEach((output) => {
    (output.missing_inputs || []).forEach((entry) => gaps.push(
      `<li><span class="pr-code">${escapeHtml(yonetimKodu(entry.status))}</span>`
      + `${escapeHtml(yonetimAciklama(entry.reason || entry.capability))}`
      + '</li>'));
    if (output.needs_more_sources) {
      gaps.push(`<li><span class="pr-code">Az kaynak</span>`
        + `bağımsız kaynak sayısı ${escapeHtml(String(output.independent_sources))}</li>`);
    }
  });
  outputsByCapability('problem_opportunity_analysis').forEach((output) => {
    (output.skipped || []).forEach((entry) => gaps.push(
      `<li><span class="pr-code">Değerlendirilemedi</span>${escapeHtml(yonetimAciklama(entry.reason || entry.rule || 'Bu bulgu için yeterli veri yok.'))}</li>`));
  });
  Object.entries(state.lastRun.steps || {}).forEach(([stepId, record]) => {
    if (record.status === 'DATA_UNAVAILABLE') {
      gaps.push(`<li><span class="pr-code">VERİ YOK</span>`
        + `${escapeHtml(record.block_reason || record.capability || '')}`
        + `<span class="dom-meta">${escapeHtml(stepId)}</span></li>`);
    }
  });

  target.innerHTML = [
    listBlock('PROBLEMLER', signals.filter((s) => !isOpportunity(s)).map(signalItem),
      'Problem sinyali yok.'),
    listBlock(hasKind ? 'FIRSATLAR' : 'BİLGİ NOTLARI (fırsat olduğu doğrulanmadı)',
      signals.filter(isOpportunity).map(signalItem), 'Bilgi notu yok.'),
    listBlock('KANIT DENETİMİ', objections, 'İtiraz kaydedilmedi.'),
    listBlock('ÖNERİLEN ADIMLAR', actions, 'Önerilen adım yok.'),
    listBlock('VERİ EKSİKLERİ', gaps, 'Bildirilen veri eksiği yok.'),
  ].join('');
}

/* -- 6. one render pass ------------------------------------------------- */
function renderExecutionSurface() {
  if (!qs('execRail')) return;
  const [label, chipCls, coreKey] = deriveExecState();
  const chip = qs('execStateChip');
  chip.textContent = label;
  chip.className = 'exec-state-chip ' + chipCls;
  if (execOverride()) applyCoreState(coreKey, label);
  else applyLoopCoreState();

  const source = state.lastRun ? 'son analiz kaydı' : (state.lastPlan ? 'hazırlanan plan' : '—');
  ['execSrc', 'domainGridSrc', 'evidenceSrc', 'proposedSrc'].forEach((id) => {
    const el = qs(id);
    if (el) el.textContent = 'kaynak: ' + source;
  });
  const domainSrc = qs('domainSrc');
  /* 🔴 "plan yok" BİR HATA DEĞİL, BOŞ DURUMDU -- ama hata gibi okunuyordu.
     Sahip "bunlarda neden plan yok" diye sordu. Şerit, SON ÇALIŞTIRILAN
     planın alanlarını gösteriyor; hiç plan çalıştırılmadıysa doldurulacak
     bir şey yok. Artık ne yapılacağını söylüyor. */
  if (domainSrc) {
    domainSrc.textContent = state.lastRun ? 'yürütme kaydı'
      : (state.lastPlan ? 'plan hazır, çalıştırılmadı' : 'henüz çalıştırılmadı');
    domainSrc.title = state.lastRun || state.lastPlan ? ''
      : 'Bu şerit son çalıştırılan analizin alanlarını gösterir. '
        + 'ANALİZ sekmesinden PLAN ÜRET → ÇALIŞTIR deyin, buraya sonuç düşsün.';
    domainSrc.classList.toggle('plan-henuz', !state.lastRun && !state.lastPlan);
  }

  renderRail();
  renderDomains();
  renderEvidence();
  renderProposed();

  qs('execNote').textContent = state.lastRun
    ? `Son çalışma: ${ORCHESTRATION_STATUS[state.lastRun.status] || 'Durum belirlenemedi'}.`
    : (state.lastPlan
      ? 'Yürütme başlamadı: bu konsolda çalıştırma uç noktası yok. Aşamalar '
        + 'planın kendi kararlarını gösteriyor, ilerleme yüzdesi üretilmiyor.'
      : 'Henüz plan üretilmedi.');
}

renderExecutionSurface();
checkSession();

/* ---------------- VERİ / AJANLAR / RAPORLAR / AYARLAR ----------------
 * Bu dört bölüm markup'ta disabled duruyordu: arka uç servisi yoktu ve
 * tıklayınca bir şey varmış gibi davranmamaları doğruydu. Artık
 * /api/panel/<bölüm> gerçek ölçüm döndürüyor, o yüzden açıldılar.
 * Okunamayan bir kaynak gizlenmez -- hatasıyla gösterilir. */
/* EKIP buraya 20.09.2026'da eklendi. Ekranin TAMAMI yazilmisti --
 * viewEkip kabi, renderEkip, ekipSatir, SOR dugmesi, /api/ekip/sor ucu ve
 * _panel_ekip -- ama bu iki haritaya kaydedilmemisti. Sonuc: setView('ekip')
 * ilk satirda `if (!VIEWS[name]) return;` ile donuyor ve EKIP sekmesine
 * basinca HICBIR SEY olmuyordu. Calisan kodun kayitsiz kalmasi, olmayan
 * koddan daha zor fark ediliyor. */
const PANEL_SECTIONS = { ekip: 1, veri: 1, ajanlar: 1, raporlar: 1, ayarlar: 1 };

function kvRow(label, value, cls) {
  return `<div class="kv${cls ? ' ' + cls : ''}">
    <span class="kv-k">${escapeHtml(String(label))}</span>
    <span class="kv-v">${escapeHtml(value === undefined || value === null ? '—' : String(value))}</span>
  </div>`;
}
function stateChip(value) {
  const v = String(value || '').toUpperCase();
  const tone = /OK|AVAILABLE|CONNECTED|TRUE|PASS/.test(v) ? 'good'
    : /FAIL|UNAVAILABLE|ERROR|BLOCKED/.test(v) ? 'bad'
    : /DEGRADED|PARTIAL|WARN|UPGRADE/.test(v) ? 'warn' : 'flat';
  return `<span class="chip chip-${tone}">${escapeHtml(String(value))}</span>`;
}
function card(title, bodyHtml, meta) {
  return `<article class="sect-card">
    <header class="sect-card-head">
      <h3>${escapeHtml(title)}</h3>${meta ? `<span class="sect-meta">${meta}</span>` : ''}
    </header>
    ${bodyHtml}
  </article>`;
}

function renderVeri(d) {
  const domains = (d.domains || []).map((dom) => {
    const rows = (dom.queries || []).map((q) => kvRow(
      JarvisMetin.label(q.name, 'Veri sorgusu'), q.status === 'OK' ? `${q.rows} kayıt · ${q.latency_ms} ms`
        : JarvisMetin.errorText(q.error, 'Veri alınamadı'), q.status === 'OK' ? '' : 'is-bad')).join('');
    return card(JarvisMetin.label(dom.domain, 'Veri alanı'), rows,
                stateChip(`${dom.ok}/${dom.total}`));
  }).join('');
  const prov = (d.provenance || []).map((p) => kvRow(
    JarvisMetin.label(p.alan, 'Veri kaynağı'), `${JarvisMetin.label(p.connection, 'Bağlantı bilinmiyor')} · ${JarvisMetin.label(p.freshness, 'Güncellik bilinmiyor')}`,
    p.connection === 'CONNECTED' ? '' : 'is-warn')).join('');
  const qual = (d.quality || []).map((q) => kvRow(
    JarvisMetin.label(q.check, 'Veri kontrolü'), q.passed === true ? 'GEÇTİ' : q.passed === false ? 'KALDI' : JarvisMetin.label(q.detail, 'Kontrol sonucu yok'),
    q.passed === false ? 'is-bad' : '')).join('');
  return domains + card('KAYNAK OTORİTESİ', prov, `${(d.provenance || []).length} alan`)
    + card('VERİ KALİTESİ', qual, '');
}

/* Rollerin gercegi: panelde 28 satir var ama 28 farkli yetenek YOK.
 * Uretmeyen rol isaretlenir -- gizlemek tabloyu temiz gosterirdi ama
 * olmayan bir kabiliyeti ima ederdi. */
function renderRoleReality(block) {
  if (!block) return '';
  const rows = (block.contributions || []).map((c) => {
    const bos = c.status !== 'PRODUCED';
    const kalemler = Object.entries(c.items || {})
      .map(([k, v]) => `${escapeHtml(JarvisMetin.label(k, 'Üretilen bilgi'))}: ${v}`).join(' · ');
    return `<div class="kv${bos ? ' is-bad' : ''}">
      <span class="kv-k">${escapeHtml(JarvisMetin.label(c.role, 'Ekip üyesi'))}</span>
      <span class="kv-v">${bos ? 'ÜRETMEDİ' : escapeHtml(kalemler || '—')}</span>
    </div>`;
  }).join('');
  const son = block.last_run || {};
  const meta = son.product
    ? `${escapeHtml(String(son.product))} · ${escapeHtml(String(son.objective || ''))}`
    : 'henüz ajans koşusu yok';
  return card('SON KOŞUDA ROL KATKILARI', rows || '<p class="sect-note">Kayıt yok.</p>', meta)
    + `<p class="sect-note">${escapeHtml(String(block.note || ''))}</p>`;
}

/* Ekip: her uyenin adi, gorevi ve BU VERIYE BAKINCA ne soyledigi.
 * Konusamayan uye gizlenmez -- sebebini soyler. Gizlemek paneli temiz
 * gosterirdi ama olmayan bir kabiliyeti ima ederdi. */
function renderTeam(rows) {
  if (!Array.isArray(rows) || !rows.length) return '';
  const konusan = rows.filter((r) => r.status === 'KONUŞTU');
  const susan = rows.filter((r) => r.status !== 'KONUŞTU');
  const blok = (r) => `<details class="detail-block">
      <summary><strong>${escapeHtml(JarvisMetin.label(r.name || r.key, 'Ekip üyesi'))}</strong>
        <span class="kv-v">${escapeHtml(JarvisMetin.label(r.status, 'Durum bilinmiyor'))}</span></summary>
      <p class="sect-note">${escapeHtml(JarvisMetin.safeTitle(r.job, 'Görev açıklaması yok'))}</p>
      <p>${escapeHtml(JarvisMetin.safeTitle(r.statement, 'Bu konuda henüz açıklama yok.'))}</p>
      ${r.reads && r.reads.length
        ? `<p class="sect-note">okuduğu veri: ${escapeHtml(r.reads.map((name) => JarvisMetin.label(name, 'Veri kaynağı')).join(', '))}</p>`
        : ''}
    </details>`;
  return card('EKİP — KİM NE DİYOR', konusan.map(blok).join(''),
              `${konusan.length} üye konuştu`)
    + card('KONUŞAMAYANLAR', susan.map(blok).join(''),
           `${susan.length} üye`);
}

function renderAjanlar(d) {
  const roles = (d.roles || []).map((r) => kvRow(
    EKIP_BIRIM_ADI[r.id] || JarvisMetin.label(r.id, 'Tanımlı rol'), JarvisMetin.label(r.kind || r.domain, 'Görev alanı'))).join('');
  const provs = (d.providers || []).map((p) => kvRow(
    JarvisMetin.label(p.provider, 'Model sağlayıcısı'), JarvisMetin.label(p.state, 'Durum bilinmiyor'))).join('');
  const engines = (d.engines || []).map((e) => `<div class="kv">
      <span class="kv-k">${escapeHtml(JarvisMetin.label(e.name, 'Çalışma motoru'))}</span>
      <span class="kv-v">${stateChip(JarvisMetin.label(e.state, 'Durum bilinmiyor'))} ${escapeHtml(String(e.version || ''))}</span>
    </div>`).join('');
  return renderTeam(d.team)
    + renderRoleReality(d.role_reality)
    + card('MODEL SAĞLAYICILARI', provs, `${(d.providers || []).length}`)
    + card('MOTORLAR', engines, `${(d.engines || []).length}`)
    + card('TANIMLI ROLLER', roles, `${(d.roles || []).length} kayıt`);
}

/* Dersler: sayimdir, neden-sonuc degil. Karara hic baglanmamis kumeler once
 * gelir -- dusuk onay oranindan daha acil olan odur. */
function renderLessons(block) {
  if (!block || block.status === 'UNAVAILABLE' || block.status === 'ERROR') {
    const reason = escapeHtml(String((block && (block.note || block.error)) || 'okunamadı'));
    return card('DERSLER', `<p class="sect-note">Ders üretilemedi: ${reason}</p>`, '');
  }
  const rows = (block.lessons || []).slice(0, 10).map((lesson) => {
    const stuck = lesson.decided === 0 && lesson.stuck > 0;
    const rate = lesson.approval_rate === null || lesson.approval_rate === undefined
      ? '—' : `%${Math.round(lesson.approval_rate * 100)}`;
    return `<div class="kv${stuck ? ' is-bad' : ''}">
      <span class="kv-k">${escapeHtml(String(lesson.summary))}</span>
      <span class="kv-v">${stuck
        ? `BEKLEMEDE · ${lesson.sample} karar`
        : `${rate} onay · ${lesson.decided}/${lesson.sample} karara bağlandı`}</span>
    </div>`;
  }).join('');
  const meta = `${block.decisions || 0} karar · ${block.model_calls || 0} model çağrısı`;
  return card('DERSLER', rows || '<p class="sect-note">Yeterli örneklem yok.</p>', meta)
    + `<p class="sect-note">${escapeHtml(String(block.note || ''))}</p>`;
}


function renderImprovement(d) {
  if (!d || d.error_type) return card('GELİŞİM DÖNGÜSÜ', '<p>Gelişim defteri okunamadı.</p>', '');
  const statuses = {WAITING_APPLICATION_EVIDENCE:'Uygulama kanıtı bekliyor', WAITING_MEASUREMENT:'Sonuç ölçümü bekliyor', TARGET_REACHED:'Hedefe ulaştı', MEASURED_FOLLOW_UP:'Ölçüldü; takip gerekli', CANCELLED:'İptal edildi'};
  const works = d.works || [];
  const rows = works.slice(0, 60).map(w => `<div class="kv"><span class="kv-k">#${w.id} ${escapeHtml(JarvisMetin.safeTitle(w.objective, 'Gelişim işi'))}</span><span class="kv-v">${escapeHtml(statuses[w.status] || JarvisMetin.label(w.status, 'Durum bilinmiyor'))}</span></div><p class="sect-note">Sorumlu: ${escapeHtml(JarvisMetin.label(w.owner, 'Sorumlu belirtilmemiş'))} · Son tarih: ${escapeHtml(w.due)}${w.overdue ? ' · Süresi geçti' : ''}<br>Ölçüt: ${escapeHtml(JarvisMetin.safeTitle(w.metric, 'Başarı ölçütü'))} · Hedef: ${escapeHtml(String(w.target ?? 'belirlenecek'))} ${escapeHtml(w.unit)}<br>Kaynak: ${escapeHtml(JarvisMetin.label(w.source, 'Kaynak belirtilmemiş'))}</p>`).join('');
  const lessons = (d.outcome_lessons || []).map(r => `<p>${escapeHtml(r.summary)}<br><small>${r.sample} gözlem · ${escapeHtml(r.evidence.join(' · '))}</small></p>`).join('');
  const ev = d.evaluation || {};
  const cases = ev.cases || [];
  const tests = cases.map(r => kvRow(r.task, `${r.status === 'PASS' ? 'Kaynak okunuyor' : r.status === 'NEEDS_DATA' ? 'Veri gerekli' : 'Okuma hatası'} · ${r.duration_ms} ms`)).join('');
  const previous = d.previous_evaluation;
  const comparison = previous ? `<p class="sect-note">Önceki kontrol: ${(previous.cases || []).filter(r=>r.status==='PASS').length}/${(previous.cases || []).length} kaynak · ${previous.duration_ms} ms. Son kontrol: ${ev.duration_ms} ms.</p>` : '';
  const modelEval = d.model_evaluation || {};
  const modelTests = (modelEval.cases || []).map(r => kvRow(JarvisMetin.label(r.task, 'Model kontrolü'), `${JarvisMetin.label(r.status, 'Durum bilinmiyor')} · ${r.model || 'yanıt alınamadı'} · ${r.duration_ms} ms`)).join('');
  const options = works.map(w => `<option value="${w.id}">#${w.id} ${escapeHtml(w.objective.slice(0,100))}</option>`).join('');
  const labels = {domain:'Alan / konu',objective:'Yapılacak iş',owner:'Sorumlu rol',metric:'Başarı ölçütü',unit:'Birim',target:'Hedef değer',due:'Son tarih',source:'İşin kaynağı',at:'Uygulandığı tarih',evidence:'Uygulama / düzeltme kanıtı',baseline:'Başlangıç değeri',result:'Sonuç değeri',sample:'Gözlem sayısı',before_at:'Başlangıç ölçüm tarihi',after_at:'Sonuç ölçüm tarihi',before_source:'Başlangıç ölçümünün kaynağı',after_source:'Sonuç ölçümünün kaynağı',note:'Ölçüm yorumu ve sınırları',wrong:'Hatalı yaklaşım',right:'Doğru yaklaşım',reason:'Neden'};
  function form(operation,title,fields) {
    const inputs = fields.map(name => {
      if(name === 'work_id') return `<label>İş <select name="work_id" required>${options}</select></label>`;
      if(name === 'direction') return '<label>İyileşme yönü <select name="direction"><option value="lower">Değer azaldıkça iyileşir</option><option value="higher">Değer arttıkça iyileşir</option></select></label>';
      const type = ['baseline','result','target','sample'].includes(name) ? 'number' : ['at','due','before_at','after_at'].includes(name) ? 'datetime-local' : 'text';
      return `<label style="display:block;margin:8px 0">${labels[name]} <input style="width:100%" name="${name}" type="${type}" ${type === 'number' ? `step="${name === 'sample' ? '1' : 'any'}"` : 'maxlength="1000"'} required></label>`;
    }).join('');
    return `<details><summary>${title}</summary><form data-improvement="${operation}">${inputs}<button type="submit">Kaydet</button><p role="status" class="sect-note"></p></form></details>`;
  }
  const forms = form('work','Yeni iş ve hedef oluştur',['domain','objective','owner','metric','unit','direction','target','due','source'])
    + form('plan','Mevcut işin sorumlusunu ve hedefini belirle',['work_id','owner','metric','unit','direction','target','due'])
    + form('application','Yapılan uygulamanın kanıtını kaydet',['work_id','at','evidence'])
    + form('measurement','Önce / sonra sonuç ölçümü ekle',['work_id','baseline','result','sample','before_at','after_at','before_source','after_source','note'])
    + form('correction','Jarvis’in hatasını ve doğru yaklaşımı hatırlat',['domain','wrong','right','reason','evidence']);
  return card('GELİŞİM DÖNGÜSÜ', `<p class="sect-note">${escapeHtml(d.note)} Görevler ve kaynaklar her saat kontrol edilir.</p>${rows}`, `${works.length} iş`)
    + card('ÖLÇÜLEN SONUÇLAR', lessons || '<p>Henüz uygulama ve ölçümü birlikte kaydedilmiş iş yok.</p>', '')
    + card('CANLI KAYNAK KONTROLLERİ', `${tests}${comparison}<p class="sect-note">${escapeHtml(ev.note || '')}</p>`, `${cases.filter(r=>r.status==='PASS').length}/${cases.length} kaynak`)
    + card('MODEL KANIT YORUMLAMA TESTLERİ', modelTests + `<p class="sect-note">${escapeHtml(modelEval.note || 'Model değerlendirmesi henüz çalıştırılmadı.')}</p>`, '')
    + card('İŞ, ÖLÇÜM VE DÜZELTME KAYDI', forms+'<p class="sect-note">Tarihleri yerel saatinizle girin. Ölçüm aralığı gerçek uygulama tarihini kapsamalıdır. Kanıt olarak rapor veya kayıt konumunu belirtin.</p>', `${(d.corrections || []).length} düzeltme`);
}

document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.dataset.improvement) return;
  event.preventDefault();
  const button = form.querySelector('button');
  const message = form.querySelector('[role="status"]');
  button.disabled = true;
  try {
    const data = Object.fromEntries(Array.from(form.elements).filter(el => el.name && !el.disabled).map(el => [el.name, el.value]));
    data.operation = form.dataset.improvement;
    for (const key of ['work_id','baseline','result','sample','target']) if (key in data) data[key] = Number(data[key]);
    for (const key of ['at','due','before_at','after_at']) if (key in data) data[key] = new Date(data[key]).toISOString();
    if(data.operation === 'work') data.source_key = 'operator:'+crypto.randomUUID();
    await postJSON('/api/improvement', data);
    message.textContent = 'Kaydedildi.';
    await loadSection('raporlar');
  } catch (error) { message.textContent = error.message || String(error); }
  finally { button.disabled = false; }
});

function renderRaporlar(d) {
  const f = (d.findings || []).map((x) => `<div class="kv">
      <span class="kv-k">${escapeHtml(yonetimKodu(x.code))}</span>
      <span class="kv-v">${stateChip(JarvisMetin.label(x.severity, 'Önem belirtilmemiş'))} ${x.count}×</span>
    </div>${x.reason ? `<p class="sect-note">${escapeHtml(yonetimAciklama(x.reason))}</p>` : ''}`).join('');
  const c = (d.cycle_results || []).map((x) => kvRow(JarvisMetin.label(x.result, 'Döngü sonucu'), `${x.count} döngü`)).join('');
  const last = d.last_cycle || {};
  const b = last.business || {};
  const lastRows = kvRow('döngü', last.cycle) + kvRow('sonuç', JarvisMetin.label(last.result, 'Sonuç yok'))
    + kvRow('iş zekâsı', b.status ? `${JarvisMetin.label(b.status, 'Durum bilinmiyor')} · ${b.signals} sinyal` : '—')
    + kvRow('model çağrısı', last.model_calls) + kvRow('dış aksiyon', last.external_actions)
    + kvRow('süre', last.total_ms ? `${last.total_ms} ms` : '—');
  return renderImprovement(d.lessons && d.lessons.improvement)
    + renderLessons(d.lessons)
    + card('SON DÖNGÜ', lastRows, '')
    + card('BULGULAR', f, `${d.finding_total || 0} kayıt`)
    + card('DÖNGÜ SONUÇLARI', c, '');
}

/* Model kullanimi: UCRETLI cagri ayri isaretlenir. Para tahmin edilmez --
 * birim fiyat zamanla degisir ve panele sabit yazmak bir gun sessizce
 * yanlis rakam gostermek olurdu. */
function renderUsage(block) {
  if (!block) return '';
  if (block.error) {
    return card('MODEL KULLANIMI',
      `<p class="sect-note">Okunamadı: ${escapeHtml(String(block.error))}</p>`, '');
  }
  /* Para biçimi: kuruşun altı da görünsün. Model çağrıları kuruşun
     onda biri mertebesinde; 2 hane yuvarlarsak hepsi "0,00 TL" olur ve
     tablo hiçbir şey anlatmaz. */
  const para = (x, hane) => (x === null || x === undefined)
    ? '—'
    : Number(x).toLocaleString('tr-TR', {
        minimumFractionDigits: hane, maximumFractionDigits: hane });

  const rows = (block.providers || []).map((p) => {
    const tok = (p.prompt_tokens || 0) + (p.completion_tokens || 0);
    /* 🔴 Birim fiyat GİRDİ ve ÇIKTI diye AYRI yazılır. Tek bir "ortalama
       fiyat" yazmak yanıltırdı: çıktı tokeni girdinin 5-8 katı ve oran
       her işte değişir. */
    const birim = (p.birim_girdi_usd_m === null || p.birim_girdi_usd_m === undefined)
      ? `<i class="mk-yok">${escapeHtml(String(p.fiyat_notu || 'fiyat tanımsız'))}</i>`
      : `girdi $${para(p.birim_girdi_usd_m, 2)} · çıktı $${para(p.birim_cikti_usd_m, 2)} /M`;
    /* 🔴 Kurulu ama hic cagrilmamis saglayici, "0,00 TL" yazsaydi
       "bedava calisiyor" gibi okunurdu. Ayri bir ifade gerekiyor. */
    const maliyet = p.kullanilmadi
      ? 'hiç çağrılmadı'
      : ((p.maliyet_try === null || p.maliyet_try === undefined)
          ? '—'
          : `${para(p.maliyet_try, 4)} TL`);
    const basi = (p.cagri_basi_try === null || p.cagri_basi_try === undefined)
      ? ''
      : ` · çağrı başı ${para(p.cagri_basi_try, 4)} TL`;
    return `<div class="kv mk-satir${p.parali ? ' is-bad' : ''}${
      p.kullanilmadi ? ' mk-bos' : ''}">
      <span class="kv-k">
        <span class="mk-ad"><b>${escapeHtml(String(p.provider))}</b>${
          /* 🔴 ROZET FİYATA BAKAR, `paid` alanına DEĞİL. `paid` zincirde
             "yalnız derin modda dene" demek; Gemini orada false ama
             anahtarı faturalı, yani her çağrısı para harcıyor. Sahip
             22.09.2026'da düzeltti: "gemini de ücretli bu arada." */
          p.parali ? '<em class="mk-ucretli">ÜCRETLİ</em>'
            : (p.parali === false ? '<em class="mk-bedava">ÜCRETSİZ</em>' : '')
        }${
          p.sadece_derin ? '<em class="mk-derin">yalnız derin mod</em>' : ''
        }</span>
        <small>${birim}</small>
      </span>
      <span class="kv-v">
        <b>${escapeHtml(maliyet)}</b>
        <small>${p.kullanilmadi
          ? 'kurulu · zincirin sırası buraya gelmedi'
          : `${p.calls} çağrı · ${tok.toLocaleString('tr-TR')} token · ort ${p.avg_s}s${
              p.failed ? ` · ${p.failed} hata` : ''}${basi}`}</small>
      </span>
    </div>`;
  }).join('');

  const t = block.fiyat_tablosu || {};
  const toplam = (block.tahmini_maliyet_try === null || block.tahmini_maliyet_try === undefined)
    ? ''
    : `<div class="kv mk-toplam">
        <span class="kv-k"><b>7 günün tahmini maliyeti</b></span>
        <span class="kv-v"><b>${para(block.tahmini_maliyet_try, 2)} TL</b>
          <small>$${para(block.tahmini_maliyet_usd, 4)} · kur ${para(t.usd_try, 2)}
          (${escapeHtml(String(t.usd_try_tarih || ''))})</small></span>
      </div>`;

  /* Fiyatın YANINDA TARİHİ de durur. Tablo eskirse panel bunu söyler --
     sessizce eski rakam göstermek, rakam göstermemekten kötüdür. */
  const tabloNotu = t.gecerlilik
    ? `<p class="sect-note${t.bayat ? ' mk-bayat' : ''}">
        Liste fiyatları ${escapeHtml(String(t.gecerlilik))} tarihinde sağlayıcıların
        resmî sayfalarından alındı${t.gun_gecti ? ` (${t.gun_gecti} gün önce)` : ''}.
        ${t.bayat ? '⚠ Tablo eskimiş olabilir, güncellenmeli. ' : ''}
        ${escapeHtml(String(t.uyari || ''))}</p>`
    : '';

  const bilinmeyen = (block.fiyati_bilinmeyen || []).length
    ? `<p class="sect-note">Fiyatı tanımlı olmayan sağlayıcı:
        ${escapeHtml((block.fiyati_bilinmeyen || []).join(', '))} — bunlar toplama
        KATILMADI (sıfır sayılmadı).</p>`
    : '';

  /* "1 ücretli" yazıyordu ve YANLIŞTI: o sayı `paid` bayrağını sayıyordu,
     gerçekte 81 çağrının 80'i para harcamıştı. */
  const meta = `${block.total_calls || 0} çağrı · ${block.paid_calls || 0} ücretli`
    + `${block.ucretsiz_calls ? ` · ${block.ucretsiz_calls} ücretsiz` : ''} (7 gün)`;
  return card('MODEL KULLANIMI', rows + toplam || '<p class="sect-note">Kayıt yok.</p>', meta)
    + tabloNotu + bilinmeyen
    + `<p class="sect-note">${escapeHtml(String(block.note || ''))}</p>`;
}

function renderAyarlar(d) {
  const env = Object.entries(d.env || {}).map(([k, v]) => kvRow(k, v,
    k === 'EXTERNAL_ACTIONS' && String(v) !== 'false' ? 'is-bad' : '')).join('');
  const th = Object.entries(d.thresholds || {}).map(([k, v]) => kvRow(k, v)).join('');
  const gated = (d.compliance?.gated_actions || []).map((a) => kvRow(a, 'mevzuat kapısı açık')).join('');
  return renderUsage(d.model_usage)
    + card('YÖNETİŞİM', env, d.readonly ? stateChip('SALT OKUNUR') : '')
    + `<p class="sect-note">${escapeHtml(String(d.note || ''))}</p>`
    + card('MEVZUAT KAPISI', gated, escapeHtml(String(d.compliance?.rules_source || '')))
    + card('İŞ ZEKÂSI EŞİKLERİ', th, '')
    + card('ACİL DURDURMA', `<p class="sect-note">${escapeHtml(JarvisMetin.label(d.kill_switch, 'Durum bilgisi yok'))}</p>`, '');
}

/* ==================================================================
   EKİP PANOSU

   Ne gösterir: 45 departman, hangisinin kadrosu var, o kadro ŞU AN
   veriden konuşabiliyor mu. Ve her departmana soru sorulabilir.

   🔴 İKİ AYRI "ÇALIŞIYOR" VAR, PANO İKİSİNİ DE GÖSTERİR:
     nokta rengi  -> üyeler ŞU AN okuyabildi mi (canlı ölçüm)
     birim rozeti -> core.departman.durum (veri kaynağı tanımlı mı)
   Bir departman "CALISIYOR" işaretli olup sorgusu düştüğü için sarı
   olabilir. Tek renge indirmek, yeşil panoda ölü bir birimi gizlerdi.
   ================================================================== */

const EKIP_RENK = {
  yesil:  { sinif: 'ek-yesil',  etiket: 'veri okuyor' },
  sari:   { sinif: 'ek-sari',   etiket: 'veri veya görev bekliyor' },
  kirmizi:{ sinif: 'ek-kirmizi',etiket: 'okuması gereken veri açık değil' },
  gri:    { sinif: 'ek-gri',    etiket: 'kadrosu yok' },
};

const EKIP_AILE_ADI = {
  ALTYAPI: 'Altyapı', BRAND: 'Marka', COMMERCIAL: 'Ticaret',
  CREATIVE: 'Yaratıcı üretim', CUSTOMER: 'Müşteri', DATA: 'Veri',
  EXECUTIVE: 'Üst yönetim', GOVERNANCE: 'Yönetişim',
  INTELLIGENCE: 'Araştırma', KREATIF: 'Kreatif',
  MARKETING: 'Pazarlama', OPERATIONS: 'Operasyon',
  PLATFORM: 'Platform', PRODUCT: 'Ürün',
};

const EKIP_BIRIM_ADI = {
  TEKNOLOJI: 'Teknoloji ve araç geliştirme', WEB: 'Web ve dönüşüm',
  BRAND: 'Marka', PR: 'Basın ve halkla ilişkiler',
  B2B: 'Kurumsal satış', BIZDEV: 'İş geliştirme',
  CRO: 'Dönüşüm ve kullanıcı deneyimi', ECOM: 'E-ticaret ve sipariş',
  EXPORT: 'İhracat ve uluslararası pazar', MARKETPLACE: 'Pazaryerleri',
  PHARMACY: 'Eczane ve kilit müşteriler', ART: 'Sanat yönetimi',
  CONTENT: 'İçerik', COPY: 'Metin yazarlığı',
  CREATIVE_STRAT: 'Kreatif strateji', UGC: 'Video ve kullanıcı içerikleri',
  CRM: 'Müşteri ilişkileri', CS: 'Müşteri hizmetleri',
  CUSTOMER_INT: 'Müşteri araştırması', RETENTION: 'Müşteri bağlılığı',
  DATA_BI: 'Veri ve iş zekâsı', EXPERIMENT: 'Deneyler',
  FORECAST: 'Tahminleme', EXEC: 'Üst yönetim ve strateji',
  FINANCE: 'Finans ve birim ekonomisi', DECISION_MEM: 'Karar hafızası',
  LEGAL: 'Hukuk ve kişisel veriler', QUALITY: 'Kalite',
  RED_TEAM: 'İç denetim', REGULATORY: 'Mevzuat ve ürün iddiaları',
  COMPETITOR_INT: 'Rakip araştırması', MARKET_INT: 'Pazar araştırması',
  TASARIM: 'Tasarım ve üretim', YAYIN: 'Yayın ve editoryal',
  GOOGLE_ADS: 'Google arama reklamları', INFLUENCER: 'İçerik üreticileri',
  INSTAGRAM: 'Instagram', META_MEDIA: 'Meta reklamları',
  SEO: 'Arama görünürlüğü', SOCIAL: 'Organik sosyal medya',
  TIKTOK: 'TikTok ve kısa video', FULFILLMENT: 'Sipariş hazırlama ve kargo',
  INVENTORY: 'Stok ve envanter', PROCUREMENT: 'Satın alma',
  SUPPLY: 'Tedarik zinciri', AI_OPS: 'Otomasyon ve yapay zekâ',
  SECURITY: 'Güvenlik', PRODUCT: 'Ürün yönetimi',
  RND: 'Araştırma ve yeni ürün',
};

function ekipBirimAdi(department) {
  return EKIP_BIRIM_ADI[department.kod] || department.ad || department.kod || 'Adsız birim';
}

function ekipTakipAcikla(value) {
  return String(value || '').replace(/REQUEST_HUMAN_REVIEW/g, 'insan incelemesi');
}

function ekipAileAdi(code) {
  return EKIP_AILE_ADI[code] || code || 'Diğer';
}

function ekipBirimDurumu(value) {
  return ({ CALISIYOR: 'Kaynak tanımlı', KISMI: 'Kısmi bağlantı',
    YOK: 'Kaynak bağlı değil' })[value] || value || 'Durum bilinmiyor';
}

function ekipKaynakAdi(ref) {
  const names = {
    sales_orders: 'siparişler', sales_items: 'sipariş kalemleri',
    ecommerce_profitability: 'ürün kârlılığı', ecommerce_price: 'ürün fiyatları',
    ecommerce_funnel: 'satış yolu', advertising_performance: 'reklam performansı',
    advertising_spend: 'reklam harcaması', crm_customers: 'müşteriler',
    crm_unanswered: 'yanıtsız görüşmeler', operations_shipments: 'gönderiler',
    open_work: 'açık işler', system: 'sistem durumu',
  };
  if (String(ref).startsWith('http')) return 'dış kaynak bağlantısı';
  return names[String(ref).replace(/^postgres:/, '')] || 'şirket veri kaynağı';
}

function ekipBirimKaynagi(ref) {
  const value = String(ref || '').trim();
  if (!value || value === 'None') return 'Kaynak belirtilmemiş';
  if (value.startsWith('YOK')) return 'Kaynak bağlı değil';
  return ekipKaynakAdi(value);
}

function ekipSorumluAdi(owner) {
  return ({ operations: 'Operasyon ekibi', sales: 'Satış ekibi',
    ecommerce: 'E-ticaret ekibi', advertising: 'Reklam ekibi',
    crm: 'Müşteri ilişkileri ekibi', strategy: 'Strateji ekibi',
    research: 'Araştırma ekibi', managing_director: 'Genel müdür' })[owner] || owner;
}

function renderEkip(data) {
  if (data.error) return `<p class="sect-empty is-bad">Ekip verisi okunamadı: ${escapeHtml(data.error)}</p>`;
  let deps = data.departmanlar || [];
  const birimAdlari = new Map(deps.map(department => [department.ad, ekipBirimAdi(department)]));
  const yonetim = data.yonetim || {};
  const uyeler = yonetim.uyeler || [];
  const uyeKayitlari = new Map(uyeler.map(member => [member.key, member]));
  const sonIsler = uyeler.filter(u => u.durum === 'ÇALIŞTI')
    .sort((left, right) => (left.gorev_turu === 'VERİ KONTROLÜ') - (right.gorev_turu === 'VERİ KONTROLÜ'));
  const durumSayilari = yonetim.durum_sayilari || {};
  const oncelikler = yonetim.oncelikler || [];
  const mudur = uyeler.find(u => u.key === 'managing_director');
  const yonetimMasasi = `<div class="lead-desk">
    <div class="lead-intro">
      <div><span class="lead-eyebrow">L’CARLIÉ / Organizasyon</span>
        <h3>Yönetim masası</h3>
        <p>Ekip faaliyetleri ve takip gerektiren işler. Son kontrol: ${escapeHtml(fmtDateTime(yonetim.uretim_zamani) || 'kayıt yok')} · ${yonetim.guncel ? 'güncel' : 'güncel kayıt yok'}.</p></div>
      <div class="lead-actions"><a class="lead-ask" href="#ekipDizin">Tüm departmanlar</a>
        <button type="button" class="lead-ask" data-ask="Ekipteki son kanıtlı çıktıları ve geciken işleri özetle; kaynakları ve eksikleri ayır.">Jarvis’le konuş</button></div>
    </div>
    <div class="lead-metrics">
      <div><strong>${durumSayilari['ÇALIŞTI'] || 0}</strong><span>son kontrolde kayıt üretti · ${yonetim.rutin_kontrol || 0} yalnızca veri okudu</span></div>
      <div><strong>${durumSayilari['GÖREV BEKLİYOR'] || 0}</strong><span>veri veya görev bekliyor</span></div>
      <div><strong>${durumSayilari['HATA'] || 0}</strong><span>son kontrolde hata aldı</span></div>
      <div><strong>${durumSayilari['İZLENMİYOR'] || 0}</strong><span>bu kontrolde izlenmedi</span></div>
    </div>
    <div class="lead-director"><strong>Genel müdürün önerisi</strong><p>${mudur && mudur.son_is_acik
      ? escapeHtml(mudur.son_is_acik) : 'Son kontrolde genel müdür önerisi kaydedilmedi.'}</p></div>
    <div class="lead-columns">
      <section><h4>Son kayıtlı çıktılar</h4>${sonIsler.length ? sonIsler.slice(0, 8).map(u =>
        `<article class="lead-row"><div><b>${escapeHtml(u.ad)}</b><span>${escapeHtml(u.gorev_turu || birimAdlari.get(u.birim) || u.birim)}</span></div><p>${escapeHtml(u.son_is_acik || u.son_is)}</p></article>`).join('')
        : '<p class="lead-empty">Güncel döngüde kanıtlı çıktı kaydı yok.</p>'}</section>
      <section><h4>Yönetim takibi</h4>${oncelikler.length ? oncelikler.map(item =>
        `<article class="lead-row"><div><b>${escapeHtml(ekipSorumluAdi(item.sorumlu))}</b><span>${escapeHtml(item.durum === 'UYGULAMA KANITI BEKLER' ? 'Yapıldığını gösteren kayıt bekleniyor' : item.durum)}</span></div><p>${escapeHtml(ekipTakipAcikla(item.hedef))}</p><small>Son tarih: ${escapeHtml(String(item.son_tarih).slice(0, 10))}</small></article>`).join('')
        : '<p class="lead-empty">Takip gerektiren açık iş kaydı yok.</p>'}</section>
    </div>
    <details class="lead-members" id="ekipUyeler"><summary>Tüm üyeler · ${uyeler.length} kişi · görev, sonuç ve kanıt kayıtlarını aç</summary>
      <div class="lead-filters">${['HEPSİ', 'ÇALIŞTI', 'GÖREV BEKLİYOR', 'HATA', 'İZLENMİYOR'].map((status, index) =>
        `<button type="button" data-team-filter="${escapeHtml(status)}" aria-pressed="${index === 0}">${escapeHtml(({ 'ÇALIŞTI': 'KAYIT ÜRETTİ', 'GÖREV BEKLİYOR': 'BEKLİYOR', 'İZLENMİYOR': 'İZLENMEDİ' })[status] || status)}</button>`).join('')}</div>
      <div class="lead-member-list">${uyeler.map(u => `<div data-team-state="${escapeHtml(u.durum)}">
        <b>${escapeHtml(u.ad)}</b><span>${escapeHtml(birimAdlari.get(u.birim) || u.birim)}</span><em>${escapeHtml(({ 'ÇALIŞTI': 'Kayıt üretti', 'GÖREV BEKLİYOR': 'Bekliyor', 'İZLENMİYOR': 'İzlenmedi' })[u.durum] || u.durum)}</em>
        <small>Rol: ${escapeHtml(u.rol_tanimi || '—')}</small>
        <small>Görev türü: ${escapeHtml(u.gorev_turu || '—')}</small>
        <small>Son yürütülen görev: ${escapeHtml(u.gorev || 'bu döngüye bağlı değil')}</small>
        <small>Sonuç: ${escapeHtml(u.sonuc_acik || u.sonuc || 'henüz kayıt yok')}</small>
        <small>Kullanılan kaynaklar: ${escapeHtml((u.kanitlar || []).map(ekipKaynakAdi).join(' · ') || 'kayıt yok')}</small>
        <small>Son kontrol: ${escapeHtml(fmtDateTime(u.zaman) || 'kayıt yok')}</small>
        <small>Veri erişimi: ${escapeHtml(({ 'KONUŞTU': 'Veri okundu', 'VERİ YOK': 'Veri yok' })[u.veri_durumu] || u.veri_durumu)}</small>
      </div>`).join('')}</div>
    </details>
    <p class="lead-disclaimer">“Kayıt üretti” yalnız son döngüde bir aşamanın tamamlandığını gösterir; mesai veya dışarıya uygulanan işlem değildir. Dış araştırma kaynağı eski olabilir. Bu ekran görev atamaz veya mesaj göndermez.</p>
  </div>`;

  /* Çemberden bir küme seçildiyse yalnız o küme gösterilir.
     🔴 Sahip "şu anki halinde çok karmaşık duruyor" dedi: 45 departman
     tek sayfada alt alta. Süzgeç, ana ekrandaki düğüme tıklayınca
     devreye girer ve kaldırılabilir -- gizlemek değil, ODAKLAMAK. */
  let filtreBaslik = '';
  if (ekipFiltre && ekipFiltre.kodlar && ekipFiltre.kodlar.size) {
    const tumu = deps.length;
    deps = deps.filter((d) => ekipFiltre.kodlar.has(d.kod));
    const konusan = deps.filter((d) => d.renk === 'yesil').length;
    const bulgu = deps.reduce((t, d) => t + (d.arastirma_toplam || 0), 0);
    filtreBaslik = `
      <div class="ek-filtre">
        <div>
          <strong>${escapeHtml(ekipFiltre.ad)}</strong>
          <span> · ${deps.length}/${tumu} departman · ${konusan} birim veri okudu
            · ${bulgu} dış bulgu</span>
        </div>
        <button type="button" id="ekFiltreKaldir">TÜMÜNÜ GÖSTER</button>
      </div>`;
  }
  const oz = data.ozet || {};
  const renk = oz.renk || {};
  const aileSecenekleri = [...new Set(deps.map(d => String(d.aile || '')))].sort((left, right) =>
    ekipAileAdi(left).localeCompare(ekipAileAdi(right), 'tr'));

  const ozet = filtreBaslik + `
    <div class="ek-ozet">
      <div class="ek-tile"><span class="ek-n">${oz.departman ?? 0}</span><span class="ek-k">departman</span></div>
      <div class="ek-tile"><span class="ek-n">${oz.kadrosu_olan ?? 0}</span><span class="ek-k">kadrosu var</span></div>
      <div class="ek-tile"><span class="ek-n">${oz.konusan_uye ?? 0}/${oz.uye ?? 0}</span><span class="ek-k">üye veri okuyor</span></div>
      <div class="ek-tile ${data.arastirma_var ? '' : 'ek-tile-uyari'}">
        <span class="ek-n">${data.arastirma_toplam ?? 0}</span>
        <span class="ek-k">dış bulgu</span>
        <span class="ek-ar-son">${data.arastirma_son_kosu
          ? 'son koşu ' + escapeHtml(String(data.arastirma_son_kosu).slice(0, 10))
          : 'araştırma hiç koşmadı'}</span>
      </div>
      <div class="ek-tile ek-legend">
        <span class="ek-lg"><i class="ek-dot ek-yesil"></i>${renk.yesil ?? 0} veri okuyor</span>
        <span class="ek-lg"><i class="ek-dot ek-sari"></i>${renk.sari ?? 0} bekliyor</span>
        <span class="ek-lg"><i class="ek-dot ek-kirmizi"></i>${renk.kirmizi ?? 0} veri yok</span>
        <span class="ek-lg"><i class="ek-dot ek-gri"></i>${renk.gri ?? 0} kadrosuz</span>
      </div>
    </div>
    <p class="ek-not">Noktanın rengi son ekip döngüsündeki veri okuma sonucunu, birim etiketi ise veri kaynağının bağlantı durumunu gösterir. Bunlar farklı ölçümlerdir.</p>
    <section class="team-directory" id="ekipDizin" aria-label="Tüm departmanlar">
      <div class="team-directory-head">
        <div><span class="lead-eyebrow">EKİP DİZİNİ</span><h3>Tüm departmanlar</h3>
          <p>Birimi açarak görevini, üyelerini, son kayıtlarını ve yetki sınırlarını inceleyin.</p></div>
        <button type="button" data-team-members>${uyeler.length} kişilik üye dizinine git</button>
      </div>
      <div class="team-directory-controls">
        <label>Birimi veya kişiyi ara
          <input id="ekipArama" type="search" placeholder="Ad, görev, üye veya konu" autocomplete="off"></label>
        <label>Grup
          <select id="ekipAileSec"><option value="">Tüm gruplar</option>${aileSecenekleri.map(aile =>
            `<option value="${encodeURIComponent(aile)}">${escapeHtml(ekipAileAdi(aile))}</option>`).join('')}</select></label>
        <label>Veri erişimi
          <select id="ekipDurumSec"><option value="">Tüm durumlar</option>
            <option value="yesil">Veri okuyor</option><option value="sari">Bekliyor</option>
            <option value="kirmizi">Veri eksik</option><option value="gri">Kadrosuz</option></select></label>
      </div>
      <p class="team-directory-count" id="ekipGorunen" aria-live="polite">${deps.length} departman gösteriliyor</p>
      <p class="team-directory-empty" id="ekipBos" hidden>Bu aramaya uyan departman yok. Filtreleri değiştirebilirsiniz.</p>
    </section>`;

  // Aileye göre grupla; aile sırası veriden gelir, arayüz sabit liste tutmaz.
  const aileler = [];
  const kova = {};
  deps.forEach(d => {
    const a = d.aile || '—';
    if (!kova[a]) { kova[a] = []; aileler.push(a); }
    kova[a].push(d);
  });

  const bloklar = aileler.map(aile => {
    const liste = kova[aile];
    const konusan = liste.filter(d => d.renk === 'yesil').length;
    const satirlar = liste.map(d => ekipSatir(d, uyeKayitlari)).join('');
    return `<section class="ek-aile" data-team-family="${encodeURIComponent(aile)}">
      <div class="ek-aile-head">
        <span class="ek-aile-ad">${escapeHtml(ekipAileAdi(aile))}</span>
        <span class="ek-aile-say">${liste.length} birim · ${konusan} veri okuyor</span>
      </div>
      ${satirlar}
    </section>`;
  }).join('');

  return yonetimMasasi + ozet + bloklar;
}


/* ==================================================================
   DEPARTMANIN BUGÜNÜ

   Sahip: "içlerine girdiğimde bana bugün kendileri yaptıkları işleri,
   varsa araştırmaları, öğrendiklerini raporlasınlar düzgünce."

   🔴 VERİ ZATEN VARDI, ÖZETİ YOKTU. /api/panel/ekip her departman için
   bulguları zaman damgasıyla veriyor; panel hepsini alt alta döküyor ve
   "bugün ne oldu" sorusunun cevabı 40 satırın içinde kayboluyordu.

   🔴 "BUGÜN 0" SAKLANMAZ. Bir departman bugün hiçbir şey yapmadıysa
   bunu açıkça yazar. Boş bırakmak, çalışmayan birimi çalışıyor gibi
   göstermenin en sessiz yoluydu.
   ================================================================== */

function ekipBugun(d) {
  const bulgular = d.arastirma || [];
  const yerelGun = (date) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Istanbul',
    year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
  const bugun = yerelGun(new Date());
  const dun = yerelGun(new Date(Date.now() - 864e5));

  const gunluk = (g) => bulgular.filter((bulgu) => {
    const date = new Date(bulgu.zaman || '');
    return !isNaN(date.getTime()) && yerelGun(date) === g;
  });
  const bugunku = gunluk(bugun);
  const dunku = gunluk(dun);

  const uyeler = d.uyeler || [];
  const konusan = uyeler.filter((u) => u.durum === 'KONUŞTU');

  // Öğrenilen konular: bugünkü bulguların KONU alanları, tekrarsız.
  const konular = [...new Set(bugunku.map((b) => b.konu).filter(Boolean))];

  const parcalar = [];
  if (bugunku.length) {
    parcalar.push(`<b>${bugunku.length}</b> yeni dış bulgu okudu`);
  } else if (dunku.length) {
    parcalar.push(`bugün yeni bulgu yok · dün <b>${dunku.length}</b> bulgu`);
  } else {
    parcalar.push('bugün ve dün yeni dış bulgu yok');
  }
  if (uyeler.length) {
    parcalar.push(`<b>${konusan.length}/${uyeler.length}</b> üye veri okudu`);
  } else {
    parcalar.push('kadrosu kurulmamış');
  }
  if ((d.pazar_toplam || 0) > 0) {
    parcalar.push(`<b>${d.pazar_toplam}</b> elle gözlem`);
  }

  return `
    <div class="ek-bugun">
      <div class="ek-bugun-ust">
        <span class="ek-bugun-lbl">BUGÜN</span>
        <span class="ek-bugun-ozet">${parcalar.join(' · ')}</span>
      </div>
      ${konular.length ? `<div class="ek-bugun-konu">
        <span>çalıştığı konular:</span> ${konular.map((k) =>
          `<i>${escapeHtml(String(k))}</i>`).join(' ')}
      </div>` : ''}
      ${bugunku.length ? `<ul class="ek-bugun-liste">${bugunku.slice(0, 3).map((b) =>
        `<li><a href="${escapeHtml(b.url || '#')}" target="_blank" rel="noopener noreferrer">${
          escapeHtml(b.baslik || '(başlıksız)')}</a>
          <span class="ek-bugun-kaynak">${escapeHtml(b.yayinci || '')}</span></li>`).join('')}
        ${bugunku.length > 3 ? `<li class="ek-bugun-daha">…${bugunku.length - 3} bulgu daha aşağıda</li>` : ''}
      </ul>` : ''}
    </div>`;
}

function ekipSatir(d, uyeKayitlari = new Map()) {
  const r = EKIP_RENK[d.renk] || EKIP_RENK.gri;
  const uyeler = d.uyeler || [];

  const uyeListe = uyeler.length ? uyeler.map(u => {
    const kayit = uyeKayitlari.get(u.key) || {};
    const sonDurum = ({ 'ÇALIŞTI': 'Kayıt üretti', 'GÖREV BEKLİYOR': 'Görev bekliyor',
      'İZLENMİYOR': 'Son döngüde izlenmedi' })[kayit.durum] || kayit.durum || 'Kayıt yok';
    return `
    <div class="ek-uye ${u.durum === 'KONUŞTU' ? 'is-konustu' : ''}">
      <div class="ek-uye-ust">
        <span class="ek-uye-ad">${escapeHtml(u.ad || '')}</span>
        <span class="ek-uye-durum">${escapeHtml(({ 'KONUŞTU': 'Veri okudu', 'VERİ YOK': 'Veri yok' })[u.durum] || u.durum || '')}</span>
      </div>
      <div class="ek-uye-gorev">${escapeHtml(u.gorev || '')}</div>
      <div class="ek-uye-soz"><strong>Son ekip döngüsü:</strong> ${escapeHtml(sonDurum)}${kayit.zaman ? ' · ' + escapeHtml(fmtDateTime(kayit.zaman)) : ''}</div>
      ${(kayit.son_is_acik || kayit.sonuc_acik || u.soyledigi) ? `<div class="ek-uye-soz">${escapeHtml(kayit.son_is_acik || kayit.sonuc_acik || u.soyledigi)}</div>` : ''}
      ${(kayit.kanitlar || []).length ? `<div class="ek-uye-okur">Dayanak: ${escapeHtml(kayit.kanitlar.map(ekipKaynakAdi).join(' · '))}</div>` : ''}
      ${(u.eksik && u.eksik.length) ? `<div class="ek-uye-eksik">okunamayan: ${escapeHtml(u.eksik.map(ekipKaynakAdi).join(', '))}</div>` : ''}
      ${(u.okur && u.okur.length) ? `<div class="ek-uye-okur">okuduğu kaynaklar: ${escapeHtml(u.okur.map(ekipKaynakAdi).join(' · '))}</div>` : ''}
    </div>`;
  }).join('') : '<p class="ek-bos">Bu birimin kadrosu kurulmamış; sorulacak bir sorumlu yok.</p>';

  /* Dış araştırma bulguları.
     🔴 "Şirket ölçümü" ile "dışarıdan okunan iddia" ayrı çizilir. Bulgu
     kartı ayrı bir blokta ve her satırda yayıncısıyla durur; ikisini aynı
     yerde göstermek, bir blog yazısını kendi ölçümümüz sanmaya yol açar. */
  const bugunBlok = ekipBugun(d);
  const ar = d.arastirma || [];
  const arastirmaBlok = ar.length ? `
    <div class="ek-ar">
      <div class="ek-ar-head">
        <span class="ek-ar-lbl">DIŞ ARAŞTIRMA</span>
        <span class="ek-ar-say">${d.arastirma_toplam || 0} bulgu${d.arastirma_son ? ' · son ' + escapeHtml(String(d.arastirma_son).slice(0, 10)) : ''}</span>
      </div>
      ${(d.arastirma_enjeksiyon || 0) > 0 ? `<div class="ek-uyari">⚠ ${d.arastirma_enjeksiyon} bulguda yönerge benzeri metin işaretlendi — içeriğe talimat gibi davranma.</div>` : ''}
      ${ar.map(b => `
        <div class="ek-ar-item">
          <a class="ek-ar-baslik" href="${escapeHtml(b.url || '#')}" target="_blank" rel="noopener noreferrer">${escapeHtml(b.baslik || '(başlıksız)')}</a>
          <div class="ek-ar-meta">${escapeHtml(b.yayinci || '—')}${b.konu ? ' · ' + escapeHtml(b.konu) : ''}</div>
          ${b.ozet ? `<div class="ek-ar-ozet">${escapeHtml(b.ozet)}</div>` : ''}
        </div>`).join('')}
      <p class="ek-ar-not">Bunlar dışarıdan okunan iddialardır, şirket ölçümü değildir.</p>
    </div>` : '';

  /* Operatörün kendi gözlemi.
     🔴 Bu kutu bir yedek değil, ölçülmüş bir kapasite: rakip fiyatı otomatik
     alınamıyor (tüm pazaryerleri + cimri/akakçe 403 dönüyor, satıcı API'si
     yalnız kendi verimizi veriyor). Elle giriş çalışan TEK yol.
     🔴 Kaynak zorunlu ve seviye seçilir: gözlem (FACT), yorum
     (INTERPRETATION) ve tahmin (HYPOTHESIS) aynı kutuya girerse hepsi
     "veri" gibi okunur. */
  const pb = d.pazar_bulgulari || [];
  const pazarBlok = `
    <div class="ek-pz">
      <div class="ek-ar-head">
        <span class="ek-ar-lbl">ELLE GİRİLEN GÖZLEM</span>
        <span class="ek-ar-say">${d.pazar_toplam || 0} kayıt</span>
      </div>
      ${pb.map(b => `
        <div class="ek-pz-item">
          <span class="ek-pz-sev ek-sev-${escapeHtml(String(b.seviye || '').toLowerCase())}">${escapeHtml(({ FACT: 'Gözlem', INTERPRETATION: 'Yorum', HYPOTHESIS: 'Tahmin', NOT_CONNECTED: 'Kaynak bağlı değil' })[b.seviye] || b.seviye || '')}</span>
          <span class="ek-pz-metin">${escapeHtml(b.bulgu || '')}</span>
          <div class="ek-ar-meta">${escapeHtml(b.kaynak || '')}${b.tarih ? ' · ' + escapeHtml(b.tarih) : ''}</div>
        </div>`).join('')}
      <details class="ek-pz-ekle">
        <summary>+ gözlem ekle</summary>
        <div class="ek-pz-form">
          <select class="ek-pz-in" id="pzs-${escapeHtml(d.kod)}" aria-label="Seviye">
            <option value="FACT">Gördüğüm olgu</option>
            <option value="INTERPRETATION">Benim yorumum</option>
            <option value="HYPOTHESIS">Tahmin; sınanmalı</option>
            <option value="NOT_CONNECTED">Kaynak bağlı değil</option>
          </select>
          <input class="ek-pz-in" id="pzb-${escapeHtml(d.kod)}" type="text" placeholder="Ne gördün? (ör. rakip X 890 TL listeliyor)">
          <input class="ek-pz-in" id="pzk-${escapeHtml(d.kod)}" type="text" placeholder="Kaynak — zorunlu (ör. cimri.com, ekran görüntüsü)">
          <input class="ek-pz-in ek-pz-kisa" id="pzt-${escapeHtml(d.kod)}" type="text" placeholder="Tarih" value="${new Date().toLocaleDateString('tr-TR')}">
          <button type="button" class="ek-sor-btn" data-pazar-ekle="${escapeHtml(d.kod)}">KAYDET</button>
        </div>
        <div class="ek-pz-sonuc" id="pzr-${escapeHtml(d.kod)}" hidden></div>
      </details>
    </div>`;

  const soruKutusu = d.soru_sorulabilir ? `
    <div class="ek-sor">
      <label class="ek-sor-lbl" for="sor-${escapeHtml(d.kod)}">${escapeHtml(ekipBirimAdi(d))} sorumlusuna sor</label>
      <div class="ek-sor-row">
        <input id="sor-${escapeHtml(d.kod)}" class="ek-sor-in" type="text" autocomplete="off"
               placeholder="Bu neden böyle? Şöyle yapsak daha iyi olmaz mı?">
        <button type="button" class="ek-sor-btn" data-ekip-sor="${escapeHtml(d.kod)}">SOR</button>
      </div>
      <div class="ek-cevap" id="cevap-${escapeHtml(d.kod)}" hidden></div>
    </div>` : '';

  return `<details class="ek-dep ${r.sinif}" data-team-state="${escapeHtml(d.renk || 'gri')}">
    <summary class="ek-dep-head">
      <i class="ek-dot ${r.sinif}" title="${escapeHtml(r.etiket)}"></i>
      <span class="ek-ad">${escapeHtml(ekipBirimAdi(d))}</span>
      <span class="ek-rozet ek-rz-${escapeHtml(String(d.birim_durumu || '').toLowerCase())}">${escapeHtml(ekipBirimDurumu(d.birim_durumu))}</span>
      <span class="ek-say" title="Veri okuyan üye / toplam üye">${d.konusan || 0}/${d.uye_sayisi || 0} üye</span>
    </summary>
    <div class="ek-dep-govde">
      <div class="ek-misyon">${escapeHtml(d.misyon || '')}</div>
      <div class="team-department-facts">
        <div><span>Veri kaynağı</span><strong>${escapeHtml(ekipBirimKaynagi(d.veri_kaynagi))}</strong>
          ${d.veri_kaynagi ? `<details><summary>Kaynak kaydını gör</summary><small>${escapeHtml(String(d.veri_kaynagi))}</small></details>` : ''}</div>
        <div><span>Yetki sınırı</span><strong>${escapeHtml(d.otonomi_tavani ? 'Seviye ' + d.otonomi_tavani : 'Kayıt yok')}</strong></div>
        <div><span>Üst mercie taşıma</span><strong>${escapeHtml(d.escalation === 'MANAGING_DIRECTOR' ? 'Genel müdür' : d.escalation || 'Kayıt yok')}</strong></div>
        <div><span>Son dış araştırma</span><strong>${escapeHtml(d.arastirma_son ? fmtDateTime(d.arastirma_son) : 'Kayıt yok')}</strong></div>
      </div>
      ${bugunBlok}
      <h4 class="team-detail-heading">Ekip üyeleri · ${uyeler.length}</h4>
      ${uyeListe}
      ${arastirmaBlok}
      ${pazarBlok}
      ${soruKutusu}
    </div>
  </details>`;
}

/* ---- gözlem kaydet -------------------------------------------------
   🔴 Kaynak boşsa sunucu reddeder; arayüz de aynı hatayı gösterir ki
   kullanıcı 400 görmek yerine neyi eksik bıraktığını okusun.           */
document.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('[data-pazar-ekle]');
  if (!btn) return;
  const kod = btn.getAttribute('data-pazar-ekle');
  const sev = qs('pzs-' + kod), bul = qs('pzb-' + kod);
  const kay = qs('pzk-' + kod), tar = qs('pzt-' + kod), out = qs('pzr-' + kod);
  if (!sev || !bul || !kay || !out) return;

  btn.disabled = true;
  out.hidden = false;
  out.innerHTML = '<p class="ek-bekle">Kaydediliyor…</p>';

  const { ok, body } = await api('/api/pazar/bulgu', {
    method: 'POST',
    body: JSON.stringify({
      kod, seviye: sev.value, bulgu: bul.value,
      kaynak: kay.value, tarih: (tar && tar.value) || '',
    }),
  });
  btn.disabled = false;

  if (!ok || body.hata) {
    out.innerHTML = `<p class="ek-hata">${escapeHtml(String(body.hata || 'kaydedilemedi'))}</p>`;
    return;
  }
  out.innerHTML = '<p class="ek-dogru">✓ Kaydedildi. Bu gözlem artık bu birimin kanıtı.</p>';
  bul.value = '';
  kay.value = '';
});

/* ---- soru sor -----------------------------------------------------
   🔴 CEVAP HAM GÖSTERİLMEZ. Üç şey cevabın yanında ZORUNLU olarak
   çizilir: kaç kanıt parçasından üretildiği, hangi kaynaklardan, ve
   DOĞRULANMAYAN SAYILAR. Son madde kritik: cevapta geçip kanıtta
   geçmeyen bir rakam varsa kullanıcı bunu görmek zorundadır, yoksa
   uydurulmuş bir sayıyı ölçülmüş sanır.                              */
document.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('[data-ekip-sor]');
  if (!btn) return;
  const kod = btn.getAttribute('data-ekip-sor');
  const input = qs('sor-' + kod);
  const kutu = qs('cevap-' + kod);
  if (!input || !kutu) return;
  const soru = (input.value || '').trim();
  if (!soru) { input.focus(); return; }

  btn.disabled = true;
  const eskiMetin = btn.textContent;
  btn.textContent = '…';
  kutu.hidden = false;
  kutu.innerHTML = '<p class="ek-bekle">Sorumlu kanıtı okuyor…</p>';

  const { ok, status, body } = await api('/api/ekip/sor', {
    method: 'POST',
    body: JSON.stringify({ kod, soru }),
  });

  btn.disabled = false;
  btn.textContent = eskiMetin;

  if (!ok) {
    kutu.innerHTML = `<p class="ek-hata">${escapeHtml(JarvisMetin.errorText(body?.error, 'Cevap alınamadı. Biraz sonra tekrar deneyin.'))}</p>`;
    return;
  }
  if (body.hata) {
    kutu.innerHTML = `<p class="ek-hata">${escapeHtml(body.hata)}</p>`;
    return;
  }

  const sayilar = body.dogrulanmayan_sayilar || [];
  const uyari = sayilar.length
    ? `<div class="ek-uyari">⚠ Cevapta geçip kanıtta bulunmayan sayı(lar): <b>${escapeHtml(sayilar.join(', '))}</b> — bu rakamlar doğrulanmadı.</div>`
    : `<div class="ek-dogru">✓ Cevaptaki her sayı kanıtta bulundu.</div>`;

  const okunamayan = (body.okunamayan || []).length
    ? `<div class="ek-uyari">Okunamayan kaynak: ${escapeHtml((body.okunamayan || []).join(', '))}</div>` : '';

  kutu.innerHTML = `
    <div class="ek-cevap-metin">${escapeHtml(body.cevap || '')}</div>
    ${uyari}${okunamayan}
    <div class="ek-cevap-alt">
      <span>${body.kanit_sayisi || 0} kanıt parçası</span>
      <span>${escapeHtml((body.kanit_kaynaklari || []).join(' · '))}</span>
      <span>${escapeHtml(body.model || '')}${body.guven ? ' · güven ' + escapeHtml(body.guven) : ''}</span>
    </div>`;
});

function renderEkipVeCekirdek(data) {
  // Aynı veri iki yerde kullanılır: EKİP panosu ve ana ekrandaki
  // çekirdek. Çekirdeğe ayrı bir uç açmak, iki kaynağın zamanla
  // ayrışması demekti.
  cekirdekDurumUygula((data && data.departmanlar) || []);
  return renderEkip(data);
}

const SECTION_RENDERERS = { ekip: renderEkipVeCekirdek, veri: renderVeri, ajanlar: renderAjanlar,
                            raporlar: renderRaporlar, ayarlar: renderAyarlar };

async function loadSection(name) {
  const body = qs(name + 'Body');
  const count = qs(name + 'Count');
  if (!body) return;
  body.innerHTML = '<p class="sect-empty">Yükleniyor…</p>';
  // api() kullanılır, ham fetch değil: 401'i orası yakalayıp giriş ekranına
  // döndürür. Ham fetch ile yazıldığında servis yeniden başlatılıp oturumlar
  // düşünce panel "Bölüm yüklenemedi" diyordu -- kullanıcı hatanın bölümde
  // olduğunu sanıyor, oysa sadece yeniden giriş yapması gerekiyor.
  const { ok, status, body: data } = await api('/api/panel/' + name);
  if (!ok) {
    body.innerHTML = status === 401
      ? '<p class="sect-empty">Oturum düştü. Giriş ekranına yönlendiriliyorsunuz…</p>'
      : `<p class="sect-empty is-bad">${escapeHtml(JarvisMetin.errorText(data?.error, 'Bölüm şu anda yüklenemedi.'))}</p>`;
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    return;
  }
  try {
    body.innerHTML = SECTION_RENDERERS[name](data);
    if (count) {
      count.textContent = name === 'ekip'
        ? `${(data.ozet && data.ozet.departman) || 0} departman · ${(data.ozet && data.ozet.uye) || 0} üye`
        : name === 'veri'
        ? `${(data.domains || []).reduce((a, d) => a + d.ok, 0)} sorgu`
        : name === 'ajanlar' ? `${(data.engines || []).length} motor`
        : name === 'raporlar' ? `${data.finding_total || 0} kayıt` : 'salt okunur';
    }
  } catch (err) {
    body.innerHTML = `<p class="sect-empty is-bad">Bölüm çizilemedi: ${escapeHtml(String(err.message || err))}</p>`;
    if (count) count.textContent = 'hata';
  }
}

/* ==================================================================
   PLATFORM FİYAT YÖNETİMİ

   Panelin varlık sebebi tek cümle: toplu bir fiyat işlemi onaya
   gitmeden ÖNCE kaç ürünü zarara soktuğu görünsün.

   Üç kural burada kodla zorlanır:
   1. Önizleme hiçbir şey yazmaz. Yazma yalnız onay kuyruğundan geçer.
   2. Eksik veri uydurulmaz. Komisyon girilmemişse marj hesaplanmaz,
      "KOMISYON_YOK" yazılır -- boş hücre "sorun yok" demek değildir.
   3. Maliyetin sahip beyanı olduğu dipnotta durur; marj kesin sayı
      gibi sunulmaz.
   ================================================================== */

const fmState = {
  rows: [],          // sunucudan gelen ham izgara
  platform: 'wix',
  platforms: [],
  search: '',
  filter: '',
  sortKey: 'urun_adi',
  sortDir: 1,
  preview: null,     // son onizleme sonucu; onaya gonderme buna baglidir
  uyari: '',
};

const FM_DURUM_ETIKET = {
  ZARAR: 'ZARAR', KRITIK: 'KRİTİK', DUSUK: 'DÜŞÜK', OK: 'UYGUN',
  KOMISYON_YOK: 'komisyon girilmedi',
  MALIYET_YOK: 'maliyet yok',
  FIYAT_YOK: 'fiyat yok',
};

function fmNum(v, suffix) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return n.toLocaleString('tr-TR', { minimumFractionDigits: 2,
                                     maximumFractionDigits: 2 }) + (suffix || '');
}

function fmPct(v) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return (n > 0 ? '+' : '') + n.toLocaleString('tr-TR',
    { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%';
}

async function loadFiyatMatrisi() {
  const body = qs('fiyatBody');
  const count = qs('fiyatCount');
  if (!body) return;
  if (count) count.textContent = 'yükleniyor…';

  const { ok, status, body: data } = await api('/api/fiyat-matrisi');
  if (!ok) {
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    const foot = qs('fmFoot');
    if (foot) {
      foot.className = 'fm-foot is-bad';
      foot.textContent = status === 401
        ? 'Oturum düştü. Giriş ekranına yönlendiriliyorsunuz…'
        : JarvisMetin.errorText(data?.error, 'Fiyat bilgileri şu anda yüklenemedi.');
    }
    return;
  }

  fmState.rows = (data && data.rows) || [];
  fmState.uyari = (data && data.uyari) || '';
  fmState.platforms = [];
  const gorulen = new Set();
  for (const r of fmState.rows) {
    if (gorulen.has(r.platform_kod)) continue;
    gorulen.add(r.platform_kod);
    fmState.platforms.push({
      kod: r.platform_kod, ad: r.platform_adi,
      aktif: !!r.platform_aktif, yazma: !!r.yazma_izni,
    });
  }
  if (!gorulen.has(fmState.platform) && fmState.platforms.length) {
    fmState.platform = fmState.platforms[0].kod;
  }
  fmRenderPlatforms();
  fmRender();
}

function fmRenderPlatforms() {
  const box = qs('fmPlatforms');
  if (!box) return;
  box.innerHTML = fmState.platforms.map((p) => {
    const secili = p.kod === fmState.platform;
    // Yazma izni olmayan platform acikca isaretlenir: panelde fiyat
    // belirlemek ile o fiyati platforma YAZMAK ayri seylerdir.
    const rozet = p.yazma ? '' : '<span class="fm-ro" title="yazma kapalı">salt okunur</span>';
    return `<button type="button" class="fm-chip${secili ? ' is-on' : ''}"
      data-platform="${escapeHtml(p.kod)}" aria-pressed="${secili}">
      ${escapeHtml(p.ad)}${rozet}</button>`;
  }).join('');
}

function fmFiltrele() {
  const ara = fmState.search.trim().toLocaleLowerCase('tr');
  let rows = fmState.rows.filter((r) => r.platform_kod === fmState.platform);
  if (ara) {
    rows = rows.filter((r) =>
      String(r.urun_adi || '').toLocaleLowerCase('tr').includes(ara));
  }
  const f = fmState.filter;
  if (f === 'ZARAR') rows = rows.filter((r) => r.marj_uyari === 'ZARAR');
  else if (f === 'KRITIK') rows = rows.filter((r) => r.marj_uyari === 'ZARAR' || r.marj_uyari === 'KRITIK');
  else if (f === 'DEGISIK') rows = rows.filter((r) => r.platform_fiyati !== null && r.platform_fiyati !== undefined);
  else if (f === 'EKSIK') rows = rows.filter((r) =>
    ['KOMISYON_YOK', 'MALIYET_YOK', 'FIYAT_YOK'].includes(r.marj_uyari));

  const k = fmState.sortKey;
  const d = fmState.sortDir;
  rows.sort((a, b) => {
    const x = a[k], y = b[k];
    // Bos degerler HER ZAMAN sona; yon degisince basa gelip listeyi
    // okunmaz hale getirmesinler.
    const xb = x === null || x === undefined || x === '';
    const yb = y === null || y === undefined || y === '';
    if (xb && yb) return 0;
    if (xb) return 1;
    if (yb) return -1;
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * d;
    return String(x).localeCompare(String(y), 'tr') * d;
  });
  return rows;
}

function fmRender() {
  const rows = fmFiltrele();
  const tbody = qs('fmRows');
  const count = qs('fiyatCount');
  const scope = qs('fmScope');
  const foot = qs('fmFoot');

  if (count) {
    const toplam = fmState.rows.filter((r) => r.platform_kod === fmState.platform).length;
    count.textContent = rows.length === toplam
      ? `${toplam} ürün` : `${rows.length}/${toplam} ürün`;
  }
  if (scope) {
    scope.textContent = rows.length
      ? `${rows.length} ürüne uygulanacak`
      : 'eşleşen ürün yok';
  }

  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="fm-empty">Süzgece uyan ürün yok.</td></tr>';
  } else {
    tbody.innerHTML = rows.map((r) => {
      const durum = r.marj_uyari || '';
      const etiket = FM_DURUM_ETIKET[durum] || durum || '—';
      const sinif = 'fm-d-' + (durum || 'yok').toLowerCase();
      const platformHucre = (r.platform_fiyati === null || r.platform_fiyati === undefined)
        ? '<span class="fm-ref">referans</span>'
        : fmNum(r.platform_fiyati);
      const komisyon = (r.komisyon_yuzde === null || r.komisyon_yuzde === undefined)
        ? '<span class="fm-miss">girilmedi</span>'
        : fmPct(r.komisyon_yuzde).replace('+', '') +
          (r.komisyon_istisnasi ? '<span class="fm-ex" title="ürün bazlı istisna">·</span>' : '');
      return `<tr>
        <td class="fm-urun">${escapeHtml(String(r.urun_adi || '—'))}</td>
        <td class="fm-n">${fmNum(r.referans_fiyat)}</td>
        <td class="fm-n">${platformHucre}</td>
        <td class="fm-n">${fmPct(r.fark_yuzde)}</td>
        <td class="fm-n">${komisyon}</td>
        <td class="fm-n">${fmNum(r.net_kdvsiz)}</td>
        <td class="fm-n">${fmNum(r.marj)}</td>
        <td class="fm-n">${fmPct(r.marj_yuzde)}</td>
        <td><span class="fm-durum ${sinif}">${escapeHtml(etiket)}</span></td>
      </tr>`;
    }).join('');
  }

  if (foot) {
    const p = fmState.platforms.find((x) => x.kod === fmState.platform);
    const yazma = p && p.yazma
      ? 'Bu platforma yazma AÇIK.'
      : 'Bu platforma yazma KAPALI — panelde belirlenen fiyat dışarı gönderilmez.';
    foot.className = 'fm-foot';
    foot.textContent = `${yazma} ${fmState.uyari}`;
  }
}

async function fmOnizle() {
  const yontem = (qs('fmMethod') || {}).value;
  const ham = (qs('fmValue') || {}).value;
  const kutu = qs('fmPreviewBox');
  const tally = qs('fmTally');
  const gonder = qs('fmSubmit');

  const deger = Number(ham);
  if (ham === '' || !isFinite(deger)) {
    if (tally) tally.innerHTML = '<li class="fm-t-bad">Geçerli bir değer girin.</li>';
    if (kutu) kutu.hidden = false;
    return;
  }

  // Yalniz SUZULEN urunler islenir -- ekranda gordugunuz neyse o.
  const idler = fmFiltrele().map((r) => r.urun_id);
  if (!idler.length) {
    if (tally) tally.innerHTML = '<li class="fm-t-bad">Eşleşen ürün yok.</li>';
    if (kutu) kutu.hidden = false;
    return;
  }

  if (tally) tally.innerHTML = '<li>Hesaplanıyor…</li>';
  if (kutu) kutu.hidden = false;

  const { ok, status, body } = await api('/api/fiyat-toplu-onizleme', {
    method: 'POST',
    body: JSON.stringify({ platform: fmState.platform, yontem,
                           deger, urun_idler: idler }),
  });

  if (!ok) {
    fmState.preview = null;
    if (gonder) gonder.disabled = true;
    if (tally) {
      tally.innerHTML = `<li class="fm-t-bad">${escapeHtml(JarvisMetin.errorText(body?.error, 'Önizleme hazırlanamadı. Lütfen tekrar deneyin.'))}</li>`;
    }
    return;
  }

  fmState.preview = body;
  const o = body.ozet || {};
  const sira = ['ZARAR', 'KRITIK', 'DUSUK', 'OK',
                'KOMISYON_YOK', 'MALIYET_YOK', 'FIYAT_YOK'];
  const parcalar = sira.filter((k) => o[k]).map((k) => {
    const kotu = k === 'ZARAR' || k === 'KRITIK';
    const eksik = k.endsWith('_YOK');
    const sinif = kotu ? 'fm-t-bad' : (eksik ? 'fm-t-miss' : 'fm-t-ok');
    return `<li class="${sinif}"><b>${o[k]}</b> ${escapeHtml(FM_DURUM_ETIKET[k] || k)}</li>`;
  });
  if (tally) {
    tally.innerHTML = `<li class="fm-t-head"><b>${body.urun_sayisi}</b> ürün</li>` +
      parcalar.join('');
  }

  // Zarar varsa gondermeyi engellemiyoruz -- karar sahibin. Ama dugme
  // acikca uyarir; sessizce onaylatmak dogru olmaz.
  if (gonder) {
    gonder.disabled = false;
    const zarar = (o.ZARAR || 0) + (o.KRITIK || 0);
    gonder.textContent = zarar
      ? `ONAYA GÖNDER (${zarar} riskli)` : 'ONAYA GÖNDER';
    gonder.classList.toggle('is-risky', !!zarar);
  }
}

function fmSubmitSifirla() {
  const g = qs('fmSubmit');
  if (!g) return;
  g.disabled = true;
  g.textContent = 'ONAYA GÖNDER';
  g.classList.remove('is-risky');
}

function fmBind() {
  const chips = qs('fmPlatforms');
  if (chips) {
    chips.addEventListener('click', (e) => {
      const b = e.target.closest('[data-platform]');
      if (!b) return;
      fmState.platform = b.dataset.platform;
      fmState.preview = null;
      // Etiket de sifirlanir. Platform degisince onceki platformun risk
      // sayisi dugmede kalirsa, onizleme YAPILMAMIS bir platformda
      // "14 riskli" yaziyor gorunur -- yaniltici.
      fmSubmitSifirla();
      const pv = qs('fmPreviewBox'); if (pv) pv.hidden = true;
      fmRenderPlatforms();
      fmRender();
    });
  }
  const ara = qs('fmSearch');
  if (ara) ara.addEventListener('input', () => { fmState.search = ara.value; fmRender(); });
  const suz = qs('fmFilter');
  if (suz) suz.addEventListener('change', () => { fmState.filter = suz.value; fmRender(); });

  const tablo = qs('fmTable');
  if (tablo) {
    tablo.addEventListener('click', (e) => {
      const th = e.target.closest('[data-sort]');
      if (!th) return;
      const k = th.dataset.sort;
      fmState.sortDir = (fmState.sortKey === k) ? -fmState.sortDir : 1;
      fmState.sortKey = k;
      fmRender();
    });
  }

  const onizle = qs('fmPreview');
  if (onizle) onizle.addEventListener('click', fmOnizle);
  const kapat = qs('fmPreviewClose');
  if (kapat) {
    kapat.addEventListener('click', () => {
      const pv = qs('fmPreviewBox'); if (pv) pv.hidden = true;
      fmState.preview = null;
      fmSubmitSifirla();
    });
  }

  const gonder = qs('fmSubmit');
  if (gonder) {
    gonder.addEventListener('click', () => {
      fmOnayaGonder();
    });
  }
}

fmBind();

/* ==================================================================
   E-TİCARET · ÜRÜN BİLGİLERİ

   Amaç: bir ürünün DEĞİŞTİRİLEBİLİR tüm alanlarına tek yerden erişmek
   ve kolayca müdahale etmek.

   Üç kural kodla zorlanır:
   1. Değiştirilemeyen alan düzenlenebilir GÖSTERİLMEZ. `yazilabilir`
      false ise o platform hücresi salt okunur kalır -- kullanıcıya
      yapamayacağı bir şeyi teklif etmek yanlıştır.
   2. Düzenleme doğrudan uygulanmaz. "Onaya gönder" der; dış platforma
      yazma izni kapalı olduğu sürece bunu açıkça söyler.
   3. Uzun metin (açıklama, SEO) hücreye sığmaz; kısaltılır ve tam hali
      ayrı pencerede gösterilir. Sessizce kırpmak veri kaybı izlenimi verir.
   ================================================================== */

const etState = {
  rows: [],
  urunler: [],
  secili: null,      // urun_id
  search: '',
  filter: '',
  uyari: '',
};

const ET_DURUM_ETIKET = {
  AYNI: 'aynı',
  FARKLI: 'farklı',
  YALNIZ_WIX: 'yalnız Wix',
  YALNIZ_TRENDYOL: 'yalnız Trendyol',
  IKISINDE_DE_YOK: 'yok',
};

function etKisalt(s, n) {
  if (s === null || s === undefined || s === '') return null;
  const t = String(s).replace(/\s+/g, ' ').trim();
  return t.length > n ? t.slice(0, n) + '…' : t;
}

async function loadUrunAlanlari() {
  const count = qs('etCount');
  if (count) count.textContent = 'yükleniyor…';

  const { ok, status, body } = await api('/api/urun-alanlari');
  if (!ok) {
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    const foot = qs('etFoot');
    if (foot) {
      foot.className = 'fm-foot is-bad';
      foot.textContent = status === 401
        ? 'Oturum düştü. Giriş ekranına yönlendiriliyorsunuz…'
        : JarvisMetin.errorText(body?.error, 'Ürün bilgileri şu anda yüklenemedi.');
    }
    return;
  }

  etState.rows = (body && body.rows) || [];
  etState.uyari = (body && body.uyari) || '';

  const gorulen = new Map();
  for (const r of etState.rows) {
    if (!gorulen.has(r.urun_id)) {
      gorulen.set(r.urun_id, { urun_id: r.urun_id, ad: r.urun_adi, sku: r.sku });
    }
  }
  etState.urunler = [...gorulen.values()]
    .sort((a, b) => String(a.ad).localeCompare(String(b.ad), 'tr'));

  if (!etState.secili && etState.urunler.length) {
    etState.secili = etState.urunler[0].urun_id;
  }
  if (count) count.textContent = `${etState.urunler.length} ürün`;
  etRenderListe();
  etRenderDetay();
}

function etRenderListe() {
  const box = qs('etUrunler');
  if (!box) return;
  const ara = etState.search.trim().toLocaleLowerCase('tr');
  const liste = ara
    ? etState.urunler.filter((u) =>
        String(u.ad).toLocaleLowerCase('tr').includes(ara))
    : etState.urunler;

  if (!liste.length) {
    box.innerHTML = '<li class="et-bos">eşleşen ürün yok</li>';
    return;
  }
  box.innerHTML = liste.map((u) => {
    // Kac alani farkli? Listede gorunmesi, hangi urune bakmak gerektigini
    // aramadan soyler.
    const farkli = etState.rows.filter(
      (r) => r.urun_id === u.urun_id && r.durum === 'FARKLI').length;
    const secili = u.urun_id === etState.secili;
    return `<li><button type="button" class="et-urun${secili ? ' is-on' : ''}"
      data-urun="${escapeHtml(String(u.urun_id))}" aria-pressed="${secili}">
      <span class="et-urun-ad">${escapeHtml(String(u.ad || '—'))}</span>
      ${farkli ? `<span class="et-rozet">${farkli}</span>` : ''}
    </button></li>`;
  }).join('');
}

function etRenderDetay() {
  const tbody = qs('etRows');
  const adEl = qs('etAd');
  const skuEl = qs('etSku');
  const scope = qs('etScope');
  const foot = qs('etFoot');
  if (!tbody) return;

  const urun = etState.urunler.find((u) => u.urun_id === etState.secili);
  if (adEl) adEl.textContent = urun ? String(urun.ad) : 'Ürün seçin';
  if (skuEl) skuEl.textContent = urun && urun.sku ? urun.sku : '';

  let satirlar = etState.rows.filter((r) => r.urun_id === etState.secili);
  const toplam = satirlar.length;
  if (etState.filter === 'FARKLI') {
    satirlar = satirlar.filter((r) => r.durum === 'FARKLI');
  } else if (etState.filter === 'YAZILIR') {
    satirlar = satirlar.filter((r) => r.wix_yazilabilir || r.trendyol_yazilabilir);
  }
  if (scope) {
    scope.textContent = toplam
      ? `${satirlar.length}/${toplam} alan` : '';
  }

  if (!satirlar.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="fm-empty">Gösterilecek alan yok.</td></tr>';
  } else {
    tbody.innerHTML = satirlar.map((r) => {
      const d = r.durum || '';
      const hucre = (deger, yazilir) => {
        if (deger === null || deger === undefined || deger === '') {
          return '<span class="fm-miss">—</span>';
        }
        const kisa = etKisalt(deger, 46);
        const uzun = String(deger).length > 46;
        // Degistirilemeyen alan duzenlenebilir GORUNMEZ.
        const sinif = yazilir ? 'et-v et-v-acik' : 'et-v';
        return `<span class="${sinif}"${uzun ? ' data-uzun="1"' : ''}>${escapeHtml(kisa)}</span>`;
      };
      const mudahale = (r.wix_yazilabilir || r.trendyol_yazilabilir)
        ? `<button type="button" class="et-op" data-sira="${r.sira}"
             data-alan="${escapeHtml(String(r.alan))}">DÜZENLE</button>`
        : '<span class="fm-miss">değiştirilemez</span>';
      return `<tr data-sira="${r.sira}">
        <td class="et-alan">${escapeHtml(String(r.alan))}
          <span class="et-grup">${escapeHtml(String(r.grup || ''))}</span></td>
        <td>${hucre(r.wix_deger, r.wix_yazilabilir)}</td>
        <td>${hucre(r.trendyol_deger, r.trendyol_yazilabilir)}</td>
        <td><span class="fm-durum et-d-${d.toLowerCase()}">${escapeHtml(ET_DURUM_ETIKET[d] || d)}</span></td>
        <td class="et-ops">${mudahale}</td>
      </tr>`;
    }).join('');
  }

  if (foot) {
    foot.className = 'fm-foot';
    foot.textContent = etState.uyari;
  }
}

function etBind() {
  const liste = qs('etUrunler');
  if (liste) {
    liste.addEventListener('click', (e) => {
      const b = e.target.closest('[data-urun]');
      if (!b) return;
      etState.secili = b.dataset.urun;
      etRenderListe();
      etRenderDetay();
    });
  }
  const ara = qs('etSearch');
  if (ara) ara.addEventListener('input', () => { etState.search = ara.value; etRenderListe(); });
  const suz = qs('etFilter');
  if (suz) suz.addEventListener('change', () => { etState.filter = suz.value; etRenderDetay(); });

  const tablo = qs('etTable');
  if (tablo) {
    tablo.addEventListener('click', (e) => {
      const kapat = e.target.closest('[data-dk-vazgec]');
      if (kapat) { etDuzenleKapat(); return; }
      const gonder = e.target.closest('[data-dk-gonder]');
      if (gonder) { etDuzenleGonder(gonder); return; }
      const b = e.target.closest('.et-op');
      if (!b) return;
      etDuzenleAc(b);
    });
  }
}


/* ==================================================================
   DEĞİŞİKLİK ÖNERİSİ · onay kuyruğuna gönderme

   Panelde iki düğme "henüz bağlanmadı" diyordu ve DOĞRU söylüyordu:
   arkasında uç yoktu. Artık var ve zincir şu:

       panel -> /api/degisiklik -> diske şartname -> görev ->
       jarvis döngüsü öneriyi yazar -> ÖNERİLER'de sahip onaylar

   🔴 "KAYDEDİLDİ" YAZMIYORUZ ve bu bilinçli. Sözleşmede bu eylem
   tiplerinde execution_enabled=false; onay Wix'i/Trendyol'u
   DEĞİŞTİRMİYOR, değişikliğin yapılmasına karar verildiğini kaydediyor.
   Kullanıcıya "kaydedildi" demek, eski bağlanmamış hâlinden daha kötü
   bir yalan olurdu.
   ================================================================== */

async function degisiklikGonder(govde) {
  const r = await api('/api/degisiklik', {
    method: 'POST', body: JSON.stringify(govde),
  });
  return r;
}

function etSeciliUrunAdi() {
  const u = (etState.urunler || []).find(
    (x) => String(x.urun_id) === String(etState.secili));
  return u ? String(u.urun_adi || '') : '';
}

function etSatirBul(sira, alan) {
  return (etState.rows || []).find(
    (r) => String(r.sira) === String(sira) && String(r.alan) === String(alan));
}

function etDuzenleKapat() {
  const eski = document.querySelector('.et-duzenle-satir');
  if (eski) eski.remove();
}

function etDuzenleAc(dugme) {
  etDuzenleKapat();
  const tr = dugme.closest('tr');
  if (!tr) return;
  const alan = dugme.dataset.alan;
  const sira = dugme.dataset.sira;
  const satir = etSatirBul(sira, alan);
  // Mevcut deger: Wix yazilabiliyorsa Wix, degilse Trendyol. Hangisinin
  // gosterildigi ONEMLI -- onaylayan insan neyin degistigini bilmeli.
  let mevcut = '';
  let kaynak = '';
  if (satir) {
    if (satir.wix_yazilabilir && satir.wix_deger !== null && satir.wix_deger !== undefined) {
      mevcut = String(satir.wix_deger); kaynak = 'Wix';
    } else if (satir.trendyol_deger !== null && satir.trendyol_deger !== undefined) {
      mevcut = String(satir.trendyol_deger); kaynak = 'Trendyol';
    }
  }
  const yeni = document.createElement('tr');
  yeni.className = 'et-duzenle-satir';
  yeni.innerHTML = `
    <td colspan="5">
      <div class="dk-kutu" data-dk-alan="${escapeHtml(String(alan))}"
           data-dk-sira="${escapeHtml(String(sira))}">
        <div class="dk-baslik">${escapeHtml(String(alan))} — değişiklik önerisi</div>
        <label class="dk-etiket">Şu anki değer${kaynak ? ' (' + kaynak + ')' : ''}
          <input class="dk-girdi" type="text" value="${escapeHtml(mevcut)}" readonly></label>
        <label class="dk-etiket">Önerilen yeni değer
          <input class="dk-girdi" type="text" data-dk-yeni value="${escapeHtml(mevcut)}"></label>
        <label class="dk-etiket">Gerekçe — onaylayan bunu görecek
          <textarea class="dk-girdi dk-alan" data-dk-gerekce rows="2"
            placeholder="Neden değişsin? Hangi ölçüme dayanıyor?"></textarea></label>
        <div class="dk-dugmeler">
          <button type="button" class="dk-btn dk-btn-ana" data-dk-gonder>ONAYA GÖNDER</button>
          <button type="button" class="dk-btn" data-dk-vazgec>Vazgeç</button>
        </div>
        <p class="dk-not">Onay, değişikliğin yapılmasına karar verildiğini
          kaydeder. Wix/Trendyol tarafında değişikliği insan uygular.</p>
        <p class="dk-sonuc" data-dk-sonuc hidden></p>
      </div>
    </td>`;
  tr.insertAdjacentElement('afterend', yeni);
  const odak = yeni.querySelector('[data-dk-yeni]');
  if (odak) odak.focus();
}

async function etDuzenleGonder(dugme) {
  const kutu = dugme.closest('.dk-kutu');
  if (!kutu) return;
  const sonuc = kutu.querySelector('[data-dk-sonuc]');
  const alan = kutu.dataset.dkAlan;
  const satir = etSatirBul(kutu.dataset.dkSira, alan);
  const yeni = (kutu.querySelector('[data-dk-yeni]') || {}).value || '';
  const gerekce = (kutu.querySelector('[data-dk-gerekce]') || {}).value || '';
  let eski = '';
  if (satir) {
    eski = satir.wix_yazilabilir && satir.wix_deger !== null && satir.wix_deger !== undefined
      ? String(satir.wix_deger)
      : String(satir.trendyol_deger === null || satir.trendyol_deger === undefined
        ? '' : satir.trendyol_deger);
  }
  dugme.disabled = true;
  const yanit = await degisiklikGonder({
    tur: 'tek_alan', urun_id: etState.secili, urun_adi: etSeciliUrunAdi(),
    alan, eski, yeni, gerekce,
  });
  dugme.disabled = false;
  if (!sonuc) return;
  sonuc.hidden = false;
  const govde = yanit && yanit.body;
  if (!govde || !govde.ok) {
    sonuc.className = 'dk-sonuc is-bad';
    sonuc.textContent = (govde && govde.error)
      ? String(govde.error)
      : 'Öneri hazırlanamadı — hiçbir değişiklik yapılmadı.';
    return;
  }
  sonuc.className = 'dk-sonuc is-ok';
  sonuc.textContent = 'Öneri onay kuyruğuna hazırlandı (görev #' +
    String(govde.task_id || '?') + '). ÖNERİLER sekmesinde çıkacak.';
}

async function fmOnayaGonder() {
  const tally = qs('fmTally');
  const ekle = (sinif, metin) => {
    if (tally) {
      tally.insertAdjacentHTML('beforeend',
        '<li class="' + sinif + '">' + escapeHtml(metin) + '</li>');
    }
  };
  const on = fmState.preview;
  if (!on) {
    ekle('fm-t-miss', 'Önce önizleme alın; gönderilecek satır yok.');
    return;
  }
  // 🔴 Onizlemenin DEGISEN satirlari gonderilir, hepsi degil. Degismeyen
  // satiri onaya koymak, onaylayana yapilmayacak isi okutmaktir.
  const ham = on.satirlar || on.rows || [];
  const satirlar = ham.map((r) => ({
    urun: r.urun_adi || r.urun || '',
    eski: r.gecerli_fiyat !== undefined ? r.gecerli_fiyat : r.eski,
    yeni: r.yeni_fiyat !== undefined ? r.yeni_fiyat : r.yeni,
  })).filter((r) => r.eski !== undefined && r.yeni !== undefined
    && String(r.eski) !== String(r.yeni));
  if (!satirlar.length) {
    ekle('fm-t-miss', 'Önizlemede değişen satır yok; hiçbir şey gönderilmedi.');
    return;
  }
  const gerekce = (qs('fmGerekce') || {}).value
    || 'Fiyat matrisi önizlemesinden toplu değişiklik önerisi.';
  const yanit = await degisiklikGonder({
    tur: 'toplu_fiyat', satirlar, gerekce,
  });
  const govde = yanit && yanit.body;
  if (!govde || !govde.ok) {
    ekle('fm-t-bad', (govde && govde.error)
      ? String(govde.error) : 'Öneri hazırlanamadı — hiçbir şey gönderilmedi.');
    return;
  }
  ekle('fm-t-ok', satirlar.length + ' satırlık fiyat önerisi onay kuyruğuna ' +
    'hazırlandı (görev #' + String(govde.task_id || '?') + '). Onay, ' +
    'değişikliğin yapılmasına karar verildiğini kaydeder; fiyatı insan uygular.');
}

etBind();

/* ==================================================================
   REKLAM · KREATİF ANALİZİ

   Sahip 20.09.2026: "performansların ne anlama geldiği açıklama ve
   çözüm yolları da eklensin... ROAS CRM veya diğer terimler ne anlama
   geliyor ben bilmiyorum... yönetebilmek üretebilmek ve ne dediğini
   anlamak istiyorum."

   Bu yüzden her sayı üç şeyle birlikte gelir:
     DEĞER  -> ne olduğu
     ANLAM  -> bu sayı neyi ölçüyor, düşük/yüksek olması ne demek
     YAPILACAK -> bu durumda ne yapılır

   Eşik değerleri SUNUCUDAN gelir ya da burada AÇIKÇA yazılır; panel
   kendi eşiğini uydurmaz.
   ================================================================== */

const krState = { rows: [], esik: 1000 };

/* Terim sözlüğü. Tanımlar sade Türkçe; her birinde "neye yarar" var.
   Reklamcılık jargonu bilmeyen biri okuyup yönetebilmeli. */
const KR_SOZLUK = [
  ['Gösterim', 'Reklamın ekranda kaç kez göründüğü. Aynı kişi üç kez görürse üç gösterim sayılır — yani kaç KİŞİ gördüğünü söylemez.'],
  ['Erişim', 'Reklamı gören FARKLI kişi sayısı. Gösterimden her zaman küçüktür.'],
  ['Frekans', 'Gösterim ÷ Erişim. Aynı kişinin reklamı ortalama kaç kez gördüğü. Reklamcılıkta 2,5–3 üstü "yorgunluk" eşiği olarak <strong>yaygın kabul görür</strong> — ama bu bizim hesabımızda ölçülmüş bir eşik değil, genel bir kuraldır. Kendi verinizle doğrulayana kadar kesin sayı gibi kullanmayın.'],
  ['Tıklama', 'Reklama yapılan her tıklama — beğeni, yorum, "devamını gör" dahil. Tek başına yanıltıcıdır.'],
  ['Bağlantı tıklaması', 'Siteye veya profile GİDEN gerçek tıklama. Asıl bakılması gereken budur.'],
  ['Tıklama oranı', 'Tıklama ÷ gösterim. Reklamın ilgi çekme oranı. Düşükse görsel ya da ilk üç saniye tutmuyordur.'],
  ['Bin gösterim maliyeti', 'Reklamın 1000 kez gösterilmesinin maliyeti. Dar hedefleme bu tutarı yükseltebilir.'],
  ['Tıklama başına maliyet', 'Bir tıklamanın maliyeti. Harcama ÷ tıklama. Yüksekse reklam ilgi çekmiyor ya da hedef kitle pahalı olabilir.'],
  ['Reklam harcamasının getirisi', 'Reklam harcamasının kaç katı ciro döndüğü. 1 TL harcayıp 3 TL ciro elde etmek üç kat getiri demektir. <strong>Bizde şu an güvenilir hesaplanamıyor:</strong> Reklam platformunun bildirdiği satışlar ticari olarak doğrulanmadı; site ölçüm verisi gelmiyor.'],
  ['Müşteri ilişkileri', 'Müşteri konuşmaları, cevapsız mesajlar ve hangi müşterinin ne sorduğu.'],
  ['Eylem düğmesi', 'Reklamdaki çağrı düğmesi. Kullanıcıyı mağazaya, profile veya mesajlaşmaya götürür.'],
  ['Kreatif', 'Reklamın kendisi: görsel/video + başlık + metin + düğme. "Hangi kreatif tutuyor" = hangi reklam işe yarıyor.'],
  ['Ölçülebilir örnek', 'Yeterince gösterim almış reklam. Az gösterimde oranlar rastlantıdır; bu panelde 1000 gösterim altı sıralamaya sokulmaz.'],
  ['Bu paneldeki sayılar', 'Hepsi kendi Meta verimizden, toplamlardan hesaplanır. <strong>Sektör ortalaması ya da "olması gereken" eşik yazılmaz</strong> — öyle rakamlar bizim hesabımız için ölçülmedi ve karar verirken yanıltır. Kıyaslamayı kendi geçmişinizle yapın.'],
];

function krSayi(v, ondalik) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return n.toLocaleString('tr-TR', {
    minimumFractionDigits: ondalik || 0, maximumFractionDigits: ondalik || 0 });
}

async function loadKreatif() {
  const count = qs('krCount');
  if (count) count.textContent = 'yükleniyor…';
  const { ok, status, body } = await api('/api/kreatif');
  if (!ok) {
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    const foot = qs('krFoot');
    if (foot) {
      foot.className = 'fm-foot is-bad';
      foot.textContent = status === 401
        ? 'Oturum düştü. Giriş ekranına yönlendiriliyorsunuz…'
        : 'Görsel çalışmaları şu anda yüklenemedi.';
    }
    return;
  }
  krState.rows = (body && body.rows) || [];
  krState.esik = (body && body.ornek_esigi) || 1000;
  krRender();
}

/* Oranlar TOPLAMLARDAN hesaplanir. Gunluk oranlarin ortalamasi, az
   gosterimli gunu cok gosterimliyle esit sayar ve yanlis sonuc verir. */
function krOran(grup) {
  const g = grup.reduce((s, r) => s + Number(r.gosterim || 0), 0);
  const t = grup.reduce((s, r) => s + Number(r.link_tiklama || 0), 0);
  const h = grup.reduce((s, r) => s + Number(r.harcama || 0), 0);
  return { gosterim: g, tik: t, harcama: h,
           ctr: g ? (100 * t / g) : null, birim: t ? (h / t) : null };
}

function krBarListe(hedefId, gruplar, toplamCtr) {
  const el = qs(hedefId);
  if (!el) return;
  if (!gruplar.length) { el.innerHTML = '<p class="kr-bos">Ölçülebilir veri yok.</p>'; return; }
  const enYuksek = Math.max(...gruplar.map((x) => x.ctr || 0)) || 1;
  el.innerHTML = gruplar.map((x) => {
    // CSP `style-src 'self'` satir ici stile izin vermiyor. Genislik bu
    // yuzden HAZIR SINIFLA verilir (kr-w-5 ... kr-w-100, 5'er adim).
    // JS'ten stil atamak sessizce calismama riski tasirdi.
    const ham = Math.max(5, Math.round(100 * (x.ctr || 0) / enYuksek));
    const adim = Math.min(100, Math.round(ham / 5) * 5);
    const ustu = toplamCtr && x.ctr > toplamCtr;
    return `<div class="kr-bar-satir">
      <div class="kr-bar-ad">${escapeHtml(x.ad)}
        <span class="kr-bar-alt">${krSayi(x.gosterim)} gösterim · ${x.kreatif} kreatif</span></div>
      <div class="kr-bar-alan">
        <div class="kr-bar kr-w-${adim}${ustu ? ' is-ust' : ''}"></div>
      </div>
      <div class="kr-bar-deger">%${krSayi(x.ctr, 1)}
        <span class="kr-bar-alt">${x.birim ? krSayi(x.birim, 2) + ' TL/tık' : '—'}</span></div>
    </div>`;
  }).join('');
}

function krRender() {
  const rows = krState.rows;
  const olc = rows.filter((r) => r.yeterli_ornek);
  const count = qs('krCount');
  if (count) count.textContent = `${olc.length}/${rows.length} ölçülebilir`;

  const t = krOran(olc);
  const giris = qs('krGiris');
  if (giris) {
    giris.innerHTML =
      `<strong>${rows.length}</strong> reklam kreatifinden <strong>${olc.length}</strong> tanesi ` +
      `değerlendirilebilir durumda (${krState.esik} gösterimin altındakiler sıralamaya alınmaz — ` +
      `orada oranlar rastlantıdır). Toplam ${krSayi(t.gosterim)} gösterim, ` +
      `${krSayi(t.harcama, 2)} TL harcama.`;
  }

  // --- ozet kartlari: deger + anlam + yapilacak
  const yorgun = olc.filter((r) => Number(r.en_yuksek_frekans || 0) >= 2.5);
  const basliksiz = rows.filter((r) => !r.baslik);
  const kayitsiz = rows.filter((r) => r.olcum_durumu === 'PERFORMANS_KAYDI_YOK');
  const kartlar = [
    {
      deger: '%' + krSayi(t.ctr, 2), ad: 'ORTALAMA BAĞLANTI TIKLAMA ORANI',
      // Sektor kiyasi YAZILMADI: elimizde olculmus bir referans yok ve
      // uydurulmus bir esik, karar verirken en tehlikeli seydir.
      anlam: 'Reklamı gören her 100 kişiden kaçı bağlantıya tıkladı. Tek başına "iyi" ya da "kötü" denemez: tıklamaların bir kısmı profil görüntülemesi, bir kısmı mağaza ziyareti — ikisi aynı değer taşımaz.',
      yap: 'Mağazaya giden tıklamaları ayrı izleyin. Karşılaştırmayı kendi geçmişinizle yapın; sektör ortalaması diye dolaşan rakamlar bizim hesabımız için ölçülmedi.',
      sinif: 'notr',
    },
    {
      deger: krSayi(t.birim, 2) + ' TL', ad: 'TIKLAMA BAŞINA MALİYET',
      anlam: 'Bir bağlantı tıklaması ortalama bu kadara mal oluyor. Harcama ÷ bağlantı tıklaması.',
      // Donusum oranimiz BILINMIYOR (GA4 akmiyor, Meta satislari ticari
      // olarak dogrulanmadi). O yuzden "su kadara kadar mantikli" demiyoruz.
      yap: 'Bunun makul olup olmadığını söylemek için kaç tıklamadan bir satış çıktığını bilmek gerekir — o veri bizde henüz yok (site ölçümü çalışmıyor, reklam satışları doğrulanmadı). Önce dönüşüm ölçümünü kurun.',
      sinif: 'notr',
    },
    {
      deger: String(yorgun.length), ad: 'YORGUN KREATİF',
      anlam: 'Frekansı 2,5 üstüne çıkan reklam sayısı — yani aynı kişi reklamı ortalama 2,5 kereden fazla görmüş. 2,5 eşiği reklamcılıkta yaygın bir kuraldır, bizim verimizde ölçülmüş değildir.',
      yap: yorgun.length
        ? 'Bu reklamların tıklama oranı zaman içinde düşüyor mu, ona bakın. Düşüyorsa kreatifi yenileyin ya da hedef kitleyi genişletin; düşmüyorsa frekans tek başına sorun değildir.'
        : 'Şu an 2,5 üstüne çıkan kreatif yok.',
      sinif: yorgun.length ? 'uyari' : 'iyi',
    },
    {
      deger: String(basliksiz.length) + '/' + String(rows.length), ad: 'BAŞLIKSIZ KREATİF',
      anlam: 'Başlık, görselin altındaki kalın yazıdır. Yoksa reklam yalnız görsele güvenir.',
      yap: 'Aynı görseli başlıklı ve başlıksız yayınlayıp karşılaştırın — hangisinin tuttuğunu ancak ölçerek bilirsiniz.',
      sinif: basliksiz.length > rows.length / 2 ? 'uyari' : 'notr',
    },
  ];
  const kel = qs('krKartlar');
  if (kel) {
    kel.innerHTML = kartlar.map((k) => `<div class="kr-kart kr-${k.sinif}">
      <div class="kr-kart-deger">${escapeHtml(k.deger)}</div>
      <div class="kr-kart-ad">${escapeHtml(k.ad)}</div>
      <p class="kr-kart-anlam"><span class="kr-etiket">NE DEMEK</span>${escapeHtml(k.anlam)}</p>
      <p class="kr-kart-yap"><span class="kr-etiket">NE YAPMALI</span>${escapeHtml(k.yap)}</p>
    </div>`).join('');
  }

  // --- CTA ve bicim
  const grupla = (alan, varsayilan) => {
    const m = new Map();
    for (const r of olc) {
      const k = r[alan] || varsayilan;
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(r);
    }
    return [...m.entries()]
      .map(([ad, g]) => ({ ad, kreatif: g.length, ...krOran(g) }))
      .sort((a, b) => (b.ctr || 0) - (a.ctr || 0));
  };
  krBarListe('krCta', grupla('cta', '(düğme yok)'), t.ctr);
  krBarListe('krBicim', grupla('bicim', '(bilinmiyor)'), t.ctr);

  // --- en iyi kreatifler
  const tbody = qs('krRows');
  if (tbody) {
    const ilk = [...olc].sort((a, b) => Number(b.link_ctr || 0) - Number(a.link_ctr || 0)).slice(0, 10);
    tbody.innerHTML = ilk.length ? ilk.map((r) => {
      const metin = r.baslik || r.govde || '(metinsiz — yalnız görsel/video)';
      const frek = Number(r.en_yuksek_frekans || 0);
      return `<tr>
        <td class="kr-metin">${escapeHtml(String(metin).slice(0, 64))}</td>
        <td>${escapeHtml(String(r.bicim || '—'))}</td>
        <td class="mono">${escapeHtml(String(r.cta || '—'))}</td>
        <td class="fm-n">${krSayi(r.gosterim)}</td>
        <td class="fm-n">%${krSayi(r.link_ctr, 2)}</td>
        <td class="fm-n">${krSayi(r.link_basi_maliyet, 2)}</td>
        <td class="fm-n${frek >= 2.5 ? ' kr-kotu' : ''}">${krSayi(frek, 2)}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="7" class="fm-empty">Ölçülebilir kreatif yok.</td></tr>';
  }

  // --- uyarilar: her biri BULGU + NE YAPMALI
  const uy = [];
  if (yorgun.length) {
    uy.push([`${yorgun.length} kreatifte frekans 2,5 üstünde`,
      'Aynı kişi reklamı ortalama 2,5 kereden fazla görmüş. 2,5 eşiği ' +
      'reklamcılıkta yaygın bir kuraldır; bizim verimizde ölçülmedi.',
      'Önce bu kreatiflerin tıklama oranı zaman içinde düşüyor mu, ona bakın. ' +
      'Düşüyorsa kreatifi yenileyin ya da hedef kitleyi genişletin.']);
  }
  if (kayitsiz.length) {
    uy.push([`${kayitsiz.length} kreatifin performans kaydı yok`,
      'Bu reklamlar ya hiç yayınlanmadı ya da veri çekilmedi.',
      'Meta panelinde durumlarını kontrol edin; yayınlanmayan kreatif harcamaz ama yer kaplar.']);
  }
  const ctaGruplari = grupla('cta', '(düğme yok)');
  const pahali = ctaGruplari.filter((x) => x.birim && x.birim > 3);
  if (pahali.length) {
    uy.push([`${pahali.map((x) => x.ad).join(', ')} tıklaması pahalı`,
      `Tıklama başına ${pahali.map((x) => krSayi(x.birim, 2)).join(', ')} TL. Ama bu tek başına kötü değildir: mağazaya giden tıklama, profil tıklamasından daha değerlidir.`,
      'Bu düğmelerin SATIŞA dönüp dönmediğine bakın; dönüyorsa pahalı olması sorun değil.']);
  }
  const uyEl = qs('krUyarilar');
  if (uyEl) {
    uyEl.innerHTML = uy.length ? uy.map(([b, n, y]) => `<li class="kr-uyari">
      <strong>${escapeHtml(b)}</strong>
      <span class="kr-uyari-n">${escapeHtml(n)}</span>
      <span class="kr-uyari-y"><span class="kr-etiket">NE YAPMALI</span>${escapeHtml(y)}</span>
    </li>`).join('') : '<li class="kr-bos">Veriden çıkan bir uyarı yok.</li>';
  }

  // --- sozluk
  const sz = qs('krSozluk');
  if (sz) {
    sz.innerHTML = KR_SOZLUK.map(([t2, a]) =>
      `<dt>${escapeHtml(t2)}</dt><dd>${a}</dd>`).join('');
  }

  const foot = qs('krFoot');
  if (foot) {
    foot.className = 'fm-foot';
    foot.textContent = 'Oranlar toplamlardan hesaplanır (günlük oranların ' +
      'ortalaması değil). Meta\'nın bildirdiği satışlar ticari olarak ' +
      'doğrulanmadığı için reklam harcamasının getirisi burada hesaplanmıyor.';
  }
}

function krBind() {
  // Panel gorunume gecince yuklenir; ayrica baglanacak olay yok.
}

krBind();

/* ==================================================================
 * SESLİ KONUŞMA — çekirdek düğmesi
 * ==================================================================
 * İstenen akış: ortadaki L'CARLIÉ küresine bas -> dinlemeye başlar;
 * tekrar bas -> durur, söylenen metin sohbet hattından geçer ve gelen
 * cevap sesli okunur. Konuşurken tekrar basmak susturur.
 *
 * Ses TARAYICIDA çözülür ve TARAYICIDA okunur (Web Speech API). Sunucuya
 * ses dosyası gönderilmez ve YENİ UÇ NOKTA AÇILMADI: backend yalnızca
 * metin görüyor, yani mevcut yetki sınırı ve /api/chat/stream sözleşmesi
 * aynen duruyor. Duyulan cevap, ekrana basılan cevabın aynısıdır.
 *
 * 🔴 Caddy'de `Permissions-Policy: microphone=()` dururken tarayıcı bu
 * sayfada mikrofonu HİÇ açmaz -- düğme çalışıyor görünüp sessizce ölür.
 * O başlık jarvis bloğunda `microphone=(self)` yapıldı; geri alınırsa
 * sesli konuşma yeniden ölür.
 *
 * Motor yoksa (Firefox'ta SpeechRecognition yok) düğme sessiz kalmaz:
 * çekirdek "SES YOK" yazar ve sebebi sohbet kutusuna düşer. */

const SpeechCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;
const canSpeak = ('speechSynthesis' in window)
  && typeof window.SpeechSynthesisUtterance === 'function';

const voice = { rec: null, finalText: '', stopping: false, guard: null };

function voiceSetMode(mode) { state.voiceMode = mode; }

/* Konuşma motoruna verilecek metin. Görüntüyü DEĞİŞTİRMEZ, yalnızca
 * okunacak kopyayı sadeleştirir: markdown işaretleri sesli okunduğunda
 * gürültü olur, "1 200.00" ise "bir iki yüz nokta sıfır sıfır" diye
 * okunur. Sayının DEĞERİ korunur, yalnız yazımı sadeleşir. */
function speechText(raw) {
  return String(raw || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>|]/g, ' ')
    .replace(/(\d)[  ](\d{3})(?!\d)/g, '$1$2')
    .replace(/(\d)[.,]00(?!\d)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

let trVoice = null;
function turkishVoice() {
  if (trVoice) return trVoice;
  const list = (canSpeak && window.speechSynthesis.getVoices()) || [];
  trVoice = list.find((v) => String(v.lang || '').toLowerCase().indexOf('tr') === 0) || null;
  return trVoice;
}
if (canSpeak) {
  window.speechSynthesis.addEventListener('voiceschanged', () => { trVoice = null; turkishVoice(); });
}

/* Chrome uzun tek utterance'ı ~15 sn sonra yarıda kesiyor; metin cümle
 * sınırlarından parçalanıp sıraya konuyor. */
function speakOut(text, done) {
  if (!canSpeak) { done(); return; }
  const clean = speechText(text);
  if (!clean) { done(); return; }
  window.speechSynthesis.cancel();

  const sentences = clean.match(/[^.!?…]+[.!?…]*/g) || [clean];
  const chunks = [];
  let buffer = '';
  sentences.forEach((part) => {
    if ((buffer + part).length > 180 && buffer) { chunks.push(buffer.trim()); buffer = part; }
    else buffer += part;
  });
  if (buffer.trim()) chunks.push(buffer.trim());

  let index = 0;
  const next = () => {
    if (index >= chunks.length || state.voiceMode !== 'speaking') { done(); return; }
    const utter = new SpeechSynthesisUtterance(chunks[index]);
    index += 1;
    utter.lang = 'tr-TR';
    const picked = turkishVoice();
    if (picked) utter.voice = picked;
    utter.onend = next;
    utter.onerror = () => done();
    window.speechSynthesis.speak(utter);
  };
  next();
}

function voiceCoreState() {
  const btn = qs('coreBtn');
  const hint = qs('coreHint');
  const mode = state.voiceMode;
  if (btn) {
    btn.setAttribute('aria-pressed', mode === 'listening' ? 'true' : 'false');
    btn.setAttribute('aria-label',
      mode === 'idle' ? 'Sesli konuşmayı başlat' : 'Sesli konuşmayı durdur');
  }
  if (mode === 'idle') {
    if (hint) hint.textContent = SpeechCtor ? 'SESLİ KONUŞ' : 'SES YOK';
    applyLoopCoreState();
    return;
  }
  const map = {
    listening: ['listening', 'DİNLİYOR', 'BİTİRMEK İÇİN BAS'],
    thinking: ['thinking', 'DÜŞÜNÜYOR', 'CEVAP HAZIRLANIYOR'],
    speaking: ['speaking', 'KONUŞUYOR', 'SUSTURMAK İÇİN BAS'],
  }[mode];
  if (hint) hint.textContent = map[2];
  applyCoreState(map[0], map[1]);
}

function voiceFinish(note) {
  if (voice.guard) { clearTimeout(voice.guard); voice.guard = null; }
  voice.rec = null;
  voice.finalText = '';
  voice.stopping = false;
  voiceSetMode('idle');
  if (note) addChatMessage('jarvis', escapeHtml(note));
  voiceCoreState();
}

async function voiceHandleTranscript() {
  if (state.voiceMode !== 'listening') return;
  if (voice.guard) { clearTimeout(voice.guard); voice.guard = null; }
  const said = (voice.finalText || qs('chatInput').value || '').trim();
  voice.rec = null;
  voice.finalText = '';
  qs('chatInput').value = '';
  if (!said) { voiceFinish('Ses algılanmadı, bir şey söylenmedi.'); return; }

  voiceSetMode('thinking');
  voiceCoreState();
  let answer = '';
  try {
    answer = await sendMessage(said);
  } catch (err) {
    answer = '';
  }
  if (!answer || state.voiceMode !== 'thinking') { voiceFinish(); return; }

  voiceSetMode('speaking');
  voiceCoreState();
  speakOut(answer, () => voiceFinish());
}

function voiceStop() {
  voice.stopping = true;
  try { if (voice.rec) voice.rec.stop(); } catch (err) { /* zaten durmuş */ }
  // onend gelmezse takılı kalmasın.
  voice.guard = setTimeout(() => { voiceHandleTranscript(); }, 1500);
}

function voiceStart() {
  if (!SpeechCtor) {
    voiceFinish('Bu tarayıcı ses tanımayı desteklemiyor. Chrome veya Edge ile deneyin.');
    return;
  }
  const rec = new SpeechCtor();
  rec.lang = 'tr-TR';
  rec.continuous = true;
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  voice.rec = rec;
  voice.finalText = '';
  voice.stopping = false;

  rec.addEventListener('result', (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const item = event.results[i];
      if (item.isFinal) voice.finalText += item[0].transcript;
      else interim += item[0].transcript;
    }
    // Söylenen kelimeler komut kutusunda görünsün: yanlış duyulduysa
    // kullanıcı gönderilmeden önce görür.
    qs('chatInput').value = (voice.finalText + ' ' + interim).trim();
  });

  rec.addEventListener('error', (event) => {
    const reason = {
      'not-allowed': 'Mikrofon izni verilmedi. Adres çubuğundaki kilit simgesinden mikrofona izin verin.',
      'service-not-allowed': 'Mikrofon tarayıcı ayarlarınca engellendi.',
      'audio-capture': 'Mikrofon bulunamadı. Cihaz bağlı mı?',
      'network': 'Ses tanıma servisine ulaşılamadı.',
      'no-speech': 'Ses algılanmadı.',
      'aborted': '',
    }[event.error];
    voiceFinish(reason === undefined ? ('Ses hatası: ' + event.error) : (reason || null));
  });

  rec.addEventListener('end', () => {
    if (state.voiceMode !== 'listening') return;
    // Sessizlik yüzünden kendiliğinden kapandıysa dinlemeye devam et:
    // bitirme kararı kullanıcının ikinci basışına ait.
    if (!voice.stopping) {
      try { rec.start(); return; } catch (err) { /* yeniden başlayamadı */ }
    }
    voiceHandleTranscript();
  });

  try {
    rec.start();
  } catch (err) {
    voiceFinish('Ses tanıma başlatılamadı.');
    return;
  }
  voiceSetMode('listening');
  voiceCoreState();
}

function voiceBind() {
  const btn = qs('coreBtn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const mode = state.voiceMode;
    if (mode === 'listening') { voiceStop(); return; }
    if (mode === 'speaking') {
      if (canSpeak) window.speechSynthesis.cancel();
      voiceFinish();
      return;
    }
    if (mode === 'thinking') return;   // cevap bekleniyor, kesme
    voiceStart();
  });
  voiceCoreState();
}

voiceBind();

/* ==================================================================
   HAFIZA -- kisisel asistan katmaninin gorunur yuzu

   Katman 20.09.2026'da kuruldu ve calisiyordu, ama panelde hicbir
   karsiligi yoktu: operator neyin hatirlandigini goremiyordu. Bir
   hafizanin denetlenebilir olmasi, dogru hatirlamasi kadar onemli --
   goremedigi bir notu kimse duzeltemez.

   Bu ekranin uc kurali, hepsi arka uctan gelen alanlara dayanir:
   1. Dosya ve dizin AYRI gosterilir. Dosya notun aslI, dizin yalnizca
      arama katmani. Tek sayiya indirmek, dizin coktugunde paneli
      yalanci yapardI.
   2. Silme parcaya gore calisir; kac notun gittigi SUNUCUDAN gelir ve
      birden fazlaysa ayrica soylenir.
   3. Hicbir sayi burada uretilmez. Sayac uzunlugu disinda ekranda
      gorunen her deger /api/hafiza yanitindan gelir.
   ================================================================== */

const hfState = { notlar: [], yukleniyor: false };

function hfMesajGoster(metin, kotu) {
  const el = qs('hfMesaj');
  if (!el) return;
  if (!metin) { el.hidden = true; el.textContent = ''; return; }
  el.className = kotu ? 'hf-mesaj is-bad' : 'hf-mesaj is-ok';
  el.textContent = metin;
  el.hidden = false;
}

/* Dosya ve dizin, her biri kendi kaynagiyla. */
function hfDurumCiz(data) {
  const kutu = qs('hfDurum');
  if (!kutu) return;
  const dizin = data.dizin || {};
  const dosya = data.dosya || {};
  const notSayisi = (data.notlar || []).length;

  const dizinDurum = dizin.kurulu
    ? (dizin.not_sayisi === null || dizin.not_sayisi === undefined
        ? 'erişilebilir, sayı okunamadı'
        : dizin.not_sayisi + ' satır')
    : 'ERİŞİLEMİYOR';

  const kart = (baslik, deger, alt, kotu) => `
    <div class="hf-kart${kotu ? ' is-bad' : ''}">
      <span class="hf-kart-b">${escapeHtml(baslik)}</span>
      <span class="hf-kart-d">${escapeHtml(String(deger))}</span>
      <span class="hf-kart-a">${escapeHtml(alt)}</span>
    </div>`;

  let parcalar = kart('DOSYA', notSayisi + ' not',
                      'kayıt kaynağı · en fazla ' + (data.sinir || '—'), false)
    + kart('ARAMA DİZİNİ', dizinDurum,
           dizin.kurulu ? 'anlamsal arama açık' : 'not kaybolmaz, arama körelir',
           !dizin.kurulu)
    + kart('SOHBET GEÇMİŞİ', (dosya.turns || 0) + ' tur',
           'pencere içi; kalıcı not değil', false);

  kutu.innerHTML = parcalar;

  const foot = qs('hfFoot');
  if (!foot) return;
  const satirlar = [String(data.uyari || '')];
  if (dizin.hata) satirlar.push('Dizin hatası: ' + String(dizin.hata));
  // tutarli: sunucu hesaplar. null ise dizin kapali demektir, kiyas yapilmaz.
  if (data.tutarli === false) {
    satirlar.push('Dosya ile dizin aynı sayıda değil — arama eksik ' +
                  'sonuç verebilir, ama hiçbir not kaybolmuş değildir.');
  }
  foot.className = data.tutarli === false || dizin.hata ? 'fm-foot is-bad' : 'fm-foot';
  foot.textContent = satirlar.join(' ');
}

function hfListeCiz(notlar) {
  const liste = qs('hfListe');
  if (!liste) return;
  if (!notlar.length) {
    liste.innerHTML = '<p class="sect-empty">Henüz kayıtlı not yok. ' +
      'Yukarıdan ekleyebilir ya da sohbette “bunu hatırla” diyebilirsiniz.</p>';
    return;
  }
  liste.innerHTML = notlar.map((n, i) => `
    <article class="hf-not">
      <p class="hf-not-metin">${escapeHtml(n.note)}</p>
      <div class="hf-not-alt">
        <span class="hf-not-bilgi">${escapeHtml(fmtDateTime(n.at) || 'tarih yok')}
          ${n.source ? ' · ' + escapeHtml(n.source) : ''}</span>
        <button type="button" class="hf-sil" data-index="${i}">UNUT</button>
      </div>
    </article>`).join('');
}

async function loadHafiza() {
  const count = qs('hafizaCount');
  const liste = qs('hfListe');
  if (!liste) return;
  if (hfState.yukleniyor) return;
  hfState.yukleniyor = true;
  if (count) count.textContent = 'yükleniyor…';
  liste.innerHTML = '<p class="sect-empty">Yükleniyor…</p>';

  // api() kullanilir: 401'i o yakalayip giris ekranina dondurur.
  const { ok, status, body: data } = await api('/api/hafiza');
  hfState.yukleniyor = false;
  if (!ok) {
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    liste.innerHTML = status === 401
      ? '<p class="sect-empty">Oturum düştü. Giriş ekranına yönlendiriliyorsunuz…</p>'
      : `<p class="sect-empty is-bad">${escapeHtml(JarvisMetin.errorText(data?.error, 'Hafıza şu anda yüklenemedi.'))}</p>`;
    return;
  }
  hfState.notlar = data.notlar || [];
  hfDurumCiz(data);
  hfListeCiz(hfState.notlar);
  if (count) count.textContent = hfState.notlar.length + ' not';
}

function hfSayacGuncelle() {
  const input = qs('hfInput');
  const sayac = qs('hfSayac');
  if (input && sayac) sayac.textContent = input.value.length + ' / 400';
}

function hfBind() {
  const form = qs('hfForm');
  const input = qs('hfInput');
  const liste = qs('hfListe');
  if (!form || !input || !liste) return;

  input.addEventListener('input', hfSayacGuncelle);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const note = input.value.trim();
    if (!note) { hfMesajGoster('Boş not kaydedilmez.', true); return; }
    const btn = qs('hfSubmit');
    if (btn) btn.disabled = true;
    hfMesajGoster('Kaydediliyor…', false);
    const { ok, status, body } = await api('/api/hafiza', {
      method: 'POST', body: JSON.stringify({ note }),
    });
    if (btn) btn.disabled = false;
    if (!ok) {
      hfMesajGoster(JarvisMetin.errorText(body?.error, 'Not kaydedilemedi. Biraz sonra tekrar deneyin.'), true);
      return;
    }
    input.value = '';
    hfSayacGuncelle();
    hfMesajGoster('Kaydedildi. Bundan sonraki cevaplarda dikkate alınır.', false);
    hfState.notlar = body.notlar || [];
    hfDurumCiz(body);
    hfListeCiz(hfState.notlar);
    const count = qs('hafizaCount');
    if (count) count.textContent = hfState.notlar.length + ' not';
  });

  liste.addEventListener('click', async (event) => {
    const btn = event.target.closest('.hf-sil');
    if (!btn) return;
    const not = hfState.notlar[Number(btn.dataset.index)];
    if (!not) return;
    // Silme PARCAYA gore calisir: bu metin baska bir notun icinde de
    // geciyorsa o da gider. Bu yuzden iki adim. Yerel confirm() bilerek
    // kullanilmiyor -- panelin hicbir yerinde tarayici diyalogu yok ve
    // engelleyici bir modal, akisi durdurmaktan baska is gormuyor.
    if (btn.dataset.onay !== '1') {
      document.querySelectorAll('.hf-sil').forEach((b) => {
        if (b !== btn) { delete b.dataset.onay; b.textContent = 'UNUT'; }
      });
      btn.dataset.onay = '1';
      btn.textContent = 'EMİN MİSİNİZ?';
      hfMesajGoster('Silmek için tekrar basın. Bu metin başka bir notun ' +
                    'içinde de geçiyorsa o da silinir.', false);
      return;
    }
    btn.disabled = true;
    const { ok, status, body } = await api('/api/hafiza/sil', {
      method: 'POST', body: JSON.stringify({ fragment: not.note }),
    });
    if (!ok) {
      btn.disabled = false;
      hfMesajGoster(JarvisMetin.errorText(body?.error, 'Not silinemedi. Biraz sonra tekrar deneyin.'), true);
      return;
    }
    const silinen = Number(body.silinen || 0);
    hfMesajGoster(silinen > 1
      ? silinen + ' not silindi — bu metin başka notların içinde de geçiyordu.'
      : silinen === 1 ? 'Not unutuldu.' : 'Eşleşen not bulunamadı.', silinen > 1);
    hfState.notlar = body.notlar || [];
    hfDurumCiz(body);
    hfListeCiz(hfState.notlar);
    const count = qs('hafizaCount');
    if (count) count.textContent = hfState.notlar.length + ' not';
  });
}

hfBind();

/* ==================================================================
   KREATİF PARTİLERİ

   Sahip 21.09.2026: "bunları panelden görebilmek istiyorum."

   Burada gösterilen her şey DİSKTEKİ dosyalardan gelir; ayrı bir tablo
   tutulmaz. Bir partinin görseli yoksa gizlenmez -- ONAY_BEKLIYOR diye
   görünür, çünkü hangi partinin nerede takıldığı sahibin bilmesi gereken
   şeyin ta kendisi.
   ================================================================== */

const kpState = { partiler: [], acik: null };

const KP_DURUM = {
  ONAY_BEKLIYOR: 'Görsel henüz üretilmedi',
  GORSEL_VAR: 'Görsel hazır',
  GORSEL_INCELENDI: 'Görselleri aç',
};

const KP_KARAR = { GECER: 'kp-ok', DUZELT: 'kp-orta', RED: 'kp-kotu' };

async function loadKreatifParti() {
  const { body } = await api('/api/kreatif-parti');
  kpState.partiler = (body && body.partiler) || [];
  renderKreatifParti();
}

/* Konu -> muhatap eşlemesi arayüzde TEKRARLANMAZ; uç `\/muhatap` ile
 * söyler. Burada iki yerde tutulsaydı biri güncellenir öteki unutulurdu
 * ve panel yanlış departmanı gösterirdi. */
const KP_KONULAR = [
  ['LOGO', 'Logo / yerleşim yanlış'],
  ['URUN', 'Karede yanlış ürün'],
  ['METIN', 'Metin / iddia sorunu'],
  ['MARKA', 'Marka dili, ton'],
  ['DIGER', 'Başka bir sorun'],
];

/* 🔴 İNDİRME BAĞLANTISI: "download" özniteliği olmadan görseli
 * kaydetmenin tek yolu sağ tık / uzun basmaydı; mobilde çoğu kez ekran
 * görüntüsüne düşülüyordu ve o çözünürlüğü düşürür. Dosya adı da
 * parti + kare adıyla anlamlı veriliyor.
 *
 * 🔴 BU YORUM ŞABLON DİZGİSİNİN DIŞINDA DURMALI. İçine yazmıştım ve
 * içindeki ters tırnaklar dizgiyi erken kapatıp app.js'i tamamen
 * bozmuştu (SyntaxError). Şablon dizgisi içinde ters tırnak kullanılmaz.
 */
function kpKare(k, partiKlasor) {
  const sinif = KP_KARAR[k.karar] || '';
  const olcum = [];
  if (k.beyaz_sapma !== null && k.beyaz_sapma !== undefined) {
    olcum.push('beyaz sapma ' + k.beyaz_sapma);
  }
  if (k.urun_oran !== null && k.urun_oran !== undefined) {
    olcum.push('ürün %' + Math.round(k.urun_oran * 100));
  }
  const gorusler = (k.inceleme || []).map((i) =>
    `<li><b>${escapeHtml(String(i.uye || ''))}</b> ${escapeHtml(String(i.karar || ''))} — ` +
    `${escapeHtml(String(i.gerekce || ''))}</li>`).join('');
  return `<figure class="kp-kare">
    <a href="${escapeHtml(String(k.url || ''))}" target="_blank" rel="noopener" aria-label="Görseli büyüt">
      <img src="${escapeHtml(String(k.url || ''))}" alt="${escapeHtml(String(k.ust_yazi || 'Reklam görseli'))}" loading="lazy">
      <span class="kp-buyut">Görseli büyüt</span>
    </a>
    <figcaption>
      <span class="kp-rozet ${sinif}">${escapeHtml(String(k.karar || '?'))}</span>
      <span class="kp-oran">${escapeHtml(String(k.oran || ''))}</span>
      <strong>${escapeHtml(String(k.ust_yazi || ''))}</strong>
      <span class="kp-alt">${escapeHtml(String(k.alt_yazi || ''))}</span>
      ${olcum.length ? `<span class="kp-olcum">ÖLÇÜM: ${escapeHtml(olcum.join(' · '))}</span>` : ''}
      ${gorusler ? `<details><summary>ekip görüşü</summary><ul class="kp-gorus">${gorusler}</ul></details>` : ''}
      <a class="kp-link" href="${escapeHtml(String(k.etiket_url || ''))}" target="_blank" rel="noopener">ambalaj yakın planı</a>
      <div class="kp-eylem">
        <a class="kp-indir" download="${escapeHtml(String(partiKlasor || 'kreatif'))}-${escapeHtml(String(k.dosya || 'gorsel.jpg'))}"
           href="${escapeHtml(String(k.url || ''))}">TAM ÇÖZÜNÜRLÜK İNDİR</a>
        <button type="button" class="kp-itiraz-ac"
                data-kp-itiraz="${escapeHtml(String(k.dosya || ''))}"
                data-kp-parti="${escapeHtml(String(partiKlasor || ''))}">BUNDA SORUN VAR</button>
      </div>
      <div class="kp-itiraz" data-kp-form="${escapeHtml(String(k.dosya || ''))}" hidden></div>
    </figcaption>
  </figure>`;
}

/* İtiraz formu. Muhatap SEÇTİRİLMEZ: konu seçilince uca sorulur ve
 * "kime gidiyor, o departman bu görsele daha önce ne demişti" ekranda
 * yazar. Sahibe "kime soralım?" diye sormak, cevabını sistemin bilmesi
 * gereken soruyu ona yüklemek olurdu. */
function kpItirazFormu(parti, dosya) {
  const secenek = KP_KONULAR.map(([k, ad]) =>
    `<option value="${k}">${escapeHtml(ad)}</option>`).join('');
  return `<div class="kp-if" data-kp-if-parti="${escapeHtml(parti)}" data-kp-if-dosya="${escapeHtml(dosya)}">
    <label>Sorun ne?
      <select class="dk-girdi" data-kp-konu>${secenek}</select></label>
    <div class="kp-muhatap" data-kp-muhatap>muhatap sorgulanıyor…</div>
    <label>Açıklama
      <input class="dk-girdi" type="text" data-kp-aciklama
             placeholder="örn. logo eski sürüm ve sağ altta olmalı"></label>
    <div class="dk-dugmeler">
      <button type="button" class="dk-btn dk-btn-ana" data-kp-gonder>İTİRAZI GÖNDER</button>
      <button type="button" class="dk-btn" data-kp-vazgec>VAZGEÇ</button>
    </div>
    <p class="dk-sonuc" data-kp-sonuc hidden></p>
  </div>`;
}

async function kpMuhatapGoster(kok) {
  const kutu = kok.querySelector('[data-kp-muhatap]');
  const konu = kok.querySelector('[data-kp-konu]').value;
  kutu.textContent = 'muhatap sorgulanıyor…';
  const { ok, body } = await api('/api/kreatif-itiraz/muhatap', {
    method: 'POST',
    body: JSON.stringify({
      parti: kok.dataset.kpIfParti, dosya: kok.dataset.kpIfDosya, konu })
  });
  if (!ok || !body || body.error) {
    kutu.textContent = (body && body.error) || 'muhatap bulunamadı';
    return;
  }
  // 🔴 Bos cevap "undefined" olarak yazilmaz: kullanici bunu departman
  // adi sanip itirazi gondermemeli. Muhatap yoksa GONDERIM de kapanir.
  if (!body.muhatap) {
    kutu.textContent = 'Muhatap belirlenemedi — bu görselin inceleme kaydı '
      + 'okunamadı. İtiraz göndermeyin, kime gideceği belli değil.';
    const g = kok.querySelector('[data-kp-gonder]');
    if (g) g.disabled = true;
    return;
  }
  const g = kok.querySelector('[data-kp-gonder]');
  if (g) g.disabled = false;
  const onceki = body.onceki_karari;
  kutu.innerHTML = `<b>Muhatap: ${escapeHtml(String(body.muhatap))}</b>`
    + (body.ust_merci
        ? ` <span class="kp-ust">üst merci: ${escapeHtml(String(body.ust_merci))}</span>`
        : '')
    + (onceki
        ? `<span class="kp-onceki">Bu görsele daha önce
            <b>${escapeHtml(String(onceki.karar || ''))}</b> demişti:
            “${escapeHtml(String(onceki.gerekce || '').slice(0, 220))}”</span>`
        : '')
    + (body.uyari ? `<span class="kp-uyari">${escapeHtml(String(body.uyari))}</span>` : '');
}

function kpPrompt(p) {
  return `<details class="kp-prompt">
    <summary>${escapeHtml(String(p.ad || ''))} <span class="kp-oran">${escapeHtml(String(p.oran || ''))}</span></summary>
    <p class="kp-aci">${escapeHtml(String(p.hangi_aci || ''))}</p>
    <p class="kp-yazi">“${escapeHtml(String(p.ust_yazi || ''))}” · ${escapeHtml(String(p.alt_yazi || ''))}</p>
    <pre class="kp-istem">${escapeHtml(String(p.sahne_istemi || ''))}</pre>
  </details>`;
}

function renderKreatifParti() {
  const kutu = qs('kpListe');
  if (!kutu) return;
  if (!kpState.partiler.length) {
    kutu.innerHTML = '<p class="fm-empty">Henüz kreatif partisi yok. ' +
      'Haftalık koşu pazartesi 10:00\'da çalışır.</p>';
    return;
  }
  kutu.innerHTML = kpState.partiler.map((p) => {
    const acik = kpState.acik === p.parti;
    const klasor = p.parti_klasor || (p.parti + '-gorseller');
    const kareler = (p.kareler || []).map((k) => kpKare(k, klasor)).join('');
    const ilkGorsel = (p.kareler || [])[0];
    const promptlar = (p.promptlar || []).map(kpPrompt).join('');
    const red = (p.red_team || []).map((r) =>
      `<li><span class="kp-agirlik">${escapeHtml(String(r.agirlik || ''))}</span> ` +
      `<b>“${escapeHtml(String(r.alinti || ''))}”</b> ${escapeHtml(String(r.itiraz || ''))} ` +
      `<i>→ ${escapeHtml(String(r.duzeltme || ''))}</i></li>`).join('');
    const kurul = (p.kurul || []).map((k) =>
      `<li><b>${escapeHtml(String(k.uye || ''))}</b> — ${escapeHtml(String(k.soyledigi || ''))}</li>`).join('');
    return `<article class="kp-parti${acik ? ' is-acik' : ''}">
      <header class="kp-basi" data-kp-ac="${escapeHtml(p.parti)}" role="button" tabindex="0" aria-expanded="${acik}">
        ${ilkGorsel ? `<img class="kp-onizleme" src="${escapeHtml(String(ilkGorsel.url || ''))}" alt="" loading="lazy">` : ''}
        <strong>${escapeHtml(String(p.urun_adi || p.parti))}</strong>
        <span class="kp-durum">${escapeHtml(KP_DURUM[p.durum] || p.durum || '')}</span>
        ${ilkGorsel ? `<span class="kp-sayi">${p.kareler.length} görsel</span>` : ''}
        <span class="kp-tarih">${escapeHtml(String(p.uretildi || ''))}</span>
      </header>
      <div class="kp-ozet">
        <span>${escapeHtml(String(p.fiyat_cumlesi || 'fiyat konumu ölçülemedi'))}</span>
        <span>${(p.rakip_acilari || []).length} rakip açısı · ${p.kurul_sayisi} departman ·
          ${p.silinen_cumle} cümle denetimden düştü${p.tutarsiz_reklam ?
            ' · ⚠ ' + p.tutarsiz_reklam + ' eski reklamda çelişki' : ''}</span>
        <a class="kp-link" href="${escapeHtml(String(p.brief_url || ''))}" target="_blank" rel="noopener">tam brief</a>
      </div>
      ${acik ? `<div class="kp-govde">
        ${kareler ? `<h4>ÜRETİLEN GÖRSELLER</h4><div class="kp-kareler">${kareler}</div>` : ''}
        ${!kareler ? '<p>Bu çalışma için görsel henüz üretilmedi. Hazırlanan metinleri aşağıda görebilirsiniz.</p>' : ''}
        <h4>HAZIR PROMPTLAR (${(p.promptlar || []).length})</h4>${promptlar}
        ${red ? `<h4>KANIT DENETİMİ</h4><ul class="kp-red">${red}</ul>` : ''}
        ${kurul ? `<details><summary>EKİBİN GÖRÜŞÜ (${(p.kurul || []).length} departman)</summary>
          <ul class="kp-kurul">${kurul}</ul></details>` : ''}
      </div>` : ''}
    </article>`;
  }).join('');
}

function kpBind() {
  const kutu = qs('kpListe');
  if (!kutu) return;

  // İtiraz formunu aç / kapat
  kutu.addEventListener('click', (e) => {
    const ac = e.target.closest('[data-kp-itiraz]');
    if (ac) {
      e.stopPropagation();          // parti başlığının açılmasını tetiklemesin
      const dosya = ac.dataset.kpItiraz;
      const alan = kutu.querySelector(`[data-kp-form="${CSS.escape(dosya)}"]`);
      if (!alan) return;
      if (!alan.hidden) { alan.hidden = true; alan.innerHTML = ''; return; }
      alan.hidden = false;
      alan.innerHTML = kpItirazFormu(ac.dataset.kpParti, dosya);
      const form = alan.querySelector('.kp-if');
      kpMuhatapGoster(form);
      form.querySelector('[data-kp-konu]')
          .addEventListener('change', () => kpMuhatapGoster(form));
      form.querySelector('[data-kp-vazgec]').addEventListener('click', () => {
        alan.hidden = true; alan.innerHTML = '';
      });
      form.querySelector('[data-kp-gonder]')
          .addEventListener('click', () => kpItirazGonder(form));
      return;
    }
  });

  kutu.addEventListener('click', (e) => {
    if (e.target.closest('.kp-itiraz') || e.target.closest('.kp-eylem')) return;
    const b = e.target.closest('[data-kp-ac]');
    if (!b) return;
    const p = b.dataset.kpAc;
    kpState.acik = (kpState.acik === p) ? null : p;
    renderKreatifParti();
  });
  kutu.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const b = e.target.closest('[data-kp-ac]');
    if (b) { e.preventDefault(); b.click(); }
  });
}

kpBind();

/* ==================================================================
   MENÜ · gruplar, mobil çekmece, aktif grubun kendini açması

   🔴 `setView` ve `data-view` SÖZLEŞMESİNE DOKUNULMADI. Gezinme hâlâ
   `closest('.nav-item')` üzerinden çalışıyor; buradaki kod yalnız
   SARMALAYICININ açılıp kapanmasını yönetir. Böylece bir grup yanlış
   davransa bile sekmeler çalışmaya devam eder.
   ================================================================== */


/* ==================================================================
 * TASARIM — şablon kütüğü + iş defteri
 *
 * Sahip 22.09.2026: "canva ile ilgili ayrı bir sekme, ayrı müdürlük".
 * Buradaki iki liste iki ayrı soruya cevap verir:
 *   Şablon kütüğü -> "katalog istiyorum" dendiğinde YAPILABİLİR Mİ?
 *   İş defteri    -> ne üretildi, onay bekleyen var mı?
 * ================================================================== */
async function tasarimYukle() {
  const sablonKutu = qs('tasarimSablonlar');
  const isKutu = qs('tasarimIsler');
  if (!sablonKutu || !isKutu) return;
  try {
    const d = await getJSON('/api/tasarim');
    const sablonlar = d.sablonlar || [];
    if (!sablonlar.length) {
      // Boş kütük bir HATA değil, bir DURUM: hangi işin yapılamayacağını
      // söylemek, boş kutu göstermekten yararlı.
      sablonKutu.innerHTML = '<p class="fm-sub">Kütükte şablon yok. '
        + 'Şablonsuz iş türü üretilemez — bir Canva tasarımının alanları '
        + 'işaretlenip kütüklenmeli.</p>';
    } else {
      sablonKutu.innerHTML = sablonlar.map((s) => {
        const alanlar = Object.keys(s.alan_haritasi || {}).join(', ');
        return '<details class="detail-block"><summary><strong>'
          + escapeHtml(s.ad) + '</strong><span class="pill">' + escapeHtml(s.is_turu)
          + '</span></summary><div class="fm-sub oo-govde">Canva: ' + escapeHtml(s.canva_id)
          + ' · Alanlar: ' + escapeHtml(alanlar) + '<br>' + escapeHtml(s.gerekce)
          + '</div></details>';
      }).join('');
    }

    const isler = d.isler || [];
    if (!isler.length) {
      isKutu.innerHTML = '<p class="fm-sub">Henüz tasarım üretilmedi.</p>';
      return;
    }
    isKutu.innerHTML = isler.map((i) => {
      const bekliyor = i.onay_bekliyor;
      const rozet = i.durum === 'BASARISIZ'
        ? '<span class="pill pill-red">ÜRETİLMEDİ</span>'
        : (bekliyor ? '<span class="pill pill-amber">ONAY BEKLİYOR</span>'
                    : '<span class="pill">' + escapeHtml(i.onay || '-') + '</span>');
      // Mevzuat kapısı kestiyse SEBEBİ görünsün; "üretilmedi" tek başına
      // öğretmez, hangi ifadenin kesildiği öğretir.
      const d2 = i.denetim || {};
      const bulgu = (d2.bulgu || []).filter((b) => b.label === 'BLOCKED');
      const sebep = bulgu.length
        ? '<div class="fm-sub">Kesilen: ' + escapeHtml(bulgu.map((b) => b.matched).join(', ')) + '</div>'
        : '';
      const oran = d2.oran_uyarisi
        ? '<div class="fm-sub">⚠ ' + escapeHtml(d2.oran_uyarisi) + '</div>' : '';
      const bag = i.disa_aktarim
        ? '<div class="fm-sub"><a href="' + escapeHtml(i.disa_aktarim)
          + '" target="_blank" rel="noopener">çıktıyı indir</a></div>' : '';
      return '<details class="detail-block"><summary><strong>'
        + escapeHtml(i.istek || '(istek yok)') + '</strong>' + rozet
        + '</summary><div class="fm-sub oo-govde">' + escapeHtml(i.is_turu) + ' · '
        + escapeHtml(i.sablon_adi || '-') + ' · isteyen: ' + escapeHtml(i.isteyen)
        + '</div>' + sebep + oran + bag + '</details>';
    }).join('');
  } catch (err) {
    sablonKutu.textContent = 'Tasarım verisi okunamadı: ' + err;
    isKutu.textContent = '';
  }
}


/* ==================================================================
 * ASİSTAN — hatırlatıcılar (ayrı sekme) + haberler (ana sayfa)
 * Sahip: "kişisel asistanımı farklı bir bölümde, hatırlatıcılar ve
 * haberleri ana sayfada görebilmek istiyorum, buranın düzeni önemli."
 * ================================================================== */
function haberSatiri(h) {
  var kaynak = h.kaynak_url
    ? '<a href="' + escapeHtml(h.kaynak_url) + '" target="_blank" rel="noopener">'
      + escapeHtml(h.kaynak_adi || 'kaynak') + '</a>'
    : escapeHtml(h.kaynak_adi || '');
  return '<details class="detail-block"><summary><strong>'
    + escapeHtml(h.baslik || '') + '</strong><span class="pill">'
    + escapeHtml(h.aci || '') + '</span></summary>'
    + '<div class="oo-govde">'
    + '<div class="fm-sub">' + escapeHtml(h.ozet || '') + '</div>'
    + (h.neden_onemli
        ? '<div class="fm-sub">Neden önemli: ' + escapeHtml(h.neden_onemli) + '</div>'
        : '')
    + '<div class="fm-sub">' + kaynak + ' · ' + escapeHtml(h.gun || '') + '</div>'
    + '</div></details>';
}

async function anaHaberYukle() {
  var kutu = qs('anaHaber');
  if (!kutu) return;
  try {
    var d = await getJSON('/api/asistan');
    var hb = d.haberler || [];
    if (!hb.length) {
      // Boş olmak bir HATA değil: bülten o gün yeni bir şey bulmamış olabilir.
      kutu.innerHTML = '<p class="fm-sub">Bugün için yeni haber yok.</p>';
      return;
    }
    kutu.innerHTML = hb.map(haberSatiri).join('');
  } catch (err) {
    kutu.textContent = 'Haberler okunamadı: ' + err;
  }
}

/* ASİSTAN alt sekmeleri: hatırlatıcılar · gündem&haberler · onaylar&imzalar
 * 🔴 Sekme değişimi VERİYİ YENİDEN ÇEKMEZ; üçü de tek /api/asistan
 * çağrısından beslenir. Her tıklamada istek atmak hızlı gezinende
 * yarış durumu üretir. */
var AS_PANEL = { hatirlatici: 'asPanelHatirlatici',
                 gundem: 'asPanelGundem', onay: 'asPanelOnay' };

function asSekmeSec(ad) {
  Object.keys(AS_PANEL).forEach(function (k) {
    var p = qs(AS_PANEL[k]);
    if (p) p.hidden = (k !== ad);
  });
  document.querySelectorAll('.as-tab').forEach(function (b) {
    b.classList.toggle('is-active', b.dataset.as === ad);
  });
}

/* 🔴 <details> OLMALI, <div> DEGIL.
 * Bu fonksiyon '<div class="detail-block">' uretiyordu. CSS ise tamamen
 * <details> icin yazilmis: [open] durumu, ::-webkit-details-marker,
 * okun donmesi. <summary> bir div icinde ACMAZ -- kart tiklanabilir
 * gorunup tiklaninca hicbir sey yapmiyordu. */
function onaySatiri(baslik, detay, kaynak, ek) {
  return '<details class="detail-block"><summary><strong>'
    + escapeHtml(baslik) + '</strong><span class="pill">'
    + escapeHtml(kaynak) + '</span></summary><div class="fm-sub oo-govde">'
    + escapeHtml(detay) + '</div>' + (ek || '') + '</details>';
}

/* Onay kuyrugundaki bir oneri: gercek alanlariyla, govdesiyle ve
 * KARARIYLA. Alanlar _operator.list_pending() ciktisidir:
 * action_id · action_type · payload · risk_class · proposed_at · expires_at
 * (Eski kod p.title/p.summary/p.reason/p.id okuyordu; hicbiri yok.) */
function oneriOnayKarti(p) {
  var id = String(p.key);
  var baslik = oneriBaslik((p.payload || {}).reason)
    || p.action_type || ('Öneri #' + id);
  return '<details class="detail-block" data-oneri="' + escapeHtml(id) + '">'
    + '<summary><strong>' + escapeHtml(baslik) + '</strong>'
    + '<span class="pill">' + escapeHtml(p.action_type || 'ÖNERİ') + '</span></summary>'
    + '<div class="oo-govde">'
    + (disaDonukOneri(p) ? '<div class="external-approval-warning">🔴 DIŞA DÖNÜK İŞLEM · Alıcı, içerik ve etkiyi kontrol edin. Onay, tek başına gönderim kanıtı değildir.</div>' : '')
    + '<p class="oo-kunye">#' + escapeHtml(id)
    + ' · risk ' + escapeHtml(p.risk_class || '-')
    + ' · ' + escapeHtml(fmtDateTime(p.proposed_at))
    + '<br>son geçerlilik: ' + escapeHtml(fmtDateTime(p.expires_at)) + '</p>'
    + oneriGovdesi(p.payload)
    + '<label class="oo-gerekce">GEREKÇE<input type="text" class="reason-input"'
    + ' data-oo-gerekce="' + escapeHtml(id) + '"'
    + ' placeholder="isteğe bağlı — karar kaydına yazılır"></label>'
    + '<div class="oo-dugmeler">'
    + '<button type="button" class="btn-approve" data-oo-karar="APPROVED"'
    + ' data-oo-id="' + escapeHtml(id) + '" data-oo-fingerprint="'
    + escapeHtml(p.fingerprint || '') + '"'
    + (p.status === 'UNCERTAIN' ? ' disabled' : '') + '>ONAYLA</button>'
    + '<button type="button" class="btn-reject" data-oo-karar="REJECTED"'
    + ' data-oo-id="' + escapeHtml(id) + '" data-oo-fingerprint="'
    + escapeHtml(p.fingerprint || '') + '"'
    + (p.status === 'UNCERTAIN' ? ' disabled' : '') + '>REDDET</button>'
    + '</div>'
    + '<p class="oo-durum" data-oo-durum="' + escapeHtml(id) + '"></p>'
    + '</div></details>';
}

/* Karar dugmeleri. Olay delegasyonu: kartlar her yenilemede yeniden
 * uretiliyor, tek tek baglamak kaybolan dinleyiciler birakirdi.
 * CSP inline onclick'e izin vermiyor; baglama zaten burada olmali. */
document.addEventListener('click', async function (e) {
  var btn = e.target.closest('[data-oo-karar]');
  if (!btn) return;
  var id = btn.dataset.ooId;
  var karar = btn.dataset.ooKarar;
  var fingerprint = btn.dataset.ooFingerprint;

  /* 🔴 IKI ADIM. Bir is karari tek yanlis dokunusla onaylanmamali.
   * Ayni karttaki diger dugme onaylama halinden cikarilir. */
  if (btn.dataset.ooEmin !== '1') {
    var kart = btn.closest('.detail-block');
    if (kart) {
      kart.querySelectorAll('[data-oo-karar]').forEach(function (b) {
        if (b !== btn) {
          delete b.dataset.ooEmin;
          b.textContent = b.dataset.ooKarar === 'APPROVED' ? 'ONAYLA' : 'REDDET';
        }
      });
    }
    btn.dataset.ooEmin = '1';
    btn.textContent = karar === 'APPROVED' ? 'EMİN MİSİN? ONAYLA' : 'EMİN MİSİN? REDDET';
    return;
  }

  var durumEl = document.querySelector('[data-oo-durum="' + id + '"]');
  var gerekceEl = document.querySelector('[data-oo-gerekce="' + id + '"]');
  var gerekce = (gerekceEl && gerekceEl.value.trim())
    || (karar === 'APPROVED' ? 'Operatör onayı' : 'Operatör reddi');

  btn.disabled = true;
  if (durumEl) { durumEl.className = 'oo-durum'; durumEl.textContent = 'Gönderiliyor…'; }
  try {
    await postJSON('/api/actions/' + id + '/decide',
                   { decision: karar, reason: gerekce, fingerprint: fingerprint });
    if (durumEl) {
      durumEl.className = 'oo-durum oo-ok';
      durumEl.textContent = karar === 'APPROVED' ? 'Onaylandı.' : 'Reddedildi.';
    }
    /* 🔴 Listeyi yeniden cek. Karari kaydedip ekranda birakmak, sahibin
     * ayni oneriyi ikinci kez onaylamaya calismasina yol acar. */
    asistanYukle();
    if (typeof refreshProposals === 'function') refreshProposals();
    if (typeof refreshStatus === 'function') refreshStatus();
  } catch (err) {
    btn.disabled = false;
    delete btn.dataset.ooEmin;
    btn.textContent = karar === 'APPROVED' ? 'ONAYLA' : 'REDDET';
    if (durumEl) {
      durumEl.className = 'oo-durum oo-hata';
      /* Sessiz basarisizlik YOK: sebep ekranda yazar. */
      durumEl.textContent = 'Karar kaydedilemedi: ' + String(err.message || err);
    }
  }
});

async function asistanYukle() {
  var d;
  try {
    d = await getJSON('/api/asistan');
  } catch (err) {
    var k = qs('htrListe'); if (k) k.textContent = 'Okunamadı: ' + err;
    return;
  }

  /* ── 1 hatırlatıcılar */
  var kutu = qs('htrListe');
  if (kutu) {
    var hs = d.hatirlaticilar || [];
    kutu.innerHTML = hs.length ? hs.map(function (h) {
      var rozet = h.gecikti
        ? '<span class="pill pill-red">GECİKTİ</span>'
        : (h.zamani_geldi ? '<span class="pill pill-amber">ZAMANI GELDİ</span>'
                          : '<span class="pill">' + escapeHtml(h.onem) + '</span>');
      var tk = h.tekrar ? '<span class="pill">' + escapeHtml(h.tekrar) + '</span>' : '';
      return '<details class="detail-block"><summary><strong>'
        + escapeHtml(h.baslik) + '</strong>' + rozet + tk + '</summary>'
        + '<div class="oo-govde">'
        + '<div class="fm-sub">' + escapeHtml(String(h.zaman || '').slice(0, 16))
        + (h.not_ ? ' · ' + escapeHtml(h.not_) : '') + '</div>'
        + '<div class="fm-sub"><button type="button" class="btn btn-sm" '
        + 'data-htr-tamam="' + escapeHtml(String(h.id)) + '">'
        + (h.tekrar ? 'Yapıldı, ötele' : 'Tamamlandı') + '</button></div>'
        + '</div></details>';
    }).join('') : '<p class="fm-sub">Açık hatırlatıcı yok.</p>';
  }

  /* ── 2 gündem & haberler */
  var hk = qs('asHaber');
  if (hk) {
    var hb = d.haberler || [];
    hk.innerHTML = hb.length ? hb.map(haberSatiri).join('')
      : '<p class="fm-sub">Bugün için yeni haber yok.</p>';
  }
  var gk = qs('asGundem');
  if (gk) {
    var gd = d.gundem || [];
    gk.innerHTML = gd.length ? gd.map(function (g) {
      return '<details class="detail-block"><summary><strong>'
        + escapeHtml(g.soru || '') + '</strong><span class="pill">'
        + escapeHtml(g.oncelik || '') + '</span></summary>'
        + '<div class="oo-govde">'
        + '<div class="fm-sub">' + escapeHtml(g.neden_onemli || '') + '</div>'
        + '<div class="fm-sub">Hedef: ' + escapeHtml(g.hedef || '-')
        + ' · Durum: ' + escapeHtml(g.durum || '-') + '</div>'
        + '</div></details>';
    }).join('') : '<p class="fm-sub">Gündemde madde yok.</p>';
  }

  /* ── 3 onaylar & imzalar */
  var ok = qs('asOneri');
  if (ok) {
    var op = d.oneriler || [];
    ok.innerHTML = d.hatalar && d.hatalar.oneriler
      ? '<p class="fm-sub">Onaylar şu anda yüklenemedi.</p>'
      : (op.length ? op.map(oneriOnayKarti).join('')
        : '<p class="fm-sub">Bekleyen öneri yok.</p>');
  }
  var tk2 = qs('asTasarimOnay');
  if (tk2) {
    var ts = d.tasarim_onay || [];
    tk2.innerHTML = ts.length ? ts.map(function (t) {
      var bag = t.disa_aktarim
        ? '<div class="fm-sub"><a href="' + escapeHtml(t.disa_aktarim)
          + '" target="_blank" rel="noopener">çıktıyı gör</a></div>' : '';
      return onaySatiri(t.istek || ('Tasarım #' + t.is_id),
                        (t.is_turu || '') + ' · ' + (t.sablon_adi || ''),
                        'TASARIM', bag);
    }).join('') : '<p class="fm-sub">Onay bekleyen tasarım yok.</p>';
  }

  /* sekme rozetinde toplam imza sayısı */
  var sayi = (d.oneriler || []).length + (d.tasarim_onay || []).length;
  var rz = qs('asOnaySayi');
  if (rz) { rz.textContent = String(sayi); rz.hidden = (sayi === 0); }
}

document.addEventListener('click', function (e) {
  var t = e.target.closest('.as-tab');
  if (t) asSekmeSec(t.dataset.as);
});

document.addEventListener('click', async function (e) {
  var ekle = e.target.closest('#htrEkle');
  if (ekle) {
    var b = qs('htrBaslik').value.trim();
    var z = qs('htrZaman').value;
    var durum = qs('htrDurum');
    if (!b || !z) {
      durum.textContent = 'Başlık ve zaman gerekli.';
      return;
    }
    try {
      await postJSON('/api/asistan', {
        islem: 'ekle', baslik: b, zaman: z,
        not_: qs('htrNot').value.trim(),
        tekrar: qs('htrTekrar').value, onem: qs('htrOnem').value });
      qs('htrBaslik').value = ''; qs('htrNot').value = '';
      durum.textContent = 'Eklendi.';
      asistanYukle();
    } catch (err) { durum.textContent = 'Eklenemedi: ' + err; }
    return;
  }
  var tamam = e.target.closest('[data-htr-tamam]');
  if (tamam) {
    try {
      await postJSON('/api/asistan', {
        islem: 'tamamla', id: Number(tamam.dataset.htrTamam) });
      asistanYukle();
    } catch (err) { /* liste yenilenince görünür */ }
  }
});

const NAV_DURUM_ANAHTARI = 'jarvis.nav.kapali';

function navKapaliOku() {
  try {
    const saved = localStorage.getItem(NAV_DURUM_ANAHTARI);
    return new Set(saved === null ? ['is', 'kreatif', 'org'] : JSON.parse(saved));
  }
  catch (_) { return new Set(); }
}
function navKapaliYaz(kume) {
  // localStorage gizli pencerede ya da site verisi kapalıyken PATLAR;
  // menünün açılıp kapanması buna bağlı olmamalı.
  try { localStorage.setItem(NAV_DURUM_ANAHTARI, JSON.stringify([...kume])); }
  catch (_) { /* tercih kaydedilemedi, menü yine çalışır */ }
}

function navGruplariKur() {
  const nav = qs('mainNav');
  if (!nav) return;
  const kapali = navKapaliOku();

  nav.querySelectorAll('.nav-group').forEach((g) => {
    if (kapali.has(g.dataset.group)) {
      g.classList.add('is-kapali');
      const h = g.querySelector('.nav-head');
      if (h) h.setAttribute('aria-expanded', 'false');
    }
  });

  nav.addEventListener('click', (e) => {
    const bas = e.target.closest('.nav-head');
    if (!bas) return;
    const grup = bas.closest('.nav-group');
    if (!grup) return;
    const kapandi = grup.classList.toggle('is-kapali');
    bas.setAttribute('aria-expanded', kapandi ? 'false' : 'true');
    const k = navKapaliOku();
    if (kapandi) { k.add(grup.dataset.group); } else { k.delete(grup.dataset.group); }
    navKapaliYaz(k);
  });

  // Mobil çekmece
  const dugme = qs('navToggle');
  if (dugme) {
    dugme.addEventListener('click', () => {
      const acik = nav.classList.toggle('is-acik');
      dugme.setAttribute('aria-expanded', acik ? 'true' : 'false');
    });
  }
  // Sekme seçilince mobil çekmece kapanır -- açık kalırsa içeriğin
  // üstünü örtüyor ve kullanıcı her seferinde elle kapatmak zorunda.
  nav.addEventListener('click', (e) => {
    if (!e.target.closest('.nav-item')) return;
    nav.classList.remove('is-acik');
    if (dugme) dugme.setAttribute('aria-expanded', 'false');
  });
}

/* Aktif sekmenin grubu KAPALIYSA kendini açar. Aksi halde bir sekmeye
 * (ör. bildirimle) geçildiğinde hangi grupta olduğu görünmezdi. */
function navAktifGrubuAc(name) {
  const dugme = document.querySelector(`.nav-item[data-view="${name}"]`);
  const grup = dugme && dugme.closest('.nav-group');
  if (grup && grup.classList.contains('is-kapali')) {
    grup.classList.remove('is-kapali');
    const h = grup.querySelector('.nav-head');
    if (h) h.setAttribute('aria-expanded', 'true');
    const k = navKapaliOku(); k.delete(grup.dataset.group); navKapaliYaz(k);
  }
}

navGruplariKur();

/* ==================================================================
   ZEKÂ ÇEKİRDEĞİ · tıklanabilir departman düğümleri + canlı durum

   Sahip: "çevresindeki yazılar basılabilir olsun, o departmanın
   sayfalarına yönlendirsin… çalışan birimler ana ekranda çalıştıkları
   çıksın… konuşurken hareket etsin."

   Düğümlerin durumu UYDURULMAZ: /api/panel/ekip her departman için zaten
   bir renk hesaplıyor (yesil=veriden konuştu, sari=bekliyor,
   kirmizi=veri yok, gri=kadrosuz). Düğüm, kümesindeki departmanların
   renklerinden türetilir. Yeni bir "çalışıyor" tanımı icat etmek,
   panelin iki yerde iki farklı şey söylemesi demekti.
   ================================================================== */

let ekipFiltre = null;   // {ad, kodlar:Set} — çemberden seçilen küme

function cekirdekDugumleriKur() {
  const svg = qs('jarvisCore');
  if (!svg) return;

  const ac = (g) => {
    const kodlar = (g.dataset.dept || '').split(',').filter(Boolean);
    if (!kodlar.length) return;
    ekipFiltre = { ad: g.dataset.deptAd || '', kodlar: new Set(kodlar) };
    setView('ekip');
  };

  svg.addEventListener('click', (e) => {
    const g = e.target.closest('.onode');
    if (g) ac(g);
  });
  // Klavye: düğümler role="button" tabindex="0"; fare olmadan da açılmalı.
  svg.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const g = e.target.closest('.onode');
    if (!g) return;
    e.preventDefault();
    ac(g);
  });
}

/* Departman renklerini düğümlere taşır.
   Bir düğüm, kümesinde EN AZ BİR yeşil departman varsa "çalışıyor". */
function cekirdekDurumUygula(deps) {
  const svg = qs('jarvisCore');
  if (!svg || !Array.isArray(deps)) return;
  const renkler = {};
  deps.forEach((d) => { if (d && d.kod) renkler[d.kod] = d.renk; });

  svg.querySelectorAll('.onode').forEach((g) => {
    const kodlar = (g.dataset.dept || '').split(',').filter(Boolean);
    let calisan = 0, kadrolu = 0;
    kodlar.forEach((k) => {
      const r = renkler[k];
      if (r && r !== 'gri') kadrolu += 1;
      if (r === 'yesil') calisan += 1;
    });
    g.classList.toggle('is-calisiyor', calisan > 0);
    g.classList.toggle('is-bos', kadrolu === 0);
    const ad = g.dataset.deptAd || '';
    g.setAttribute('aria-label', calisan
      ? `${ad}: ${calisan} birim çalışıyor — aç`
      : (kadrolu ? `${ad}: bekliyor — aç` : `${ad}: kadrosuz — aç`));
    // Çalışan düğüm sayısı kadar gecikme: hepsi aynı anda yanıp sönmesin.
    g.style.setProperty('--gecikme', `${(kodlar.length % 5) * 0.4}s`);
  });
}

/* Konuşma/dinleme hareketi. `core-state-*` sınıfı zaten vardı; buraya
 * eklenen şey, durumun DIŞARIDAN tek bir yerden sürülmesi. */
function cekirdekDurumu(durum) {
  const svg = qs('jarvisCore');
  if (!svg) return;
  ['idle', 'dinliyor', 'dusunuyor', 'konusuyor'].forEach(
    (d) => svg.classList.remove('core-state-' + d));
  svg.classList.add('core-state-' + (durum || 'idle'));
  const et = qs('coreStateLabel');
  if (et) {
    et.textContent = { dinliyor: 'DİNLİYOR', dusunuyor: 'DÜŞÜNÜYOR',
                       konusuyor: 'KONUŞUYOR' }[durum] || 'HAZIR';
  }
}

cekirdekDugumleriKur();


/* Süzgeci kaldırma düğmesi. Delege dinleyici: EKİP panosu her yenilemede
 * yeniden çizildiği için düğmeye doğrudan bağlanmak bir yenilemede kopardı. */
document.addEventListener('click', (e) => {
  if (!e.target.closest('#ekFiltreKaldir')) return;
  ekipFiltre = null;
  loadSection('ekip');
});

/* ==================================================================
   SOHBET CEVABI · 7 satır + "devamını gör"

   🔴 BU TASARIMI BEN SEÇMEDİM, EKİP SEÇTİ.
   Sahip "bu görsel düzeltmeyi kreatif ekibe görev olarak ver, red team
   çürütsün, müdür karar versin" dedi. Zincir koştu:
     Sanat Yönetmeni    -> 6 satır
     Kreatif Direktör   -> 7 satır + "devamını gör"
     Marka Stratejisti  -> dinamik sınırlama
     Red team           -> 3 itiraz (hepsi YÜKSEK)
     Direktör kararı    -> Kreatif Direktör'ün önerisi, red team'in
                           "yükseklik ekrana göre değişsin" itirazı
                           KABUL EDİLEREK
   Karar dosyası: state/tasarim/sohbet-cevap-kutusu-20260921-1609.json

   Uygulanan maddeler (kararda yazdığı gibi):
     · .chat-msg en fazla 7 satır
     · 7. satırın altı "devamını gör" ile açılır
     · düğme 0.85rem, 24px yükseklik, 10px padding
     · max-width 78ch korunur
     · düğme YALNIZ taşma varsa görünür
   ================================================================== */

const SOHBET_SATIR_SINIRI = 7;

function devaminiGor(mesaj) {
  // Taşma var mı? scrollHeight, clamp'lenmiş clientHeight'ı aşıyorsa var.
  // 🔴 Ölçüm render'dan SONRA yapılmalı; yoksa her mesaja düğme konur ve
  // kısa cevapta "devamını gör" boş yere görünür (red team'in itirazı).
  if (!mesaj || mesaj.dataset.devamKuruldu) return;
  mesaj.classList.add('is-kisali');
  const tasma = mesaj.scrollHeight - mesaj.clientHeight > 4;
  if (!tasma) {
    mesaj.classList.remove('is-kisali');
    mesaj.dataset.devamKuruldu = '1';
    return;
  }
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'chat-devam';
  btn.textContent = 'DEVAMINI GÖR';
  btn.addEventListener('click', () => {
    const acik = mesaj.classList.toggle('is-acik');
    mesaj.classList.toggle('is-kisali', !acik);
    btn.textContent = acik ? 'DARALT' : 'DEVAMINI GÖR';
  });
  mesaj.appendChild(btn);
  mesaj.dataset.devamKuruldu = '1';
}

/* ==================================================================
   SATIŞLAR · tüm gönderiler, elle açıklama, dağıtım, stok

   🔴 BAĞLI OLMAYAN KANAL GİZLENMEZ. `mart.siparis` içindeki 37 siparişin
   hepsi Wix (kanal=WEB); Trendyol siparişleri sisteme HİÇ alınmıyor
   (`raw.trendyol_order` tablosu yok). Panel "tüm platformlar" diye
   göstermez, eksiği YAZAR -- eksik ciroyu tam göstermek, sahibin yanlış
   karar vermesine yol açar.
   ================================================================== */

const SATIS_TUR_ETIKET = {
  SATIS: 'satış', UGC: 'UGC içerik', INFLUENCER: 'influencer',
  NUMUNE: 'numune', HEDIYE: 'hediye', IADE: 'iade',
  DEGISIM: 'değişim', BILINMIYOR: 'bilinmiyor',
};

let satisVeri = null;

async function loadSatislar() {
  const { body } = await api('/api/satislar');
  satisVeri = body || {};
  renderSatislar();
}

function satisPara(x) {
  if (x === null || x === undefined || x === '') return '—';
  const n = Number(x);
  return Number.isFinite(n) ? n.toLocaleString('tr-TR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' TL' : String(x);
}

function satisNotFormu(sip) {
  const ref = sip ? sip.entity_id : '';
  const urun = sip && sip.urunler ? String(sip.urunler).split(' x')[0] : '';
  const turler = (satisVeri.turler || []).map((t) =>
    `<option value="${escapeHtml(t)}">${escapeHtml(SATIS_TUR_ETIKET[t] || t)}</option>`).join('');
  return `<div class="sn-form" data-sn-ref="${escapeHtml(String(ref))}">
    <div class="sn-satir">
      <label>Bu gönderi neydi?
        <select class="dk-girdi" data-sn-tur>${turler}</select></label>
      <label>Kime gitti
        <input class="dk-girdi" type="text" data-sn-alici placeholder="ad / hesap"></label>
    </div>
    <div class="sn-satir">
      <label>Ürün
        <input class="dk-girdi" type="text" data-sn-urun value="${escapeHtml(urun)}"></label>
      <label>Adet
        <input class="dk-girdi" type="number" min="0" step="1" data-sn-adet value="1"></label>
      <label>Değeri (fiyatsızsa siz yazın)
        <input class="dk-girdi" type="number" min="0" step="0.01" data-sn-fiyat></label>
    </div>
    <label>Not
      <input class="dk-girdi" type="text" data-sn-not placeholder="neden bedelsiz gitti, hangi iş için"></label>
    <div class="dk-dugmeler">
      <button type="button" class="dk-btn dk-btn-ana" data-sn-kaydet>KAYDET</button>
    </div>
    <p class="dk-sonuc" data-sn-sonuc hidden></p>
  </div>`;
}

function renderSatislar() {
  const kutu = qs('satisGovde');
  if (!kutu || !satisVeri) return;
  const sip = satisVeri.siparisler || [];
  const bekleyen = satisVeri.aciklama_bekleyen || [];
  const dagitim = satisVeri.dagitim || [];
  const stok = satisVeri.stok || [];
  const notlar = satisVeri.notlar || [];

  const dogrulanan = sip.filter((s) => s.ciro_sinifi === 'DOGRULANMIS').length;
  const toplamCiro = sip.reduce((t, s) =>
    t + (Number(s.ciro_dogrulanmis_net) || 0), 0);

  const ozet = `
    <div class="ek-ozet">
      <div class="ek-tile"><span class="ek-n">${sip.length}</span><span class="ek-k">gönderi</span></div>
      <div class="ek-tile"><span class="ek-n">${dogrulanan}</span><span class="ek-k">doğrulanmış satış</span></div>
      <div class="ek-tile ${bekleyen.length ? 'ek-tile-uyari' : ''}">
        <span class="ek-n">${bekleyen.length}</span><span class="ek-k">açıklama bekliyor</span></div>
      <div class="ek-tile"><span class="ek-n">${satisPara(toplamCiro)}</span><span class="ek-k">doğrulanmış ciro</span></div>
    </div>
    <p class="o-uyari">${escapeHtml(satisVeri.kanal_notu || '')}</p>`;

  const bekleyenBlok = bekleyen.length ? `
    <h3 class="rp-sub">AÇIKLAMA BEKLEYEN GÖNDERİLER
      <span class="rp-src">fiyatı yok, iptal ya da yalnız beyan edilmiş — ne olduğunu siz yazın</span></h3>
    <div class="sn-liste">
      ${bekleyen.map((s) => `
        <details class="sn-kart">
          <summary>
            <span class="sn-gun">${escapeHtml(String(s.gun || ''))}</span>
            <span class="sn-no">#${escapeHtml(String(s.siparis_no || ''))}</span>
            <span class="sn-urun">${escapeHtml(String(s.urunler || '—'))}</span>
            <span class="sn-durum">${escapeHtml(String(s.ciro_sinifi || ''))} · ${escapeHtml(String(s.odeme_durumu || ''))}</span>
          </summary>
          ${satisNotFormu(s)}
        </details>`).join('')}
    </div>` : '<p class="sect-note">Açıklama bekleyen gönderi yok.</p>';

  const dagitimBlok = `
    <h3 class="rp-sub">ÜRÜN DAĞITIMI
      <span class="rp-src">satılan ve bedelsiz giden AYRI sayılır</span></h3>
    <div class="tablo-kab"><table>
      <thead><tr><th>Ürün</th><th>Satılan</th><th>Bedelsiz</th><th>Toplam çıkan</th></tr></thead>
      <tbody>${dagitim.map((d) => `<tr>
        <td>${escapeHtml(String(d.urun_adi || ''))}</td>
        <td>${Number(d.satilan_adet || 0)}</td>
        <td>${Number(d.bedelsiz_adet || 0)}</td>
        <td><b>${Number(d.toplam_cikan || 0)}</b></td></tr>`).join('')}</tbody>
    </table></div>`;

  const stokBlok = `
    <h3 class="rp-sub">STOK
      <span class="rp-src">elle sayım — platformun kendi stok sayısından ayrıdır</span></h3>
    <div class="tablo-kab"><table>
      <thead><tr><th>Ürün</th><th>Adet</th><th>Nerede</th><th>Sayım</th><th>Giren</th></tr></thead>
      <tbody>${stok.length ? stok.map((s) => `<tr>
        <td>${escapeHtml(String(s.urun_adi || ''))}</td>
        <td><b>${Number(s.adet || 0)}</b></td>
        <td>${escapeHtml(String(s.nerede || ''))}</td>
        <td>${escapeHtml(String(s.sayim_zamani || '').slice(0, 10))}
          ${Number(s.gun_gecti) > 14 ? '<span class="sn-eski">· ' + s.gun_gecti + ' gün önce</span>' : ''}</td>
        <td>${escapeHtml(String(s.giren || ''))}</td></tr>`).join('')
        : '<tr><td colspan="5" class="fm-empty">Henüz sayım girilmemiş.</td></tr>'}</tbody>
    </table></div>
    <div class="sn-form" id="stokForm">
      <div class="sn-satir">
        <label>Ürün<input class="dk-girdi" type="text" id="stokUrun"
          list="stokUrunListe" placeholder="ürün adı"></label>
        <label>Sayılan adet<input class="dk-girdi" type="number" min="0" step="1" id="stokAdet"></label>
        <label>Nerede<input class="dk-girdi" type="text" id="stokNerede" value="DEPO"></label>
      </div>
      <label>Not<input class="dk-girdi" type="text" id="stokNot" placeholder="isteğe bağlı"></label>
      <div class="dk-dugmeler">
        <button type="button" class="dk-btn dk-btn-ana" id="stokKaydet">SAYIMI KAYDET</button>
      </div>
      <p class="dk-sonuc" id="stokSonuc" hidden></p>
      <datalist id="stokUrunListe">${dagitim.map((d) =>
        `<option value="${escapeHtml(String(d.urun_adi || ''))}"></option>`).join('')}</datalist>
    </div>`;

  const notBlok = notlar.length ? `
    <h3 class="rp-sub">ELLE GİRİLEN AÇIKLAMALAR<span class="rp-src">${notlar.length} kayıt</span></h3>
    <div class="tablo-kab"><table>
      <thead><tr><th>Tarih</th><th>Tür</th><th>Ürün</th><th>Adet</th><th>Değer</th><th>Kime</th><th>Not</th></tr></thead>
      <tbody>${notlar.map((n) => `<tr>
        <td>${escapeHtml(String(n.girildi || '').slice(0, 10))}</td>
        <td><span class="sn-tur">${escapeHtml(SATIS_TUR_ETIKET[n.tur] || n.tur || '')}</span></td>
        <td>${escapeHtml(String(n.urun_adi || ''))}</td>
        <td>${n.adet === null ? '—' : Number(n.adet)}</td>
        <td>${satisPara(n.elle_fiyat)}</td>
        <td>${escapeHtml(String(n.alici || '—'))}</td>
        <td>${escapeHtml(String(n.not_metni || ''))}</td></tr>`).join('')}</tbody>
    </table></div>` : '';

  const tumBlok = `
    <h3 class="rp-sub">TÜM GÖNDERİLER<span class="rp-src">${sip.length} kayıt</span></h3>
    <div class="tablo-kab"><table>
      <thead><tr><th>Tarih</th><th>No</th><th>Kanal</th><th>Ürünler</th>
        <th>Tutar</th><th>Ödeme</th><th>Ciro sınıfı</th><th>Not</th></tr></thead>
      <tbody>${sip.map((s) => `<tr class="${s.ciro_sinifi === 'IPTAL' ? 'sn-iptal' : ''}">
        <td>${escapeHtml(String(s.gun || ''))}</td>
        <td>#${escapeHtml(String(s.siparis_no || ''))}</td>
        <td>${escapeHtml(String(s.kanal || ''))}</td>
        <td>${escapeHtml(String(s.urunler || '—'))}</td>
        <td>${satisPara(s.toplam)}</td>
        <td>${escapeHtml(String(s.odeme_durumu || ''))}</td>
        <td>${escapeHtml(String(s.ciro_sinifi || ''))}</td>
        <td>${Number(s.not_sayisi) > 0 ? '✔' : ''}</td></tr>`).join('')}</tbody>
    </table></div>`;

  kutu.innerHTML = ozet + bekleyenBlok + dagitimBlok + stokBlok + notBlok + tumBlok;
}

/* Delege dinleyiciler: panel her yenilemede yeniden çizildiği için
 * düğmeye doğrudan bağlanmak bir yenilemede kopardı. */
document.addEventListener('click', async (e) => {
  const kaydet = e.target.closest('[data-sn-kaydet]');
  if (kaydet) {
    const form = kaydet.closest('.sn-form');
    const al = (sec) => { const el = form.querySelector(sec); return el ? el.value : ''; };
    const sonuc = form.querySelector('[data-sn-sonuc]');
    kaydet.disabled = true;
    const { body } = await api('/api/satis/not', {
      method: 'POST',
      body: JSON.stringify({
        siparis_ref: form.dataset.snRef || '',
        tur: al('[data-sn-tur]'), alici: al('[data-sn-alici]'),
        urun_adi: al('[data-sn-urun]'), adet: al('[data-sn-adet]'),
        elle_fiyat: al('[data-sn-fiyat]'), not_metni: al('[data-sn-not]'),
      }),
    });
    kaydet.disabled = false;
    if (sonuc) {
      sonuc.hidden = false;
      sonuc.className = 'dk-sonuc ' + (body && body.ok ? 'is-ok' : 'is-bad');
      sonuc.textContent = body && body.ok
        ? 'Kaydedildi. Bu gönderi artık açıklanmış sayılıyor.'
        : ((body && body.hata) || 'Kaydedilemedi.');
    }
    if (body && body.ok) setTimeout(loadSatislar, 700);
    return;
  }

  if (e.target.closest('#stokKaydet')) {
    const btn = e.target.closest('#stokKaydet');
    const sonuc = qs('stokSonuc');
    btn.disabled = true;
    const { body } = await api('/api/stok', {
      method: 'POST',
      body: JSON.stringify({
        urun_adi: (qs('stokUrun') || {}).value || '',
        adet: (qs('stokAdet') || {}).value || '',
        nerede: (qs('stokNerede') || {}).value || 'DEPO',
        not_metni: (qs('stokNot') || {}).value || '',
      }),
    });
    btn.disabled = false;
    if (sonuc) {
      sonuc.hidden = false;
      sonuc.className = 'dk-sonuc ' + (body && body.ok ? 'is-ok' : 'is-bad');
      sonuc.textContent = body && body.ok
        ? `Sayım kaydedildi: ${body.urun_adi} = ${body.adet}`
        : ((body && body.hata) || 'Kaydedilemedi.');
    }
    if (body && body.ok) setTimeout(loadSatislar, 700);
  }
});

/* ============================ KARGO ============================
 * Sahip 21.09.2026: *"taşıyıcıyı seçebilmek, karşı ödemeli mi biz mi
 * ödemeli gibi bilgileri seçebilme gibi panel istiyorum. burası bizim
 * merkez üssümüz."*
 *
 * Dört iş var ve YALNIZ BİRİ PARA HARCAR:
 *   taslak aç  · ücretsiz
 *   fiyat sor  · ücretsiz
 *   BARKOD AL  · 🔴 şirket bakiyesinden düşer, geri alınamaz
 *   etiket üret· ücretsiz
 *
 * 🔴 BARKOD DÜĞMESİ TEK TIKLA ÇALIŞMAZ. Önce taşıyıcı seçilir, sonra
 * ekranda tutarı yazan bir onay şeridi çıkar, para ancak o şeritteki
 * ONAYLA'ya basılınca harcanır. Sebebi biçimsel değil: yanlışlıkla
 * tıklanan bir düğme burada gerçek para demek.
 */

let kargoVeri = null;
let kargoSecili = new Set();

async function loadKargo() {
  const kutu = qs('kargoGovde');
  if (kutu && !kargoVeri) kutu.innerHTML = '<p class="fm-empty">Yükleniyor…</p>';
  const { body } = await api('/api/kargo');
  kargoVeri = body || {};
  renderKargo();
}

function kargoPara(x) {
  if (x === null || x === undefined || x === '') return '—';
  const n = Number(x);
  return Number.isFinite(n)
    ? n.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' TL'
    : String(x);
}

function kargoTarih(x) {
  if (!x) return '—';
  const d = new Date(x);
  return Number.isNaN(d.getTime()) ? String(x).slice(0, 10)
    : d.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

/* Sipariş → kargo → teslimat zinciri. Üç zaman damgasından hangileri
 * dolu ise o kadar halka yanar; uç `lastState`i zaten Türkçe veriyor. */
function kargoZincir(g) {
  const adim = [
    ['açıldı', g.olusturuldu],
    ['kargoda', g.kargoya_verildi],
    ['teslim', g.teslim_edildi],
  ];
  return `<div class="kg-zincir">${adim.map(([ad, zaman]) => `
    <span class="kg-halka ${zaman ? 'kg-halka-dolu' : ''}" title="${escapeHtml(ad)}">
      <b>${escapeHtml(ad)}</b><i>${zaman ? kargoTarih(zaman) : '—'}</i></span>`).join('')}</div>`;
}

function kargoSatir(g) {
  const id = escapeHtml(String(g.siparis_id || ''));
  const secili = kargoSecili.has(g.siparis_id) ? 'checked' : '';
  const kapida = g.karsi_odemeli
    ? `<span class="kg-rozet kg-rozet-kapida">kapıda ${kargoPara(g.kapida_tutar)}</span>`
    : '';
  const tahsil = g.tahsilat_durumu
    ? `<span class="kg-rozet">${escapeHtml(g.tahsilat_durumu)}</span>` : '';
  const takip = g.takip_linki
    ? `<a class="kg-takip" href="${escapeHtml(g.takip_linki)}" target="_blank" rel="noopener noreferrer">takip →</a>`
    : '';
  return `<article class="kg-kart" data-kg-id="${id}">
    <header class="kg-ust">
      <label class="kg-sec"><input type="checkbox" data-kg-sec="${id}" ${secili}>
        <span>etiket</span></label>
      <div class="kg-kim">
        <b>${escapeHtml(g.alici || '—')}</b>
        <span>${escapeHtml(g.nere || '')}</span>
      </div>
      <div class="kg-durum">
        <span class="kg-son">${escapeHtml(g.son_durum || g.durum || '—')}</span>
        ${kapida}${tahsil}
      </div>
    </header>
    <div class="kg-orta">
      <p class="kg-icerik">${escapeHtml(g.icerik || '—')}
        ${g.desi ? `<span class="kg-desi">${escapeHtml(String(g.desi))} desi</span>` : ''}</p>
      ${kargoZincir(g)}
    </div>
    <footer class="kg-alt">
      <span class="kg-tasiyici">${escapeHtml(g.tasiyici_adi || g.tasiyici || 'taşıyıcı seçilmedi')}</span>
      <span class="kg-barkod">${g.barkod ? escapeHtml(g.barkod) : 'barkod yok'}</span>
      ${takip}
      <span class="kg-ucret" title="Uç üç rakamı ayrı veriyor; toplanmadı">
        kargo ${kargoPara(g.ucret)}${g.ek_ucret ? ' · ek ' + kargoPara(g.ek_ucret) : ''}</span>
      ${g.barkod ? '' : `<button type="button" class="dk-btn kg-fiyat-btn" data-kg-fiyat="${id}">TAŞIYICI VE FİYAT</button>`}
    </footer>
    <div class="kg-secim" data-kg-secim="${id}" hidden></div>
  </article>`;
}

function kargoYeniForm() {
  const turler = (kargoVeri.odeme_turleri || ['CASH', 'CREDIT_CARD']).map((t) =>
    `<option value="${escapeHtml(t)}">${t === 'CASH' ? 'nakit' : 'kredi kartı'}</option>`).join('');
  return `<details class="kg-yeni">
    <summary>YENİ GÖNDERİ AÇ <span class="kg-bedava">ücretsiz · barkod üretmez</span></summary>
    <div class="kg-form" id="kargoForm">
      <div class="kg-satir">
        <label>Alıcı adı<input class="dk-girdi" type="text" data-kf="alici" autocomplete="off"></label>
        <label>Telefon<input class="dk-girdi" type="tel" data-kf="telefon" placeholder="5551112233"></label>
      </div>
      <div class="kg-satir">
        <label>İl<input class="dk-girdi" type="text" data-kf="il"></label>
        <label>İlçe<input class="dk-girdi" type="text" data-kf="ilce"></label>
        <label>Desi<input class="dk-girdi" type="number" min="0.1" step="0.1" data-kf="desi" value="1"></label>
      </div>
      <label>Açık adres<input class="dk-girdi" type="text" data-kf="adres"></label>
      <div class="kg-satir">
        <label>İçerik<input class="dk-girdi" type="text" data-kf="icerik" placeholder="Vireon x1"></label>
        <label>Kendi referansınız<input class="dk-girdi" type="text" data-kf="referans" placeholder="isteğe bağlı"></label>
      </div>
      <div class="kg-satir kg-kapida-satir">
        <label class="kg-onay"><input type="checkbox" data-kf="karsi_odemeli">
          <span>Karşı ödemeli (parayı kapıda kurye tahsil etsin)</span></label>
        <label>Kapıda tahsil edilecek<input class="dk-girdi" type="number" min="0" step="0.01" data-kf="kapida_tutar" disabled></label>
        <label>Nasıl<select class="dk-girdi" data-kf="kapida_tur" disabled>${turler}</select></label>
      </div>
      <div class="dk-dugmeler">
        <button type="button" class="dk-btn dk-btn-ana" id="kargoTaslakBtn">TASLAK OLUŞTUR</button>
      </div>
      <p class="dk-sonuc" id="kargoTaslakSonuc" hidden></p>
    </div>
  </details>`;
}

function renderKargo() {
  const kutu = qs('kargoGovde');
  if (!kutu || !kargoVeri) return;
  const liste = kargoVeri.gonderiler || [];
  const kararlar = kargoVeri.kararlar || [];

  const hata = kargoVeri.gonderi_hatasi
    ? `<p class="o-uyari">${escapeHtml(kargoVeri.gonderi_hatasi)}</p>` : '';

  const barkodsuz = liste.filter((g) => !g.barkod).length;
  const yolda = liste.filter((g) => g.kargoya_verildi && !g.teslim_edildi).length;
  const kapidaAdet = liste.filter((g) => g.karsi_odemeli).length;

  const ozet = `<div class="ek-ozet">
    <div class="ek-tile"><span class="ek-n">${liste.length}</span><span class="ek-k">gönderi</span></div>
    <div class="ek-tile ${barkodsuz ? 'ek-tile-uyari' : ''}">
      <span class="ek-n">${barkodsuz}</span><span class="ek-k">barkod bekliyor</span></div>
    <div class="ek-tile"><span class="ek-n">${yolda}</span><span class="ek-k">yolda</span></div>
    <div class="ek-tile"><span class="ek-n">${kapidaAdet}</span><span class="ek-k">kapıda ödemeli</span></div>
  </div>`;

  const etiketCubugu = `<div class="kg-etiket-cubuk">
    <span id="kargoSecimSayi">${kargoSecili.size} gönderi seçili</span>
    <button type="button" class="dk-btn" id="kargoEtiketBtn" ${kargoSecili.size ? '' : 'disabled'}>
      HB-1006 ETİKET SAYFASI ÜRET</button>
    <span class="kg-bedava">ücretsiz · sayfada 6 etiket</span>
    <p class="dk-sonuc" id="kargoEtiketSonuc" hidden></p>
  </div>`;

  const kararBlok = kararlar.length ? `<section class="kg-bolum">
    <h3>BARKOD KARARLARI <span class="kg-alt-baslik">para harcayan her çağrının kaydı</span></h3>
    <table class="kg-tablo"><thead><tr>
      <th>tarih</th><th>gönderi</th><th>taşıyıcı</th><th>tutar</th><th>sonuç</th><th>veren</th>
    </tr></thead><tbody>
      ${kararlar.map((k) => `<tr>
        <td>${kargoTarih(k.verildi)}</td>
        <td>${escapeHtml(k.siparis_id || '')}</td>
        <td>${escapeHtml(k.tasiyici || '')}</td>
        <td>${kargoPara(k.gosterilen_ucret)}</td>
        <td class="kg-karar-${escapeHtml(k.karar || '')}">${escapeHtml(k.karar || '')}${
          k.hata ? ` <i title="${escapeHtml(k.hata)}">?</i>` : ''}</td>
        <td>${escapeHtml(k.veren || '')}</td></tr>`).join('')}
    </tbody></table></section>` : '';

  kutu.innerHTML = hata + ozet + kargoYeniForm() + etiketCubugu
    + `<section class="kg-bolum"><h3>GÖNDERİLER</h3>
       <div class="kg-liste">${liste.map(kargoSatir).join('') ||
         '<p class="fm-empty">Gönderi yok.</p>'}</div></section>`
    + kararBlok
    + `<section class="kg-bolum" id="kargoKapida">
        <h3>KAPIDA ÖDEME <span class="kg-alt-baslik">Wix ciro hattında görünmeyen para</span></h3>
        <button type="button" class="dk-btn" id="kargoKapidaBtn">HESAPLA</button>
        <div id="kargoKapidaGovde"></div></section>`;

  kargoBagla();
}

/* ------------------------------------------------- olay bağlama */
function kargoBagla() {
  const kutu = qs('kargoGovde');
  if (!kutu) return;

  // karşı ödemeli kutusu tutar alanını açar/kapar
  const kapidaKutu = kutu.querySelector('[data-kf="karsi_odemeli"]');
  if (kapidaKutu) {
    kapidaKutu.addEventListener('change', () => {
      ['kapida_tutar', 'kapida_tur'].forEach((ad) => {
        const el = kutu.querySelector(`[data-kf="${ad}"]`);
        if (el) el.disabled = !kapidaKutu.checked;
      });
    });
  }

  const taslakBtn = qs('kargoTaslakBtn');
  if (taslakBtn) taslakBtn.addEventListener('click', kargoTaslakGonder);

  kutu.querySelectorAll('[data-kg-sec]').forEach((kutucuk) => {
    kutucuk.addEventListener('change', () => {
      const id = kutucuk.dataset.kgSec;
      if (kutucuk.checked) kargoSecili.add(id); else kargoSecili.delete(id);
      const sayi = qs('kargoSecimSayi');
      if (sayi) sayi.textContent = `${kargoSecili.size} gönderi seçili`;
      const btn = qs('kargoEtiketBtn');
      if (btn) btn.disabled = kargoSecili.size === 0;
    });
  });

  kutu.querySelectorAll('[data-kg-fiyat]').forEach((btn) => {
    btn.addEventListener('click', () => kargoFiyatSor(btn.dataset.kgFiyat, btn));
  });

  const etiketBtn = qs('kargoEtiketBtn');
  if (etiketBtn) etiketBtn.addEventListener('click', kargoEtiketUret);

  const kapidaBtn = qs('kargoKapidaBtn');
  if (kapidaBtn) kapidaBtn.addEventListener('click', kargoKapidaYukle);
}

function kargoSonuc(id, metin, kotu) {
  const el = qs(id);
  if (!el) return;
  el.hidden = false;
  el.textContent = metin;
  el.classList.toggle('dk-sonuc-hata', !!kotu);
}

async function kargoTaslakGonder() {
  const kutu = qs('kargoForm');
  if (!kutu) return;
  const al = (ad) => {
    const el = kutu.querySelector(`[data-kf="${ad}"]`);
    if (!el) return '';
    return el.type === 'checkbox' ? el.checked : el.value;
  };
  const btn = qs('kargoTaslakBtn');
  btn.disabled = true;
  kargoSonuc('kargoTaslakSonuc', 'taslak açılıyor…', false);
  const { ok, body } = await api('/api/kargo/taslak', {
    method: 'POST',
    body: JSON.stringify({
      alici: al('alici'), telefon: al('telefon'), il: al('il'),
      ilce: al('ilce'), adres: al('adres'), icerik: al('icerik'),
      desi: al('desi'), referans: al('referans'),
      karsi_odemeli: al('karsi_odemeli'),
      kapida_tutar: al('kapida_tutar'), kapida_tur: al('kapida_tur'),
    }),
  });
  btn.disabled = false;
  if (!ok || !body || body.error) {
    kargoSonuc('kargoTaslakSonuc', (body && body.error) || 'taslak açılamadı', true);
    return;
  }
  kargoSonuc('kargoTaslakSonuc',
    `taslak açıldı: ${body.siparis_id} — henüz barkod YOK, para harcanmadı.`, false);
  kargoVeri = null;
  loadKargo();
}

async function kargoFiyatSor(siparisId, btn) {
  const alan = document.querySelector(`[data-kg-secim="${CSS.escape(siparisId)}"]`);
  if (!alan) return;
  btn.disabled = true;
  alan.hidden = false;
  alan.innerHTML = '<p class="fm-empty">fiyatlar soruluyor…</p>';
  const { ok, body } = await api('/api/kargo/fiyat', {
    method: 'POST', body: JSON.stringify({ siparis_id: siparisId }) });
  btn.disabled = false;
  if (!ok || !body || body.error) {
    alan.innerHTML = `<p class="o-uyari">${escapeHtml((body && body.error) || 'fiyat alınamadı')}</p>`;
    return;
  }
  const fiyatlar = body.fiyatlar || [];
  if (!fiyatlar.length) {
    alan.innerHTML = `<p class="o-uyari">${escapeHtml(body.uyari || 'uç fiyat döndürmedi')}</p>`;
    return;
  }
  alan.innerHTML = `<div class="kg-fiyatlar">
    ${fiyatlar.map((f) => {
      const gun = f.gun ? `${Math.round(f.gun * 10) / 10} gün` : '';
      const kapidaEk = f.kapida_ucret
        ? `kapıda +${kargoPara(f.kapida_ucret)}` : '';
      const ek = [gun, kapidaEk, f.risk ? String(f.risk) : ''].filter(Boolean).join(' · ');
      return `<button type="button" class="kg-fiyat${f.kapali ? ' kg-fiyat-kapali' : ''}"
        ${f.kapali ? 'disabled title="Bu gönderi için kapalı"' : ''}
        data-kg-sec-tasiyici="${escapeHtml(f.tasiyici)}"
        data-kg-sec-ad="${escapeHtml(f.ad || f.tasiyici)}"
        data-kg-sec-ucret="${escapeHtml(String(f.ucret === null ? '' : f.ucret))}"
        data-kg-sec-kapida="${escapeHtml(String(f.kapida_ucret || 0))}"
        data-kg-sec-siparis="${escapeHtml(siparisId)}">
        <b>${escapeHtml(f.ad || f.tasiyici)}</b>
        <i>${kargoPara(f.ucret)}</i>
        ${ek ? `<u>${escapeHtml(ek)}</u>` : ''}
        ${f.kapali ? '<u>kapalı</u>' : ''}</button>`;
    }).join('')}
  </div>
  <div class="kg-onay-serit" data-kg-serit hidden></div>`;
  alan.querySelectorAll('[data-kg-sec-tasiyici]').forEach((b) => {
    b.addEventListener('click', () => kargoOnaySerit(alan, b.dataset));
  });
}

/* 🔴 İKİNCİ ADIM. Taşıyıcıya tıklamak para harcamaz; yalnız tutarı yazan
 * onay şeridini açar. Para ancak buradaki ONAYLA'dan geçer. */
function kargoOnaySerit(alan, veri) {
  const serit = alan.querySelector('[data-kg-serit]');
  if (!serit) return;
  const tutar = veri.kgSecUcret === '' ? null : Number(veri.kgSecUcret);
  const kapidaEk = Number(veri.kgSecKapida || 0);
  serit.hidden = false;
  serit.innerHTML = `
    <p class="kg-uyari-para">Bu işlem şirketin BasitKargo bakiyesinden
      <b>${kargoPara(tutar)}</b> düşürür ve
      ${escapeHtml(veri.kgSecAd || veri.kgSecTasiyici)} kargosunu çağırır.
      ${kapidaEk ? `Karşı ödeme için ayrıca <b>${kargoPara(kapidaEk)}</b> ek ücret var.` : ''}
      Geri alınamaz.</p>
    <div class="dk-dugmeler">
      <button type="button" class="dk-btn dk-btn-ana" data-kg-onayla>ONAYLA VE BARKOD AL</button>
      <button type="button" class="dk-btn" data-kg-vazgec>VAZGEÇ</button>
    </div>
    <p class="dk-sonuc" data-kg-barkod-sonuc hidden></p>`;
  serit.querySelector('[data-kg-vazgec]').addEventListener('click', () => {
    serit.hidden = true; serit.innerHTML = '';
  });
  serit.querySelector('[data-kg-onayla]').addEventListener('click', async (ev) => {
    const dugme = ev.currentTarget;
    dugme.disabled = true;
    const sonuc = serit.querySelector('[data-kg-barkod-sonuc]');
    sonuc.hidden = false;
    sonuc.classList.remove('dk-sonuc-hata');
    sonuc.textContent = 'barkod üretiliyor…';
    const { ok, body } = await api('/api/kargo/barkod', {
      method: 'POST',
      body: JSON.stringify({
        siparis_id: veri.kgSecSiparis,
        tasiyici: veri.kgSecTasiyici,
        gosterilen_ucret: tutar,
      }),
    });
    if (!ok || !body || body.error) {
      sonuc.classList.add('dk-sonuc-hata');
      sonuc.textContent = (body && body.error) || 'barkod üretilemedi';
      dugme.disabled = false;
      return;
    }
    sonuc.textContent = `barkod: ${body.barkod || '(uç kod döndürmedi)'} · ${kargoPara(body.ucret)} harcandı`;
    kargoVeri = null;
    setTimeout(loadKargo, 1200);
  });
}

async function kargoEtiketUret() {
  const btn = qs('kargoEtiketBtn');
  btn.disabled = true;
  kargoSonuc('kargoEtiketSonuc', 'etiketler alınıyor ve sayfaya diziliyor…', false);
  const { ok, body } = await api('/api/kargo/etiket', {
    method: 'POST', body: JSON.stringify({ siparisler: [...kargoSecili] }) });
  btn.disabled = false;
  if (!ok || !body || body.hata || body.error) {
    kargoSonuc('kargoEtiketSonuc', (body && (body.hata || body.error)) || 'etiket üretilemedi', true);
    return;
  }
  const el = qs('kargoEtiketSonuc');
  el.hidden = false;
  el.classList.remove('dk-sonuc-hata');
  el.innerHTML = `${escapeHtml(body.ozet || '')} — <a href="${escapeHtml(body.baglanti)}"
    download>${escapeHtml(body.dosya)}</a> · HB-1006 sayfasına dizildi`;
}

async function kargoKapidaYukle() {
  const govde = qs('kargoKapidaGovde');
  const btn = qs('kargoKapidaBtn');
  btn.disabled = true;
  govde.innerHTML = '<p class="fm-empty">gönderiler taranıyor…</p>';
  const { ok, body } = await api('/api/kargo/kapida');
  btn.disabled = false;
  if (!ok || !body || body.error || body.hata) {
    govde.innerHTML = `<p class="o-uyari">${escapeHtml((body && (body.error || body.hata)) || 'okunamadı')}</p>`;
    return;
  }
  const satirlar = body.satirlar || [];
  govde.innerHTML = `
    <div class="ek-ozet">
      <div class="ek-tile"><span class="ek-n">${body.kapida_adet}</span><span class="ek-k">kapıda ödemeli gönderi</span></div>
      <div class="ek-tile"><span class="ek-n">${kargoPara(body.kapida_toplam)}</span><span class="ek-k">kapıda tahsil edilen</span></div>
      <div class="ek-tile"><span class="ek-n">${kargoPara(body.elle_tahsil)}</span><span class="ek-k">bunun Wix'te olmayanı</span></div>
      <div class="ek-tile ${body.sinifsiz_gonderi ? 'ek-tile-uyari' : ''}">
        <span class="ek-n">${body.sinifsiz_gonderi || 0}</span><span class="ek-k">sınıfsız gönderi</span></div>
    </div>
    <p class="o-uyari">${escapeHtml(body.not || '')}</p>
    <table class="kg-tablo"><thead><tr>
      <th>tarih</th><th>sınıf</th><th>ürün</th><th>kapıda</th>
      <th>tahsilat</th><th>Wix siparişi</th>
    </tr></thead><tbody>
      ${satirlar.map((s) => `<tr>
        <td>${kargoTarih(s.gun)}</td>
        <td class="kg-sinif-${escapeHtml(s.sinif || '')}">${escapeHtml(s.sinif || '')}</td>
        <td>${escapeHtml(s.urun || '')}</td>
        <td>${kargoPara(s.cod_tutar)}</td>
        <td>${escapeHtml(s.cod_durum || '')}</td>
        <td>${s.siparis_id ? escapeHtml(s.siparis_id) : '<i>yok</i>'}</td></tr>`).join('')}
    </tbody></table>`;
}

/* ========================== MÜŞTERİLER ==========================
 * Sahip: *"müşteri kartı — kim kaç kere almış"* ve *"iade değişim takibi"*.
 * İkisi aynı sekmede: ikisi de satış SONRASI konular.
 *
 * 🔴 Kişisel veri burada yalnız GÖSTERİLİR. Uç, adı istek anında Wix
 * kaydından okuyup veriyor; hiçbir tabloya ve şirket hafızasına yazılmıyor.
 */

let musteriVeri = null;
let iadeVeri = null;

async function loadMusteri() {
  const kutu = qs('musteriGovde');
  if (kutu && !musteriVeri) kutu.innerHTML = '<p class="fm-empty">Yükleniyor…</p>';
  const [m, i] = await Promise.all([api('/api/musteri'), api('/api/iade')]);
  musteriVeri = (m && m.body) || {};
  iadeVeri = (i && i.body) || {};
  renderMusteri();
}

function musteriPara(x) {
  if (x === null || x === undefined || x === '') return '—';
  const n = Number(x);
  return Number.isFinite(n) ? n.toLocaleString('tr-TR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' TL' : String(x);
}

function musteriSatir(m) {
  const kere = Number(m.siparis) || 0;
  const odenen = Number(m.odenen) || 0;
  /* 🔴 "2 sipariş" tek başına yanıltıyor: ikisi de iptalse müşteri hiç
     para ödememiştir. Ölçümde tam böyle bir kayıt çıktı (2 sipariş,
     0 TL). Bu yüzden ödenen sayısı her zaman yanında yazılıyor. */
  const kereMetni = odenen === kere
    ? `${kere} kez aldı`
    : `${kere} sipariş · ${odenen} tanesi ödendi`;
  return `<button type="button" class="ms-satir" data-ms-id="${escapeHtml(String(m.buyer_id))}">
    <span class="ms-ad">${escapeHtml(m.gorunen_ad || '')}
      ${kere > 1 ? '<em class="ms-tekrar">tekrar eden</em>' : ''}</span>
    <span class="ms-kere">${escapeHtml(kereMetni)}</span>
    <span class="ms-harcama">${musteriPara(m.harcama)}</span>
    <span class="ms-tarih">${escapeHtml(String(m.son || ''))}</span>
  </button>`;
}

function iadeBolumu() {
  const v = iadeVeri || {};
  const wix = v.wix_para_iadesi || [];
  const iptal = v.iptal_siparis || [];
  const gelen = v.gelen_kargo || [];
  const beyan = v.elle_beyan || [];

  const tablo = (baslik, satirlar, ciz) => `
    <div class="ms-iade-kutu">
      <h4>${escapeHtml(baslik)} <b>${satirlar.length}</b></h4>
      ${satirlar.length
        ? `<table class="kg-tablo">${ciz(satirlar)}</table>`
        : '<p class="fm-empty">kayıt yok</p>'}
    </div>`;

  return `<section class="kg-bolum">
    <h3>İADE VE DEĞİŞİM
      <span class="kg-alt-baslik">üç ayrı kaynak · toplanmaz</span></h3>
    <p class="o-uyari">${escapeHtml(v.not || '')}</p>
    <div class="ms-iade-izgara">
      ${tablo('Wix para iadesi', wix, (r) => `
        <thead><tr><th>tarih</th><th>sipariş</th><th>tutar</th></tr></thead>
        <tbody>${r.map((x) => `<tr><td>${escapeHtml(String(x.gun))}</td>
          <td>${escapeHtml(String(x.siparis_no || ''))}</td>
          <td>${musteriPara(x.toplam)}</td></tr>`).join('')}</tbody>`)}
      ${tablo('İptal edilen sipariş', iptal, (r) => `
        <thead><tr><th>tarih</th><th>ürün</th><th>tutar</th></tr></thead>
        <tbody>${r.map((x) => `<tr><td>${escapeHtml(String(x.gun))}</td>
          <td>${escapeHtml(x.urunler || '—')}</td>
          <td>${musteriPara(x.toplam)}</td></tr>`).join('')}</tbody>`)}
      ${tablo('Geri gelen kargo', gelen, (r) => `
        <thead><tr><th>tarih</th><th>ürün</th><th>durum</th></tr></thead>
        <tbody>${r.map((x) => `<tr><td>${escapeHtml(String(x.gun))}</td>
          <td>${escapeHtml(x.urun || '—')}</td>
          <td>${escapeHtml(x.son_hareket || x.durum || '')}</td></tr>`).join('')}</tbody>`)}
      ${tablo('Elle beyan edilen', beyan, (r) => `
        <thead><tr><th>tarih</th><th>tür</th><th>ürün</th></tr></thead>
        <tbody>${r.map((x) => `<tr><td>${escapeHtml(String(x.gun))}</td>
          <td>${escapeHtml(x.tur || '')}</td>
          <td>${escapeHtml(x.urun_adi || '')}</td></tr>`).join('')}</tbody>`)}
    </div>
  </section>`;
}

function renderMusteri() {
  const kutu = qs('musteriGovde');
  if (!kutu || !musteriVeri) return;
  const liste = musteriVeri.musteriler || [];

  const ozet = `<div class="ek-ozet">
    <div class="ek-tile"><span class="ek-n">${musteriVeri.toplam_musteri || 0}</span>
      <span class="ek-k">müşteri</span></div>
    <div class="ek-tile"><span class="ek-n">${musteriVeri.tekrar_eden || 0}</span>
      <span class="ek-k">birden fazla alan</span></div>
    <div class="ek-tile"><span class="ek-n">${musteriVeri.tekrar_orani ?? '—'}%</span>
      <span class="ek-k">tekrar oranı</span></div>
    <div class="ek-tile ${(iadeVeri && iadeVeri.kayitli_iade_toplami) ? '' : 'ek-tile-uyari'}">
      <span class="ek-n">${(iadeVeri && iadeVeri.kayitli_iade_toplami) || 0}</span>
      <span class="ek-k">kayıtlı iade</span></div>
  </div>`;

  kutu.innerHTML = ozet
    + `<p class="o-uyari">${escapeHtml(musteriVeri.not || '')}</p>`
    + `<section class="kg-bolum"><h3>MÜŞTERİLER
         <span class="kg-alt-baslik">satır tıklanınca geçmişi açılır</span></h3>
       <div class="ms-baslik">
         <span>müşteri</span><span>kaç kez</span><span>harcama</span><span>son</span>
       </div>
       <div class="ms-liste">${liste.map(musteriSatir).join('')
         || '<p class="fm-empty">Müşteri yok.</p>'}</div>
       <div class="ms-kart" id="musteriKart" hidden></div>
     </section>`
    + iadeBolumu();

  kutu.querySelectorAll('[data-ms-id]').forEach((btn) => {
    btn.addEventListener('click', () => musteriKartAc(btn.dataset.msId, btn));
  });
}

async function musteriKartAc(kimlik, btn) {
  const kart = qs('musteriKart');
  if (!kart) return;
  document.querySelectorAll('.ms-satir').forEach((x) =>
    x.classList.toggle('is-active', x === btn));
  kart.hidden = false;
  kart.innerHTML = '<p class="fm-empty">geçmiş okunuyor…</p>';
  const { ok, body } = await api('/api/musteri/kart?id=' + encodeURIComponent(kimlik));
  if (!ok || !body || body.hata || body.error) {
    kart.innerHTML = `<p class="o-uyari">${escapeHtml((body && (body.hata || body.error)) || 'okunamadı')}</p>`;
    return;
  }
  const m = body.musteri || {};
  const sip = body.siparisler || [];
  kart.innerHTML = `
    <div class="ms-kart-ust">
      <div>
        <b>${escapeHtml(m.gorunen_ad || '')}</b>
        <span>${escapeHtml(m.eposta || '')}${m.telefon ? ' · ' + escapeHtml(m.telefon) : ''}</span>
      </div>
      <div class="ms-kart-sayi">
        <span><i>${body.siparis_adedi}</i> sipariş</span>
        <span><i>${body.odenen_adet}</i> ödendi</span>
        <span><i>${musteriPara(body.harcama)}</i> harcama</span>
      </div>
    </div>
    <table class="kg-tablo"><thead><tr>
      <th>tarih</th><th>ürünler</th><th>tutar</th><th>ödeme</th><th>kargo</th>
    </tr></thead><tbody>
      ${sip.map((s) => `<tr>
        <td>${escapeHtml(String(s.gun))}</td>
        <td class="ms-urun">${escapeHtml(s.urunler || '—')}</td>
        <td>${musteriPara(s.toplam)}</td>
        <td class="${s.odeme_durumu === 'PAID' ? 'ms-odendi' : 'ms-odenmedi'}">
          ${escapeHtml(s.odeme_durumu || '')}</td>
        <td>${escapeHtml(s.kargo || '—')}</td></tr>`).join('')}
    </tbody></table>`;
}

/* ==================== AÇILIR GRUP MENÜSÜ (masaüstü) ====================
 * Sahip 22.09.2026: *"üst menüyü kendi aralarında grupla ve açılan menü
 * tarzında olsun. daha premium durur. ve bu kadar karmaşık olmaz."*
 *
 * 🔴 BU AYNI ZAMANDA BİR YAPISAL DÜZELTME. Üst çubuk 16 sekmeyi yan yana
 * taşıyordu; ölçümde menü 1215px kaplayıp sağdaki saat bloğunu 45px'e
 * sıkıştırmış ve tarihi üç satıra bölmüştü. Artık çubukta 4 grup adı var;
 * sekmeler açılır panelde. Yeni sekme eklemek çubuğu bir daha zorlamaz.
 *
 * Mevcut `is-kapali` akordeonuna DOKUNULMADI: o mobil çekmecenin
 * mekanizması ve orada doğru davranış o. Masaüstü açılır menüsü ayrı bir
 * sınıf (`is-acik`) kullanır; ikisi çakışmaz.
 */
(function () {
  var nav = document.getElementById('mainNav');
  if (!nav) return;

  // Açılır menü yalnız masaüstünde; altında çekmece var.
  var masaustu = window.matchMedia('(min-width: 861px)');

  function hepsiniKapat(haric) {
    nav.querySelectorAll('.nav-group.is-acik').forEach(function (g) {
      if (g === haric) return;
      g.classList.remove('is-acik');
      var h = g.querySelector('.nav-head');
      if (h) h.setAttribute('aria-expanded', 'false');
    });
  }

  /* 🔴 YAKALAMA (capture) EVRESİNDE dinliyoruz ve `stopPropagation`
     çağırıyoruz: aynı düğmeye bağlı eski akordeon dinleyicisi masaüstünde
     çalışmamalı, yoksa iki mekanizma birbirini iptal eder. */
  nav.addEventListener('click', function (e) {
    if (!masaustu.matches) return;
    // Sidebar headings use the accordion handler instead of the old dropdown.
    if (document.querySelector('.ed-dashboard')) return;
    var bas = e.target.closest('.nav-head');
    if (!bas || !nav.contains(bas)) return;
    e.preventDefault();
    e.stopPropagation();
    var grup = bas.closest('.nav-group');
    if (!grup) return;
    var acildi = !grup.classList.contains('is-acik');
    hepsiniKapat(grup);
    grup.classList.toggle('is-acik', acildi);
    bas.setAttribute('aria-expanded', acildi ? 'true' : 'false');
  }, true);

  // Sekme seçilince menü kapanır.
  nav.addEventListener('click', function (e) {
    if (!masaustu.matches) return;
    if (e.target.closest('.nav-item')) hepsiniKapat(null);
  });

  // Dışarı tıklama ve Escape kapatır. Açık kalan menü içeriğin üstünü
  // örter; kullanıcı her seferinde düğmeye dönmek zorunda kalmamalı.
  document.addEventListener('click', function (e) {
    if (!masaustu.matches) return;
    if (!e.target.closest('#mainNav')) hepsiniKapat(null);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    hepsiniKapat(null);
  });

  // Genişlik değişince açık menü kalıntısı kalmasın.
  masaustu.addEventListener('change', function () { hepsiniKapat(null); });
})();

/* Aktif sekmenin grubunu çubukta işaretler. Açılır menüde sekmeler
 * görünmediği için, hangi bölümde olunduğu yalnız grup adından anlaşılır;
 * işaret olmasa kullanıcı nerede olduğunu kaybeder. */
(function () {
  var nav = document.getElementById('mainNav');
  if (!nav) return;
  var eski = window.navAktifGrubuAc;
  window.navAktifGrubuAc = function (ad) {
    try { if (typeof eski === 'function') eski(ad); } catch (_) { /* yoksay */ }
    var dugme = nav.querySelector('.nav-item[data-view="' + ad + '"]');
    var grup = dugme && dugme.closest('.nav-group');
    nav.querySelectorAll('.nav-group').forEach(function (g) {
      g.classList.toggle('grup-aktif', g === grup);
    });
  };
})();

async function kpItirazGonder(form) {
  const sonuc = form.querySelector('[data-kp-sonuc]');
  const btn = form.querySelector('[data-kp-gonder]');
  btn.disabled = true;
  sonuc.hidden = false;
  sonuc.classList.remove('dk-sonuc-hata');
  sonuc.textContent = 'gönderiliyor…';
  const { ok, body } = await api('/api/kreatif-itiraz', {
    method: 'POST',
    body: JSON.stringify({
      parti: form.dataset.kpIfParti,
      dosya: form.dataset.kpIfDosya,
      konu: form.querySelector('[data-kp-konu]').value,
      aciklama: form.querySelector('[data-kp-aciklama]').value,
    }),
  });
  btn.disabled = false;
  if (!ok || !body || body.error) {
    sonuc.classList.add('dk-sonuc-hata');
    sonuc.textContent = (body && body.error) || 'itiraz gönderilemedi';
    return;
  }
  sonuc.textContent = `İtiraz ${body.muhatap} departmanına açıldı. `
    + 'Bir sonraki kreatif koşusu bu itirazı okumak zorunda.';
}


/* ===================================================================
   SISTEM sekmesi -- uc makinenin kaynak kullanimi + kaynak politikasi.

   🔴 CSP kurali: style-src 'self', unsafe-inline YOK. Bir cubugun
   genisligi bu yuzden satir ici bicimle verilemez -- ne HTML metninde
   bir bicim ozniteligiyle, ne de onu DOM'dan yazarak. Cozum: yuzde 5'in
   katina yuvarlanip `w-40` gibi bir SINIF veriliyor (app.css'te 21 tane
   tanimli). Gorsel cozunurluk %5; sayinin kendisi her zaman tam
   degeriyle yanina yazili duruyor.
   Not: asagida o yasak kalibin harfi harfine yazilmamasi da bilincli --
   sozlesme testi ham metinde ariyor ve bir ornek bile testi kirar.
   =================================================================== */

const sistemState = { yukleniyor: false, veri: null, onayBekleyen: null };

function sysBar(yuzde, tehlikeEsigi) {
  if (yuzde === null || yuzde === undefined || isNaN(yuzde)) {
    return '<div class="sys-bar"><span class="sys-bar-yok">ölçülemedi</span></div>';
  }
  const v = Math.max(0, Math.min(100, Number(yuzde)));
  const adim = Math.round(v / 5) * 5;
  const esik = tehlikeEsigi === undefined ? 90 : tehlikeEsigi;
  const ton = v >= esik ? 'bad' : v >= esik - 15 ? 'warn' : 'good';
  return `<div class="sys-bar"><i class="sys-bar-ic t-${ton} w-${adim}"></i></div>`;
}

function sysSatir(etiket, deger, yuzde, esik) {
  return `<div class="sys-row">
    <span class="sys-k">${escapeHtml(etiket)}</span>
    <span class="sys-v">${escapeHtml(deger)}</span>
    ${sysBar(yuzde, esik)}
  </div>`;
}

function sysDurumRozeti(m) {
  const d = m.durum || '';
  const ton = d === 'TAZE' ? 'good' : d === 'BAYAT' ? 'warn' : 'bad';
  const yas = (m.yas_s === null || m.yas_s === undefined) ? '' : ` · ${m.yas_s} sn önce`;
  return `<span class="chip chip-${ton}">${escapeHtml(d)}${escapeHtml(yas)}</span>`;
}

/* Sunucu karti: olcum app.py'den anlik gelir. Balon duzeltmesi varsa
   HAM yuzdenin yaninda GERCEK satirlari da gosterilir -- sanal makinede
   `free`'nin "used" degeri uygulamalarin kullanimi DEGILDIR. */
function sistemSunucuKart(m) {
  const v = m.veri || {};
  const cpu = v.cpu || {};
  const ram = v.ram || {};
  const disk = v.disk || {};
  const bg = v.bellek_gercegi || {};
  let govde = '';

  govde += sysSatir('CPU',
    cpu.percent === null || cpu.percent === undefined
      ? (cpu.error || 'ölçülemedi')
      : `%${cpu.percent}` + (cpu.cores ? ` · ${cpu.cores} çekirdek` : '')
        + (cpu.load ? ` · yük ${cpu.load.join(' ')}` : ''),
    cpu.percent);

  if (ram.percent === null || ram.percent === undefined) {
    govde += sysSatir('RAM', ram.error || 'ölçülemedi', null);
  } else {
    govde += sysSatir('RAM (ham)', `%${ram.percent} · ${ram.used_gib} / ${ram.total_gib} GB`, ram.percent);
  }

  if (bg.durum === 'BALON_VAR') {
    govde += sysSatir('RAM (gerçek)',
      `%${bg.gercek_yuzde} · ${bg.surec_rss_gib} / ${bg.gercek_toplam_gib} GB · boş ${bg.gercek_bos_gib} GB`,
      bg.gercek_yuzde);
    govde += `<p class="sys-not is-warn">${escapeHtml(bg.not || '')}</p>`;
  } else if (bg.durum === 'DUZELTILEMEDI') {
    govde += `<p class="sys-not is-warn">${escapeHtml(bg.not || '')}</p>`;
  } else if (bg.surec_rss_gib !== undefined && bg.surec_rss_gib !== null) {
    govde += sysSatir('Süreçlerin gerçek kullanımı', `${bg.surec_rss_gib} GB (RSS toplamı, üst sınır)`, null);
  }

  govde += sysSatir('Disk',
    disk.percent === null || disk.percent === undefined
      ? (disk.error || 'ölçülemedi')
      : `%${disk.percent} · ${disk.used_gib} / ${disk.total_gib} GB`,
    disk.percent);

  return card('SUNUCU', `<div class="sys-kart">${govde}</div>`, sysDurumRozeti(m));
}

function sistemPcKart(m, baslik) {
  if (!m.veri) {
    return card(baslik,
      `<div class="sys-kart"><p class="sys-not is-bad">${escapeHtml(m.sebep || 'veri yok')}</p></div>`,
      sysDurumRozeti(m));
  }
  const v = m.veri;
  let govde = '';
  if (m.durum === 'BAYAT') {
    govde += `<p class="sys-not is-warn">${escapeHtml(m.sebep || '')}</p>`;
  }
  govde += sysSatir('CPU',
    v.cpu_yuzde === null || v.cpu_yuzde === undefined ? 'ölçülemedi'
      : `%${v.cpu_yuzde} · ${escapeHtml(String(v.cpu_model || ''))}`,
    v.cpu_yuzde);
  govde += sysSatir('RAM',
    v.ram_yuzde === null || v.ram_yuzde === undefined ? 'ölçülemedi'
      : `%${v.ram_yuzde} · ${(v.ram_dolu_mb / 1024).toFixed(1)} / ${(v.ram_toplam_mb / 1024).toFixed(1)} GB · boş ${v.ram_bos_mb} MB`,
    v.ram_yuzde);

  const g = v.gpu || {};
  if (g.kaynak === 'nvidia-smi') {
    govde += sysSatir('Ekran kartı',
      `${escapeHtml(String(g.ad || ''))} · %${g.kullanim_yuzde} · ${g.sicaklik_c} °C · ${g.guc_w} W`,
      g.kullanim_yuzde);
    govde += sysSatir('VRAM', `%${g.vram_yuzde} · ${g.vram_dolu_mb} / ${g.vram_toplam_mb} MB`, g.vram_yuzde, 92);
  } else if (g.kaynak === 'windows-sayac') {
    govde += sysSatir('Ekran kartı',
      `${escapeHtml(String(g.ad || ''))} · %${g.kullanim_yuzde === undefined ? '—' : g.kullanim_yuzde}`
      + (g.vram_dolu_mb !== undefined ? ` · ${g.vram_dolu_mb} MB kullanımda` : ''),
      g.kullanim_yuzde);
    govde += `<p class="sys-not">${escapeHtml(g.not || '')}</p>`;
  } else {
    govde += sysSatir('Ekran kartı', g.not || 'okunamadı', null);
  }

  (v.diskler || []).forEach((d) => {
    govde += sysSatir(`Disk ${d.surucu}`,
      `%${d.yuzde} · boş ${d.bos_gb} GB / ${d.toplam_gb} GB · ${escapeHtml(String(d.dosya_sistemi || ''))}`,
      d.yuzde);
  });

  /* "PC-2'nin RAM'ini kim yiyor" 24.09.2026'da soruldu ve cevap Jarvis
     DEGILDI. Bu satir o ayrimi her zaman gorunur tutar. */
  const bizimMb = v.jarvis_ram_mb || 0;
  govde += sysSatir('Bunun Jarvis&#39;e ait olan kısmı',
    `${bizimMb} MB` + (v.ram_dolu_mb ? ` (toplam kullanımın %${(bizimMb / v.ram_dolu_mb * 100).toFixed(1)}&#39;i)` : ''),
    null);

  const enb = (v.en_buyuk_surecler || []).map((p) => `${escapeHtml(p.ad)} ${p.ram_mb} MB`).join(' · ');
  if (enb) govde += `<p class="sys-not">En büyük süreçler: ${enb}</p>`;
  govde += `<p class="sys-not">Açık kalma: ${v.acik_saat} saat · ölçüm ${escapeHtml(String(v.olcum_utc || ''))}</p>`;

  return card(baslik, `<div class="sys-kart">${govde}</div>`, sysDurumRozeti(m));
}

/* Politika anahtarlari. Kilitli bir anahtari ACMAK iki adim ister:
   tarayici modali kullanmiyoruz (sayfayi kilitler), yerine satirin
   icinde bir onay dugmesi aciliyor. */
function sistemPolitikaKart(pol) {
  const anahtarlar = pol.anahtarlar || {};
  const sirali = Object.keys(anahtarlar).sort(
    (a, b) => (anahtarlar[a].sira || 99) - (anahtarlar[b].sira || 99));

  const satirlar = sirali.map((ad) => {
    const t = anahtarlar[ad];
    const acik = !!t.acik;
    const kilitli = t.kilit === 'ozel_izin';
    const onayda = sistemState.onayBekleyen === ad;
    const durumSinif = acik ? 'is-acik' : 'is-kapali';
    const kim = t.degistiren
      ? `<span class="pol-kim">${escapeHtml(t.degistiren)} · ${escapeHtml(String(t.degistirildi || ''))}</span>`
      : '';
    let dugme;
    if (onayda) {
      dugme = `<span class="pol-onay">
          <button type="button" class="btn btn-danger pol-btn" data-anahtar="${escapeHtml(ad)}" data-acik="1" data-onay="1">ÖZEL İZNİ VER</button>
          <button type="button" class="btn pol-btn" data-anahtar="${escapeHtml(ad)}" data-iptal="1">VAZGEÇ</button>
        </span>`;
    } else {
      dugme = `<button type="button" class="btn pol-btn ${durumSinif}"
          data-anahtar="${escapeHtml(ad)}" data-acik="${acik ? '0' : '1'}"
          ${kilitli && !acik ? 'data-kilit="1"' : ''}>${acik ? 'AÇIK' : 'KAPALI'}</button>`;
    }
    return `<div class="pol-row ${durumSinif}">
      <div class="pol-metin">
        <span class="pol-baslik">${escapeHtml(t.baslik || ad)}${kilitli ? ' <span class="pol-kilit">özel izin</span>' : ''}</span>
        <span class="pol-aciklama">${escapeHtml(t.aciklama || '')}</span>
        ${kim}
      </div>
      ${dugme}
    </div>`;
  }).join('');

  const sira = (pol.siralama || []).join(' → ');
  const meta = pol.kaynak === 'dosya'
    ? '<span class="chip chip-good">kayıtlı</span>'
    : '<span class="chip chip-flat">varsayılan</span>';

  return card('KAYNAK POLİTİKASI',
    `<div class="sys-kart">
      <p class="sys-not">Sıra: <strong>${escapeHtml(sira)}</strong>. Bir iş önce
      sunucuda denenir; sunucu yetmezse PC-1 devreye girer; PC-2&#39;den yalnız
      ekran kartı kullanılır.</p>
      ${satirlar}
    </div>`, meta);
}

async function sistemAnahtarCevir(anahtar, acik, ozelIzin) {
  /* ozel_izin YALNIZCA iki adimli onaydan sonra gonderilir. Arka uc bunu
     gormeden kilitli bir anahtari ACMAZ (403 doner) -- kilit 25.09.2026'da
     arayuzden sistem.py'ye tasindi, cunku arayuzdeki kilit panel disindaki
     cagiranlari (ornegin PC-2 kisayollarini besleyen politika-yaz.sh)
     hic baglamiyordu. */
  const { ok, status, body } = await api('/api/sistem/anahtar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ozelIzin ? { anahtar, acik, ozel_izin: true }
                                  : { anahtar, acik }),
  });
  if (!ok) {
    const govde = qs('sistemGovde');
    if (govde) {
      govde.insertAdjacentHTML('afterbegin',
        `<p class="sys-not is-bad">${escapeHtml(JarvisMetin.errorText(body?.error, 'Ayar değiştirilemedi. Biraz sonra tekrar deneyin.'))}</p>`);
    }
    return;
  }
  sistemState.onayBekleyen = null;
  if (sistemState.veri) sistemState.veri.politika = body.politika;
  sistemCiz();
}

/* Saglik gostergeleri seridi.

   NEDEN VAR: 25.09.2026'da bes ayri ariza bulundu ve BESI DE SESSIZDI --
   servis "calisiyor" goruniyordu, panel bir sey demiyordu. Bu serit o
   siniftan bir arizanin bir dahaki sefere EKRANDA gorunmesi icin.

   Her kutu "yakaladigi" seyi de yazar: bir gostergenin neden orada
   oldugunu bilmeyen kimse ona bakmaz. */
function sistemGostergeTonu(durum) {
  return durum === 'IYI' ? 'good'
    : durum === 'ZAYIF' ? 'warn'
    : durum === 'BOZUK' ? 'bad' : 'flat';
}

function sistemGostergeDeger(ad, g) {
  /* Her gosterge icin TEK bakilacak sayi. SORULAMADI'da sayi YAZILMAZ --
     olculemeyen seye rakam uydurmak bu projede tekrar eden kok hata. */
  if (g.durum === 'SORULAMADI') return 'ölçülemedi';
  if (ad === 'kuyruk') return `${g.askida_kira} askıda · ${g.bekleyen} bekleyen`;
  if (ad === 'tuneller') {
    const acik = (g.uclar || []).filter((u) => u.durum === 'ACIK').length;
    return `${acik}/${(g.uclar || []).length} uç açık`;
  }
  if (ad === 'model_kademesi') return `${g.zincir_tukendi} tükendi · ${g.basarili} başarılı`;
  if (ad === 'mutabakat') return g.ozet || '—';
  if (ad === 'siparis') return `${g.gun} gün önce`;
  return '—';
}

const SISTEM_GOSTERGE_ADI = {
  kuyruk: 'KUYRUK', tuneller: 'TÜNELLER', model_kademesi: 'MODEL KADEMESİ',
  mutabakat: 'MUTABAKAT', siparis: 'SİPARİŞ AKIŞI',
};

function sistemGostergeler(g) {
  if (!g) return '';
  const sira = ['kuyruk', 'tuneller', 'model_kademesi', 'mutabakat', 'siparis'];
  const kutular = sira.filter((ad) => g[ad]).map((ad) => {
    const v = g[ad];
    const ton = sistemGostergeTonu(v.durum);
    const detay = v.durum === 'SORULAMADI'
      ? `<span class="gst-sebep">${escapeHtml(v.sebep || 'sebep yazılmamış')}</span>`
      : `<span class="gst-yakala">${escapeHtml(v.yakaladigi || '')}</span>`;
    const ek = [];
    if (v.kapali && v.kapali.length) ek.push('kapalı: ' + v.kapali.join(', '));
    if (v.goremedigi) ek.push('göremediği: ' + v.goremedigi);
    if (v.kapsam) ek.push(v.kapsam);
    return `<article class="gst-kutu t-${ton}">
      <header class="gst-bas">
        <span class="gst-ad">${escapeHtml(SISTEM_GOSTERGE_ADI[ad] || ad)}</span>
        <span class="chip chip-${ton}">${escapeHtml(v.durum)}</span>
      </header>
      <div class="gst-deger">${escapeHtml(sistemGostergeDeger(ad, v))}</div>
      ${detay}
      ${ek.length ? `<p class="gst-ek">${escapeHtml(ek.join(' · '))}</p>` : ''}
    </article>`;
  }).join('');
  return `<section class="gst-serit" aria-label="SAĞLIK GÖSTERGELERİ">${kutular}</section>`;
}

function sistemCiz() {
  const govde = qs('sistemGovde');
  const d = sistemState.veri;
  if (!govde || !d) return;
  const m = d.makineler || {};
  govde.innerHTML = [
    sistemGostergeler(d.gostergeler),
    sistemPolitikaKart(d.politika || {}),
    sistemSunucuKart(m.sunucu || {}),
    sistemPcKart(m.pc1 || {}, 'PC-1  (gömme · RX 6600)'),
    sistemPcKart(m.pc2 || {}, 'PC-2  (dil modeli · RTX 5060)'),
  ].join('');

  const say = qs('sistemCount');
  if (say) {
    const taze = ['sunucu', 'pc1', 'pc2'].filter((k) => (m[k] || {}).durum === 'TAZE').length;
    say.textContent = `${taze}/3 makine taze`;
  }
}

async function loadSistem() {
  const govde = qs('sistemGovde');
  if (!govde || sistemState.yukleniyor) return;
  sistemState.yukleniyor = true;
  if (!sistemState.veri) govde.innerHTML = '<p class="sect-empty">Yükleniyor…</p>';

  const { ok, status, body } = await api('/api/sistem');
  sistemState.yukleniyor = false;
  if (!ok) {
    govde.innerHTML = '<p class="sect-empty is-bad">Sistem durumu şu anda yüklenemedi.</p>';
    return;
  }
  sistemState.veri = body;
  loadKademe();
  sistemCiz();
}

/* Tek delege dinleyici: kartlar her cizimde yeniden yazildigi icin
   dugmelere tek tek dinleyici baglamak sessizce kopardi. */
document.addEventListener('click', (ev) => {
  const btn = ev.target.closest && ev.target.closest('.pol-btn');
  if (!btn) return;
  ev.preventDefault();
  if (btn.dataset.iptal) { sistemState.onayBekleyen = null; sistemCiz(); return; }
  const anahtar = btn.dataset.anahtar;
  const acik = btn.dataset.acik === '1';
  if (btn.dataset.kilit && !btn.dataset.onay) {
    sistemState.onayBekleyen = anahtar;
    sistemCiz();
    return;
  }
  sistemAnahtarCevir(anahtar, acik, btn.dataset.onay === '1');
});


/* ==================== İŞLER — görsel üretim kuyruğu ====================
 *
 * Kuyruk sunucuda dosya sistemi olarak duruyor ve PC-2'deki hakem onu 20
 * saniyede bir yokluyor. Bu ekran o kuyruğa iş koyar ve hâlini gösterir.
 *
 * 🔴 İki durum birbirine karıştırılmaz:
 *   "iş yok"     kuyruk gerçekten boş
 *   "okunamadı"  sayı yerine null gelir -- sıfır YAZILMAZ
 *
 * Hatırlatma da bir iddia değil: iş beklerken PC-2'nin raporu eskiyse panel
 * bunu söyler ama makinenin KAPALI olduğunu ileri sürmez -- sebebi ağ da
 * olabilir, sahip yanındaki makineye bakıp karar verir.
 */
const IS_ASAMA_ETIKET = { bekleyen: 'SIRADA', calisan: 'ÜRETİLİYOR',
                          biten: 'BİTTİ', hata: 'HATA' };

function isSayiYaz(n) { return (n === null || n === undefined) ? 'okunamadı' : String(n); }

async function loadIsler() {
  const count = qs('islerCount');
  const liste = qs('islerListe');
  const uyari = qs('islerUyari');
  if (!liste) return;
  if (count) count.textContent = 'yükleniyor…';

  const { ok, status, body: d } = await api('/api/isler');
  if (!ok) {
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    liste.innerHTML = '<p class="sect-empty is-bad">İşler şu anda yüklenemedi. Biraz sonra tekrar deneyin.</p>';
    return;
  }

  if (d.durum === 'KUYRUK_YOK') {
    if (count) count.textContent = 'kuyruk yok';
    liste.innerHTML = '<p class="sect-empty is-bad">İş kayıtlarına şu anda erişilemiyor.</p>';
    return;
  }

  const s = d.sayilar || {};
  if (count) count.textContent = isSayiYaz(s.bekleyen) + ' sırada';

  uyari.innerHTML = d.hatirlatma
    ? '<div class="is-uyari"><strong>' + escapeHtml(d.hatirlatma.metin) + '</strong>'
      + '<button type="button" class="btn btn-ince" id="isUyandir">PC-2&#39;Yİ AÇ</button>'
      + '<span id="isUyandirSonuc" class="is-sonuc"></span></div>'
    : '';

  const satirlar = (d.isler || []).map(function (i) {
    const etiket = IS_ASAMA_ETIKET[i.asama] || 'Durum bilinmiyor';
    const metin = i.bozuk
      ? '<em>dosya bozuk — okunamadı</em>'
      : escapeHtml(JarvisMetin.jobTitle(i));
    return '<li class="is-satir-kayit"><span class="is-rozet is-rozet-'
      + escapeHtml(String(i.asama)) + '">' + escapeHtml(etiket) + '</span>'
      + '<span class="is-metin">' + metin + '</span>'
      + '<span class="is-kim">' + escapeHtml(JarvisMetin.source(i)) + '</span></li>';
  });

  liste.innerHTML =
    '<p class="fm-sub">sırada ' + isSayiYaz(s.bekleyen)
    + ' · üretiliyor ' + isSayiYaz(s.calisan)
    + ' · bitti ' + isSayiYaz(s.biten)
    + ' · hata ' + isSayiYaz(s.hata) + '</p>'
    + (satirlar.length
        ? '<ul class="is-liste">' + satirlar.join('') + '</ul>'
        : '<p class="sect-empty">Kuyrukta hiç iş yok.</p>');
}

/* Form ve uyandırma düğmesi olay temsilcisiyle bağlanır: içerik yeniden
 * çizildiğinde dinleyici kaybolmasın. */
document.addEventListener('submit', async function (e) {
  const form = e.target.closest('#isForm');
  if (!form) return;
  e.preventDefault();
  const sonuc = qs('isSonuc');
  sonuc.className = 'is-sonuc';
  sonuc.textContent = 'gönderiliyor…';
  const cevap = await api('/api/isler', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ istem: (qs('isIstem').value || '').trim(),
                           negatif: qs('isNegatif').value || '',
                           adet: Number(qs('isAdet').value || 1) }),
  });
  if (!cevap.ok) {
    /* 400 = doğrulama reddi. Sebebi AYNEN gösterilir; "bir hata oluştu"
     * demek, sahibi aynı hatayı tekrar yapmaya davet eder. */
    sonuc.className = 'is-sonuc is-bad';
    sonuc.textContent = JarvisMetin.errorText(cevap.body?.error, 'İş gönderilemedi. Bilgileri kontrol edip tekrar deneyin.');
    return;
  }
  sonuc.className = 'is-sonuc is-ok';
  sonuc.textContent = 'kuyruğa eklendi';
  qs('isIstem').value = '';
  loadIsler();
});

document.addEventListener('click', async function (e) {
  if (!e.target.closest('#isUyandir')) return;
  const sonuc = qs('isUyandirSonuc');
  sonuc.className = 'is-sonuc';
  sonuc.textContent = 'isteniyor…';
  const cevap = await api('/api/uyandir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hedef: 'pc2' }),
  });
  if (cevap.ok && cevap.body && cevap.body.hazir === false) {
    /* Uzaktan açma DONANIM olarak hazır değil. Düğmeyi "çalıştı" gibi
     * göstermek en kötüsü olurdu: eksik ön koşullar adıyla yazılır. */
    sonuc.className = 'is-sonuc is-bad';
    sonuc.textContent = 'Uzaktan açma hazır değil — '
      + ((cevap.body.eksikler || []).join(' · '));
    return;
  }
  sonuc.textContent = cevap.ok ? 'istek kaydedildi' : 'istek gönderilemedi';
});


/* ==================== MODEL KADEMELERİ (SİSTEM sekmesi içinde) ==========
 *
 * İki ayrı şey gösterilir ve BİRBİRİNİN YERİNE GEÇMEZ:
 *   ŞU AN  canlı sağlık yoklaması -- bu saniyedeki durum
 *   ÖZET   son çağrıların kaydı   -- geçmiş
 * İkisi çelişebilir ve bu bir hata değildir: makine az önce açılmış ya da
 * az önce kapanmış olabilir. Tek satırda birleştirmek, birini diğerinin
 * kanıtı gibi göstermek olurdu.
 */
const KD_DURUM_ETIKET = {
  AVAILABLE: 'HAZIR', UNAVAILABLE: 'KAPALI', DEGRADED: 'ZAYIF',
  RATE_LIMITED: 'KOTA DOLU', BILINMIYOR: 'BİLİNMİYOR',
};
const KD_UC_ADI = { external: 'API (dış sağlayıcı)', gpu: 'PC-2 ekran kartı',
                    local: 'Sunucu CPU', '-': 'zincirin tamamı' };
const KD_SONUC_ETIKET = { BASARILI: 'cevapladı', HATA: 'düştü',
                          ATLANDI: 'hazır değildi', ZINCIR_TUKENDI: 'cevap yok' };

async function loadKademe() {
  const govde = qs('kademeGovde');
  if (!govde) return;
  const { ok, status, body: d } = await api('/api/kademe');
  if (!ok) {
    govde.innerHTML = '<p class="sect-empty is-bad">Model bilgileri şu anda yüklenemedi.</p>';
    return;
  }

  /* ŞU AN */
  const simdi = d.simdi || {};
  let satirlar = '';
  if (simdi.hata) {
    satirlar = '<p class="sect-empty is-bad">Yoklanamadı: '
      + escapeHtml(String(simdi.hata)) + '</p>';
  } else {
    satirlar = '<ul class="kd-liste">' + ['external', 'gpu', 'local'].map(function (uc) {
      const ham = String(simdi[uc] || 'BILINMIYOR');
      const et = KD_DURUM_ETIKET[ham] || ham;
      const sinif = ham === 'AVAILABLE' ? 'kd-hazir'
                  : (ham === 'UNAVAILABLE' ? 'kd-kapali' : 'kd-zayif');
      return '<li class="kd-satir"><span class="kd-uc">'
        + escapeHtml(KD_UC_ADI[uc] || uc) + '</span>'
        + '<span class="kd-rozet ' + sinif + '">' + escapeHtml(et) + '</span></li>';
    }).join('') + '</ul>';
  }

  /* ÖZET */
  const ozet = d.ozet || {};
  let ozetHtml = '';
  if (ozet.hata) {
    ozetHtml = '<p class="sect-empty is-bad">Geçmiş okunamadı: '
      + escapeHtml(String(ozet.hata)) + '</p>';
  } else if (!ozet.toplam) {
    ozetHtml = '<p class="sect-empty">Henüz kayıtlı çağrı yok.</p>';
  } else {
    const gec = ozet.ortalama_gecikme_ms || {};
    const dag = ozet.dagilim || {};
    ozetHtml = '<ul class="kd-liste">' + Object.keys(dag).map(function (uc) {
      const parcalar = Object.keys(dag[uc]).map(function (s) {
        return escapeHtml(KD_SONUC_ETIKET[s] || s) + ' ' + dag[uc][s];
      }).join(' · ');
      const ms = (gec[uc] !== undefined && gec[uc] !== null)
        ? ('<span class="kd-ms">' + gec[uc] + ' ms</span>') : '';
      return '<li class="kd-satir"><span class="kd-uc">'
        + escapeHtml(KD_UC_ADI[uc] || uc) + '</span>'
        + '<span class="kd-dagilim">' + parcalar + '</span>' + ms + '</li>';
    }).join('') + '</ul>'
      + '<p class="fm-sub">son ' + ozet.toplam + ' çağrı</p>';
  }

  govde.innerHTML =
    '<div class="kd-yan"><div class="kd-kutu"><h4 class="kd-alt">ŞU AN</h4>'
    + satirlar + '</div>'
    + '<div class="kd-kutu"><h4 class="kd-alt">SON ÇAĞRILAR</h4>'
    + ozetHtml + '</div></div>';
}


/* ==================== SAHA — ziyaret hedefleri ve rota ==================
 *
 * İki akış tek ekranda:
 *   MASAÜSTÜ  filtrele -> LİSTELE -> seç -> ROTA OLUŞTUR
 *   TELEFON   📍 BURADAN ROTA -> duraklar -> her durakta ziyaret kaydet
 *
 * 🔴 18.845 kayıt tarayıcıya tek seferde YÜKLENMEZ. Her sorgu ya konum
 * yarıçapıyla ya da limitle sınırlıdır; "hepsini getir" diye bir düğme
 * bilerek yok -- olsaydı ilk tıklamada panel donardı.
 *
 * Konum: tarayıcının kendi izni istenir. Telefon kilitlenince tarayıcı
 * konum göndermeyi durdurur; bu "duruyor" demek DEĞİLDİR ve panel de öyle
 * yazmaz.
 */
const SH = {
  hedefler: [], rota: null, secili: new Set(),
  konum: null, izleme: null, filtreler: null,
};

const SH_SONUC = [
  ['GORUSULDU', 'görüşüldü'], ['NUMUNE_BIRAKILDI', 'numune bırakıldı'],
  ['SIPARIS_SOZU', 'sipariş sözü'], ['TEKRAR_GEL', 'tekrar gel'],
  ['YETKILI_YOK', 'yetkili yok'], ['KAPALI', 'kapalı'],
  ['ILGILENMEDI', 'ilgilenmedi'],
];

function shDurum(metin, kotu) {
  const d = qs('shDurum');
  if (!d) return;
  d.className = 'is-sonuc' + (kotu ? ' is-bad' : '');
  d.textContent = metin || '';
}

/* Seçili değerler: artık <select multiple> değil, işaretli kutular.
 * Neden değişti: çoklu seçim kutusunda kaç kayıt olduğu görünmüyordu,
 * seçenekler ham anahtarlarıyla ("PSIKOLOG", "BEBEK") alt alta diziliyordu
 * ve bir branş seçildiğinde o branşta olmayan ilçeler listede duruyordu --
 * kullanıcı boş sonuca ancak tıklayarak varıyordu. */
function shSecilenler(id) {
  const kap = qs(id);
  if (!kap) return [];
  return Array.from(kap.querySelectorAll('input:checked')).map(function (o) {
    return o.value;
  });
}

const SH_FACET = { tur: 'shTur', brans: 'shBrans', ilce: 'shIlce' };

function shSayi(n) {
  return Number(n || 0).toLocaleString('tr-TR');
}

/* Bir facet'i çizer. SIFIR ÇIKAN SEÇENEK LİSTEDEN DÜŞMEZ, sönük görünür ve
 * tıklanamaz. Düşseydi liste her tıklamada zıplar, kullanıcı bir seçeneğin
 * hiç var olmadığını mı yoksa kendi seçimiyle elendiğini mi anlayamazdı. */
function shFacetCiz(alan, secenekler) {
  const kap = qs(SH_FACET[alan]);
  if (!kap) return;
  const secili = new Set(shSecilenler(SH_FACET[alan]));
  const ara = document.querySelector('.sh-facet-ara[data-alan="' + alan + '"]');
  const suzgec = (ara && ara.value.trim().toLocaleLowerCase('tr')) || '';
  const liste = (secenekler || []).filter(function (s) {
    if (!suzgec) return true;
    return String(s.etiket || s.deger).toLocaleLowerCase('tr').indexOf(suzgec) >= 0;
  });
  if (!liste.length) {
    kap.innerHTML = '<p class="sh-facet-bos">eşleşen yok</p>';
    return;
  }
  kap.innerHTML = liste.map(function (s) {
    const sifir = !s.adet && !secili.has(s.deger);
    return '<label class="sh-secim' + (sifir ? ' sh-secim-sifir' : '') + '">'
      + '<input type="checkbox" value="' + escapeHtml(s.deger) + '"'
      + (secili.has(s.deger) ? ' checked' : '') + (sifir ? ' disabled' : '') + '>'
      + '<span class="sh-secim-ad">' + escapeHtml(s.etiket || s.deger) + '</span>'
      + '<span class="sh-secim-adet">' + shSayi(s.adet) + '</span>'
      + '</label>';
  }).join('');
}

/* Sayılar seçime göre yeniden hesaplanır: bir tür seçilince branş ve ilçe
 * sayıları O TÜRÜN içindekini gösterir. Bir facet kendi seçimiyle
 * daraltılmaz -- yoksa seçimi genişletmek imkânsız olurdu. */
async function shFiltreYenile() {
  const p = new URLSearchParams();
  shSecilenler('shTur').forEach(function (v) { p.append('tur', v); });
  shSecilenler('shBrans').forEach(function (v) { p.append('brans', v); });
  shSecilenler('shIlce').forEach(function (v) { p.append('ilce', v); });
  const z = qs('shZiyaret');
  if (z && z.value) p.set('ziyaret', z.value);
  const a = qs('shArama');
  if (a && a.value.trim()) p.set('arama', a.value.trim());
  const el = qs('shEleme');
  if (el && el.value) p.set('eleme', el.value);

  const cevap = await api('/api/saha/filtreler?' + p.toString());
  if (!cevap.ok) {
    shDurum(JarvisMetin.errorText(cevap.body?.error, 'Filtreler şu anda yüklenemedi.'), true);
    return;
  }
  SH.filtreler = cevap.body;
  shFacetCiz('tur', cevap.body.turler);
  shFacetCiz('brans', cevap.body.branslar);
  shFacetCiz('ilce', cevap.body.ilceler);
  const e = qs('shEslesen');
  if (e) {
    e.textContent = shSayi(cevap.body.eslesen) + ' / '
      + shSayi(cevap.body.toplam) + ' hedef';
    e.className = 'sh-eslesen' + (cevap.body.eslesen ? '' : ' sh-eslesen-bos');
  }
  const c = qs('sahaCount');
  if (c) c.textContent = shSayi(cevap.body.toplam) + ' hedef';

  /* İlçesi bilinmeyen kayıt GİZLENMEZ, sayısı yazılır. Kaynak veride
   * ilçe yerine 'Ankara' yazan 575 kayıt ve hiç ilçe yazmayan 2.264 kayıt
   * var; bunlar ilçe seçilince listeden düşer. Sayıyı göstermeseydik
   * kullanıcı "ilçeleri topladığımda toplam çıkmıyor" derdi ve haklı
   * olurdu. */
  const inot = qs('shIlceNot');
  if (inot) {
    inot.textContent = cevap.body.ilcesiz
      ? shSayi(cevap.body.ilcesiz) + ' kaydın ilçesi kaynakta yok — ilçe seçilince düşer'
      : '';
  }
  const eleme = qs('shEleme');
  if (eleme && cevap.body.elenen !== undefined) {
    const ilk = eleme.options[0];
    if (ilk) {
      ilk.textContent = cevap.body.elenen
        ? shSayi(cevap.body.elenen) + ' elenen gizli' : 'elenen yok';
    }
  }

  const nt = qs('shnTur');
  if (nt && !nt.options.length && cevap.body.turler_tanim) {
    nt.innerHTML = Object.keys(cevap.body.turler_tanim).map(function (k) {
      return '<option value="' + escapeHtml(k) + '">'
        + escapeHtml(cevap.body.turler_tanim[k]) + '</option>';
    }).join('');
  }
}

async function loadSaha() {
  await shFiltreYenile();
  if (!SH.hedefler.length) shListele();
}

function shSorguDizesi(konum) {
  const p = new URLSearchParams();
  shSecilenler('shTur').forEach(function (v) { p.append('tur', v); });
  shSecilenler('shBrans').forEach(function (v) { p.append('brans', v); });
  shSecilenler('shIlce').forEach(function (v) { p.append('ilce', v); });
  const z = qs('shZiyaret');
  if (z && z.value) p.set('ziyaret', z.value);
  const a = qs('shArama');
  if (a && a.value.trim()) p.set('arama', a.value.trim());
  const el = qs('shEleme');
  if (el && el.value) p.set('eleme', el.value);
  if (konum) {
    p.set('enlem', konum.enlem); p.set('boylam', konum.boylam);
    p.set('yaricap_m', (qs('shYaricap') || {}).value || 1500);
  }
  p.set('limit', 200);
  return p.toString();
}

async function shListele(konum) {
  shDurum('yükleniyor…');
  const cevap = await api('/api/saha?' + shSorguDizesi(konum));
  if (!cevap.ok) {
    shDurum(JarvisMetin.errorText(cevap.body?.error, 'Liste şu anda yüklenemedi.'), true);
    return;
  }
  SH.hedefler = cevap.body.hedefler || [];
  SH.sonSorguKonum = konum || null;
  SH.rota = null;
  qs('shRotaOzet').innerHTML = '';
  shDurum(shSayi(cevap.body.sayi) + ' hedef' + (cevap.body.sayi >= cevap.body.limit
    ? ' (ilk ' + cevap.body.limit + ' — daralt)' : ''));
  shCiz();
  shHaritaCiz();
}

function shTurAdi(k) {
  const t = SH.filtreler && SH.filtreler.turler_tanim;
  return (t && t[k]) || k || '';
}

function shBransAdi(k) {
  const b = (SH.filtreler && SH.filtreler.branslar) || [];
  for (let i = 0; i < b.length; i += 1) if (b[i].deger === k) return b[i].etiket;
  return k || '';
}

function shCiz() {
  const liste = qs('shListe');
  if (!liste) return;
  const kayitlar = SH.rota ? SH.rota.duraklar : SH.hedefler;
  if (!kayitlar.length) {
    liste.innerHTML = '<p class="sect-empty">Bu filtrede hedef yok.</p>';
    return;
  }
  liste.innerHTML = '<ul class="sh-liste">' + kayitlar.map(function (h, i) {
    const anahtar = escapeHtml(h.hedef_anahtari);
    const secili = SH.secili.has(h.hedef_anahtari) ? ' checked' : '';
    const mesafe = (h.onceki_mesafe_m !== undefined)
      ? ('<span class="sh-m">' + h.onceki_mesafe_m + ' m</span>')
      : (h.mesafe_m != null ? '<span class="sh-m">' + h.mesafe_m + ' m</span>' : '');
    const sira = SH.rota ? '<span class="sh-sira">' + (i + 1) + '</span>' : '';
    const ziyaret = h.ziyaret_sayisi
      ? '<span class="sh-rozet sh-gidildi">' + escapeHtml(h.son_sonuc || 'gidildi') + '</span>'
      : '';
    /* "~" işareti: branş kategoriden ÇIKARILDI, kimse beyan etmedi.
     * Çıkarımı beyan gibi göstermek, sahada yanlış kapıya götürür. */
    const brans = h.brans
      ? (' · ' + escapeHtml(shBransAdi(h.brans))
         + (h.brans_kaynagi && h.brans_kaynagi !== 'BEYAN'
            ? '<span class="sh-cikarim" title="kategoriden çıkarıldı, beyan değil">~</span>'
            : ''))
      : '';
    return '<li class="sh-kayit" data-anahtar="' + anahtar + '">'
      + sira
      + '<input type="checkbox" class="sh-sec" data-anahtar="' + anahtar + '"' + secili + '>'
      + '<span class="sh-orta">'
      +   '<span class="sh-ad">' + escapeHtml(h.ad || '(adsız)') + '</span>'
      +   '<span class="sh-alt">' + escapeHtml(shTurAdi(h.tur)) + brans
      +     (h.ilce ? ' · ' + escapeHtml(h.ilce) : '')
      +     (h.adres ? ' · ' + escapeHtml(String(h.adres).slice(0, 40)) : '')
      +   '</span>'
      + '</span>'
      + '<span class="sh-iletisim">'
      +   (h.telefon ? '<a class="sh-tel" href="tel:' + escapeHtml(h.telefon) + '">'
                     + escapeHtml(h.telefon) + '</a>' : '<span class="sh-yok">telefon yok</span>')
      +   (h.eposta ? '<a class="sh-eposta" href="mailto:' + escapeHtml(h.eposta) + '">'
                    + escapeHtml(h.eposta) + '</a>' : '')
      + '</span>'
      + mesafe + ziyaret
      + (h.hedef_disi_neden
         ? '<span class="sh-rozet sh-elendi" title="elendi">'
           + escapeHtml(h.hedef_disi_neden) + '</span>' : '')
      + '<button type="button" class="btn btn-ince sh-ziyaret" data-anahtar="'
      + anahtar + '">ZİYARET</button>'
      /* Kalıpla yakalanamayan kayıtlar için tek tıkla eleme. Veride
       * 'Ardacan Oto' (otomotiv) ile 'Prof Dr M Ali Oto' (hekim, soyadı
       * Oto) aynı şekilde yazılıyor -- hiçbir desen bu ikisini ayıramaz,
       * bakan insan ayırır. */
      + '<button type="button" class="btn btn-ince sh-disla" data-anahtar="'
      + anahtar + '" data-ad="' + escapeHtml(h.ad || '')
      + '">' + (h.hedef_disi_neden ? 'HEDEFTİR' : 'HEDEF DEĞİL') + '</button>'
      + (SH.rota ? '<button type="button" class="btn btn-ince sh-cikar" data-anahtar="'
                 + anahtar + '">ÇIKAR</button>' : '')
      + '</li>';
  }).join('') + '</ul>';
}

async function shRotaKur(konum) {
  shDurum('rota hesaplanıyor…');
  const govde = {
    enlem: konum.enlem, boylam: konum.boylam,
    yaricap_m: Number((qs('shYaricap') || {}).value || 1500),
    en_fazla_durak: Number((qs('shDurak') || {}).value || 20),
    tur: shSecilenler('shTur'), brans: shSecilenler('shBrans'),
    ziyaret: (qs('shZiyaret') || {}).value || null,
  };
  const { ok, status, body } = await api('/api/saha/rota', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(govde),
  });
  if (!ok) { shDurum('Rota oluşturulamadı. Biraz sonra tekrar deneyin.', true); return; }
  if (body.durum === 'HEDEF_YOK') {
    shDurum('bu yarıçapta hedef yok — yarıçapı büyüt', true);
    return;
  }
  SH.rota = body;
  /* Kopya ayıklama ve 2-opt kazancı AYNEN yazılır: "en iyi rota" demek
   * ispatlanmamış bir iddia olurdu, "şu kadar kısalttı" ölçülebilir. */
  qs('shRotaOzet').innerHTML =
    '<div class="sh-ozet"><strong>' + body.duraklar.length + ' durak · '
    + (body.toplam_m / 1000).toFixed(2) + ' km</strong>'
    + ' · aday ' + body.aday_sayisi
    + (body.kopya_ayiklanan ? ' · ' + body.kopya_ayiklanan + ' kopya ayıklandı' : '')
    + (body.iyilesme_m > 0 ? ' · sıralama ' + Math.round(body.iyilesme_m) + ' m kısalttı' : '')
    + ' <span class="sh-not">kuş uçuşu mesafe — gerçek yürüyüş değil</span></div>';
  shDurum('');
  shCiz();
}

/* ---------- olaylar (temsilci: içerik yeniden çizilince kaybolmasın) ---------- */
document.addEventListener('click', async function (e) {
  if (e.target.closest('#shListele')) { shListele(SH.konum); return; }

  if (e.target.closest('#shBuradan')) {
    shDurum('konum alınıyor…');
    const k = await shKonumAl();
    if (!k) { shDurum('konum alınamadı — tarayıcı izni gerekli', true); return; }
    SH.konum = k;
    shKonumBildir(k);
    shRotaKur(k);
    return;
  }

  if (e.target.closest('#shNoktaAc')) {
    const f = qs('shNoktaForm');
    f.hidden = !f.hidden;
    if (!f.hidden) {
      const k = await shKonumAl();
      qs('shnKonum').textContent = k
        ? ('konum alındı (±' + Math.round(k.dogruluk_m) + ' m)')
        : 'konum alınamadı — kayıt konumsuz eklenemez';
      f.dataset.konum = k ? JSON.stringify(k) : '';
    }
    return;
  }
  if (e.target.closest('#shnVazgec')) { qs('shNoktaForm').hidden = true; return; }

  const cikar = e.target.closest('.sh-cikar');
  if (cikar && SH.rota) {
    /* Duraktan elleme: rota yeniden hesaplanmaz, yalnız o durak düşer.
     * Yeniden hesaplasaydık sıra değişir ve kullanıcının zihnindeki plan
     * bozulurdu. */
    const a = cikar.dataset.anahtar;
    SH.rota.duraklar = SH.rota.duraklar.filter(function (d) {
      return d.hedef_anahtari !== a;
    });
    shCiz();
    return;
  }

  const sec = e.target.closest('.sh-sec');
  if (sec) {
    if (sec.checked) SH.secili.add(sec.dataset.anahtar);
    else SH.secili.delete(sec.dataset.anahtar);
    return;
  }

  const ziy = e.target.closest('.sh-ziyaret');
  if (ziy) { shZiyaretAc(ziy.dataset.anahtar); return; }
});

/* ---------- ziyaret formu ---------- */
function shZiyaretAc(anahtar) {
  const kayit = (SH.rota ? SH.rota.duraklar : SH.hedefler)
    .find(function (h) { return h.hedef_anahtari === anahtar; });
  const satir = document.querySelector('.sh-kayit[data-anahtar="' + anahtar + '"]');
  if (!satir) return;
  const varOlan = satir.querySelector('.sh-zform');
  if (varOlan) { varOlan.remove(); return; }

  const form = document.createElement('form');
  form.className = 'sh-zform';
  form.dataset.anahtar = anahtar;
  form.innerHTML =
    '<div class="sh-zbaslik">' + escapeHtml((kayit && kayit.ad) || '') + '</div>'
    + '<label class="is-label">SONUÇ</label>'
    + '<select class="is-input sh-zsonuc">'
    + SH_SONUC.map(function (s) {
        return '<option value="' + s[0] + '">' + s[1] + '</option>';
      }).join('') + '</select>'
    + '<label class="is-label">NOT</label>'
    + '<textarea class="is-input sh-znot" rows="2" maxlength="4000" '
    + 'placeholder="görüşmede ne konuşuldu"></textarea>'
    + '<label class="is-label">FOTOĞRAF (isteğe bağlı)</label>'
    + '<input type="file" class="is-input sh-zfoto" accept="image/jpeg,image/png" capture="environment">'
    + '<div class="is-satir"><button type="submit" class="btn">KAYDET</button>'
    + '<span class="is-sonuc sh-zsonucmetin"></span></div>';
  satir.appendChild(form);
}

/* Fotoğraf telefondan 4-8 MB gelebilir; sunucu tavanı 4 MB. Tarayıcıda
 * küçültmek, yüklemeyi hem hızlandırır hem tavana takılmayı önler. */
function shFotoKucult(dosya, enBuyukKenar) {
  return new Promise(function (coz, red) {
    const okuyucu = new FileReader();
    okuyucu.onerror = function () { red(new Error('dosya okunamadı')); };
    okuyucu.onload = function () {
      const img = new Image();
      img.onerror = function () { red(new Error('görsel çözülemedi')); };
      img.onload = function () {
        const oran = Math.min(1, enBuyukKenar / Math.max(img.width, img.height));
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * oran);
        c.height = Math.round(img.height * oran);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        coz(c.toDataURL('image/jpeg', 0.82));
      };
      img.src = okuyucu.result;
    };
    okuyucu.readAsDataURL(dosya);
  });
}

document.addEventListener('submit', async function (e) {
  const zform = e.target.closest('.sh-zform');
  if (zform) {
    e.preventDefault();
    const sonucAlani = zform.querySelector('.sh-zsonucmetin');
    sonucAlani.className = 'is-sonuc sh-zsonucmetin';
    sonucAlani.textContent = 'kaydediliyor…';
    let foto = '';
    const dosya = zform.querySelector('.sh-zfoto').files[0];
    if (dosya) {
      try { foto = await shFotoKucult(dosya, 1600); }
      catch (hata) {
        sonucAlani.className = 'is-sonuc is-bad';
        sonucAlani.textContent = 'fotoğraf işlenemedi: ' + hata.message;
        return;
      }
    }
    const k = await shKonumAl(8000);
    const cevap = await api('/api/saha/ziyaret', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hedef_anahtari: zform.dataset.anahtar,
        sonuc: zform.querySelector('.sh-zsonuc').value,
        not: zform.querySelector('.sh-znot').value,
        foto: foto,
        enlem: k ? k.enlem : null, boylam: k ? k.boylam : null,
        konum_dogruluk_m: k ? k.dogruluk_m : null,
      }),
    });
    if (!cevap.ok) {
      sonucAlani.className = 'is-sonuc is-bad';
      sonucAlani.textContent = JarvisMetin.errorText(cevap.body?.error, 'Kayıt tamamlanamadı. Bilgileri kontrol edin.');
      return;
    }
    sonucAlani.className = 'is-sonuc is-ok';
    sonucAlani.textContent = 'kaydedildi' + (k ? '' : ' (konumsuz)');
    setTimeout(function () { zform.remove(); }, 1200);
    return;
  }

  const nform = e.target.closest('#shNoktaForm');
  if (nform) {
    e.preventDefault();
    const konum = nform.dataset.konum ? JSON.parse(nform.dataset.konum) : null;
    if (!konum) { shDurum('konum olmadan nokta eklenemez', true); return; }
    const cevap = await api('/api/saha/nokta', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ad: qs('shnAd').value, tur: qs('shnTur').value,
        telefon: qs('shnTel').value, eposta: qs('shnEposta').value,
        enlem: konum.enlem, boylam: konum.boylam,
        konum_kaynagi: 'GPS', konum_dogruluk_m: konum.dogruluk_m,
      }),
    });
    if (!cevap.ok) {
      shDurum((cevap.body && cevap.body.error) || 'nokta eklenemedi', true);
      return;
    }
    shDurum('nokta eklendi: ' + (cevap.body.ad || ''));
    nform.hidden = true;
    qs('shnAd').value = ''; qs('shnTel').value = ''; qs('shnEposta').value = '';
    shListele(SH.konum);
  }
});

/* ---------- konum bildirimi ----------
 * Panel açıkken periyodik gönderilir. Telefon kilitlenince tarayıcı bunu
 * durdurur; "bayat" kayıt kişinin durduğunu KANITLAMAZ ve panel de öyle
 * yazmaz (bkz. /api/saha/konum cevabındaki uyarı). */
function shKonumBildir(k) {
  if (!k) return;
  api('/api/saha/konum', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enlem: k.enlem, boylam: k.boylam,
                           dogruluk_m: k.dogruluk_m, kaynak: 'TARAYICI' }),
  });
}

setInterval(function () {
  if (state.view !== 'saha' || document.hidden) return;
  shKonumAl(9000).then(function (k) {
    if (k) { SH.konum = k; shKonumBildir(k); }
  });
}, 120000);


/* ==================== SAHA HARİTASI ====================================
 *
 * Karolar /karo/{z}/{x}/{y}.png üzerinden KENDİ SUNUCUMUZDAN gelir.
 * Tarayıcı dış bir sunucuyla hiç konuşmaz: içerik güvenliği ilkesi
 * (img-src 'self') olduğu gibi kalır ve saha elemanının haritada nereye
 * baktığı üçüncü tarafa gitmez. Sunucu indirdiği karoyu diske yazar,
 * ikinci kez indirmez.
 *
 * 🔴 HARİTA VARSAYILAN OLARAK KAPALI. Açılışta kurulsaydı, listeyi
 * kullanmak isteyen herkes için onlarca karo indirilirdi -- sahada mobil
 * veri bedava değil. Düğmeye basılınca kurulur.
 */
const SH_HARITA = { harita: null, katman: null, rota: null, secKonum: null };

const SH_TUR_RENK = {
  ECZANE: '#2e9e6b', HUZUREVI: '#c2572f', KLINIK: '#3f7bd1',
  DOKTOR: '#3f7bd1', HASTANE: '#2b5fa8', DIS: '#5aa9c9',
  GUZELLIK: '#b3559b', KUAFOR: '#b3559b', SPOR: '#7a57c4',
  OTEL: '#8a8f98', KRES: '#d2a13a', PSIKOLOG: '#6f8fb0',
  OPTIK: '#4f9c9c', DIYETISYEN: '#79a343', BEBEK: '#d98cb3',
  AYAK: '#9c7a4f',
};

function shHaritaKur() {
  if (SH_HARITA.harita) return SH_HARITA.harita;
  const el = qs('shHarita');
  if (!el || typeof L === 'undefined') return null;
  const m = L.map(el, { zoomControl: true, attributionControl: true })
    .setView([39.925, 32.866], 12);
  L.tileLayer('/karo/{z}/{x}/{y}.png', {
    minZoom: 10, maxZoom: 18,
    attribution: 'Karo verisi &copy; OpenStreetMap katkıcıları (ODbL)',
  }).addTo(m);
  SH_HARITA.katman = L.layerGroup().addTo(m);
  SH_HARITA.harita = m;
  /* Haritaya tıklayınca "yeni nokta" formu açıksa koordinat oraya düşer.
   * Telefonda GPS çalışmadığında (bodrum, kapalı otopark) tek yol bu. */
  m.on('click', function (olay) {
    const form = qs('shNoktaForm');
    if (!form || form.hidden) return;
    SH_HARITA.secKonum = {
      enlem: olay.latlng.lat, boylam: olay.latlng.lng, dogruluk_m: null,
    };
    form.dataset.konum = JSON.stringify(SH_HARITA.secKonum);
    form.dataset.kaynak = 'HARITA';
    const n = qs('shnKonum');
    if (n) {
      n.className = 'is-sonuc is-ok';
      n.textContent = 'haritadan seçildi: '
        + olay.latlng.lat.toFixed(5) + ', ' + olay.latlng.lng.toFixed(5);
    }
    shHaritaCiz();
  });
  return m;
}

function shHaritaCiz() {
  const m = SH_HARITA.harita;
  if (!m || !SH_HARITA.katman) return;
  SH_HARITA.katman.clearLayers();
  const kayitlar = SH.rota ? SH.rota.duraklar : SH.hedefler;
  const noktalar = [];

  kayitlar.forEach(function (h, i) {
    if (h.enlem == null || h.boylam == null) return;
    const yer = [h.enlem, h.boylam];
    noktalar.push(yer);
    if (SH.rota) {
      /* Rotada sıra numarası GÖRÜNMELİ: saha elemanı hangi duraktan
       * sonra hangisine gideceğini haritadan okur. */
      L.marker(yer, {
        icon: L.divIcon({
          className: 'sh-pin', html: String(i + 1),
          iconSize: [26, 26], iconAnchor: [13, 13],
        }),
      }).addTo(SH_HARITA.katman).bindPopup(shHaritaBalon(h));
    } else {
      L.circleMarker(yer, {
        radius: 6, weight: 2, opacity: 0.95, fillOpacity: 0.65,
        color: h.ziyaret_sayisi ? '#8a8f98' : (SH_TUR_RENK[h.tur] || '#3f7bd1'),
        fillColor: h.ziyaret_sayisi ? '#8a8f98' : (SH_TUR_RENK[h.tur] || '#3f7bd1'),
      }).addTo(SH_HARITA.katman).bindPopup(shHaritaBalon(h));
    }
  });

  if (SH.rota && SH.rota.baslangic) {
    const b = [SH.rota.baslangic.enlem, SH.rota.baslangic.boylam];
    noktalar.unshift(b);
    L.marker(b, {
      icon: L.divIcon({ className: 'sh-pin sh-pin-bas', html: '▶',
                        iconSize: [26, 26], iconAnchor: [13, 13] }),
    }).addTo(SH_HARITA.katman).bindPopup('Başlangıç');
    /* 🔴 ÇİZGİ KUŞ UÇUŞU. Gerçek yürüyüş güzergâhı DEĞİL; yalnız hangi
     * duraktan hangisine gidildiğini gösterir. Yol çizgisi çizseydik
     * ölçmediğimiz bir şeyi ölçmüş gibi gösterirdik. */
    L.polyline(noktalar, { color: '#c2572f', weight: 2.5, opacity: 0.8,
                           dashArray: '6 5' }).addTo(SH_HARITA.katman);
  }

  if (SH_HARITA.secKonum) {
    L.circleMarker([SH_HARITA.secKonum.enlem, SH_HARITA.secKonum.boylam], {
      radius: 9, weight: 3, color: '#d2a13a', fillOpacity: 0.25,
    }).addTo(SH_HARITA.katman).bindPopup('Yeni nokta buraya eklenecek');
  }

  if (noktalar.length) {
    m.fitBounds(L.latLngBounds(noktalar).pad(0.12), { maxZoom: 16 });
  }
}

function shHaritaBalon(h) {
  const parcalar = ['<strong>' + escapeHtml(h.ad || '(adsız)') + '</strong>',
    '<span class="sh-balon-alt">' + escapeHtml(shTurAdi(h.tur))
      + (h.brans ? ' · ' + escapeHtml(shBransAdi(h.brans)) : '')
      + (h.ilce ? ' · ' + escapeHtml(h.ilce) : '') + '</span>'];
  if (h.adres) parcalar.push('<span class="sh-balon-alt">' + escapeHtml(h.adres) + '</span>');
  parcalar.push(h.telefon
    ? '<a href="tel:' + escapeHtml(h.telefon) + '">' + escapeHtml(h.telefon) + '</a>'
    : '<span class="sh-yok">telefon yok</span>');
  if (h.ziyaret_sayisi) {
    parcalar.push('<span class="sh-rozet sh-gidildi">'
      + escapeHtml(h.son_sonuc || 'gidildi') + '</span>');
  }
  parcalar.push('<button type="button" class="btn btn-ince sh-ziyaret" data-anahtar="'
    + escapeHtml(h.hedef_anahtari) + '">ZİYARET KAYDET</button>');
  return '<div class="sh-balon">' + parcalar.join('<br>') + '</div>';
}

function shHaritaGoster() {
  const sar = qs('shHaritaSar');
  const dugme = qs('shHaritaAc');
  const tara = qs('shAlanTara');
  if (!sar) return;
  const acilacak = sar.hidden;
  sar.hidden = !acilacak;
  if (tara) tara.hidden = !acilacak;
  if (dugme) dugme.textContent = acilacak ? '🗺 HARİTAYI KAPAT' : '🗺 HARİTA';
  if (!acilacak) return;
  const m = shHaritaKur();
  if (!m) { shDurum('harita yüklenemedi', true); return; }
  /* Kap yeni görünür oldu; Leaflet boyutu yeniden ölçmeli yoksa karolar
   * yarım kalır. */
  setTimeout(function () { m.invalidateSize(); shHaritaCiz(); }, 60);
}

/* Haritada görünen alanı tara: merkez + köşeye olan uzaklık yarıçap olur. */
function shAlaniTara() {
  const m = SH_HARITA.harita;
  if (!m) return;
  const merkez = m.getCenter();
  const yaricap = Math.round(Math.min(20000, Math.max(100,
    merkez.distanceTo(m.getBounds().getNorthEast()))));
  const y = qs('shYaricap');
  if (y) y.value = yaricap;
  shListele({ enlem: merkez.lat, boylam: merkez.lng });
}

/* ---------- filtre olayları ----------
 * Her tıklamada sunucuya gitmek yerine kısa bir bekleme: kullanıcı üç
 * kutuyu peş peşe işaretlerse tek sorgu gider. */
let shFiltreZaman = null;
function shFiltreGecikmeli(msn) {
  clearTimeout(shFiltreZaman);
  shFiltreZaman = setTimeout(function () {
    shFiltreYenile();
    shListele(SH.sonSorguKonum || null);
  }, msn || 260);
}

document.addEventListener('change', function (e) {
  const kutu = e.target.closest('.sh-facet-liste input[type="checkbox"]');
  if (kutu) { shFiltreGecikmeli(); return; }
  if (e.target.id === 'shZiyaret' || e.target.id === 'shEleme') {
    shFiltreGecikmeli(0);
  }
});

document.addEventListener('input', function (e) {
  if (e.target.id === 'shArama') { shFiltreGecikmeli(420); return; }
  const ara = e.target.closest('.sh-facet-ara');
  if (ara && SH.filtreler) {
    /* Facet içi arama SUNUCUYA GİTMEZ: zaten elimizdeki seçenekleri süzer.
     * Gitseydi her harfte bir sorgu olurdu ve sayılar değişmezdi. */
    const alan = ara.dataset.alan;
    const kaynak = { tur: 'turler', brans: 'branslar', ilce: 'ilceler' }[alan];
    shFacetCiz(alan, SH.filtreler[kaynak]);
  }
});

document.addEventListener('click', function (e) {
  const temizle = e.target.closest('.sh-facet-temizle');
  if (temizle) {
    const kap = qs(SH_FACET[temizle.dataset.alan]);
    if (kap) {
      kap.querySelectorAll('input:checked').forEach(function (i) { i.checked = false; });
    }
    shFiltreGecikmeli(0);
    return;
  }
  if (e.target.closest('#shSifirla')) {
    Object.keys(SH_FACET).forEach(function (alan) {
      const kap = qs(SH_FACET[alan]);
      if (kap) kap.querySelectorAll('input:checked').forEach(function (i) { i.checked = false; });
    });
    document.querySelectorAll('.sh-facet-ara').forEach(function (i) { i.value = ''; });
    const a = qs('shArama'); if (a) a.value = '';
    const z = qs('shZiyaret'); if (z) z.value = '';
    SH.konum = null;
    shFiltreGecikmeli(0);
    return;
  }
  const disla = e.target.closest('.sh-disla');
  if (disla) { shDisla(disla); return; }
  if (e.target.closest('#shHaritaAc')) { shHaritaGoster(); return; }
  if (e.target.closest('#shAlanTara')) { shAlaniTara(); return; }
});


/* Bir kaydı hedef listesinden çıkar ya da geri al.
 *
 * 🔴 SİLMEZ. core.saha_bilgi'ye insan beyanı yazar; kayıt duruyor, yalnız
 * işaretli. Silseydik yanlış elediğimizi bir daha göremez, aylık tarama da
 * onu yeniden getirirdi. Beyan deseni YENER: "hedeftir" dendiyse otomatik
 * kalıp onu geri eleyemez. */
async function shDisla(dugme) {
  const anahtar = dugme.dataset.anahtar;
  const geriAl = dugme.textContent.trim() === 'HEDEFTİR';
  dugme.disabled = true;
  const cevap = await api('/api/saha/bilgi', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hedef_anahtari: anahtar, hedef_disi: !geriAl }),
  });
  dugme.disabled = false;
  if (!cevap.ok) {
    shDurum((cevap.body && cevap.body.error) || 'işaretlenemedi', true);
    return;
  }
  shDurum((geriAl ? 'hedefe geri alındı: ' : 'hedef dışı: ')
    + (dugme.dataset.ad || ''));
  shFiltreYenile();
  shListele(SH.sonSorguKonum || null);
}


/* ==================== KATALOG — eczane/profesyonel sunumu ================
 *
 * Katalog metni BU DOSYADA YAZILMAZ. Sunucu `state/katalog.json`ı servis
 * eder; o dosyayı `scripts/katalog-uret.py` yayındaki Wix metninden
 * türetip mevzuat denetçisinden geçirir. Panelde gördüğün her cümle hem
 * sitede duruyor hem denetimden temiz geçmiş.
 *
 * 🔴 İÇERİK LİSTESİ İKİ AYRI ŞEYDİR ve ayrı etiketlenir: INCI
 * (uluslararası ad, Latince) ve Türkçe içindekiler. Kaynakta 29 üründe
 * INCI, 26'sında Türkçe liste var; yedi üründe İngilizce INCI YOK ve
 * katalog bunu "kaynakta yok" diye YAZAR. Eczacının ilk sorusu içeriktir;
 * bilmediğimizi bilmek, bildiğimizi sanmaktan iyidir.
 *
 * 🔴 BAYİ FİYATI GİRİLMEDİYSE "—" GÖRÜNÜR. Uydurulmuş bir toptan fiyat,
 * sahada verilmiş yanlış bir sözdür.
 */
const KAT = { veri: null, acik: null, hedef: null, hedefAd: '' };

function katDurum(metin, kotu) {
  const d = qs('katDurum');
  if (!d) return;
  d.className = 'is-sonuc' + (kotu ? ' is-bad' : '');
  d.textContent = metin || '';
}

async function loadKatalog() {
  if (KAT.veri) { katCiz(); return; }
  katDurum('yükleniyor…');
  const cevap = await api('/api/katalog');
  if (!cevap.ok) {
    katDurum(JarvisMetin.errorText(cevap.body?.error, 'Katalog şu anda yüklenemedi.'), true);
    return;
  }
  KAT.veri = cevap.body;
  katDurum('');
  katCiz();
}

/* SAHA ekranından bir hedef seçilmişse notlar o eczaneye bağlanır.
 * Bağlanmazsa not "ürün hakkında genel not" olur -- ikisi ayrı şeydir ve
 * karıştırılırsa hangi eczanenin ne dediği kaybolur. */
function katHedefBagla(anahtar, ad) {
  KAT.hedef = anahtar || null;
  KAT.hedefAd = ad || '';
  const e = qs('katHedefEtiket');
  if (e) {
    e.textContent = KAT.hedef ? ('notlar → ' + KAT.hedefAd) : '';
    e.className = 'kat-hedef' + (KAT.hedef ? ' kat-hedef-var' : '');
  }
}

function katSirali() {
  const u = ((KAT.veri && KAT.veri.urunler) || []).slice();
  const ara = ((qs('katArama') || {}).value || '').trim().toLocaleLowerCase('tr');
  const yalnizEksik = (qs('katEksik') || {}).checked;
  const sirala = (qs('katSirala') || {}).value || 'ad';
  return u.filter(function (p) {
    if (yalnizEksik && p.inci && p.icindekiler && p.bayi_fiyat) return false;
    if (!ara) return true;
    return (p.ad || '').toLocaleLowerCase('tr').indexOf(ara) >= 0
        || (p.slug || '').indexOf(ara) >= 0;
  }).sort(function (a, b) {
    if (sirala === 'fiyat') return (b.fiyat || 0) - (a.fiyat || 0);
    if (sirala === 'ilgi') {
      return ((b.ilgi && b.ilgi.ilgili) || 0) - ((a.ilgi && a.ilgi.ilgili) || 0);
    }
    return (a.ad || '').localeCompare(b.ad || '', 'tr');
  });
}

function katPara(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('tr-TR', { maximumFractionDigits: 0 }) + ' TL';
}

function katCiz() {
  const kap = qs('katListe');
  if (!kap || !KAT.veri) return;
  const liste = katSirali();
  const c = qs('katCount');
  if (c) {
    c.textContent = liste.length + ' / ' + KAT.veri.urun_sayisi + ' ürün';
  }

  /* Eksikler ekranın tepesinde YAZAR. Gizlenseydi katalog tam görünür ve
   * eczacının sorduğu ilk soruda boşluk sahada ortaya çıkardı. */
  /* Kampanya koşulları fiyatın yanında konuşulur: '70.000 TL üzeri
   * stand desteği' demek, fiyat kırmadan değer katar. */
  katPdfCiz();

  const kamp = qs('katKampanya');
  if (kamp) {
    const liste = KAT.veri.kampanyalar || [];
    kamp.innerHTML = liste.length
      ? '<h4>Kampanyalar</h4><ul>' + liste.map(function (x) {
          return '<li>' + escapeHtml(x.baslik) + '</li>';
        }).join('') + '</ul>'
      : '';
    kamp.hidden = !liste.length;
  }

  const u = qs('katUyari');
  if (u) {
    const k = KAT.veri.kapsama || {};
    const n = KAT.veri.urun_sayisi;
    const eksik = [];
    if (k.inci_var < n) eksik.push((n - k.inci_var) + ' üründe INCI (uluslararası ad) kaynakta yok');
    if (!KAT.veri.bayi_fiyati_girilen) eksik.push('bayi fiyatı hiçbir üründe girilmedi');
    else if (KAT.veri.bayi_fiyati_girilen < n) {
      eksik.push((n - KAT.veri.bayi_fiyati_girilen) + ' üründe bayi fiyatı yok');
    }
    if (KAT.veri.bayi_celiskili) {
      eksik.push(KAT.veri.bayi_celiskili
        + ' üründe fiyat listesi kendi hesabını tutmuyor — teyit gerekiyor');
    }
    /* Barkod şüphesi AYRI uyarı: fiyatı gizlemez, deposu ilgilendirir. */
    if (KAT.veri.bayi_barkod_supheli) {
      eksik.push(KAT.veri.bayi_barkod_supheli
        + ' üründe barkod teyide muhtaç (fiyatlar geçerli)');
    }
    const cakisan = Object.keys(KAT.veri.barkod_cakismasi || {});
    if (cakisan.length) {
      eksik.push('aynı barkodu taşıyan ürün: '
        + cakisan.map(function (b) {
            return KAT.veri.barkod_cakismasi[b].join(' + ');
          }).join(' · '));
    }
    u.hidden = !eksik.length;
    u.textContent = eksik.length ? ('⚠ ' + eksik.join(' · ')) : '';
  }

  if (!liste.length) {
    kap.innerHTML = '<p class="sect-empty">Bu aramada ürün yok.</p>';
    return;
  }
  kap.innerHTML = liste.map(katKart).join('');
}

function katKart(p) {
  const acik = KAT.acik === p.slug;
  const gorsel = p.gorseller && p.gorseller.length
    ? '<img class="kat-gorsel" src="/katalog-gorsel/' + escapeHtml(p.gorseller[0])
      + '" alt="' + escapeHtml(p.ad) + '" loading="lazy">'
    : '<span class="kat-gorsel kat-gorsel-yok">görsel yok</span>';
  const ilgi = p.ilgi && p.ilgi.ilgili
    ? '<span class="kat-rozet">' + p.ilgi.ilgili + ' ilgi</span>' : '';
  const siparis = p.ilgi && p.ilgi.siparis_sozu
    ? '<span class="kat-rozet kat-rozet-iyi">' + p.ilgi.siparis_sozu + ' sipariş sözü</span>' : '';

  return '<article class="kat-kart' + (acik ? ' kat-kart-acik' : '')
    + '" data-slug="' + escapeHtml(p.slug) + '">'
    + '<button type="button" class="kat-bas" data-slug="' + escapeHtml(p.slug) + '">'
    +   gorsel
    +   '<span class="kat-bas-orta">'
    +     '<span class="kat-ad">' + escapeHtml(p.ad) + '</span>'
    +     '<span class="kat-ozet">' + escapeHtml((p.ozet || '').slice(0, 150)) + '</span>'
    +     '<span class="kat-etiketler">' + ilgi + siparis + '</span>'
    +   '</span>'
    +   '<span class="kat-fiyatlar">'
    +     '<span class="kat-fiyat">' + katPara(p.fiyat) + '</span>'
    +     '<span class="kat-fiyat-alt">tavsiye edilen satış</span>'
    +     katBayiOzet(p)
    +   '</span>'
    + '</button>'
    + (acik ? katDetay(p) : '')
    + '</article>';
}

/* Bayi fiyatı kart üstünde ÖZET, detayda KADEMELİ.
 *
 * 🔴 FİYAT ÇELİŞKİSİ OLAN SATIRDA FİYAT YAZILMAZ. Sahada yanlış fiyat
 * vermek, fiyat verememekten pahalıdır: ilki verilmiş bir sözdür,
 * ikincisi bir telefon görüşmesi.
 *
 * Barkod şüphesi bundan AYRI tutulur ve fiyatı GİZLEMEZ. Önce tek
 * bayrak iki işi birden görüyordu; OPTYWAVE'in fiyatları doğru olduğu
 * hâlde barkod belirsizliği yüzünden sahada fiyat söylenemiyordu. */
function katBayiOzet(p) {
  const b = p.bayi;
  if (!b) {
    return '<span class="kat-fiyat-bayi kat-fiyat-yok">bayi fiyatı yok</span>';
  }
  if (b.celiskili) {
    return '<span class="kat-fiyat-bayi kat-fiyat-teyit">teyit gerekiyor</span>';
  }
  return '<span class="kat-fiyat-bayi">%40: ' + katPara(b.isk40_dahil) + '</span>';
}

function katBayiTablosu(p) {
  const b = p.bayi;
  if (!b) {
    return '<div class="kat-bolum kat-bolum-uyari"><h4>Bayi fiyatı</h4>'
      + '<p class="kat-yok">Fiyat listesinde yok — sahada fiyat verilemez.</p>'
      + '</div>';
  }
  if (b.celiskili) {
    return '<div class="kat-bolum kat-bolum-uyari">'
      + '<h4>Bayi fiyatı — TEYİT GEREKİYOR</h4>'
      + '<p>' + escapeHtml(b.celiski_notu || '') + '</p>'
      + '<p class="kat-not-kucuk">Bu üründe iskontolu fiyat gösterilmiyor. '
      + 'Liste düzeltilene kadar fiyatı merkeze sorarak ver.</p></div>';
  }
  const satir = function (etiket, deger) {
    return '<tr><td>' + escapeHtml(etiket) + '</td><td>'
      + katPara(deger) + '</td></tr>';
  };
  return '<div class="kat-bolum"><h4>Bayi fiyatı</h4>'
    + '<table class="kat-fiyat-tablo"><tbody>'
    + satir('Tavsiye edilen satış (PSF)', b.psf)
    + satir('%30 iskonto · KDV hariç', b.isk30_haric)
    + satir('%30 iskonto · KDV dahil', b.isk30_dahil)
    + satir('%40 iskonto · KDV hariç', b.isk40_haric)
    + satir('%40 iskonto · KDV dahil', b.isk40_dahil)
    + satir('Trendyol satış', b.trendyol)
    + '</tbody></table>'
    /* "Bu fiyat kesin mi?" sahada sorulan bir sorudur; cevabı olsun. */
    + (b.psf_kaynagi
        ? '<p class="kat-not-kucuk">PSF kaynağı: '
          + escapeHtml(b.psf_kaynagi)
          + ' · kademeler %30 / %40 iskonto ve KDV ile hesaplandı</p>'
        : '')
    + '</div>'
    + katBarkodUyarisi(b);
}

/* Barkod şüphesi: fiyatın yanında değil, ALTINDA ve ayrı bir kutuda.
 * Depoyu ve etiketi ilgilendirir; sahada söylenecek fiyatı değil. */
function katBarkodUyarisi(b) {
  if (!b || !b.barkod_celiskili) return '';
  return '<div class="kat-bolum kat-bolum-uyari">'
    + '<h4>Barkod teyide muhtaç</h4>'
    + '<p>' + escapeHtml(b.barkod_notu || '') + '</p>'
    + '<p class="kat-not-kucuk">Fiyatlar geçerlidir. Teyit, sevkiyat ve '
    + 'etiket içindir.</p></div>';
}

function katBolum(baslik, govde, sinif) {
  if (!govde) return '';
  return '<div class="kat-bolum' + (sinif ? ' ' + sinif : '') + '">'
    + '<h4>' + escapeHtml(baslik) + '</h4>'
    + '<p>' + escapeHtml(govde) + '</p></div>';
}

function katDetay(p) {
  const galeri = (p.gorseller || []).slice(0, 6).map(function (g) {
    return '<img class="kat-kucuk" src="/katalog-gorsel/' + escapeHtml(g)
      + '" alt="" loading="lazy">';
  }).join('');

  const cumleler = (p.satis_cumleleri || []).length
    ? '<div class="kat-bolum"><h4>Sunumda söylenebilir</h4><ul class="kat-cumleler">'
      + p.satis_cumleleri.map(function (c) {
          return '<li>' + escapeHtml(c) + '</li>';
        }).join('') + '</ul>'
      + '<p class="kat-not-kucuk">Bu cümleler yayındaki ürün metninden alındı '
      + 've mevzuat denetiminden temiz geçti — olduğu gibi söylenebilir.</p></div>'
    : '<div class="kat-bolum"><h4>Sunumda söylenebilir</h4>'
      + '<p class="kat-yok">Denetimden temiz geçen cümle çıkmadı.</p></div>';

  const uyarilar = (p.zorunlu_uyarilar || []).length
    ? '<div class="kat-bolum kat-bolum-uyari"><h4>Zorunlu uyarılar (silinmez)</h4>'
      + '<ul class="kat-cumleler">'
      + p.zorunlu_uyarilar.map(function (c) {
          return '<li>' + escapeHtml(c) + '</li>';
        }).join('') + '</ul></div>'
    : '';

  /* INCI yoksa "yok" YAZAR. Boş bırakılsaydı eczacı listeyi görmediğini
   * değil, ürünün içeriğinin olmadığını sanabilirdi. */
  const inci = p.inci
    ? katBolum('INCI (uluslararası ad)', p.inci, 'kat-bolum-inci')
    : '<div class="kat-bolum kat-bolum-inci"><h4>INCI (uluslararası ad)</h4>'
      + '<p class="kat-yok">Kaynağımızda yok — etiketten doğrulanmalı.</p></div>';

  return '<div class="kat-detay">'
    + (galeri ? '<div class="kat-galeri">' + galeri + '</div>' : '')
    + (p.ozet ? '<p class="kat-tanitim">' + escapeHtml(p.ozet) + '</p>' : '')
    + cumleler
    + katBolum('Kullanım', p.kullanim)
    + inci
    + katBolum('İçindekiler (Türkçe)', p.icindekiler)
    + katBayiTablosu(p)
    + katBolum('Raf ömrü', p.raf_omru)
    + katBolum('Saklama', p.saklama)
    + uyarilar
    + '<div class="kat-bolum kat-bolum-teknik">'
    +   '<h4>Teknik</h4>'
    +   '<p>Barkod: <code>' + escapeHtml(p.sku || '—') + '</code>'
    +   ' · Stok: ' + (p.stok === null || p.stok === undefined ? '—' : p.stok)
    +   ' · Tavsiye edilen satış: ' + katPara(p.fiyat)
    +   ' · Bayi: ' + katPara(p.bayi_fiyat) + '</p>'
    + '</div>'
    + katNotFormu(p)
    + '</div>';
}

function katNotFormu(p) {
  const ilgiler = ((KAT.veri && KAT.veri.ilgi_degerleri) || []).map(function (i) {
    return '<option value="' + escapeHtml(i.deger) + '">'
      + escapeHtml(i.etiket) + '</option>';
  }).join('');
  return '<form class="kat-notform" data-slug="' + escapeHtml(p.slug) + '">'
    + '<h4>Sunum notu</h4>'
    + '<p class="kat-not-kucuk">'
    + (KAT.hedef
        ? 'Not şu hedefe bağlanacak: <strong>' + escapeHtml(KAT.hedefAd) + '</strong>'
        : 'Hedef seçilmedi — not ürün hakkında <strong>genel</strong> kaydedilir.')
    + '</p>'
    + '<div class="kat-notsatir">'
    +   '<select class="is-input kat-ilgi"><option value="">ilgi işaretlenmedi</option>'
    +     ilgiler + '</select>'
    +   '<button type="submit" class="btn">KAYDET</button>'
    +   '<span class="is-sonuc kat-notsonuc"></span>'
    + '</div>'
    + '<textarea class="is-input kat-notmetin" rows="2" maxlength="4000"'
    + ' placeholder="ne konuşuldu, ne sordu, ne istedi"></textarea>'
    + '<div class="kat-notlar" data-slug="' + escapeHtml(p.slug) + '"></div>'
    + '</form>';
}

async function katNotlariYukle(slug, kap) {
  const p = new URLSearchParams({ urun: slug, limit: 20 });
  if (KAT.hedef) p.set('hedef', KAT.hedef);
  const cevap = await api('/api/katalog/not?' + p.toString());
  if (!cevap.ok || !kap) return;
  const n = (cevap.body && cevap.body.notlar) || [];
  kap.innerHTML = n.length
    ? '<ul class="kat-notliste">' + n.map(function (x) {
        return '<li><span class="kat-notilgi">'
          + escapeHtml(x.ilgi_etiket || '—') + '</span>'
          + '<span class="kat-nottext">' + escapeHtml(x.not_metni || '') + '</span>'
          + '<span class="kat-notkim">' + escapeHtml(x.giren) + ' · '
          + escapeHtml(String(x.girildi).slice(0, 16).replace('T', ' ')) + '</span></li>';
      }).join('') + '</ul>'
    : '<p class="kat-yok">Bu ürün için henüz not yok.</p>';
}

document.addEventListener('click', function (e) {
  const bas = e.target.closest('.kat-bas');
  if (bas) {
    const slug = bas.dataset.slug;
    KAT.acik = (KAT.acik === slug) ? null : slug;
    katCiz();
    if (KAT.acik) {
      const kap = document.querySelector('.kat-notlar[data-slug="' + KAT.acik + '"]');
      katNotlariYukle(KAT.acik, kap);
    }
    return;
  }
  if (e.target.closest('#katYazdir')) {
    /* Yazdırma düzeni AYRI: ekranda katlanmış kartlar, kâğıtta her ürün
     * kendi bloğu ve altında not satırları. Eczacı kâğıda yazacak. */
    window.print();
  }
});

document.addEventListener('input', function (e) {
  if (e.target.id === 'katArama') katCiz();
});

document.addEventListener('change', function (e) {
  if (e.target.id === 'katSirala' || e.target.id === 'katEksik') katCiz();
});

document.addEventListener('submit', async function (e) {
  const form = e.target.closest('.kat-notform');
  if (!form) return;
  e.preventDefault();
  const sonuc = form.querySelector('.kat-notsonuc');
  const ilgi = form.querySelector('.kat-ilgi').value;
  const metin = form.querySelector('.kat-notmetin').value;
  if (!ilgi && !metin.trim()) {
    sonuc.className = 'is-sonuc is-bad';
    sonuc.textContent = 'not ya da ilgi işareti gerekli';
    return;
  }
  sonuc.className = 'is-sonuc';
  sonuc.textContent = 'kaydediliyor…';
  const cevap = await api('/api/katalog/not', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      urun_slug: form.dataset.slug, ilgi: ilgi || null, not: metin,
      hedef_anahtari: KAT.hedef || '',
    }),
  });
  if (!cevap.ok) {
    sonuc.className = 'is-sonuc is-bad';
    sonuc.textContent = (cevap.body && cevap.body.error) || 'kaydedilemedi';
    return;
  }
  sonuc.className = 'is-sonuc is-ok';
  sonuc.textContent = 'kaydedildi';
  form.querySelector('.kat-notmetin').value = '';
  form.querySelector('.kat-ilgi').value = '';
  katNotlariYukle(form.dataset.slug, form.querySelector('.kat-notlar'));
  /* İlgi sayacı kartın üstünde duruyor; tazelemek için katalog yeniden
   * okunur. Sayıyı yerelde artırsaydık sunucudaki gerçekle ayrışabilirdi. */
  KAT.veri = null;
  loadKatalog();
});


/* ==================== INSTAGRAM GÖNDERİ PLANI ===========================
 *
 * Paketler sunucuda üretilir (scripts/ig-gonderi-uret.py); panel okur ve
 * sahibin kararını yazar.
 *
 * 🔴 ONAY KAPISI ŞEMADA. Denetimden bulgulu geçen ya da itirazı
 * yanıtlanmamış paket veritabanı kısıtıyla reddedilir. Panelde ayrıca
 * kontrol etmiyorum: iki yer ayrı karar verirse biri diğerini sessizce
 * kabul eder. Kısıt hata döndürürse sebebi AYNEN gösterilir.
 */
function igDurumYaz(metin, kotu) {
  const d = qs('igDurumMetni');
  if (!d) return;
  d.className = 'is-sonuc' + (kotu ? ' is-bad' : '');
  d.textContent = metin || '';
}

async function loadIgPlan() {
  const secim = (qs('igDurum') || {}).value || '';
  const p = new URLSearchParams({ limit: 60 });
  if (secim) p.set('durum', secim);
  const cevap = await api('/api/ig-plan?' + p.toString());
  if (!cevap.ok) {
    igDurumYaz((cevap.body && cevap.body.error) || 'plan okunamadı', true);
    return;
  }
  igDurumYaz('');
  igPlanCiz(cevap.body);
}

function igPlanCiz(veri) {
  const kap = qs('igPlanListe');
  if (!kap) return;
  const o = veri.ozet || {};
  const c = qs('igCount');
  if (c) {
    c.textContent = (o.karar_bekleyen || 0) + ' karar bekliyor · '
      + (o.onayli || 0) + ' onaylı · ' + (o.yayinda || 0) + ' yayında';
  }
  const paketler = veri.paketler || [];
  if (!paketler.length) {
    kap.innerHTML = '<p class="sect-empty">Bu durumda paket yok.</p>';
    return;
  }
  kap.innerHTML = paketler.map(igKart).join('');
}

function igKart(p) {
  const bulgulu = p.denetim !== 'TEMIZ';
  const etiketler = (p.hashtagler || []).join(' ');
  const kararli = p.durum !== 'ONERI';
  return '<article class="ig-kart ig-' + escapeHtml(p.durum.toLowerCase()) + '">'
    + '<header class="ig-bas">'
    +   '<span class="ig-amac">' + escapeHtml(p.amac_etiket || p.amac) + '</span>'
    +   '<span class="ig-bicim">' + escapeHtml(p.bicim) + '</span>'
    +   '<span class="ig-urun">' + escapeHtml(p.urun_slug) + '</span>'
    +   '<span class="ig-durum">' + escapeHtml(p.durum) + '</span>'
    +   (bulgulu ? '<span class="ig-bulgu">DENETİM: BULGULU</span>' : '')
    + '</header>'
    + igGorsel(p)
    + '<pre class="ig-caption">' + escapeHtml(p.caption) + '</pre>'
    + '<p class="ig-etiket">' + escapeHtml(etiketler) + '</p>'
    + igSatir('EYLEM DÜĞMESİ', escapeHtml(JarvisMetin.label(p.cta, 'Belirtilmedi')) + ' — ' + escapeHtml(p.cta_gerekce || ''))
    + igSatir('GÖRSEL AÇIKLAMASI', escapeHtml(JarvisMetin.safeTitle(p.gorsel_brief, 'Görsel açıklaması hazırlanıyor.')))
    + igSatir('DAYANAK', escapeHtml(p.dayanak || ''))
    + igSatir('İTİRAZ', escapeHtml(p.itiraz || '—'), 'ig-itiraz')
    + igSatir('YANIT', escapeHtml(p.itiraza_yanit || '—'), 'ig-yanit')
    + (bulgulu
        ? igSatir('DENETİM NOTU', escapeHtml(p.denetim_notu || ''), 'ig-bulgu-not')
        : '')
    + '<div class="ig-karar">'
    +   (kararli
          ? '<span class="ig-kararli">' + escapeHtml(p.durum) + ' · '
            + escapeHtml(p.karar_veren || '') + '</span>'
          : '<button type="button" class="btn ig-onay" data-id="' + p.plan_id
            + '" data-durum="ONAYLANDI">ONAYLA</button>'
            + '<button type="button" class="btn btn-ince ig-onay" data-id="'
            + p.plan_id + '" data-durum="REDDEDILDI">REDDET</button>')
    +   (p.durum === 'ONAYLANDI'
          ? '<button type="button" class="btn btn-ince ig-onay" data-id="'
            + p.plan_id + '" data-durum="YAYINLANDI">YAYINLANDI</button>' : '')
    +   '<a class="btn btn-ince" href="/ig-foy/' + p.plan_id
    +     '" download>\u2913 ÇEKİM FÖYÜ</a>'
    +   '<span class="is-sonuc ig-sonuc" data-id="' + p.plan_id + '"></span>'
    + '</div>'
    + '</article>';
}

function igSatir(baslik, govde, sinif) {
  if (!govde) return '';
  return '<div class="ig-satir' + (sinif ? ' ' + sinif : '') + '">'
    + '<span class="ig-satir-bas">' + escapeHtml(baslik) + '</span>'
    + '<span class="ig-satir-govde">' + govde + '</span></div>';
}

document.addEventListener('change', function (e) {
  if (e.target.id === 'igDurum') loadIgPlan();
});

document.addEventListener('click', async function (e) {
  const dugme = e.target.closest('.ig-onay');
  if (!dugme) return;
  const sonuc = document.querySelector('.ig-sonuc[data-id="' + dugme.dataset.id + '"]');
  if (sonuc) { sonuc.className = 'is-sonuc ig-sonuc'; sonuc.textContent = '…'; }
  const cevap = await api('/api/ig-plan/karar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: Number(dugme.dataset.id),
                           durum: dugme.dataset.durum }),
  });
  if (!cevap.ok) {
    /* Şema kısıtının hata metni AYNEN gösterilir: "bulgulu paket
     * onaylanamaz" bilgisi kullanıcıya ulaşmalı, yoksa düğme bozuk
     * görünür. */
    if (sonuc) {
      sonuc.className = 'is-sonuc is-bad';
      sonuc.textContent = (cevap.body && cevap.body.error) || 'kaydedilemedi';
    }
    return;
  }
  loadIgPlan();
});


/* Basılı katalog indirme.
 *
 * 🔴 İKİ DOSYA, İKİ AYRI İŞ. Baskı aslı 26 MB, A4 + taşma, fontlar
 * gömülü -- basımevine giden budur. Gözden geçirme kopyası 2 MB, 110 DPI
 * -- ekranda bakmak ve paylaşmak için. Karıştırmak, gözden kopyasını
 * matbaaya göndermek demek olur; o yüzden ikisi ayrı ayrı ve ne
 * oldukları yazılı duruyor. */
function katPdfCiz() {
  const kap = qs('katPdf');
  if (!kap || !KAT.veri) return;
  const liste = KAT.veri.pdf || [];
  if (!liste.length) { kap.hidden = true; return; }
  kap.hidden = false;
  kap.innerHTML = '<h4>Basılı katalog</h4>' + liste.map(function (p) {
    if (!p.var) {
      return '<div class="kat-pdf-satir"><span class="kat-yok">'
        + escapeHtml(p.etiket) + ' — henüz üretilmedi</span></div>';
    }
    return '<div class="kat-pdf-satir">'
      + '<a class="btn btn-ince" href="/katalog-pdf/' + escapeHtml(p.tur)
      + '" download>⤓ ' + escapeHtml(p.etiket.toUpperCase()) + '</a>'
      + '<span class="kat-pdf-not">' + escapeHtml(p.aciklama)
      + ' · ' + p.mb + ' MB · ' + escapeHtml(p.uretim) + '</span>'
      + '</div>';
  }).join('');
}


/* Üretilen görsel KARTTA görünür.
 *
 * 🔴 Daha önce hiç çizilmiyordu. Görsel üretiliyor, diske yazılıyor,
 * veritabanına işleniyor, yolu bile açık -- ama panelde hiçbir yerde
 * görünmüyordu. "Sürekli bir şeyler üretiliyor ama görünmüyor" şikâyeti
 * ölçüldü ve haklı çıktı.
 *
 * Reels paketinde bu kare VİDEO DEĞİL, kapak/başlangıç karesidir; etiket
 * bunu açıkça yazar, yoksa hazır video sanılır. */
function igGorsel(p) {
  if (!p.gorsel_dosya) {
    return '<p class="ig-gorsel-yok">görsel henüz üretilmedi</p>';
  }
  const url = '/gonderi-gorsel/' + encodeURIComponent(p.gorsel_dosya);
  const reels = p.bicim === 'REELS';
  return '<figure class="ig-gorsel">'
    + '<a href="' + url + '" target="_blank" rel="noopener">'
    +   '<img src="' + url + '" alt="" loading="lazy">'
    + '</a>'
    + '<figcaption>'
    +   (reels
          ? '<span class="ig-uyari-etiket">KAPAK KARESİ — video değil</span>'
          : '<span class="ig-hazir-etiket">yayına hazır kare</span>')
    +   (p.gorsel_taslak_mi
          ? '<span class="ig-taslak">taslak</span>' : '')
    +   '<a class="ig-indir" href="' + url + '" download>indir</a>'
    + '</figcaption></figure>';
}


/* ---------------------------- ÜRETİLENLER ----------------------------
 * 🔴 Üretilen şeyler 22 sekmeye dağılmıştı: katalog PDF'i KATALOG'da,
 * gönderi görselleri INSTAGRAM'da, çekim föyü gönderi kartının içinde,
 * kreatif konseptler HİÇBİR YERDE. "Şu dosya nerede" sorusunun tek bir
 * cevabı yoktu. Burada hepsi aynı biçimde durur.
 *
 * Boş bölüm GİZLENMEZ: üretilmemiş olan, görünmez olmamalı. */
async function loadUretilenler() {
  const cevap = await api('/api/uretilenler');
  const kap = qs('urListe');
  if (!kap) return;
  if (!cevap.ok) {
    kap.innerHTML = '<p class="sect-empty">Üretilenler okunamadı: '
      + escapeHtml((cevap.body && cevap.body.error) || 'bilinmeyen hata')
      + '</p>';
    return;
  }
  urCiz(cevap.body);
}

function urCiz(veri) {
  const sayi = qs('urSayi');
  if (sayi) {
    sayi.textContent = (veri.toplam || 0) + ' üretilmiş kayıt'
      + (veri.soramadim && veri.soramadim.length
          ? ' · sorulamayan: ' + veri.soramadim.join(', ') : '');
  }
  const kap = qs('urListe');
  kap.innerHTML = (veri.bolumler || []).map(urBolum).join('');
}

function urBolum(b) {
  let govde;
  if (b.durum === 'SORAMADIM') {
    /* SORAMADIM ile YOK ayrı şeyler: biri üretilmediğini, öbürü
       bakamadığımızı söyler. */
    govde = '<p class="ur-soramadim">Bakılamadı: '
      + escapeHtml(b.sebep || '') + '</p>';
  } else if (!b.kayitlar || !b.kayitlar.length) {
    govde = '<p class="ur-yok">' + escapeHtml(b.bos_notu || 'henüz üretilmedi')
      + '</p>';
  } else if (b.anahtar === 'konsept') {
    govde = b.kayitlar.map(urKonsept).join('');
  } else if (b.anahtar === 'gonderi') {
    govde = b.kayitlar.map(urGonderi).join('');
  } else if (b.anahtar === 'tasarim') {
    govde = b.kayitlar.map(urTasarim).join('');
  } else {
    govde = b.kayitlar.map(urDosya).join('');
  }
  return '<section class="ur-bolum">'
    + '<header><h3>' + escapeHtml(b.baslik) + '</h3>'
    + '<span class="ur-adet">' + ((b.kayitlar || []).length) + '</span></header>'
    + '<p class="ur-aciklama">' + escapeHtml(b.aciklama || '') + '</p>'
    + (b.elenen ? '<p class="ur-elenen">' + b.elenen
        + ' konsept klişe nedeniyle elendi</p>' : '')
    + '<div class="ur-govde">' + govde + '</div></section>';
}

function urKonsept(k) {
  const satir = function (ad, deger) {
    if (!deger) return '';
    return '<div class="ur-satir"><span>' + escapeHtml(ad) + '</span><span>'
      + escapeHtml(deger) + '</span></div>';
  };
  return '<article class="ur-kart">'
    + '<header class="ur-kart-bas">'
    +   '<span class="ur-urun">' + escapeHtml(k.urun_slug) + '</span>'
    +   '<strong class="ur-ad">' + escapeHtml(k.ad) + '</strong>'
    +   '<span class="ur-puan">' + k.puan + '/30</span>'
    + '</header>'
    + '<p class="ur-fikir">' + escapeHtml(k.ana_fikir || '') + '</p>'
    + satir('Görsel metafor', k.gorsel_metafor)
    + satir('Kompozisyon', k.kompozisyon)
    + satir('Ne durdurur', k.neden_durdurur)
    + satir('Kamera', k.ay_kamera)
    + satir('Işık', k.ay_isik)
    + satir('Yazı alanı', k.ay_tipografi_alani)
    + (k.istem ? '<p class="ur-istem">' + escapeHtml(JarvisMetin.jobTitle({istem:k.istem})) + '</p>' : '')
    + '<p class="ur-zaman">paket ' + k.plan_id + ' · ' + escapeHtml(k.uretim)
    + '</p></article>';
}

function urGonderi(g) {
  const gorsel = g.gorsel
    ? '<a href="/gonderi-gorsel/' + encodeURIComponent(g.gorsel)
      + '" target="_blank" rel="noopener"><img src="/gonderi-gorsel/'
      + encodeURIComponent(g.gorsel) + '" alt="" loading="lazy"></a>'
    : '<span class="ur-gorsel-yok">görsel yok</span>';
  return '<article class="ur-kart ur-kart-gorsel">'
    + '<div class="ur-kucuk">' + gorsel + '</div>'
    + '<div class="ur-kart-govde">'
    +   '<header class="ur-kart-bas">'
    +     '<span class="ur-urun">' + escapeHtml(g.urun) + '</span>'
    +     '<strong class="ur-ad">' + escapeHtml(g.bicim) + '</strong>'
    +     '<span class="ur-rozet">' + escapeHtml(g.durum) + '</span>'
    +   '</header>'
    +   (g.kapak_karesi
          ? '<p class="ur-uyari">Bu kare KAPAK KARESİ — video değil</p>' : '')
    +   (g.taslak
          ? '<p class="ur-not">taslak'
            + (g.konsept_id ? '' : ' · konsept bağlanmadı') + '</p>' : '')
    +   '<p class="ur-zaman">paket ' + g.plan_id + ' · '
    +     escapeHtml(g.amac) + ' · ' + escapeHtml(g.uretim)
    +     (g.mb ? ' · ' + g.mb + ' MB' : '') + '</p>'
    +   '<p class="ur-baglar">'
    +     (g.gorsel ? '<a href="/gonderi-gorsel/'
          + encodeURIComponent(g.gorsel) + '" download>görseli indir</a>' : '')
    +     '<a href="' + escapeHtml(g.foy) + '" download>çekim föyü</a>'
    +   '</p>'
    + '</div></article>';
}

function urDosya(d) {
  return '<article class="ur-kart ur-kart-dosya">'
    + '<div class="ur-kart-govde">'
    +   '<strong class="ur-ad">' + escapeHtml(d.baslik) + '</strong>'
    +   (d.aciklama ? '<p class="ur-not">' + escapeHtml(d.aciklama)
        + '</p>' : '')
    +   '<p class="ur-zaman">' + escapeHtml(d.uretim)
    +     (d.mb ? ' · ' + d.mb + ' MB' : '') + '</p>'
    + '</div>'
    + (d.indir ? '<a class="btn btn-ince" href="' + escapeHtml(d.indir)
        + '" download>indir</a>' : '')
    + '</article>';
}

function urTasarim(t) {
  return '<article class="ur-kart ur-kart-dosya">'
    + '<div class="ur-kart-govde">'
    +   '<strong class="ur-ad">' + escapeHtml(t.istek || t.is_turu) + '</strong>'
    +   '<p class="ur-not">' + escapeHtml(t.is_turu) + ' · isteyen: '
    +     escapeHtml(t.isteyen) + '</p>'
    +   '<p class="ur-zaman">' + escapeHtml(t.uretim) + '</p>'
    + '</div>'
    + '<span class="ur-rozet">' + escapeHtml(t.durum) + '</span>'
    + '</article>';
}


/* ===================== GELEN KUTUSU =====================================
 * Musteri konusmalari ve her birinin KIMDE oldugu.
 *
 * Panel hicbir mesaj GONDERMEZ. Devir durumunu degistirir ve kapinin
 * kararini GOSTERIR -- sessizce uygulamaz. Gonderme ayri bir ucun ve ayri
 * bir sahip eyleminin isidir.
 *
 * Musteri metni GUVENILMEZ girdidir: her yerde escapeHtml()'den gecer.
 */
let gkDurum = '';
let gkSecili = null;

function gkEtiket(durum) {
  if (durum === 'JARVIS') return '<span class="gk-rozet gk-jarvis">JARVIS</span>';
  if (durum === 'KAPALI') return '<span class="gk-rozet gk-kapali">KAPALI</span>';
  return '<span class="gk-rozet gk-insan">SENDE</span>';
}

function gkSatir(k) {
  var son = (k.son_metin || '').slice(0, 90);
  var cevapsiz = k.cevapsiz ? '<span class="gk-bekleyen">CEVAPSIZ</span>' : '';
  var sinif = k.son_sinif
    ? '<span class="gk-sinif">' + escapeHtml(k.son_sinif) + '</span>' : '';
  return '<button type="button" class="gk-satir' +
    (gkSecili === k.id ? ' is-secili' : '') + '" data-kid="' + k.id + '">' +
    '<span class="gk-ust">' + gkEtiket(k.devir_durumu) + cevapsiz +
    '<span class="gk-kanal">' + escapeHtml(k.kanal || '') + '</span>' + sinif +
    '</span>' +
    '<span class="gk-ad">' + escapeHtml(String(k.musteri || '')) + '</span>' +
    '<span class="gk-son">' + escapeHtml(son) + '</span>' +
    '</button>';
}

async function loadGelenKutusu() {
  var liste = qs('gkListe');
  if (liste && !gkSecili) liste.innerHTML = '<p class="fm-empty">Yukleniyor...</p>';
  var yol = '/api/gelenkutusu' +
    (gkDurum ? '?durum=' + encodeURIComponent(gkDurum) : '');
  var r = await api(yol);
  if (!r.ok || !r.body) {
    if (liste) {
      liste.innerHTML = '<p class="fm-empty">Gelen kutusu okunamadi' +
        (r.body && r.body.error ? ': ' + escapeHtml(r.body.error) : '') + '</p>';
    }
    return;
  }
  var o = r.body.ozet || {};
  var sayac = qs('gkSayac');
  if (sayac) {
    sayac.innerHTML =
      '<span class="gk-s"><b>' + (o.cevapsiz || 0) + '</b> cevapsiz</span>' +
      '<span class="gk-s"><b>' + (o.insanda || 0) + '</b> sende</span>' +
      '<span class="gk-s"><b>' + (o.jarviste || 0) + '</b> Jarviste</span>' +
      '<span class="gk-s gk-s-sade">' + (o.toplam || 0) + ' konusma</span>';
  }
  var kayitlar = r.body.konusmalar || [];
  if (liste) {
    liste.innerHTML = kayitlar.length
      ? kayitlar.map(gkSatir).join('')
      : '<p class="fm-empty">Bu suzgecte konusma yok.</p>';
  }
}

async function gkKonusmaAc(kid) {
  gkSecili = kid;
  var kutu = qs('gkDetay');
  if (kutu) kutu.innerHTML = '<p class="fm-empty">Yukleniyor...</p>';
  var r = await api('/api/gelenkutusu/konusma?id=' + encodeURIComponent(kid));
  if (!r.ok || !r.body) {
    if (kutu) kutu.innerHTML = '<p class="fm-empty">Konusma acilamadi.</p>';
    return;
  }
  var k = r.body;
  var oneri = k.oneri || {};
  var mesajlar = (k.mesajlar || []).map(function (m) {
    var yon = m.yon === 'gelen' ? 'gk-m-gelen' : 'gk-m-giden';
    var kim = m.yon === 'gelen' ? 'Musteri' : 'Biz';
    return '<div class="gk-m ' + yon + '">' +
      '<span class="gk-m-kim">' + kim + '</span>' +
      '<span class="gk-m-metin">' + escapeHtml(m.metin || '') + '</span></div>';
  }).join('');

  var oneriMetni = oneri.devir
    ? 'Devir kapisi bu konusmayi <b>sana</b> veriyor &mdash; ' +
      escapeHtml(oneri.sebep_metni || '')
    : 'Devir kapisina gore <b>Jarvis</b> cevaplayabilir.';

  kutu.innerHTML =
    '<div class="gk-d-bas"><b>' + escapeHtml(String(k.musteri || '')) + '</b>' +
    '<span class="gk-kanal">' + escapeHtml(k.kanal || '') + '</span>' +
    gkEtiket(k.devir_durumu) + '</div>' +
    '<p class="gk-oneri">' + oneriMetni + '</p>' +
    '<div class="gk-akis">' +
      (mesajlar || '<p class="fm-empty">Mesaj yok.</p>') + '</div>' +
    '<div class="gk-eylem">' +
      '<button type="button" class="gk-b" data-devir="INSANDA" data-kid="' +
        k.id + '">BANA AL</button>' +
      '<button type="button" class="gk-b" data-devir="JARVIS" data-kid="' +
        k.id + '">JARVISE VER</button>' +
      '<button type="button" class="gk-b gk-b-sade" data-devir="KAPALI" data-kid="' +
        k.id + '">KAPAT</button>' +
    '</div>' +
    '<div class="gk-cevap">' +
      '<label class="gk-c-etiket" for="gkCevapMetin">Cevap yaz</label>' +
      '<textarea id="gkCevapMetin" class="gk-c-alan" rows="3" ' +
        'placeholder="Musteriye gidecek metin..."></textarea>' +
      '<div class="gk-c-dugmeler">' +
        '<button type="button" class="gk-b" data-taslak="1" ' +
          'data-kid="' + k.id + '">JARVIS TASLAK URETSIN</button>' +
        '<button type="button" class="gk-b gk-b-sade" data-cevap="kuru" ' +
          'data-kid="' + k.id + '">ONCE DENETLE</button>' +
        '<button type="button" class="gk-b" data-cevap="gonder" ' +
          'data-kid="' + k.id + '">GONDER</button>' +
      '</div>' +
      '<p class="gk-c-sonuc" id="gkCevapSonuc"></p>' +
    '</div>' +
    '<p class="gk-not">Gonderme bes kapidan gecer: onay kaynagi, metin siniri, ' +
    'MEVZUAT denetimi, gonderme anahtari ve kimlik. &quot;Once denetle&quot; aga ' +
    'cikmaz, yalniz metnin gecip gecmeyecegini soyler.</p>';
}

function gkUyari(mesaj) {
  var kutu = qs('gkDetay');
  if (!kutu) return;
  var p = document.createElement('p');
  p.className = 'fm-empty';
  p.textContent = mesaj;
  kutu.prepend(p);
}

async function gkDevret(kid, durum) {
  var r = await api('/api/gelenkutusu/devir', {
    method: 'POST',
    body: JSON.stringify({ id: kid, durum: durum })
  });
  if (!r.ok) {
    gkUyari('Devir degistirilemedi' +
      (r.body && r.body.error ? ': ' + r.body.error : ''));
    return;
  }
  await loadGelenKutusu();
  await gkKonusmaAc(kid);
}

document.addEventListener('click', function (ev) {
  var suz = ev.target.closest ? ev.target.closest('#gkSuzgec .gk-f') : null;
  if (suz) {
    gkDurum = suz.dataset.durum || '';
    document.querySelectorAll('#gkSuzgec .gk-f').forEach(function (b) {
      b.classList.toggle('is-active', b === suz);
    });
    gkSecili = null;
    var d = qs('gkDetay');
    if (d) d.innerHTML = '<p class="fm-empty">Soldan bir konusma sec.</p>';
    loadGelenKutusu();
    return;
  }
  var satir = ev.target.closest ? ev.target.closest('.gk-satir') : null;
  if (satir) {
    gkKonusmaAc(Number(satir.dataset.kid));
    loadGelenKutusu();
    return;
  }
  var btn = ev.target.closest ? ev.target.closest('.gk-eylem .gk-b') : null;
  if (btn) gkDevret(Number(btn.dataset.kid), btn.dataset.devir);
});


/* Cevap gonderme. `kuru` aga cikmaz ama MEVZUAT kapisini isletir --
   sahip gondermeden once metnin gecip gecmeyecegini gorur. */
async function gkCevapla(kid, kuru) {
  var alan = qs('gkCevapMetin');
  var sonuc = qs('gkCevapSonuc');
  if (!alan || !sonuc) return;
  var metin = (alan.value || '').trim();
  if (!metin) { sonuc.textContent = 'Once bir metin yaz.'; return; }
  sonuc.textContent = kuru ? 'Denetleniyor...' : 'Gonderiliyor...';
  var r = await api('/api/gelenkutusu/cevap', {
    method: 'POST',
    body: JSON.stringify({ id: kid, metin: metin, kuru: !!kuru })
  });
  if (!r.ok) {
    sonuc.textContent = 'Gonderilmedi: ' +
      ((r.body && r.body.error) || 'bilinmeyen sebep');
    return;
  }
  if (r.body && r.body.kuru) {
    sonuc.textContent = 'Denetimden gecti. Gondermek icin GONDER.';
    return;
  }
  sonuc.textContent = 'Gonderildi.';
  alan.value = '';
  await gkKonusmaAc(kid);
}

document.addEventListener('click', function (ev) {
  var b = ev.target.closest ? ev.target.closest('[data-cevap]') : null;
  if (b) gkCevapla(Number(b.dataset.kid), b.dataset.cevap === 'kuru');
});


/* Jarvis taslagi. URETIR, GONDERMEZ -- metin cevap kutusuna dusur, sahip
   okur ve isterse degistirip GONDER'e basar. Devir kapisi modelden once
   isledigi icin devredilmesi gereken konusmada model hic cagrilmaz. */
async function gkTaslak(kid) {
  var alan = qs('gkCevapMetin');
  var sonuc = qs('gkCevapSonuc');
  if (!alan || !sonuc) return;
  sonuc.textContent = 'Jarvis taslak uretiyor...';
  var r = await api('/api/gelenkutusu/taslak', {
    method: 'POST',
    body: JSON.stringify({ id: kid })
  });
  if (!r.ok || !r.body) {
    sonuc.textContent = 'Taslak uretilemedi: ' +
      ((r.body && r.body.error) || 'bilinmeyen sebep');
    return;
  }
  var t = r.body;
  if (t.devredilmeli) {
    alan.value = t.metin || '';
    sonuc.textContent = t.metin
      ? 'Devir taslağı hazır: ' + (t.sebep_metni || 'yetkili incelemesi gerekli') +
        '. Bu metni kontrol et; göndermeden önce konuşmayı üzerine al.'
      : 'Bu konu sana devredilmeli: ' +
        (t.sebep_metni || 'yetkili incelemesi gerekli') + '. Cevabı sen yazmalısın.';
    return;
  }
  if (!t.uretildi) {
    sonuc.textContent = 'Taslak bos dondu' +
      (t.gerekce ? ' (' + t.gerekce + ')' : '') + '.';
    return;
  }
  alan.value = t.metin || '';
  var notlar = [];
  if (t.urun_soruluyor) notlar.push('urun bilinmedigi icin hangi urun oldugunu soruyor');
  if (t.mevzuat) notlar.push('mevzuat: ' + t.mevzuat);
  if (t.model) notlar.push('model: ' + t.model);
  else notlar.push('model cagrilmadi');
  sonuc.textContent = 'Taslak hazir — ' + notlar.join(' · ') +
    '. Oku, gerekirse degistir, sonra GONDER.';
}

document.addEventListener('click', function (ev) {
  var b = ev.target.closest ? ev.target.closest('[data-taslak]') : null;
  if (b) gkTaslak(Number(b.dataset.kid));
});
