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
const VIEWS = { home: 'viewHome', analiz: 'viewAnaliz', gorevler: 'viewGorevler',
                veri: 'viewVeri', ajanlar: 'viewAjanlar', fiyat: 'viewFiyat',
                raporlar: 'viewRaporlar', ayarlar: 'viewAyarlar',
                eticaret: 'viewEticaret', reklam: 'viewReklam',
                hafiza: 'viewHafiza' };

function setView(name) {
  if (!VIEWS[name]) return;
  state.view = name;
  Object.entries(VIEWS).forEach(([key, id]) => { qs(id).hidden = key !== name; });
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.view === name);
  });
  if (name === 'gorevler') { refreshActivity(); refreshProposals(); }
  if (name === 'fiyat') loadFiyatMatrisi();
  if (name === 'eticaret') loadUrunAlanlari();
  if (name === 'reklam') loadKreatif();
  if (name === 'hafiza') loadHafiza();
  if (PANEL_SECTIONS[name]) loadSection(name);
}

qs('mainNav').addEventListener('click', (event) => {
  const btn = event.target.closest('.nav-item');
  if (!btn || btn.disabled) return;
  setView(btn.dataset.view);
});

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
    ['Company Memory', memoryOk ? ['SAĞLIKLI', 's-ok'] : ['HATA', 's-error']],
    ['Action Firewall', contract === null || contract === undefined
      ? ['BİLİNMİYOR', 's-warn'] : (contract ? ['SÖZLEŞME GEÇERLİ', 's-ok'] : ['GEÇERSİZ', 's-error'])],
    ['AI Worker', flag(health && health.ai_worker_enabled, 'AÇIK', 'KAPALI', 's-ok', 's-off')],
    ['Action Worker', flag(health && health.action_worker_enabled, 'AÇIK', 'KAPALI', 's-ok', 's-off')],
    ['Dış Eylemler', body.external_actions_enabled ? ['AÇIK', 's-warn'] : ['KAPALI', 's-off']],
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
  red_team_objection: ['RED TEAM', 'f-redteam'],
  approval_backlog: ['ONAY', 'f-onay'],
  open_work_aging: ['OPERASYON', 'f-operasyon'],
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
    case 'NOOP': return 'Company Memory kontrol edildi — değişiklik yok';
    case 'PROPOSED': return `Öneri oluşturuldu (${detail.action_type || '—'})`;
    case 'SKIPPED_NOT_MINE': return 'Farklı bir görev tipi tespit edildi, dokunulmadı';
    case 'FIREWALL_REJECTED': return 'Bir görev firewall tarafından reddedildi';
    case 'CLAIM_FAILED': return 'Görev alma başarısız';
    case 'CODING_TASK_DENIED': return 'Kodlama görevi reddedildi';
    default: return row.result || '—';
  }
}
function auditSub(row) {
  const detail = row.task_detail || {};
  const bits = [];
  if (detail.task_id) bits.push(`görev ${detail.task_id}`);
  if (detail.proposal_id) bits.push(`öneri ${detail.proposal_id}`);
  if (detail.error) bits.push(detail.error);
  if (row.business && row.business.codes && row.business.codes.length) {
    bits.push(`sinyal: ${row.business.codes.join(', ')}`);
  }
  return bits.join(' · ');
}

function feedItem({ cls, tag, meta, text, sub }) {
  return `<li class="${cls}">
    <div class="f-head"><span class="f-tag">${escapeHtml(tag)}</span><span class="f-time">${escapeHtml(meta)}</span></div>
    <div class="f-text">${escapeHtml(text)}${sub ? `<span class="f-sub">${escapeHtml(sub)}</span>` : ''}</div>
  </li>`;
}

function buildFindingItems(findings) {
  return findings.slice().reverse().map((f) => {
    const [tag, cls] = SIGNAL_TAG[f.signal_code]
      || [f.severity === 'CRITICAL' ? 'KRİTİK' : 'BULGU', f.severity === 'CRITICAL' ? 'f-redteam' : 'f-onay'];
    return feedItem({
      cls, tag,
      meta: fmtDateTime(f.observed_at),
      text: f.reason || f.signature || '—',
      sub: f.severity ? `önem: ${f.severity}` : '',
    });
  });
}

function buildAuditItems(audit) {
  const rows = audit.slice().reverse();  // newest cycle first
  const items = [];
  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    if (row.result === 'NOOP') {
      let j = i;
      while (j < rows.length && rows[j].result === 'NOOP') j += 1;
      const run = rows.slice(i, j);
      const newest = run[0].cycle;
      const oldest = run[run.length - 1].cycle;
      items.push(feedItem({
        cls: 'f-sistem', tag: 'SİSTEM',
        meta: run.length > 1 ? `DÖNGÜ #${oldest}–#${newest}` : `DÖNGÜ #${newest}`,
        text: auditText(run[0]),
        sub: run.length > 1 ? `${run.length} döngü tek satırda toplandı` : auditSub(run[0]),
      }));
      i = j;
      continue;
    }
    const [tag, cls] = AUDIT_TAG[row.result] || ['SİSTEM', 'f-sistem'];
    items.push(feedItem({
      cls, tag,
      meta: `DÖNGÜ #${row.cycle}`,
      text: auditText(row),
      sub: auditSub(row),
    }));
    i += 1;
  }
  return items;
}

async function refreshActivity() {
  const { ok, body } = await api('/api/activity?limit=60');
  if (!ok || !body) return;
  state.lastActivity = body;

  const findingItems = buildFindingItems(body.findings || []);
  const auditItems = buildAuditItems(body.audit || []);
  const all = findingItems.concat(auditItems);

  const feed = qs('activityFeed');
  feed.innerHTML = all.length ? all.join('') : '<li class="f-sistem"><div class="f-text">Henüz kayıtlı etkinlik yok.</div></li>';
  qs('feedCount').textContent = `${(body.findings || []).length} bulgu · ${(body.audit || []).length} döngü`;

  const cycleList = qs('taskCycleList');
  if (cycleList) {
    cycleList.innerHTML = auditItems.length ? auditItems.join('')
      : '<li class="f-sistem"><div class="f-text">Henüz döngü kaydı yok.</div></li>';
    qs('taskCycleCount').textContent = `${(body.audit || []).length} kayıt`;
  }
}

/* ---------------- proposals ---------------- */
function proposalCardHtml(p) {
  return `<div class="p-type">${escapeHtml(p.action_type)} <span class="risk-badge risk-${escapeHtml(p.risk_class)}">${escapeHtml(p.risk_class)}</span></div>
    <div class="p-meta">#${escapeHtml(p.action_id)} · ${escapeHtml(fmtDateTime(p.proposed_at))}</div>`;
}

function fillProposalList(listEl, emptyEl, pending) {
  if (!listEl) return;
  listEl.innerHTML = '';
  if (emptyEl) emptyEl.hidden = pending.length > 0;
  pending.forEach((p) => {
    const li = document.createElement('li');
    li.className = 'proposal-card';
    li.innerHTML = proposalCardHtml(p);
    li.addEventListener('click', () => openProposal(p.action_id));
    listEl.appendChild(li);
  });
}

async function refreshProposals() {
  const { ok, body } = await api('/api/proposals');
  if (!ok || !body) return;
  const pending = body.pending || [];
  fillProposalList(qs('proposalList'), qs('proposalEmpty'), pending);
  fillProposalList(qs('taskProposalList'), qs('taskProposalEmpty'), pending);
  const count = qs('taskPropCount');
  if (count) count.textContent = `${pending.length} kayıt`;
}

async function openProposal(actionId) {
  const { ok, body } = await api('/api/proposals/' + actionId);
  if (!ok || !body) return;
  qs('modalBody').innerHTML = `
    <h3>${escapeHtml(body.action_type)} <span class="risk-badge risk-${escapeHtml(body.risk_class)}">${escapeHtml(body.risk_class)}</span></h3>
    <p><strong>#${escapeHtml(body.action_id)}</strong> · görev ${escapeHtml(body.task_id)} · ${escapeHtml(fmtDateTime(body.proposed_at))}</p>
    <p>Son geçerlilik: ${escapeHtml(fmtDateTime(body.expires_at))}</p>
    <div class="evidence-block">${escapeHtml(JSON.stringify(body.payload, null, 2))}</div>
    <label class="reason-label">GEREKÇE
      <input id="decisionReason" type="text" class="reason-input">
    </label>
    <div class="modal-actions">
      <button class="btn-approve" id="btnApprove" type="button">ONAYLA</button>
      <button class="btn-reject" id="btnReject" type="button">REDDET</button>
    </div>
  `;
  qs('btnApprove').addEventListener('click', () => decide(actionId, 'APPROVED'));
  qs('btnReject').addEventListener('click', () => decide(actionId, 'REJECTED'));
  qs('proposalModal').hidden = false;
}

async function decide(actionId, decision) {
  const reason = qs('decisionReason').value.trim() || (decision === 'APPROVED' ? 'Operatör onayı' : 'Operatör reddi');
  const { ok, body } = await api(`/api/proposals/${actionId}/decide`, {
    method: 'POST', body: JSON.stringify({ decision, reason }),
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
                 + (why ? `<span class="plan-unavailable">${escapeHtml(why)}</span>` : ''));
      } else if (blocked) {
        marks.push(`<span class="plan-flag plan-flag-blocked">BLOKE: ${escapeHtml(step.blocked_by.join(', '))}</span>`);
      }
      if (step.requires_human_origination) marks.push('<span class="plan-flag plan-flag-human">İNSAN BAŞLATIR</span>');
      if (step.produces_action) marks.push('<span class="plan-flag">ONAY GEREKİR</span>');
      const deps = step.depends_on.length ? ` ← ${escapeHtml(step.depends_on.join(', '))}` : '';
      return `<li class="plan-step${blocked ? ' is-blocked' : ''}">
        <div class="plan-step-head"><strong>${escapeHtml(step.step_id)}</strong> ${escapeHtml(step.capability)}<span class="plan-deps">${deps}</span></div>
        <div class="plan-step-desc">${escapeHtml(step.description)}</div>
        <div class="plan-step-target">${escapeHtml(step.target)}</div>
        ${marks.length ? `<div class="plan-flags">${marks.join(' ')}</div>` : ''}
      </li>`;
    }).join('');
    const parallel = group.length > 1 ? ' · paralel' : '';
    return `<div class="plan-group"><div class="plan-group-title">GRUP ${index + 1}${parallel}</div><ol class="plan-steps">${rows}</ol></div>`;
  }).join('');
}

function renderPlan(plan) {
  const blockedCaps = [...new Set(plan.steps.flatMap((s) => s.blocked_by || []))];
  const statusText = PLAN_STATUS_TEXT[plan.status] || plan.status;
  const chips = [
    planChip('MOD', plan.mode, `plan-mode-${plan.mode}`),
    planChip('RİSK', plan.risk, `risk-badge risk-${plan.risk}`),
    planChip('NİYET', plan.intent),
    planChip('SINIF', plan.estimated_execution_class),
    planChip('TAZE ARAŞTIRMA', plan.requires_fresh_research ? 'GEREKLİ' : 'GEREKMİYOR'),
    planChip('ONAY', plan.approval_required ? 'GEREKLİ' : 'GEREKMİYOR'),
  ].join('');
  return `
    <h3>Yürütme Planı <span class="risk-badge risk-${escapeHtml(plan.risk)}">${escapeHtml(plan.status)}</span></h3>
    <p class="plan-request">${escapeHtml(plan.request)}</p>
    <p class="plan-status-text">${escapeHtml(statusText)}${plan.reason ? ' — ' + escapeHtml(plan.reason) : ''}</p>
    <div class="plan-chips">${chips}</div>
    ${renderPlanSteps(plan)}
    <dl class="plan-meta">
      <dt>Gerekli yetenekler</dt><dd>${escapeHtml(plan.required_capabilities.join(', ') || '—')}</dd>
      <dt>Bloke yetenekler</dt><dd>${blockedCaps.length ? `<span class="plan-flag plan-flag-blocked">${escapeHtml(blockedCaps.join(', '))}</span>` : '—'}</dd>
      <dt>Gerekli iç veri</dt><dd>${escapeHtml(plan.required_internal_data.join(', ') || '—')}</dd>
      <dt>Plan kimliği</dt><dd>${escapeHtml(plan.plan_id)}</dd>
    </dl>
    <p class="plan-note">Bu yalnızca bir plandır. Hiçbir adım çalıştırılmadı; model çağrısı yapılmadı (model_calls=${escapeHtml(String(plan.model_calls))}).</p>
  `;
}

async function requestPlan(message) {
  state.planInFlight = true;
  renderExecutionSurface();
  let result;
  try {
    const { ok, body } = await api('/api/plan', { method: 'POST', body: JSON.stringify({ message }) });
    if (!ok || !body) {
      state.lastPlan = null;
      state.lastRun = null;
      result = { error: (body && body.error) || 'bilinmeyen hata' };
    } else {
      state.lastPlan = body;
      // The runtime is not exposed over HTTP yet. If and when the backend
      // attaches its own RunRecord.to_dict() to this response under `run`,
      // every stage, domain card, evidence row and objection below starts
      // rendering from it with no further frontend change. Until then this
      // is null and the surface stays a labelled skeleton.
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

qs('analizForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = qs('analizInput').value.trim();
  if (!message) return;
  const target = qs('analizResult');
  target.innerHTML = '<p class="empty-note">Plan üretiliyor…</p>';
  const result = await requestPlan(message);
  target.innerHTML = result.error
    ? `<p class="empty-note">Plan üretilemedi: ${escapeHtml(result.error)}</p>`
    : renderPlan(result.plan);
});

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
    ${p.payload ? `<div class="evidence-block">${escapeHtml(JSON.stringify(p.payload, null, 2))}</div>` : ''}
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
      body: JSON.stringify({ message }),
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
  { id: 'crm', label: 'CRM' },
  { id: 'operations', label: 'OPERASYON' },
];
const DOMAIN_CAPS = DOMAIN_CARDS.map((d) => `${d.id}_analysis`);

const EXEC_STAGES = [
  { id: 'plan', label: 'PLAN', caps: [] },
  { id: 'domains', label: '5 DOMAIN', caps: DOMAIN_CAPS.concat(['internal_data_analysis']) },
  { id: 'fusion', label: 'KANIT BİRLEŞTİRME', caps: ['evidence_fusion'] },
  { id: 'signals', label: 'PROBLEM / FIRSAT', caps: ['problem_opportunity_analysis'] },
  { id: 'redteam', label: 'RED TEAM', caps: ['red_team_review'] },
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
    return ['RED TEAM', 'st-run', 'proposing'];
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
    else if (plan) { text = 'HAZIR'; cls = 'st-ready'; meta = plan.plan_id || ''; }
    else { text = 'PLAN YOK'; cls = 'st-absent'; }
    return { label, text, cls, meta };
  }
  if (!plan) return { label, text: 'PLAN YOK', cls: 'st-absent', meta: '' };

  const steps = planSteps().filter((s) => stage.caps.includes(s.capability));
  if (!steps.length) return { label, text: 'PLANDA YOK', cls: 'st-absent', meta: '' };
  if (stage.id === 'domains') label = `${steps.length} DOMAIN`;
  meta = steps.map((s) => s.step_id).join(' · ');

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
      <th>KAYNAK</th><th>DOMAIN</th><th>BULGU</th><th>KANIT REF</th>
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
    + `${escapeHtml(s.severity || '—')}</span><span class="pr-code">${escapeHtml(s.code || '')}</span>`
    + `${escapeHtml(s.summary || '')}</li>`;

  const objections = outputsByCapability('red_team_review')
    .flatMap((output) => output.objections || [])
    .map((o) => `<li><span class="pr-code">${escapeHtml(o.code || '')}</span>`
      + `${escapeHtml(o.detail || '')}<span class="dom-meta">${escapeHtml(o.step_id || '')}</span></li>`);

  const actions = ['human_review_proposal', 'action_plan']
    .flatMap((cap) => outputsByCapability(cap))
    .map((output) => {
      const payload = output.payload || {};
      const applied = output.submitted === true;
      return `<li><span class="pr-code">${escapeHtml(output.action_type || output.internal_intent || '—')}</span>`
        + `${escapeHtml(payload.reason || '')}`
        + `<span class="dom-meta">${applied ? 'gönderildi' : 'ÖNERİ — uygulanmadı, gönderilmedi'}`
        + `${output.submit_with ? ' · ' + escapeHtml(output.submit_with) : ''}</span></li>`;
    });

  const gaps = [];
  outputsByCapability('evidence_fusion').forEach((output) => {
    (output.missing_inputs || []).forEach((entry) => gaps.push(
      `<li><span class="pr-code">${escapeHtml(entry.status || '')}</span>`
      + `${escapeHtml(entry.reason || entry.capability || '')}`
      + `<span class="dom-meta">${escapeHtml(entry.step_id || '')}</span></li>`));
    if (output.needs_more_sources) {
      gaps.push(`<li><span class="pr-code">THIN_SOURCING</span>`
        + `bağımsız kaynak sayısı ${escapeHtml(String(output.independent_sources))}</li>`);
    }
  });
  outputsByCapability('problem_opportunity_analysis').forEach((output) => {
    (output.skipped || []).forEach((entry) => gaps.push(
      `<li><span class="pr-code">SKIPPED</span>${escapeHtml(entry.reason || entry.rule || '')}</li>`));
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
    listBlock(hasKind ? 'FIRSATLAR' : 'FIRSATLAR (INFO seviyeli sinyaller)',
      signals.filter(isOpportunity).map(signalItem), 'Fırsat sinyali yok.'),
    listBlock('RED TEAM İTİRAZLARI', objections, 'İtiraz kaydedilmedi.'),
    listBlock('ÖNERİLEN AKSİYONLAR', actions, 'Önerilen aksiyon yok.'),
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

  const source = state.lastRun ? 'yürütme kaydı (run)' : (state.lastPlan ? 'plan (/api/plan)' : '—');
  ['execSrc', 'domainGridSrc', 'evidenceSrc', 'proposedSrc'].forEach((id) => {
    const el = qs(id);
    if (el) el.textContent = 'kaynak: ' + source;
  });
  const domainSrc = qs('domainSrc');
  if (domainSrc) domainSrc.textContent = state.lastRun ? 'yürütme kaydı' : (state.lastPlan ? 'plan' : 'plan yok');

  renderRail();
  renderDomains();
  renderEvidence();
  renderProposed();

  qs('execNote').textContent = state.lastRun
    ? `Yürütme kaydı ${state.lastRun.run_id || ''} · durum ${state.lastRun.status || '—'}.`
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
const PANEL_SECTIONS = { veri: 1, ajanlar: 1, raporlar: 1, ayarlar: 1 };

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
      q.name, q.status === 'OK' ? `${q.rows} kayıt · ${q.latency_ms} ms`
        : (q.error || 'okunamadı'), q.status === 'OK' ? '' : 'is-bad')).join('');
    return card(dom.domain.toUpperCase(), rows,
                stateChip(`${dom.ok}/${dom.total}`));
  }).join('');
  const prov = (d.provenance || []).map((p) => kvRow(
    p.alan || p.error || '?', `${p.connection || '—'} · ${p.freshness || '—'}`,
    p.connection === 'CONNECTED' ? '' : 'is-warn')).join('');
  const qual = (d.quality || []).map((q) => kvRow(
    q.check || q.error || '?', q.passed === true ? 'GEÇTİ' : q.passed === false ? 'KALDI' : (q.detail || '—'),
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
      .map(([k, v]) => `${escapeHtml(k)}: ${v}`).join(' · ');
    return `<div class="kv${bos ? ' is-bad' : ''}">
      <span class="kv-k">${escapeHtml(String(c.role || '?'))}</span>
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
      <summary><strong>${escapeHtml(String(r.name || r.key || '?'))}</strong>
        <span class="kv-v">${escapeHtml(String(r.status || ''))}</span></summary>
      <p class="sect-note">${escapeHtml(String(r.job || ''))}</p>
      <p>${escapeHtml(String(r.statement || ''))}</p>
      ${r.reads && r.reads.length
        ? `<p class="sect-note">okuduğu veri: ${escapeHtml(r.reads.join(', '))}</p>`
        : ''}
    </details>`;
  return card('EKİP — KİM NE DİYOR', konusan.map(blok).join(''),
              `${konusan.length} üye konuştu`)
    + card('KONUŞAMAYANLAR', susan.map(blok).join(''),
           `${susan.length} üye`);
}

function renderAjanlar(d) {
  const roles = (d.roles || []).map((r) => kvRow(
    r.id || r.error || '?', r.kind || r.domain || '')).join('');
  const provs = (d.providers || []).map((p) => kvRow(
    p.provider || p.error || '?', p.state)).join('');
  const engines = (d.engines || []).map((e) => `<div class="kv">
      <span class="kv-k">${escapeHtml(String(e.name || e.error || '?'))}</span>
      <span class="kv-v">${stateChip(e.state || '—')} ${escapeHtml(String(e.version || ''))}</span>
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
      <span class="kv-v">${stuck ? 'BEKLEMEDE' : rate} · ${lesson.sample} vaka</span>
    </div>`;
  }).join('');
  const meta = `${block.decisions || 0} karar · ${block.model_calls || 0} model çağrısı`;
  return card('DERSLER', rows || '<p class="sect-note">Yeterli örneklem yok.</p>', meta)
    + `<p class="sect-note">${escapeHtml(String(block.note || ''))}</p>`;
}

function renderRaporlar(d) {
  const f = (d.findings || []).map((x) => `<div class="kv">
      <span class="kv-k">${escapeHtml(String(x.code))}</span>
      <span class="kv-v">${stateChip(x.severity || '—')} ${x.count}×</span>
    </div>${x.reason ? `<p class="sect-note">${escapeHtml(String(x.reason))}</p>` : ''}`).join('');
  const c = (d.cycle_results || []).map((x) => kvRow(x.result, `${x.count} döngü`)).join('');
  const last = d.last_cycle || {};
  const b = last.business || {};
  const lastRows = kvRow('döngü', last.cycle) + kvRow('sonuç', last.result)
    + kvRow('iş zekâsı', b.status ? `${b.status} · ${b.signals} sinyal` : '—')
    + kvRow('model çağrısı', last.model_calls) + kvRow('dış aksiyon', last.external_actions)
    + kvRow('süre', last.total_ms ? `${last.total_ms} ms` : '—');
  return renderLessons(d.lessons)
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
  const rows = (block.providers || []).map((p) => {
    const tok = (p.prompt_tokens || 0) + (p.completion_tokens || 0);
    return `<div class="kv${p.paid ? ' is-bad' : ''}">
      <span class="kv-k">${escapeHtml(String(p.provider))}${p.paid ? ' · ÜCRETLİ' : ''}</span>
      <span class="kv-v">${p.calls} çağrı · ${tok.toLocaleString('tr-TR')} token · ort ${p.avg_s}s${
        p.failed ? ` · ${p.failed} hata` : ''}</span>
    </div>`;
  }).join('');
  const meta = `${block.total_calls || 0} çağrı · ${block.paid_calls || 0} ücretli (7 gün)`;
  return card('MODEL KULLANIMI', rows || '<p class="sect-note">Kayıt yok.</p>', meta)
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
    + card('KILL SWITCH', `<pre class="sect-pre">${escapeHtml(String(d.kill_switch || ''))}</pre>`, '');
}

const SECTION_RENDERERS = { veri: renderVeri, ajanlar: renderAjanlar,
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
      : `<p class="sect-empty is-bad">Bölüm yüklenemedi (HTTP ${status}). ${escapeHtml(String((data && data.error) || ''))}</p>`;
    if (count) count.textContent = status === 401 ? 'oturum yok' : 'hata';
    return;
  }
  try {
    body.innerHTML = SECTION_RENDERERS[name](data);
    if (count) {
      count.textContent = name === 'veri'
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
        : `Fiyat matrisi yüklenemedi (HTTP ${status}). ` +
          String((data && data.error) || '');
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
      tally.innerHTML = `<li class="fm-t-bad">Önizleme üretilemedi (HTTP ${status}). ` +
        escapeHtml(String((body && body.error) || '')) + '</li>';
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
      // Onay kuyrugu ucu henuz yok. Olmayan bir seyi "gonderildi" diye
      // gostermek yalan olurdu; acikca soyleriz.
      const tally = qs('fmTally');
      if (tally) {
        tally.insertAdjacentHTML('beforeend',
          '<li class="fm-t-miss">Onay kuyruğuna gönderme ucu henüz bağlanmadı; ' +
          'hiçbir şey gönderilmedi.</li>');
      }
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
        : `Ürün alanları yüklenemedi (HTTP ${status}). ` +
          String((body && body.error) || '');
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
      const b = e.target.closest('.et-op');
      if (!b) return;
      // Duzenleme ucu henuz bagli degil. Olmayan bir seyi "kaydedildi"
      // diye gostermek yalan olurdu; acikca soyleriz.
      const foot = qs('etFoot');
      if (foot) {
        foot.className = 'fm-foot is-bad';
        foot.textContent = `"${b.dataset.alan}" alanı için düzenleme ucu ` +
          'henüz bağlanmadı — hiçbir değişiklik yapılmadı. Değişiklikler ' +
          'onay kuyruğundan geçecek şekilde kurulacak.';
      }
    });
  }
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
  ['Link tıklama', 'Siteye veya profile GİDEN gerçek tıklama. Asıl bakılması gereken budur.'],
  ['CTR', '"Click Through Rate" — tıklama ÷ gösterim. Reklamın ilgi çekme oranı. Düşükse görsel ya da ilk üç saniye tutmuyordur.'],
  ['CPM', '1000 gösterimin maliyeti. Kitleye ulaşmak ne kadara mal oluyor. Dar hedefleme CPM\'i yükseltir.'],
  ['CPC / TL per tıklama', 'Bir tıklamanın maliyeti. Harcama ÷ tıklama. Yüksekse ya reklam ilgi çekmiyordur ya hedef kitle pahalıdır.'],
  ['ROAS', '"Return On Ad Spend" — reklam harcamasının kaç katı ciro döndüğü. 3 ROAS = 1 TL harcayıp 3 TL ciro. <strong>Bizde şu an güvenilir hesaplanamıyor:</strong> Meta\'nın bildirdiği satışlar ticari olarak doğrulanmadı, GA4 verisi hiç akmıyor.'],
  ['CRM', '"Customer Relationship Management" — müşteri ilişkileri yönetimi. Bizde: müşteri konuşmaları, cevapsız mesajlar, hangi müşteri ne sormuş.'],
  ['CTA', '"Call To Action" — reklamın altındaki çağrı düğmesi. SHOP_NOW mağazaya, VIEW_INSTAGRAM_PROFILE profile, MESSAGE_PAGE mesaja götürür.'],
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
        : `Kreatif verisi yüklenemedi (HTTP ${status}).`;
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
      deger: '%' + krSayi(t.ctr, 2), ad: 'ORTALAMA LİNK CTR',
      // Sektor kiyasi YAZILMADI: elimizde olculmus bir referans yok ve
      // uydurulmus bir esik, karar verirken en tehlikeli seydir.
      anlam: 'Reklamı gören her 100 kişiden kaçı linke tıkladı. Tek başına "iyi" ya da "kötü" denemez: tıklamaların bir kısmı profil görüntülemesi, bir kısmı mağaza ziyareti — ikisi aynı değer taşımaz.',
      yap: 'Mağazaya giden tıklamaları ayrı izleyin. Karşılaştırmayı kendi geçmişinizle yapın; sektör ortalaması diye dolaşan rakamlar bizim hesabımız için ölçülmedi.',
      sinif: 'notr',
    },
    {
      deger: krSayi(t.birim, 2) + ' TL', ad: 'TIKLAMA BAŞINA MALİYET',
      anlam: 'Bir link tıklaması ortalama bu kadara mal oluyor. Harcama ÷ link tıklama.',
      // Donusum oranimiz BILINMIYOR (GA4 akmiyor, Meta satislari ticari
      // olarak dogrulanmadi). O yuzden "su kadara kadar mantikli" demiyoruz.
      yap: 'Bunun makul olup olmadığını söylemek için kaç tıklamadan bir satış çıktığını bilmek gerekir — o veri bizde henüz yok (GA4 akmıyor, Meta satışları doğrulanmadı). Önce dönüşüm ölçümünü kurun.',
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
      'doğrulanmadığı için ROAS burada hesaplanmıyor.';
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
      : `<p class="sect-empty is-bad">Hafıza okunamadı (HTTP ${status}). ${escapeHtml(String((data && data.error) || ''))}</p>`;
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
      hfMesajGoster(`Not yazılamadı (HTTP ${status}). ` +
                    String((body && body.error) || ''), true);
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
      hfMesajGoster(`Silinemedi (HTTP ${status}). ` +
                    String((body && body.error) || ''), true);
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
