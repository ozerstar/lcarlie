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
const VIEWS = { home: 'viewHome', analiz: 'viewAnaliz', gorevler: 'viewGorevler' };

function setView(name) {
  if (!VIEWS[name]) return;
  state.view = name;
  Object.entries(VIEWS).forEach(([key, id]) => { qs(id).hidden = key !== name; });
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.view === name);
  });
  if (name === 'gorevler') { refreshActivity(); refreshProposals(); }
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
    return;
  }

  const visual = body.visual_state || 'IDLE';
  const core = qs('jarvisCore');
  core.setAttribute('class', 'core-svg core-state-' + visual.toLowerCase());
  qs('coreStateLabel').textContent = CORE_STATE_TEXT[visual] || visual.replace(/_/g, ' ');

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
  const { ok, body } = await api('/api/plan', { method: 'POST', body: JSON.stringify({ message }) });
  if (!ok || !body) {
    return { error: (body && body.error) || 'bilinmeyen hata' };
  }
  return { plan: body };
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
function renderAnswerBody(body) {
  if (body.source === 'operator.list_pending' && Array.isArray(body.data) && body.data.length) {
    return `<p>${escapeHtml(body.text)}</p>` + body.data.map(renderProposalCard).join('');
  }
  if (body.source === 'operator.inspect' && body.data) {
    return renderProposalCard(body.data);
  }
  return renderMarkdownLite(body.text || '(boş yanıt)');
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

async function sendMessage(message) {
  message = (message || '').trim();
  if (!message) return;
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
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
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
        if (event.type === 'stage') {
          stageDiv.innerHTML = `<span class="stage-dot"></span> ${escapeHtml(event.label)}…`;
        } else if (event.type === 'done') {
          const result = event.result;
          if (result.kind === 'REQUIRES_REASONING_CAPABILITY') {
            stageDiv.className = 'chat-msg jarvis reasoning';
            stageDiv.innerHTML = escapeHtml(result.message);
          } else if (result.kind === 'ERROR') {
            stageDiv.className = 'chat-msg jarvis';
            stageDiv.innerHTML = 'Anlaşılamadı: ' + escapeHtml(result.message);
          } else {
            stageDiv.className = 'chat-msg jarvis';
            stageDiv.innerHTML = renderAnswerBody(result);
          }
        } else if (event.type === 'error') {
          stageDiv.innerHTML = 'Hata: ' + escapeHtml(event.message);
        }
      }
      log_scroll();
    }
  } catch (err) {
    if (err.name !== 'AbortError') stageDiv.innerHTML = 'Bağlantı kesildi.';
    else stageDiv.innerHTML = '(durduruldu)';
  } finally {
    qs('stopBtn').hidden = true;
    qs('sendBtn').disabled = false;
    qs('retryBtn').hidden = false;
    activeStreamController = null;
    refreshActivity();
  }
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

checkSession();
