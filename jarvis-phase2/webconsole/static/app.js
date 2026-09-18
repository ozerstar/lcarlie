'use strict';
/* L'CARLIE Jarvis Web Console frontend.
 * No secrets stored in localStorage/sessionStorage: only the CSRF token is
 * kept in memory (a JS variable), the session id lives in an HttpOnly
 * cookie the browser sends automatically and this code never reads. */

const state = {
  csrfToken: null,
  username: null,
  statusPollTimer: null,
  activityPollTimer: null,
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
  qs('chipOperator').querySelector('.state-value').textContent = state.username || '—';
  startPolling();
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
    const msg = status === 429 ? `Çok fazla deneme. ${body && body.retry_after_s ? body.retry_after_s + ' sn sonra tekrar deneyin.' : ''}`
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
  qs('chipTime').querySelector('.state-value').textContent =
    now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}
setInterval(tickClock, 1000);
tickClock();

/* ---------------- status + core visualization ---------------- */
function setChip(id, text, cls) {
  const el = qs(id);
  el.querySelector('.state-value').textContent = text;
  el.className = 'state-chip' + (cls ? ' ' + cls : '');
}

async function refreshStatus() {
  const { ok, body } = await api('/api/status');
  if (!ok || !body) return;

  const visual = (body.visual_state || 'IDLE').toLowerCase();
  const core = qs('jarvisCore');
  core.className = 'jarvis-core core-state-' + visual;
  qs('coreStateLabel').textContent = (body.visual_state || 'IDLE').replace('_', ' ');

  if (body.company_memory && body.company_memory.healthy) {
    setChip('chipMemory', 'SAĞLIKLI', 'state-ok');
  } else {
    setChip('chipMemory', 'HATA', 'state-error');
  }

  if (visual === 'offline') setChip('chipJarvis', 'ÇEVRİMDIŞI', 'state-error');
  else if (visual === 'waiting_approval') setChip('chipJarvis', 'ONAY BEKLİYOR', 'state-warn');
  else if (visual === 'proposing') setChip('chipJarvis', 'ÖNERİYOR', 'state-active');
  else setChip('chipJarvis', 'AKTİF', 'state-ok');

  const firewallOk = body.action_firewall && body.action_firewall.contract_valid;
  setChip('chipFirewall', firewallOk ? 'GEÇERLİ' : 'BİLİNMİYOR', firewallOk ? 'state-ok' : 'state-warn');
}

/* ---------------- activity feed ---------------- */
function classifyAudit(row) {
  if (row.result === 'PROPOSED') return 'a-proposed';
  if (row.result === 'CLAIM_FAILED' || row.result === 'FIREWALL_REJECTED') return 'a-error';
  return 'a-noop';
}
function formatAuditLine(row) {
  const map = {
    NOOP: 'Company Memory kontrol edildi — değişiklik yok',
    PROPOSED: `Öneri oluşturuldu (${row.task_detail && row.task_detail.action_type || '—'})`,
    SKIPPED_NOT_MINE: 'Farklı bir görev tipi tespit edildi, dokunulmadı',
    FIREWALL_REJECTED: 'Bir görev firewall tarafından reddedildi',
    CLAIM_FAILED: 'Görev alma başarısız',
  };
  return map[row.result] || row.result;
}

async function refreshActivity() {
  const { ok, body } = await api('/api/activity?limit=25');
  if (!ok || !body) return;
  const feed = qs('activityFeed');
  feed.innerHTML = '';
  const merged = [];
  (body.audit || []).slice().reverse().forEach((a) => merged.push({
    time: a.observed_at || '', cls: classifyAudit(a), text: formatAuditLine(a),
  }));
  (body.findings || []).slice().reverse().forEach((f) => merged.push({
    time: f.observed_at || '', cls: 'a-issue', text: `Bulgu: ${f.reason}`,
  }));
  merged.sort((a, b) => (a.time < b.time ? 1 : -1));
  merged.slice(0, 30).forEach((item) => {
    const li = document.createElement('li');
    li.className = item.cls;
    const time = document.createElement('span');
    time.className = 'a-time';
    time.textContent = item.time ? new Date(item.time).toLocaleString('tr-TR') : '';
    li.appendChild(time);
    li.appendChild(document.createTextNode(item.text));
    feed.appendChild(li);
  });
  if (!merged.length) {
    feed.innerHTML = '<li class="a-noop">Henüz kayıtlı etkinlik yok.</li>';
  }
}

/* ---------------- proposals ---------------- */
async function refreshProposals() {
  const { ok, body } = await api('/api/proposals');
  const list = qs('proposalList');
  const empty = qs('proposalEmpty');
  if (!ok || !body) return;
  const pending = body.pending || [];
  list.innerHTML = '';
  empty.hidden = pending.length > 0;
  pending.forEach((p) => {
    const li = document.createElement('li');
    li.className = 'proposal-card';
    li.innerHTML = `
      <div class="p-type">${p.action_type} <span class="risk-badge risk-${p.risk_class}">${p.risk_class}</span></div>
      <div class="p-meta">#${p.action_id} · ${new Date(p.proposed_at).toLocaleString('tr-TR')}</div>
    `;
    li.addEventListener('click', () => openProposal(p.action_id));
    list.appendChild(li);
  });
}

async function openProposal(actionId) {
  const { ok, body } = await api('/api/proposals/' + actionId);
  if (!ok || !body) return;
  const modal = qs('proposalModal');
  const content = qs('modalBody');
  content.innerHTML = `
    <h3>${body.action_type} <span class="risk-badge risk-${body.risk_class}">${body.risk_class}</span></h3>
    <p><strong>#${body.action_id}</strong> · görev ${body.task_id} · ${new Date(body.proposed_at).toLocaleString('tr-TR')}</p>
    <p>Son geçerlilik: ${new Date(body.expires_at).toLocaleString('tr-TR')}</p>
    <div class="evidence-block">${JSON.stringify(body.payload, null, 2)}</div>
    <label class="reason-label">Gerekçe
      <input id="decisionReason" type="text" class="reason-input">
    </label>
    <div class="modal-actions">
      <button class="btn-approve" id="btnApprove">Onayla</button>
      <button class="btn-reject" id="btnReject">Reddet</button>
    </div>
  `;
  qs('btnApprove').addEventListener('click', () => decide(actionId, 'APPROVED'));
  qs('btnReject').addEventListener('click', () => decide(actionId, 'REJECTED'));
  modal.hidden = false;
}

async function decide(actionId, decision) {
  const reason = qs('decisionReason').value.trim() || (decision === 'APPROVED' ? 'Operatör onayı' : 'Operatör reddi');
  const { ok, body } = await api(`/api/proposals/${actionId}/decide`, {
    method: 'POST', body: JSON.stringify({ decision, reason }),
  });
  qs('proposalModal').hidden = true;
  if (ok) {
    addChatMessage('jarvis', `Proposal ${actionId} ${decision === 'APPROVED' ? 'onaylandı' : 'reddedildi'}.`);
    refreshProposals();
    refreshActivity();
  } else {
    addChatMessage('jarvis', `Karar kaydedilemedi: ${body && body.error}`);
  }
}

qs('modalClose').addEventListener('click', () => { qs('proposalModal').hidden = true; });
qs('proposalModal').addEventListener('click', (e) => { if (e.target.id === 'proposalModal') qs('proposalModal').hidden = true; });

/* ---------------- chat: minimal, dependency-free Markdown ----------------
 * Escapes HTML first (XSS-safe), then applies a small set of transforms.
 * Deliberately not a full CommonMark implementation -- covers what Jarvis's
 * grounded answers actually produce: headings, bold, inline code, code
 * blocks, lists, simple tables. */
function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
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
    <div class="p-type">${p.action_type} <span class="risk-badge risk-${p.risk_class}">${p.risk_class}</span></div>
    <div class="p-meta">#${p.action_id} · ${p.proposed_at ? new Date(p.proposed_at).toLocaleString('tr-TR') : ''}</div>
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
  const div = document.createElement('div');
  div.className = 'chat-msg ' + role + (cls ? ' ' + cls : '');
  div.innerHTML = html;
  if (role === 'jarvis') {
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.type = 'button';
    copyBtn.textContent = 'Kopyala';
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

checkSession();
