'use strict';

const $ = (id) => document.getElementById(id);
const state = { csrf: null, busy: false, audio: null, audioUrl: null, audioGeneration: 0, action: null,
  chatMode: 'work', personalTab: 'today', chatRows: { work: [], personal: [] }, attachment: null, googleProposal: null,
  contactEditId: null };
let voiceMode = false;
let selectedProposal = null;
const PENDING_CHAT_KEY = 'jarvis-pending-chat-v1';

function rememberChatTurn(turn) {
  try { sessionStorage.setItem(PENDING_CHAT_KEY, JSON.stringify({id: turn.id, mode: turn.mode,
    text: turn.text, attachmentId: turn.attachmentId, at: Date.now()})); } catch (_) { /* private mode */ }
}
function forgetChatTurn() {
  try { sessionStorage.removeItem(PENDING_CHAT_KEY); } catch (_) { /* private mode */ }
}
function pendingChatTurn() {
  try {
    const turn = JSON.parse(sessionStorage.getItem(PENDING_CHAT_KEY) || 'null');
    if (turn && Date.now() - turn.at < 24 * 60 * 60 * 1000 && /^[0-9a-f-]{36}$/.test(turn.id)
        && ['work', 'personal'].includes(turn.mode) && typeof turn.text === 'string') return turn;
  } catch (_) { /* no stored turn */ }
  forgetChatTurn();
  return null;
}
function responseWasRejected(error) { return error?.nonRetryable === true; }

function status(message) {
  const shown = friendlyMessage(message);
  $('status').textContent = shown;
  $('status').dataset.state = /hata|kesildi|açılamadı|algılanamadı|gerekli|tamamlanamadı/i.test(shown) ? 'error'
    : /dinliyor|düşünüyor/i.test(shown) ? 'busy' : 'ready';
}

function friendlyMessage(value, fallback = 'İşlem tamamlanamadı. Lütfen tekrar deneyin.') {
  const message = String(value || '').trim();
  if (!message) return fallback;
  if (/^(?:HTTP\s*\d+|JSON|SyntaxError|TypeError|Traceback|Internal Server Error)/i.test(message) ||
      /(?:parse error|unexpected token|unexpected identifier|undefined|null reference|postgres:|\/opt\/)/i.test(message)) return fallback;
  return message;
}

function approvalSummary(reason) {
  const text = String(reason || '').trim();
  if (/^CodingExecutor/i.test(text)) return 'Kod değişikliği önerildi. İnceleyip karar vermeniz gerekiyor.';
  const first = text.split('\n').map((line) => line.trim())
    .find((line) => line && !line.startsWith('/') && !/^(?:ONAY|RET)\s*=/.test(line)) || '';
  const summary = first.replace(/^[A-ZÇĞİÖŞÜ _]+\s*[—:]\s*/, '').trim();
  if (!summary || /(?:\{|\}|\[[^\]]*\]|\/opt\/|postgres:|\.json\b|_[a-z]+_)/i.test(summary))
    return 'Yeni bir öneri var. Ayrıntıları inceleyip karar verin.';
  return summary.slice(0, 180);
}
function showLogin() { $('login').hidden = false; $('app').hidden = true; $('logout').hidden = true; status('Giriş gerekli'); }
function showApp() {
  $('login').hidden = true; $('app').hidden = false; $('logout').hidden = false;
  status('Bağlı'); refreshMobile(); refreshPushStatus();
  const tab = new URLSearchParams(location.search).get('tab');
  if (['approvals', 'creative', 'jobs', 'chat'].includes(tab)) document.querySelector(`[data-tab="${tab}"]`).click();
  if (tab === 'chat' && new URLSearchParams(location.search).get('mode') === 'personal')
    document.querySelector('[data-chat-mode="personal"]').click();
  if (new URLSearchParams(location.search).has('google')) {
    status(new URLSearchParams(location.search).get('google') === 'connected' ? 'Google hesabı bağlandı' : 'Google hesabı bağlanamadı');
    history.replaceState(null, '', '/mobile/index.html?tab=chat&mode=personal');
  }
  const unfinished = pendingChatTurn();
  if (unfinished && !state.busy) {
    document.querySelector('[data-tab="chat"]').click();
    if (state.chatMode !== unfinished.mode)
      document.querySelector(`[data-chat-mode="${unfinished.mode}"]`).click();
    sendMessage(unfinished.text, unfinished);
  }
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.csrf && options.method === 'POST') headers['X-CSRF-Token'] = state.csrf;
  const response = await fetch(path, { credentials: 'same-origin', ...options, headers });
  if (response.status === 401) { state.csrf = null; showLogin(); }
  return response;
}

async function checkSession() {
  try {
    const response = await request('/api/session');
    const body = await response.json();
    if (body.authenticated) { state.csrf = body.csrf_token; showApp(); }
    else showLogin();
  } catch (_) { showLogin(); $('login-error').textContent = 'Sunucuya bağlanılamadı.'; $('login-error').hidden = false; }
}

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('login-error').hidden = true;
  try {
    const response = await request('/api/login', { method: 'POST', body: JSON.stringify({ username: $('username').value.trim(), password: $('password').value }) });
    const body = await response.json();
    if (!response.ok || !body.ok) throw new Error(response.status === 429 ? 'Çok fazla deneme. Biraz sonra tekrar dene.' : 'Giriş bilgileri hatalı.');
    state.csrf = body.csrf_token;
    $('password').value = '';
    showApp();
  } catch (error) { $('login-error').textContent = error.message || 'Giriş yapılamadı.'; $('login-error').hidden = false; }
});

$('logout').addEventListener('click', async () => {
  stopAudio();
  try { await request('/api/logout', { method: 'POST' }); } catch (_) { /* session still expires */ }
  state.csrf = null;
  showLogin();
});

$('password-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const result = $('password-result');
  result.hidden = true;
  result.classList.remove('error');
  const currentPassword = $('current-password').value;
  const newPassword = $('new-password').value;
  if (newPassword.length < 6 || newPassword !== $('confirm-password').value) {
    result.textContent = 'Yeni parola en az 6 karakter olmalı ve iki giriş aynı olmalı.';
    result.classList.add('error');
    result.hidden = false;
    return;
  }
  try {
    const response = await request('/api/account/password', {
      method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!response.ok) throw new Error(response.status === 403 ? 'Mevcut parola hatalı.' : 'Parola değiştirilemedi.');
    $('password-form').reset();
    state.csrf = null;
    showLogin();
    $('login-error').textContent = 'Parola değişti. Yeni parolanla tekrar giriş yap.';
    $('login-error').hidden = false;
  } catch (error) {
    $('current-password').value = '';
    result.textContent = error.message || 'Parola değiştirilemedi.';
    result.classList.add('error');
    result.hidden = false;
  }
});

function pushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

function pushMessage(message) { $('push-status').textContent = message; }

async function refreshPushStatus() {
  if (!pushSupported()) { pushMessage('Bu tarayıcı telefon bildirimlerini desteklemiyor.'); return; }
  try {
    const registration = await navigator.serviceWorker.register('/mobile/sw.js', { scope: '/mobile/' });
    const subscription = await registration.pushManager.getSubscription();
    const active = Boolean(subscription && Notification.permission === 'granted');
    if (active && state.csrf) await readApi('/api/push/subscribe', {
      method: 'POST', body: JSON.stringify(subscription.toJSON()),
    });
    $('push-enable').hidden = active;
    $('push-test').hidden = !active;
    $('push-disable').hidden = !active;
    pushMessage(active ? 'Bildirimler bu telefonda açık.' : 'Bildirimler bu telefonda kapalı.');
  } catch (_) { pushMessage('Bildirim durumu kontrol edilemedi.'); }
}

function pushKeyBytes(value) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=');
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

$('push-enable').addEventListener('click', async () => {
  if (!pushSupported()) { pushMessage('Bu tarayıcı bildirimleri desteklemiyor.'); return; }
  if (/iPhone|iPad|iPod/.test(navigator.userAgent) &&
      !navigator.standalone && !window.matchMedia('(display-mode: standalone)').matches) {
    pushMessage('Önce Safari paylaş menüsünden Ana Ekran’a Ekle; ardından Jarvis simgesinden aç.');
    return;
  }
  const permissionRequest = Notification.requestPermission();
  try {
    const permission = await permissionRequest;
    if (permission !== 'granted') { pushMessage('Bildirim izni verilmedi. Telefon ayarlarından izin ver.'); return; }
    const registration = await navigator.serviceWorker.register('/mobile/sw.js', { scope: '/mobile/' });
    const config = await readApi('/api/push/config');
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: pushKeyBytes(config.public_key),
    });
    await readApi('/api/push/subscribe', { method: 'POST', body: JSON.stringify(subscription.toJSON()) });
    await refreshPushStatus();
    pushMessage('Bildirimler açıldı. Test düğmesiyle deneyebilirsin.');
  } catch (_) { pushMessage('Bildirimler açılamadı. Ana ekran uygulaması ve telefon iznini kontrol et.'); }
});

$('push-test').addEventListener('click', async () => {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) throw new Error('subscription missing');
    await readApi('/api/push/test', {
      method: 'POST', body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    pushMessage('Test bildirimi gönderim servisine kabul edildi. Telefona ulaşıp ulaşmadığını kontrol et.');
  } catch (_) { pushMessage('Test bildirimi gönderilemedi.'); }
});

$('push-disable').addEventListener('click', async () => {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await readApi('/api/push/unsubscribe', {
        method: 'POST', body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
      await subscription.unsubscribe();
    }
    await refreshPushStatus();
  } catch (_) { pushMessage('Bildirimler kapatılamadı; tekrar dene.'); }
});

function bubble(kind, text) {
  const node = document.createElement('div');
  node.className = `bubble ${kind}`;
  const content = document.createElement('div');
  content.textContent = text;
  node.append(content);
  state.chatRows[state.chatMode].push(node);
  $('messages').append(node);
  updateChatStarters();
  node.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return { node, content };
}

function updateChatStarters() {
  const visible = state.chatRows[state.chatMode].length === 0 &&
    (state.chatMode !== 'personal' || state.personalTab === 'chat');
  $('chat-starters').hidden = !visible;
  document.querySelectorAll('[data-starter-mode]').forEach((group) => {
    group.hidden = group.dataset.starterMode !== state.chatMode;
  });
}

document.querySelectorAll('[data-starter]').forEach((button) => button.addEventListener('click', () => {
  $('chat-input').value = button.dataset.starter;
  $('chat-input').focus();
}));

function stopAudio() {
  state.audioGeneration += 1;
  if (state.audio) {
    state.audio.pause();
    if (typeof state.audio.onended === 'function') state.audio.onended();
    state.audio = null;
  }
  if (state.audioUrl) { URL.revokeObjectURL(state.audioUrl); state.audioUrl = null; }
}

function speechChunks(text) {
  const clean = String(text || '').replace(/```[\s\S]*?```/g, ' ').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/[*_`#>|]/g, ' ').replace(/\s+/g, ' ').trim();
  const sentences = clean.match(/[^.!?…]+[.!?…]*/g) || [clean];
  const chunks = [];
  let current = '';
  for (const sentence of sentences) {
    if ((current + sentence).length > 280 && current) { chunks.push(current.trim()); current = sentence; }
    else current += sentence;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.flatMap((chunk) => chunk.length <= 800 ? [chunk] : chunk.match(/.{1,700}/g) || []);
}

async function playAnswer(text, button) {
  if (state.audio && button.textContent === 'Durdur') { stopAudio(); button.textContent = 'Dinle'; return; }
  stopAudio();
  const generation = state.audioGeneration;
  button.textContent = 'Yükleniyor';
  button.disabled = true;
  try {
    for (const chunk of speechChunks(text)) {
      const response = await request('/api/voice/synthesize', { method: 'POST', body: JSON.stringify({ text: chunk }) });
      if (!response.ok) throw new Error('Ses servisine bağlanılamadı.');
      state.audioUrl = URL.createObjectURL(await response.blob());
      state.audio = new Audio(state.audioUrl);
      button.textContent = 'Durdur';
      button.disabled = false;
      await new Promise((resolve, reject) => {
        state.audio.onended = resolve;
        state.audio.onerror = reject;
        state.audio.play().catch(reject);
      });
      if (generation !== state.audioGeneration) return;
      state.audio = null;
      URL.revokeObjectURL(state.audioUrl);
      state.audioUrl = null;
      button.disabled = true;
    }
  } catch (_) { status('Ses açılamadı'); }
  stopAudio();
  button.textContent = 'Dinle';
  button.disabled = false;
}

function addPlayButton(row, text) {
  if (!text) return null;
  const meta = document.createElement('div');
  meta.className = 'meta';
  const label = document.createElement('span');
  label.textContent = 'JARVIS · TÜRKÇE SES';
  const button = document.createElement('button');
  button.className = 'play';
  button.textContent = 'Dinle';
  button.addEventListener('click', () => playAnswer(text, button));
  meta.append(label, button);
  row.node.append(meta);
  return button;
}

async function sendMessage(text, previous = null) {
  if (!state.csrf || state.busy || !text) return;
  const turn = previous || {id: crypto.randomUUID(), mode: state.chatMode, text,
    attachmentId: state.chatMode === 'personal' ? state.attachment?.id : null};
  state.busy = true;
  $('send').disabled = true;
  status('Düşünüyor');
  if (!previous?.row) bubble('user', text);
  const row = previous?.row || bubble('jarvis', 'Yanıt hazırlanıyor…');
  row.content.textContent = 'Yanıt hazırlanıyor…';
  rememberChatTurn(turn);
  const mode = turn.mode;
  let answer = '';
  let streamed = previous?.streamed || '';
  let after = previous?.after || 0;
  let terminal = false;
  try {
    for (let attempt = 0; attempt < 3 && !terminal; attempt++) {
      if (attempt) { status('Bağlantı yenileniyor'); await new Promise((resolve) => setTimeout(resolve, attempt * 700)); }
      try {
      const response = await request('/api/chat/stream', { method: 'POST', body: JSON.stringify({
        turn_id: turn.id, message: turn.text, mode, attachment_id: turn.attachmentId, after }) });
      if (!response.ok) {
        let detail = '';
        try { detail = (await response.json()).error || ''; } catch (_) { /* proxy response */ }
        const error = new Error(response.status === 401 ? 'Oturum sona erdi. Giriş yaptıktan sonra yanıtı kontrol edin.'
          : friendlyMessage(detail, 'Sohbet şu anda açılamadı. Yanıtı biraz sonra kontrol edin.'));
        error.nonRetryable = response.status >= 400 && response.status < 500;
        throw error;
      }
      if (!response.body || !response.headers.get('content-type')?.includes('application/x-ndjson'))
        throw new Error('Sohbet yanıtı okunamadı. Yanıtı biraz sonra kontrol edin.');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        pending += decoder.decode(part.value, { stream: true });
        let end;
        while ((end = pending.indexOf('\n')) >= 0) {
          const line = pending.slice(0, end).trim();
          pending = pending.slice(end + 1);
          if (!line) continue;
          let item;
          try { item = JSON.parse(line); }
          catch (_) { throw new Error('Yanıtın bir bölümü okunamadı. Aynı konuşmaya yeniden bağlanılıyor.'); }
          if (item.seq && item.seq <= after) continue;
          if (item.seq) after = item.seq;
        if (item.type === 'stage') row.content.textContent = `${item.label}…`;
        if (item.type === 'token') { streamed += item.delta || ''; row.content.textContent = streamed; }
        if (item.type === 'done') {
          terminal = true;
          answer = item.result?.text || item.result?.message || streamed;
          if (item.result?.source === 'operator.list_pending') {
            const count = Array.isArray(item.result.data) ? item.result.data.length : 0;
            answer = count ? `${count} öneri onayınızı bekliyor. Onaylar bölümünden inceleyebilirsiniz.` : 'Bekleyen onay yok.';
          }
          answer = friendlyMessage(answer, 'Jarvis yanıt veremedi. Lütfen tekrar deneyin.');
          row.content.textContent = answer;
          if (mode === 'work' && item.result?.source === 'kreatif.inceleme') {
            const open = document.createElement('button');
            open.className = 'chat-open-creative'; open.textContent = 'Görselleri aç';
            open.addEventListener('click', () => document.querySelector('[data-tab="creative"]').click());
            row.node.append(open);
            if (item.result.data?.incelenen > 0) {
              const assign = document.createElement('button');
              assign.className = 'chat-assign-creative'; assign.textContent = 'Ekibe düzeltme görevi ver';
              assign.addEventListener('click', async () => {
                if (!window.confirm('Görselli çalışmalar için seçim ve düzeltme isteğini kreatif ekibe iletmek istiyor musun?')) return;
                assign.disabled = true; assign.textContent = 'Kaydediliyor…';
                try {
                  const result = await readApi('/api/kreatif-gorev', {
                    method: 'POST', body: JSON.stringify({tur: 'en_iyileri_sec_ve_duzelt'}) });
                  assign.textContent = 'Görev kaydedildi';
                  const note = document.createElement('p'); note.className = 'chat-task-result';
                  note.textContent = result.message; row.node.append(note);
                } catch (error) {
                  assign.disabled = false; assign.textContent = 'Ekibe düzeltme görevi ver';
                  status(friendlyMessage(error.message, 'Görev kaydedilemedi. Tekrar deneyin.'));
                }
              });
              row.node.append(assign);
            }
          }
        }
          if (item.type === 'error') {
            terminal = true;
            answer = friendlyMessage(item.message, 'Yanıt tamamlanamadı. İşlem durumunu kontrol edin.');
            row.content.textContent = answer;
          }
        }
        row.node.scrollIntoView({ block: 'end' });
      }
      } finally { reader.releaseLock(); }
      } catch (error) {
        if (attempt === 2 || responseWasRejected(error)) throw error;
      }
    }
    if (!terminal) throw new Error('Bağlantı kesildi. Yanıtı kontrol et; mesaj tekrar gönderilmedi.');
    forgetChatTurn();
    const playButton = answer && !/durumunu kontrol|tamamlanamadı/i.test(answer) ? addPlayButton(row, answer) : null;
    if (voiceMode && playButton) { voiceMode = false; playAnswer(answer, playButton); }
    status(/tamamlanamadı|kontrol edin/i.test(answer) ? answer : 'Bağlı');
  } catch (error) {
    row.content.textContent = friendlyMessage(error.message, 'Bağlantı kesildi. Yanıtı kontrol et.');
    if (!row.node.querySelector('.chat-resume')) {
      const resume = document.createElement('button'); resume.type = 'button';
      resume.className = 'chat-resume secondary'; resume.textContent = 'Yanıtı kontrol et';
      resume.addEventListener('click', () => { resume.remove(); sendMessage(text, {...turn, row, after, streamed}); });
      row.node.append(resume);
    }
    status('Bağlantı kesildi; mesaj tekrar gönderilmedi'); voiceMode = false;
  }
  finally { state.busy = false; $('send').disabled = false; if (mode === 'personal') clearAttachment(); }
}

document.querySelectorAll('[data-chat-mode]').forEach((button) => button.addEventListener('click', () => {
  if (state.busy || button.dataset.chatMode === state.chatMode) return;
  stopAudio();
  state.chatMode = button.dataset.chatMode;
  document.querySelectorAll('[data-chat-mode]').forEach((item) => {
    const active = item.dataset.chatMode === state.chatMode;
    item.classList.toggle('active', active);
    item.setAttribute('aria-pressed', String(active));
  });
  $('messages').replaceChildren(...state.chatRows[state.chatMode]);
  $('chat-mode-help').textContent = state.chatMode === 'personal'
    ? 'Kişisel konuşmalar ayrı saklanır. Jarvis burada şirket kayıtlarını ve iş onaylarını kullanmaz.'
    : 'Şirket verileri, görevler ve onaylar bu alandadır. İşlemler için onayınız gerekir.';
  $('chat-input').placeholder = state.chatMode === 'personal' ? 'Kişisel asistana yaz…' : 'İş için Jarvis’e yaz…';
  $('personal-tools').hidden = state.chatMode !== 'personal';
  showPersonalTab(state.personalTab);
  updateChatStarters();
  clearAttachment();
  if (state.chatMode === 'personal') { loadPersonalOverview(); loadReminders(); loadMemory(); loadContacts(); loadGoogle(); loadNotificationSettings(); }
}));

function showPersonalTab(name) {
  state.personalTab = name;
  document.querySelectorAll('[data-personal-tab]').forEach((button) => {
    const active = button.dataset.personalTab === name;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  document.querySelectorAll('[data-personal-pane]').forEach((pane) => {
    pane.hidden = pane.dataset.personalPane !== name;
  });
  const showChat = state.chatMode !== 'personal' || name === 'chat';
  for (const id of ['messages', 'chat-form', 'chat-actions', 'chat-starters', 'chat-help']) $(id).hidden = !showChat;
  updateChatStarters();
}
document.querySelectorAll('[data-personal-tab]').forEach((button) => button.addEventListener('click', () => {
  showPersonalTab(button.dataset.personalTab);
  if (button.dataset.personalTab === 'today') loadPersonalOverview();
}));

function briefSection(container, title, rows, fallback) {
  const section = document.createElement('section'); section.className = 'personal-brief-section';
  const heading = document.createElement('h3'); heading.textContent = title; section.append(heading);
  if (!rows.length) { const text = document.createElement('p'); text.textContent = fallback; section.append(text); }
  for (const [label, detail] of rows) {
    const item = document.createElement('div'); item.className = 'personal-brief-row';
    const strong = document.createElement('strong'); strong.textContent = label;
    const small = document.createElement('small'); small.textContent = detail;
    item.append(strong, small); section.append(item);
  }
  container.append(section);
}

async function loadPersonalOverview() {
  const today = $('personal-today-list'); const evening = $('personal-evening-list');
  try {
    const data = await readApi('/api/mobile/personal/overview');
    $('personal-date').textContent = new Date(`${data.date}T12:00:00`).toLocaleDateString('tr-TR',
      {weekday:'long', day:'numeric', month:'long'});
    today.replaceChildren(); evening.replaceChildren();
    briefSection(today, 'Özel günler', (data.special_days || []).map((item) =>
      [item.name, item.occasion || 'Doğum günü']), 'Bugün kayıtlı özel gün yok.');
    briefSection(today, 'Takvim', (data.today_events || []).map((item) => [item.title,
      item.start?.length > 10 ? new Date(item.start).toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit'}) : 'Tüm gün']),
      data.calendar_error ? 'Takvim şu anda okunamadı.' : data.calendar_connected ? 'Bugün etkinlik yok.' : 'Google Takvim bağlı değil.');
    briefSection(today, 'Hatırlatıcılar', (data.today_reminders || []).map((item) => [item.text,
      new Date(item.due_at).toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit'})]), 'Bugün hatırlatıcı yok.');
    if (data.overdue_reminders?.length) briefSection(today, 'Gecikenler', data.overdue_reminders.map((item) =>
      [item.text, new Date(item.due_at).toLocaleDateString('tr-TR')]), '');
    briefSection(today, `Karar bekleyenler · ${(data.pending || []).length}`, (data.pending || []).slice(0, 5).map((item) =>
      [item.kind === 'gmail.send' ? 'E-posta' : item.kind === 'drive.upload' ? 'Drive' : 'Takvim', item.description.split('\n')[0]]),
      'Kişisel işlem onayı beklemiyor.');
    briefSection(evening, 'Bugün yapılanlar', (data.activities || []).slice(-5).reverse().map((item) =>
      [item.summary, new Date(item.at).toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit'})]),
      'Bugün uygulamada kaydedilen kişisel işlem yok.');
    briefSection(evening, 'Yarın', [...(data.tomorrow_events || []).map((item) => [item.title, 'Takvim']),
      ...(data.tomorrow_reminders || []).map((item) => [item.text, 'Hatırlatıcı'])], 'Yarın için kayıtlı plan yok.');
  } catch (_) { today.textContent = 'Kişisel özet yüklenemedi.'; evening.replaceChildren(); }
}

document.querySelectorAll('[data-personal-quick]').forEach((button) => button.addEventListener('click', () => {
  const action = button.dataset.personalQuick;
  showPersonalTab(action === 'reminder' ? 'reminders' : 'google');
  if (action === 'reminder') $('reminder-text').focus();
  if (action === 'drive') { $('drive-details').open = true; $('drive-query').focus(); }
  if (action === 'email') { $('email-details').open = true; $('email-to').focus(); }
}));

function clearAttachment() {
  state.attachment = null;
  $('personal-file').value = '';
  $('file-status').textContent = 'JPG, PNG, PDF veya metin · En fazla 5 MB';
  $('file-preview').hidden = true;
  $('vision-button').hidden = true;
}

$('personal-file').addEventListener('change', async () => {
  const file = $('personal-file').files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { clearAttachment(); status('Dosya en fazla 5 MB olabilir.'); return; }
  $('file-status').textContent = 'Dosya yükleniyor…';
  try {
    const result = await readApi('/api/mobile/upload', { method: 'POST', body: file,
      headers: { 'Content-Type': 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) } });
    state.attachment = result;
    $('file-status').textContent = `${result.name} hazır. ${result.kind === 'image' ? 'Analiz et düğmesine dokun.' : 'Sorunu yazıp gönder.'}`;
    if (result.kind === 'image') { $('file-preview').src = result.url; $('file-preview').hidden = false; $('vision-button').hidden = false; }
  } catch (error) { clearAttachment(); status(friendlyMessage(error.message)); }
});

$('vision-button').addEventListener('click', async () => {
  if (!state.attachment || state.busy) return;
  const button = $('vision-button'); button.disabled = true; button.textContent = 'İnceleniyor…';
  const question = $('chat-input').value.trim() || 'Bu görselde ne var? Sorunları sade anlat.';
  try {
    const result = await readApi('/api/mobile/vision', { method: 'POST', body: JSON.stringify({
      attachment_id: state.attachment.id, question, consent: true }) });
    bubble('user', `${state.attachment.name}: ${question}`);
    const row = bubble('jarvis', result.answer); addPlayButton(row, result.answer);
    $('chat-input').value = ''; clearAttachment();
  } catch (error) { status(friendlyMessage(error.message)); }
  finally { button.disabled = false; button.textContent = 'Görseli analiz et'; }
});

async function loadReminders() {
  try {
    const data = await readApi('/api/mobile/reminders'); const list = $('reminder-list'); list.replaceChildren();
    const rows = data.reminders || [];
    if (!rows.length) { empty(list, 'Henüz hatırlatıcı yok.'); return; }
    for (const item of rows.slice().reverse()) {
      const repeatLabel = {none: 'Bir kez', daily: 'Her gün', weekly: 'Her hafta', monthly: 'Her ay'}[item.repeat || 'none'];
      const card = mobileCard(item.text, `${new Date(item.due_at).toLocaleString('tr-TR')} · ${repeatLabel}`,
        new Date(item.due_at) <= new Date() ? 'Zamanı geldi' : 'Bekliyor');
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = 'Düzenle';
      edit.addEventListener('click', () => {
        state.reminderEditId = item.id;
        $('reminder-text').value = item.text;
        const local = new Date(new Date(item.due_at).getTime() - new Date(item.due_at).getTimezoneOffset() * 60000);
        $('reminder-time').value = local.toISOString().slice(0, 16);
        $('reminder-repeat').value = item.repeat || 'none';
        $('reminder-save').textContent = 'Değişiklikleri kaydet';
        $('reminder-cancel').hidden = false;
        $('reminder-text').focus();
      });
      const del = document.createElement('button'); del.type = 'button'; del.className = 'secondary'; del.textContent = 'Sil';
      del.addEventListener('click', async () => { try { await readApi('/api/mobile/reminders', {method:'POST', body:JSON.stringify({action:'delete', id:item.id})}); loadReminders(); loadDailySummary(); } catch (error) { status(friendlyMessage(error.message)); } });
      card.append(edit, del); list.append(card);
    }
  } catch (_) { empty($('reminder-list'), 'Hatırlatıcılar yüklenemedi.'); }
}
$('reminder-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const when = new Date($('reminder-time').value);
    if (Number.isNaN(when.getTime())) throw new Error('Geçerli bir tarih ve saat seç.');
    await readApi('/api/mobile/reminders', {method:'POST', body:JSON.stringify({action:state.reminderEditId ? 'update' : 'add',
      id:state.reminderEditId, text:$('reminder-text').value, due_at:when.toISOString(), repeat:$('reminder-repeat').value})});
    $('reminder-form').reset(); state.reminderEditId = null; $('reminder-save').textContent = 'Hatırlatıcı ekle';
    $('reminder-cancel').hidden = true; loadReminders(); loadDailySummary(); status('Hatırlatıcı kaydedildi');
  } catch (error) { status(friendlyMessage(error.message)); }
});
$('reminder-cancel').addEventListener('click', () => {
  state.reminderEditId = null; $('reminder-form').reset();
  $('reminder-save').textContent = 'Hatırlatıcı ekle'; $('reminder-cancel').hidden = true;
});

async function loadMemory() {
  try {
    const query = $('memory-query').value.trim();
    const data = await readApi(query ? `/api/mobile/memory/search?q=${encodeURIComponent(query)}` : '/api/mobile/memory');
    $('memory-search-method').textContent = query ? (data.method === 'meaning' ? 'Anlamına göre bulunan kayıtlar' : 'Metinle bulunan kayıtlar') : '';
    const list = $('memory-list'); list.replaceChildren();
    if (!data.notes?.length) { empty(list, 'Kayıtlı kişisel bilgi yok.'); return; }
    for (const item of (query ? data.notes : data.notes.slice().reverse())) {
      const card = mobileCard(item.text, item.source || 'Kaynak belirtilmemiş');
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = 'Düzenle';
      edit.addEventListener('click', async () => {
        const changed = window.prompt('Jarvis’in hatırlamasını istediğin bilgi', item.text);
        if (changed === null || changed.trim() === item.text) return;
        try { await readApi('/api/mobile/memory', {method:'POST', body:JSON.stringify({action:'update', id:item.id, text:changed})}); loadMemory(); status('Bilgi güncellendi'); }
        catch (error) { status(friendlyMessage(error.message)); }
      });
      const del = document.createElement('button'); del.type = 'button'; del.className = 'secondary'; del.textContent = 'Unut';
      del.addEventListener('click', async () => { try { await readApi('/api/mobile/memory', {method:'POST', body:JSON.stringify({action:'delete', id:item.id})}); loadMemory(); } catch (error) { status(friendlyMessage(error.message)); } });
      card.append(edit, del); list.append(card);
    }
  } catch (_) { empty($('memory-list'), 'Kişisel bilgiler yüklenemedi.'); }
}
$('memory-query').addEventListener('input', () => { clearTimeout(state.memorySearchTimer); state.memorySearchTimer = setTimeout(loadMemory, 350); });
$('memory-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await readApi('/api/mobile/memory', {method:'POST', body:JSON.stringify({action:'add', text:$('memory-text').value})});
    $('memory-form').reset(); loadMemory(); status('Bilgi kaydedildi');
  } catch (error) { status(friendlyMessage(error.message)); }
});
$('person-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await readApi('/api/mobile/contacts', {method:'POST', body:JSON.stringify({action:'save', id:state.contactEditId,
      name:$('person-name').value, relationship:$('person-relationship').value, detail:$('person-detail').value,
      special_day:$('person-day').value, occasion:$('person-occasion').value})});
    cancelContactEdit(); loadContacts(); loadPersonalOverview(); status('Kişi kaydedildi');
  } catch (error) { status(friendlyMessage(error.message)); }
});

function cancelContactEdit() {
  state.contactEditId = null; $('person-form').reset();
  $('person-save').textContent = 'Kişiyi kaydet'; $('person-cancel').hidden = true;
}
$('person-cancel').addEventListener('click', cancelContactEdit);

async function loadContacts() {
  const list = $('person-list');
  try {
    const data = await readApi('/api/mobile/contacts'); list.replaceChildren();
    if (!data.contacts?.length) { empty(list, 'Henüz kişi kaydı yok.'); return; }
    for (const item of data.contacts) {
      const day = item.special_day ? `${item.special_day.slice(3)}.${item.special_day.slice(0, 2)}` : '';
      const card = mobileCard(item.name, `${item.relationship}${day ? ` · ${item.occasion}: ${day}` : ''}`);
      if (item.detail) { const detail = document.createElement('p'); detail.textContent = item.detail; card.append(detail); }
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = 'Düzenle';
      edit.addEventListener('click', () => {
        state.contactEditId = item.id;
        $('person-name').value = item.name; $('person-relationship').value = item.relationship;
        $('person-detail').value = item.detail || ''; $('person-day').value = day;
        $('person-occasion').value = item.occasion || '';
        $('person-save').textContent = 'Değişiklikleri kaydet'; $('person-cancel').hidden = false;
        $('person-form').scrollIntoView({block:'start'});
      });
      const del = document.createElement('button'); del.type = 'button'; del.className = 'secondary'; del.textContent = 'Sil';
      del.addEventListener('click', async () => {
        if (!window.confirm(`${item.name} kişi kaydını sileyim mi?`)) return;
        try { await readApi('/api/mobile/contacts', {method:'POST', body:JSON.stringify({action:'delete', id:item.id})});
          loadContacts(); loadPersonalOverview(); status('Kişi silindi'); }
        catch (error) { status(friendlyMessage(error.message)); }
      });
      card.append(edit, del); list.append(card);
    }
  } catch (_) { empty(list, 'Kişiler yüklenemedi.'); }
}

async function loadGoogle() {
  try {
    const account = await readApi('/api/mobile/google/status');
    $('google-status').textContent = account.connected ? (account.drive_write
      ? 'Google hesabın bağlı. Takvim, e-posta ve Drive hazır.'
      : 'Google hesabın bağlı. Drive’a kaydetmek için yeniden bağlanıp ek izin vermelisin.')
      : account.configured ? 'Google hesabın henüz bağlı değil.' : 'Google bağlantısı için kurulum bekleniyor.';
    $('google-connect').hidden = account.connected && account.drive_write;
    $('google-connect').textContent = account.connected ? 'Drive yazma izni için yeniden bağla' : 'Google hesabını bağla';
    $('google-connect').disabled = !account.configured;
    $('drive-save').disabled = !account.drive_write;
    $('google-disconnect').hidden = !account.connected;
    for (const id of ['calendar-form', 'email-form', 'drive-section']) $(id).hidden = !account.connected;
    if (account.connected) { loadCalendar(); loadGooglePending(); }
    else { $('google-pending').hidden = true; $('google-approval').hidden = true; }
  } catch (_) { $('google-status').textContent = 'Google bağlantısı kontrol edilemedi.'; }
}
async function loadNotificationSettings() {
  try {
    const data = await readApi('/api/mobile/personal/notifications');
    $('notify-morning').checked = data.morning; $('notify-evening').checked = data.evening;
  } catch (_) { status('Bildirim tercihleri yüklenemedi.'); }
}
$('personal-notification-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await readApi('/api/mobile/personal/notifications', {method:'POST', body:JSON.stringify({
      morning:$('notify-morning').checked, evening:$('notify-evening').checked})});
    status('Bildirim tercihleri kaydedildi');
  } catch (error) { status(friendlyMessage(error.message)); }
});
$('google-connect').addEventListener('click', () => { window.location.href = '/google/start'; });
$('google-disconnect').addEventListener('click', async () => {
  if (!window.confirm('Google bağlantısını Jarvis’ten kaldırayım mı?')) return;
  try { await readApi('/api/mobile/google/disconnect', {method:'POST', body:'{}'}); loadGoogle(); }
  catch (error) { status(friendlyMessage(error.message)); }
});

async function loadCalendar() {
  const list = $('calendar-list');
  try {
    const data = await readApi('/api/mobile/google/calendar'); list.replaceChildren();
    if (!data.events?.length) { empty(list, 'Yaklaşan etkinlik görünmüyor.'); return; }
    for (const item of data.events) list.append(mobileCard(item.title,
      item.start ? new Date(item.start).toLocaleString('tr-TR') : 'Tarih yok'));
  } catch (_) { empty(list, 'Takvim şu anda okunamadı.'); }
}

function showGoogleProposal(proposal) {
  if (proposal.status && proposal.status !== 'AWAITING_APPROVAL') {
    state.googleProposal = null;
    $('google-approval').hidden = true;
    status(proposal.status === 'UNCERTAIN'
      ? 'Sonuç belirsiz. Google hesabında kontrol edin; işlem tekrar gönderilmedi.'
      : proposal.status === 'COMPLETED'
        ? 'Bu işlem daha önce tamamlandı. Aynı içerik tekrar gönderilmedi.'
        : 'Bu onay artık geçerli değil.');
    return;
  }
  state.googleProposal = proposal;
  showPersonalTab('google');
  $('google-actions-details').open = true;
  $('google-approval-text').textContent = proposal.details || proposal.description;
  const external = ['calendar.create', 'gmail.send', 'drive.upload'].includes(proposal.kind);
  $('google-approval').classList.toggle('external-warning', external);
  const preview = $('google-approval-preview-link');
  const previewUrl = proposal.preview_url;
  preview.hidden = !/^\/kreatif\/[\w./-]+\.(?:jpe?g|png|webp)$/i.test(previewUrl || '');
  if (!preview.hidden) { preview.href = previewUrl; $('google-approval-preview').src = previewUrl; }
  else { preview.removeAttribute('href'); $('google-approval-preview').removeAttribute('src'); }
  $('google-approval').hidden = false;
  $('google-approval').scrollIntoView({block:'center'});
}
async function loadGooglePending() {
  try {
    const data = await readApi('/api/mobile/google/pending');
    const list = $('google-pending-list'); list.replaceChildren();
    $('google-pending').hidden = !data.pending?.length;
    for (const proposal of data.pending || []) {
      const card = mobileCard(proposal.status === 'UNCERTAIN' ? 'Sonuç kontrolü gerekiyor'
        : proposal.kind === 'gmail.send' ? 'E-posta gönderme'
        : proposal.kind === 'drive.upload' ? 'Drive’a kaydetme' : 'Takvime ekleme',
        proposal.description.split('\n')[0]);
      if (['calendar.create', 'gmail.send', 'drive.upload'].includes(proposal.kind)) card.classList.add('external-warning');
      const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary';
      button.textContent = proposal.status === 'UNCERTAIN' ? 'Durumu gör' : 'İncele';
      button.addEventListener('click', () => showGoogleProposal(proposal));
      card.append(button); list.append(card);
    }
  } catch (_) {
    $('google-pending').hidden = false;
    empty($('google-pending-list'), 'Onaylar şu anda yüklenemedi. İşlem tekrar gönderilmedi.');
  }
}
$('calendar-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const proposal = await readApi('/api/mobile/google/prepare', {method:'POST', body:JSON.stringify({
      kind:'calendar.create', fields:{title:$('calendar-title').value,
        start:new Date($('calendar-start').value).toISOString(),
        end:new Date($('calendar-end').value).toISOString()}})});
    showGoogleProposal(proposal);
    loadGooglePending();
  } catch (error) { status(friendlyMessage(error.message)); }
});
$('email-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const proposal = await readApi('/api/mobile/google/prepare', {method:'POST', body:JSON.stringify({
      kind:'gmail.send', fields:{to:$('email-to').value, subject:$('email-subject').value,
        body:$('email-body').value}})});
    showGoogleProposal(proposal);
    loadGooglePending();
  } catch (error) { status(friendlyMessage(error.message)); }
});
async function decideGoogle(decision) {
  const proposal = state.googleProposal;
  if (!proposal) return;
  $('google-approve').disabled = true; $('google-reject').disabled = true;
  try {
    const result = await readApi(`/api/actions/personal:${proposal.id}/decide`, {method:'POST',
      body:JSON.stringify({decision, fingerprint:proposal.fingerprint})});
    $('google-approval').hidden = true; state.googleProposal = null;
    loadGooglePending();
    status(result.status === 'UNCERTAIN' ? 'İşlem sonucu belirsiz. Google hesabında kontrol edin.' : result.message);
    if (result.status === 'DONE' && proposal.kind === 'calendar.create') { $('calendar-form').reset(); loadCalendar(); }
    if (result.status === 'DONE' && proposal.kind === 'gmail.send') $('email-form').reset();
  } catch (error) { status(friendlyMessage(error.message)); }
  finally { $('google-approve').disabled = false; $('google-reject').disabled = false; }
}
$('google-approve').addEventListener('click', () => decideGoogle('APPROVED'));
$('google-reject').addEventListener('click', () => decideGoogle('REJECTED'));
function driveFolderId() {
  const folder = $('drive-folder').value.trim();
  return folder.includes('/folders/') ? folder.split('/folders/')[1].split(/[?/#]/)[0] : folder;
}
function creativeFeedbackForm(group, filename) {
  const wrapper = document.createElement('div'); wrapper.className = 'creative-feedback';
  const open = document.createElement('button'); open.type = 'button'; open.className = 'secondary';
  open.textContent = 'Düzeltme / yeni sürüm iste';
  const form = document.createElement('form'); form.hidden = true;
  const label = document.createElement('label'); label.textContent = 'Neyi değiştirelim?';
  const topic = document.createElement('select');
  for (const [value, name] of [
    ['LOGO', 'Logo, yazı tipi, yerleşim veya renk'], ['URUN', 'Ürün, şişe veya ambalaj'],
    ['METIN', 'Yazının içeriği'], ['MARKA', 'Marka dili'], ['MEVZUAT', 'Mevzuat'],
    ['DIGER', 'Daha iyi bir alternatif'],
  ]) { const option = document.createElement('option'); option.value = value; option.textContent = name; topic.append(option); }
  const note = document.createElement('textarea'); note.rows = 3; note.maxLength = 2000; note.required = true;
  note.placeholder = 'Örn. Şişe yamuk; dikleştir. Yazı tipini sadeleştir ve daha okunur yap.';
  const submit = document.createElement('button'); submit.type = 'submit'; submit.className = 'secondary';
  submit.textContent = 'Düzeltme isteğini kaydet';
  const result = document.createElement('p'); result.setAttribute('role', 'status');
  label.append(topic, note); form.append(label, submit, result);
  open.addEventListener('click', () => { form.hidden = !form.hidden; if (!form.hidden) note.focus(); });
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); submit.disabled = true;
    try {
      const answer = await readApi('/api/kreatif-itiraz', {method:'POST', body:JSON.stringify({
        parti:group, dosya:filename, konu:topic.value, aciklama:note.value.trim(),
      })});
      result.textContent = `İstek ${answer.muhatap || 'ilgili ekibe'} kaydedildi. Sonraki kreatif üretiminde dikkate alınacak; yeni görsel henüz üretilmedi.`;
      note.value = '';
    } catch (error) { result.textContent = friendlyMessage(error.message); }
    finally { submit.disabled = false; }
  });
  wrapper.append(open, form); return wrapper;
}
$('drive-save').addEventListener('click', async () => {
  if (!state.attachment?.id) { status('Önce bir dosya seç veya Drive’dan Jarvis’e ekle.'); return; }
  try {
    const proposal = await readApi('/api/mobile/google/prepare', {method:'POST', body:JSON.stringify({
      kind:'drive.upload', fields:{attachment_id:state.attachment.id, folder_id:driveFolderId()}})});
    showGoogleProposal(proposal);
    loadGooglePending();
  } catch (error) { status(friendlyMessage(error.message)); }
});
$('creative-refresh').addEventListener('click', async () => {
  const list = $('drive-creative-list');
  try {
    const data = await readApi('/api/mobile/google/creative');
    list.replaceChildren();
    if (!data.files?.length) { empty(list, 'Kreatif görsel bulunamadı.'); return; }
    for (const item of data.files) {
      const card = mobileCard(item.name, item.group);
      const preview = document.createElement('a'); preview.href = item.preview_url;
      preview.target = '_blank'; preview.rel = 'noopener'; preview.setAttribute('aria-label', `${item.name} büyüt`);
      const image = document.createElement('img'); image.src = item.preview_url; image.alt = `${item.group} · ${item.name}`;
      image.className = 'drive-creative-preview'; image.loading = 'lazy'; preview.append(image); card.append(preview);
      const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary';
      button.textContent = 'Drive’a kaydetme onayı hazırla';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const proposal = await readApi('/api/mobile/google/prepare', {method:'POST', body:JSON.stringify({
            kind:'drive.upload', fields:{creative_id:item.id, folder_id:driveFolderId()}})});
          showGoogleProposal(proposal); loadGooglePending();
        } catch (error) { status(friendlyMessage(error.message)); }
        finally { button.disabled = false; }
      });
      card.append(button, creativeFeedbackForm(item.group, item.name)); list.append(card);
    }
  } catch (error) { empty(list, friendlyMessage(error.message)); }
});
$('drive-search').addEventListener('click', async () => {
  const list = $('drive-list');
  const readableTypes = new Set([
    'application/vnd.google-apps.document', 'application/vnd.google-apps.spreadsheet',
    'application/vnd.google-apps.presentation', 'application/pdf', 'text/plain',
    'text/csv', 'text/markdown', 'image/jpeg', 'image/png', 'image/webp',
  ]);
  try {
    const data = await readApi(`/api/mobile/google/drive?q=${encodeURIComponent($('drive-query').value.trim())}`);
    list.replaceChildren();
    if (!data.files?.length) { empty(list, 'Dosya bulunamadı.'); return; }
    for (const item of data.files) {
      const card = mobileCard(item.name || 'Adsız dosya');
      if (item.id && readableTypes.has(item.mime_type)) {
        const attach = document.createElement('button'); attach.type = 'button'; attach.className = 'secondary';
        attach.textContent = 'Jarvis’e ekle';
        attach.addEventListener('click', async () => {
          attach.disabled = true;
          try {
            const result = await readApi('/api/mobile/google/drive/import', {
              method: 'POST', body: JSON.stringify({id: item.id}),
            });
            state.attachment = result;
            $('file-status').textContent = `${result.name} hazır. Kişisel sohbette sorunu yazıp gönder.`;
            $('file-preview').hidden = true;
            $('vision-button').hidden = result.kind !== 'image';
            if (result.kind === 'image') { $('file-preview').src = result.url; $('file-preview').hidden = false; }
            status('Drive dosyası kişisel sohbete eklendi.');
            $('chat-input').focus();
          } catch (error) { status(friendlyMessage(error.message)); }
          finally { attach.disabled = false; }
        });
        card.append(attach);
      }
      try {
        const url = new URL(item.url);
        if (url.protocol === 'https:' && ['drive.google.com', 'docs.google.com'].includes(url.hostname)) {
          const link = document.createElement('a'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener';
          link.textContent = 'Drive’da aç'; card.append(link);
        }
      } catch (_) { /* invalid link is simply not opened */ }
      list.append(card);
    }
  } catch (error) { empty(list, friendlyMessage(error.message)); }
});

function openAction(kind, target = '', message = '') {
  state.action = kind;
  const settings = {
    call: ['Arama başlat', 'Numarayı kontrol et. iPhone aramayı başlatmadan önce kendi ekranını açar.', 'Telefon numarası', 'Ara'],
    message: ['Mesaj hazırla', 'Metin panoya kopyalanır; Mesajlar uygulamasında yapıştırıp göndermeyi onaylarsın.', 'Telefon numarası', 'Mesajlar’ı aç'],
    maps: ['Haritada aç', 'Adres Apple Haritalar’da açılır.', 'Adres veya yer', 'Haritayı aç'],
    shortcut: ['Kestirme çalıştır', 'iPhone’da “Jarvis Telefon” adlı Kestirme oluşturulmuş olmalı. Komut metni ona aktarılır.', 'Kestirmeye gönderilecek komut', 'Kestirmeyi aç'],
  }[kind];
  if (!settings) return;
  $('action-title').textContent = settings[0];
  $('action-description').textContent = settings[1];
  $('target-label').firstChild.textContent = settings[2];
  $('action-confirm').textContent = settings[3];
  $('action-target').value = target;
  $('action-target').type = kind === 'call' || kind === 'message' ? 'tel' : 'text';
  $('message-label').hidden = kind !== 'message';
  $('action-message').value = message;
  $('action-help').textContent = kind === 'shortcut' ? 'Kestirme yalnızca iPhone’unda izin verdiğin işlemleri yapabilir.' : '';
  $('action-dialog').showModal();
}

function commandAction(text) {
  const call = text.match(/^(?:ara|telefon et)\s+([+()\d\s-]{5,})$/i);
  if (call) { openAction('call', call[1]); return true; }
  const message = text.match(/^(?:mesaj gönder|sms gönder)\s+([+()\d\s-]{5,})\s*[:,-]\s*(.+)$/i);
  if (message) { openAction('message', message[1], message[2]); return true; }
  const maps = text.match(/^(?:haritada aç|yol tarifi)\s+(.+)$/i);
  if (maps) { openAction('maps', maps[1]); return true; }
  const shortcut = text.match(/^telefonda\s+(.+)$/i);
  if (shortcut) { openAction('shortcut', shortcut[1]); return true; }
  return false;
}

function personalDraftCommand(text) {
  if (state.chatMode !== 'personal') return false;
  const reminder = text.match(/^(?:bunu hatırlat|hatırlat)(?:\s*[:,-]\s*|\s+)?(.*)$/i);
  if (reminder) {
    showPersonalTab('reminders'); $('reminder-text').value = reminder[1].trim();
    $('reminder-time').focus(); status('Hatırlatıcı taslağı hazır. Zamanı seçip kaydet.'); return true;
  }
  const email = text.match(/^(?:e-posta|mail) taslağı(?:\s*[:,-]\s*|\s+)?(.*)$/i);
  if (email) {
    showPersonalTab('google'); $('email-details').open = true;
    $('email-body').value = email[1].trim(); $('email-to').focus();
    status('E-posta taslağı hazır. Alıcı ve konuyu yaz; gönderim ayrıca onay ister.'); return true;
  }
  return false;
}

$('chat-form').addEventListener('submit', (event) => {
  event.preventDefault();
  if (state.busy) { status('Önceki yanıt hazırlanıyor. Biraz bekle.'); return; }
  if (!state.csrf) { status('Oturum açıp mesajı yeniden gönder.'); return; }
  const text = $('chat-input').value.trim();
  if (!text) return;
  $('chat-input').value = '';
  if (!personalDraftCommand(text) && !commandAction(text)) sendMessage(text);
});

document.querySelectorAll('[data-action]').forEach((button) => button.addEventListener('click', () => openAction(button.dataset.action)));
$('action-cancel').addEventListener('click', () => $('action-dialog').close());
$('action-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const target = $('action-target').value.trim();
  if (!target) return;
  const kind = state.action;
  let url = '';
  if (kind === 'call' || kind === 'message') {
    const phone = target.replace(/[\s()-]/g, '');
    if (!/^\+?\d{5,16}$/.test(phone)) { $('action-help').textContent = 'Geçerli bir telefon numarası gir.'; return; }
    if (kind === 'call') url = `tel:${phone}`;
    else {
      const message = $('action-message').value.trim();
      if (message) {
        try { await navigator.clipboard.writeText(message); } catch (_) { $('action-help').textContent = 'Metin panoya kopyalanamadı; Mesajlar’da elle yaz.'; }
      }
      url = `sms:${phone}`;
    }
  } else if (kind === 'maps') url = `https://maps.apple.com/?q=${encodeURIComponent(target)}`;
  else if (kind === 'shortcut') url = `shortcuts://run-shortcut?name=Jarvis%20Telefon&input=text&text=${encodeURIComponent(target)}`;
  $('action-dialog').close();
  bubble('jarvis', `${$('action-title').textContent}: ${target}`);
  if (url) window.location.href = url;
});

async function readApi(path, options) {
  const response = await request(path, options);
  let body;
  try { body = await response.json(); }
  catch (_) { throw new Error(response.ok
    ? 'Sunucudan okunabilir yanıt alınamadı. İşlem durumunu kontrol edin.'
    : 'Sunucu şu anda yanıt veremiyor. Biraz sonra tekrar deneyin.'); }
  if (!response.ok) throw new Error(response.status >= 500 ? 'Jarvis şu anda yanıt veremiyor. Biraz sonra tekrar deneyin.' :
    response.status === 403 ? 'Bu işlem için yetkiniz yok.' :
    friendlyMessage(body.error, 'İşlem tamamlanamadı. Tekrar deneyin.'));
  return body;
}

function mobileCard(title, description, meta) {
  const card = document.createElement('div'); card.className = 'mobile-card';
  const heading = document.createElement('strong'); heading.textContent = title;
  card.append(heading);
  if (description) { const text = document.createElement('p'); text.textContent = description; card.append(text); }
  if (meta) { const small = document.createElement('small'); small.textContent = meta; card.append(small); }
  return card;
}

function empty(container, message) {
  container.replaceChildren();
  const element = document.createElement('p'); element.className = 'empty-state';
  element.textContent = message; container.append(element);
}

function approvalTitle(proposal) {
  const reason = String(proposal.payload?.reason || '').trim();
  return approvalSummary(reason);
}

function approvalRisk(value) {
  return { LOW: 'Düşük', MEDIUM: 'Orta', HIGH: 'Yüksek', CRITICAL: 'Kritik' }[value] || 'Belirtilmemiş';
}

async function loadCreative() {
  const list = $('creative-list'); list.replaceChildren();
  try {
    const data = await readApi('/api/kreatif-parti');
    const batches = data.partiler || [];
    const ready = batches.filter((batch) => (batch.kareler || []).length);
    const waiting = batches.filter((batch) => !(batch.kareler || []).length);
    if (!ready.length) empty(list, 'Henüz üretilmiş görsel yok.');
    for (const batch of ready) {
      const section = document.createElement('section'); section.className = 'creative-batch';
      const heading = document.createElement('h2'); heading.textContent = batch.urun_adi || batch.parti;
      const count = document.createElement('p'); count.textContent = `${batch.kareler.length} görsel · Dokunarak büyüt`;
      const gallery = document.createElement('div'); gallery.className = 'creative-gallery';
      for (const frame of batch.kareler) {
        if (!/^\/kreatif\/[\w./-]+\.(?:jpe?g|png)$/i.test(frame.url || '')) continue;
        const link = document.createElement('a'); link.href = frame.url; link.target = '_blank'; link.rel = 'noopener';
        link.className = 'creative-image'; link.setAttribute('aria-label', `${frame.ust_yazi || 'Görsel'} büyüt`);
        const image = document.createElement('img'); image.src = frame.url; image.alt = frame.ust_yazi || 'Reklam görseli'; image.loading = 'lazy';
        image.onerror = () => { image.alt = 'Görsel açılamadı'; link.classList.add('image-error'); };
        const caption = document.createElement('span'); caption.textContent = frame.ust_yazi || frame.dosya || 'Görseli aç';
        const decision = document.createElement('small'); decision.className = 'creative-decision';
        decision.textContent = {GECER: 'İncelemeden geçti', DUZELT: 'Düzeltme gerekli', RED: 'Reddedildi'}[frame.karar] || 'İnceleme bekliyor';
        const tile = document.createElement('div'); tile.className = 'creative-tile';
        link.append(image, caption, decision); tile.append(link);
        if (frame.gerekce) {
          const why = document.createElement('p'); why.className = 'creative-review';
          why.textContent = `İnceleme nedeni: ${friendlyMessage(frame.gerekce, 'Ayrıntı belirtilmedi.')}`;
          tile.append(why);
        }
        tile.append(creativeFeedbackForm(batch.parti_klasor || `${batch.parti}-gorseller`, frame.dosya));
        gallery.append(tile);
      }
      section.append(heading, count, gallery); list.append(section);
      const objections = batch.red_team?.itirazlar || batch.red_team || [];
      if (Array.isArray(objections) && objections.length) {
        const review = document.createElement('details'); review.className = 'creative-red-team';
        const summary = document.createElement('summary'); summary.textContent = `İncelemede bulunan ${objections.length} sorun · Dokunup aç`;
        review.append(summary);
        for (const item of objections) {
          const card = mobileCard(friendlyMessage(item.alinti || 'İnceleme notu'),
            `Neden önemli? ${friendlyMessage(item.itiraz || 'Açıklama yok.')}`,
            `Nasıl düzeltilir? ${friendlyMessage(item.duzeltme || 'Öneri yok.')}`);
          review.append(card);
        }
        const assign = document.createElement('button'); assign.type = 'button'; assign.className = 'secondary';
        assign.textContent = 'Düzeltme görevi ver';
        assign.addEventListener('click', async () => {
          if (!window.confirm('İncelemede bulunan sorunları düzeltme görevi olarak kaydedeyim mi?')) return;
          assign.disabled = true;
          try { const result = await readApi('/api/kreatif-gorev', {method:'POST', body:JSON.stringify({tur:'en_iyileri_sec_ve_duzelt'})});
            assign.textContent = friendlyMessage(result.message, 'Görev kaydedildi'); }
          catch (error) { assign.disabled = false; status(friendlyMessage(error.message)); }
        });
        review.append(assign); section.append(review);
      }
    }
    if (waiting.length) {
      const heading = document.createElement('h2'); heading.className = 'creative-waiting-title'; heading.textContent = 'Görseli henüz hazırlanmayanlar';
      list.append(heading);
      for (const batch of waiting.slice(0, 8)) list.append(mobileCard(batch.urun_adi || batch.parti, 'Görsel henüz üretilmedi.', 'Hazırlık aşamasında'));
    }
  } catch (_) { empty(list, 'Görseller yüklenemedi. Tekrar deneyin.'); }
}

function approvalDate(value) {
  if (!value) return 'Belirtilmemiş';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Belirtilmemiş' : date.toLocaleString('tr-TR');
}

function addApprovalLine(container, text, className = '') {
  const line = document.createElement('p');
  line.className = className;
  line.textContent = text;
  container.append(line);
  return line;
}

const CATALOG_SECTIONS = {
  ritual: 'Ritüel', bebek: 'Bebek', mahrem: 'Mahrem bakım', bariyer: 'Cilt bariyeri',
  vucut: 'Vücut', yuz: 'Yüz', kapak: 'Kapak',
};

function jobDisplay(job) {
  const id = String(job.id || '');
  const request = String(job.istem || '').trim();
  if (String(job.isteyen || '').startsWith('katalog/bolum-acilisi')) {
    const section = CATALOG_SECTIONS[id.replace(/^ktb?-/, '')];
    return {title: section ? `Katalog bölüm görseli · ${section}` : 'Katalog bölüm görseli',
      source: 'Katalog çalışması', technical: request};
  }
  const englishPrompt = /\b(?:extreme macro|editorial|soft light|continuous surface|photorealistic|render)\b/i.test(request);
  return {title: englishPrompt ? `Görsel hazırlama işi${id ? ` · ${id}` : ''}` : request || 'İş',
    source: job.isteyen === 'mobil-operator' ? 'Telefondan verildi' : '',
    technical: englishPrompt ? request : ''};
}

async function loadJobs() {
  loadOrchestration();
  try {
    const data = await readApi('/api/isler');
    const counts = data.sayilar || {};
    $('job-count').textContent = `Sırada ${counts.bekleyen ?? 0} · hazırlanan ${counts.calisan ?? 0} · tamamlanan ${counts.biten ?? 0} · tamamlanamayan ${counts.hata ?? 0}`;
    const list = $('job-list'); list.replaceChildren();
    for (const job of (data.isler || []).slice(0, 50)) {
      const phase = {bekleyen: 'Sırada', calisan: 'Hazırlanıyor', biten: 'Tamamlandı', hata: 'Tamamlanamadı'}[job.asama] || 'Durum belirlenemedi';
      const display = jobDisplay(job);
      const card = mobileCard(display.title, phase, display.source);
      if (display.technical) {
        const detail = document.createElement('details');
        const summary = document.createElement('summary'); summary.textContent = 'Özgün görev metni';
        const original = document.createElement('p'); original.textContent = display.technical;
        detail.append(summary, original); card.append(detail);
      }
      list.append(card);
    }
    if (!list.children.length) empty(list, 'Kuyrukta iş yok.');
  } catch (_) { empty($('job-list'), 'İşler yüklenemedi. Sayfayı yenileyip tekrar deneyin.'); $('job-count').textContent = 'İşler alınamadı'; }
}

const ORCHESTRATION_STEPS = {
  internal_data_analysis: 'Şirket verileri incelendi',
  sales_analysis: 'Satış verileri incelendi',
  advertising_analysis: 'Reklam sonuçları incelendi',
  evidence_fusion: 'Bulgular karşılaştırıldı',
  red_team_review: 'Bulguların zayıf noktaları kontrol edildi',
  human_review_proposal: 'İncelenmek üzere öneri taslağı hazırlandı',
  action_plan: 'Yapılacaklar için öneri taslağı hazırlandı',
  capability_analysis: 'Sistemin yapabildikleri kontrol edildi',
  system_status: 'Sistem durumu kontrol edildi',
  problem_opportunity_analysis: 'Sorunlar ve fırsatlar incelendi',
};

function orchestrationStepName(capability) {
  if (ORCHESTRATION_STEPS[capability]) return ORCHESTRATION_STEPS[capability];
  if (capability?.endsWith('_analysis')) return 'İlgili veriler incelendi';
  return 'Çalışma adımı';
}

function orchestrationStepStatus(step) {
  const labels = {
    SUCCEEDED: 'Tamamlandı', PROPOSED: 'Taslak hazır; onay listesine eklenmedi',
    RUNNING: 'Devam ediyor', PENDING: 'Sırada', FAILED: 'Tamamlanamadı',
    DATA_UNAVAILABLE: 'Gerekli veriye ulaşılamadı',
    BLOCKED_CAPABILITY: 'Bu işlem şu anda yapılamıyor',
    BLOCKED_UPSTREAM: 'Önceki adım tamamlanamadığı için bekliyor',
    REQUIRES_HUMAN_ORIGINATION: 'Bu adımı bir kişinin başlatması gerekiyor',
  };
  return labels[step.status] || 'Durumu belirlenemedi';
}

function orchestrationDate(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
    : '';
}

async function loadOrchestration() {
  const list = $('orchestration-list');
  try {
    const data = await readApi('/api/orchestration');
    $('orchestration-count').textContent = `Son ${data.total} çalışma · ${data.needs_attention} çalışma kontrol gerektiriyor`;
    list.replaceChildren();
    for (const run of data.runs || []) {
      const statusText = {
        COMPLETED: 'Analiz tamamlandı', COMPLETED_DEGRADED: 'Analiz bitti; bazı bilgiler eksik',
        RUNNING: 'Analiz sürüyor', FAILED: 'Analiz tamamlanamadı',
        INTERRUPTED: 'Çalışma yarıda kalmış olabilir',
        UNVERIFIED: 'Analiz bitti; bazı bulguların kaynağı eksik',
      }[run.status] || 'Durum kontrol edilemedi';
      const card = mobileCard(run.request || 'Planlı çalışma', statusText, orchestrationDate(run.started_at));
      const detail = document.createElement('details');
      const summary = document.createElement('summary'); summary.textContent = `Neler yapıldı? (${(run.steps || []).length} adım)`;
      const steps = document.createElement('ol');
      for (const step of run.steps || []) {
        const item = document.createElement('li');
        const evidence = step.evidence_state === 'MISSING' ? ' · Dayanak bilgisi eksik' :
          step.evidence_state === 'PRESENT' ? ` · ${step.evidence_count} bilgi kaynağı kullanıldı` : '';
        const acceptance = step.acceptance_status === 'FAILED' ? ' · Sonuç kontrolü geçemedi' : '';
        item.textContent = `${orchestrationStepName(step.capability)} — ${orchestrationStepStatus(step)}${evidence}${acceptance}`;
        steps.append(item);
      }
      detail.append(summary, steps); card.append(detail); list.append(card);
    }
    if (!list.children.length) empty(list, 'Henüz kayıtlı planlı çalışma yok.');
  } catch (error) {
    $('orchestration-count').textContent = 'Çalışmalar okunamadı';
    empty(list, 'Planlı çalışmalar yüklenemedi. Sayfayı yenileyip tekrar deneyin.');
  }
}

$('job-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('job-form').querySelector('button[type="submit"]'); button.disabled = true;
  try {
    await readApi('/api/isler', { method: 'POST', body: JSON.stringify({ istem: $('job-request').value.trim(),
      negatif: $('job-negative').value.trim(), adet: 1 }) });
    $('job-form').reset(); await loadJobs(); status('İş kuyruğa eklendi');
  } catch (error) { status(error.message); }
  finally { button.disabled = false; }
});

async function loadApprovals() {
  try {
    const data = await readApi('/api/actions');
    const list = $('approval-list'); list.replaceChildren();
    const pending = data.pending || [];
    $('approval-count').textContent = String(pending.length);
    $('approval-count').hidden = pending.length === 0;
    $('home-approval-count').textContent = String(pending.length);
    for (const proposal of pending) {
      const card = mobileCard(approvalTitle(proposal), proposal.status === 'UNCERTAIN'
        ? 'Sonuç belirsiz. Dış hesapta kontrol edin.' : 'Ayrıntıları inceleyip karar verin.',
        `Risk: ${approvalRisk(proposal.risk_class)} · ${approvalDate(proposal.proposed_at)}`);
      const button = document.createElement('button'); button.textContent = 'Öneriyi incele';
      button.addEventListener('click', () => openMobileProposal(proposal.key));
      card.append(button); list.append(card);
    }
    if (!pending.length) empty(list, 'Bekleyen onay yok.');
  } catch (_) {
    empty($('approval-list'), 'Onaylar yüklenemedi. Sayfayı yenileyip tekrar deneyin.');
    $('approval-count').hidden = true;
    $('home-approval-count').textContent = '—';
  }
}

async function openMobileProposal(id) {
  try {
    const proposal = await readApi(`/api/actions/${id}`);
    selectedProposal = proposal;
    const title = approvalTitle(proposal);
    const reason = String(proposal.payload?.reason || '').trim();
    $('approval-title').textContent = `#${id} · ${title}`;
    const detail = $('approval-detail'); detail.replaceChildren();
    addApprovalLine(detail, `Risk: ${approvalRisk(proposal.risk_class)}`, 'approval-meta');
    const outcome = reason.match(/ONAY\s*=\s*(.*?)(?:\s+RET\s*=|$)/i);
    if (outcome) addApprovalLine(detail, `Onaylarsan: ${outcome[1].trim()}`, 'approval-outcome');
    addApprovalLine(detail, `Son karar tarihi: ${approvalDate(proposal.expires_at)}`, 'approval-meta');
    if (reason) {
      addApprovalLine(detail, approvalSummary(reason), 'approval-summary');
      const explanation = document.createElement('details'); explanation.className = 'approval-full';
      const label = document.createElement('summary'); label.textContent = 'Açıklamanın tamamı';
      const full = document.createElement('p'); full.textContent = reason;
      explanation.append(label, full); detail.append(explanation);
    } else {
      addApprovalLine(detail, 'Bu önerinin açıklaması yok. Ne yapılacağını bilmeden onay vermeyin.', 'approval-warning');
    }
    if (reason.startsWith('CodingExecutor')) {
      addApprovalLine(detail, 'Bu bir kod inceleme kaydı. Onaydan önce değişen dosyaları ve kanıtı kontrol edin.', 'approval-warning');
    }
    for (const match of reason.matchAll(/(?:^|\s)(\/kreatif\/[^\s]+\.(?:jpg|jpeg|png))/gi)) {
      const link = document.createElement('a');
      link.href = match[1]; link.target = '_blank'; link.rel = 'noopener';
      const preview = document.createElement('img'); preview.src = match[1]; preview.alt = 'Önerilen görsel önizlemesi';
      link.className = 'approval-image'; link.append(preview); detail.append(link);
    }
    const technical = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = 'Teknik kayıt';
    const raw = document.createElement('pre'); raw.textContent = JSON.stringify(proposal.payload || {}, null, 2);
    technical.append(summary, raw); detail.append(technical);
    $('approval-approve').disabled = !reason || proposal.status !== 'AWAITING_APPROVAL';
    $('approval-reject').disabled = proposal.status !== 'AWAITING_APPROVAL';
    $('approval-reason').value = '';
    $('approval-dialog').showModal();
  } catch (error) { status(friendlyMessage(error.message)); }
}

$('approval-close').addEventListener('click', () => $('approval-dialog').close());
async function decideMobile(decision) {
  if (!selectedProposal) return;
  if (selectedProposal.status !== 'AWAITING_APPROVAL') return;
  const id = selectedProposal.key;
  const title = approvalTitle(selectedProposal);
  if (!window.confirm(`#${id} · ${title}\n\n${decision === 'APPROVED' ? 'Bu öneriyi onaylayıp kabul etmek istiyor musun?' : 'Bu öneriyi reddetmek istiyor musun?'}`)) return;
  const reason = $('approval-reason').value.trim() || (decision === 'APPROVED' ? 'Mobil operatör onayı' : 'Mobil operatör reddi');
  try {
    await readApi(`/api/actions/${id}/decide`, { method: 'POST', body: JSON.stringify({
      decision, reason, fingerprint:selectedProposal.fingerprint }) });
    selectedProposal = null; $('approval-dialog').close();
    await loadApprovals(); status(decision === 'APPROVED' ? 'Onay kaydedildi' : 'Ret kaydedildi');
  } catch (error) { status(friendlyMessage(error.message)); }
}
$('approval-approve').addEventListener('click', () => decideMobile('APPROVED'));
$('approval-reject').addEventListener('click', () => decideMobile('REJECTED'));

async function loadSystem() {
  try {
    const data = await readApi('/api/status');
    const host = data.host || {};
    const online = data.visual_state && data.visual_state !== 'OFFLINE';
    $('home-summary').dataset.state = online ? 'ready' : 'error';
    $('home-system-state').textContent = online ? 'Jarvis bağlı' : 'Jarvis bağlantısını kontrol et';
    $('home-memory-state').textContent = data.company_memory?.healthy ? 'Şirket hafızası erişilebilir' : 'Şirket hafızasını kontrol et';
    const list = $('system-list'); list.replaceChildren();
    const jarvisState = {
      IDLE: 'Hazır', PROPOSING: 'Öneri hazırlıyor', WAITING_APPROVAL: 'Kararınızı bekleyen öneri var',
      OFFLINE: 'Bağlantı yok',
    }[data.visual_state] || 'Durum belirlenemedi';
    list.append(mobileCard('Jarvis', jarvisState, `Bekleyen onay: ${data.pending_proposals ?? '—'}`));
    list.append(mobileCard('Şirket hafızası', data.company_memory?.healthy ? 'Bağlı' : 'Erişilemiyor',
      `Eylem güvenliği: ${data.action_firewall?.contract_valid === true ? 'etkin' : 'kontrol gerekli'}`));
    list.append(mobileCard('Sunucu kullanımı', `İşlemci %${host.cpu?.percent ?? '—'} · Bellek %${host.ram?.percent ?? '—'} · Depolama %${host.disk?.percent ?? '—'}`,
      orchestrationDate(host.measured_at)));
  } catch (_) {
    empty($('system-list'), 'Sistem durumu yüklenemedi. Sayfayı yenileyip tekrar deneyin.');
    $('home-summary').dataset.state = 'error';
    $('home-system-state').textContent = 'Durum alınamadı';
    $('home-memory-state').textContent = 'Bağlantıyı kontrol edip yeniden dene';
  }
}
$('refresh-system').addEventListener('click', loadSystem);

async function loadDailySummary() {
  const container = $('daily-summary');
  const results = await Promise.allSettled([
    readApi('/api/isler'), readApi('/api/actions'), readApi('/api/mobile/reminders'), readApi('/api/satislar')]);
  container.replaceChildren();
  const jobs = results[0].status === 'fulfilled' ? results[0].value : null;
  const proposals = results[1].status === 'fulfilled' ? results[1].value : null;
  const reminderData = results[2].status === 'fulfilled' ? results[2].value : null;
  const sales = results[3].status === 'fulfilled' ? results[3].value : null;
  const approvalCount = Array.isArray(proposals?.pending) ? proposals.pending.length : 0;
  const completed = jobs?.sayilar?.biten || 0;
  const upcoming = (reminderData?.reminders || []).filter((item) => new Date(item.due_at) > new Date()).length;
  const today = new Date().toLocaleDateString('sv-SE');
  const visibleOrders = Array.isArray(sales?.siparisler) ? sales.siparisler.filter((order) => String(order.gun || '').slice(0, 10) === today).length : null;
  const items = [
    [visibleOrders === null ? 'Satış verisi alınamadı' : `Bugün kayıtlı ${visibleOrders} sipariş (bağlı kanallar)`, 'home'],
    [`${approvalCount} onay bekliyor`, 'approvals'],
    [`${upcoming} yaklaşan hatırlatıcı`, 'chat'],
    [`${completed} toplam tamamlanan iş`, 'jobs'],
  ];
  for (const [label, tab] of items) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'daily-item';
    button.textContent = label + '  ›'; button.addEventListener('click', () => {
      if (tab === 'home') { window.location.href = '/?view=satislar'; return; }
      document.querySelector(`[data-tab="${tab}"]`).click();
      if (tab === 'chat') document.querySelector('[data-chat-mode="personal"]').click();
    }); container.append(button);
  }
  if (!jobs && !proposals && !reminderData) container.textContent = 'Özet yüklenemedi. Sayfayı yenileyin.';
}
function refreshMobile() { loadJobs(); loadApprovals(); loadSystem(); loadDailySummary(); }
async function loadDevices() {
  const list = $('device-list');
  list.textContent = 'Cihazlar yükleniyor…';
  try {
    const response = await request('/api/devices');
    if (!response.ok) throw new Error('Cihazlar alınamadı. Tekrar dene.');
    const body = await response.json();
    list.replaceChildren();
    for (const device of body.devices || []) {
      const card = document.createElement('div'); card.className = 'mobile-card';
      const title = document.createElement('strong');
      title.textContent = device.current ? 'Bu cihaz' : 'Diğer cihaz';
      const detail = document.createElement('p');
      const seen = new Date(Number(device.last_seen_at) * 1000);
      detail.textContent = `${String(device.device || 'Tarayıcı bilgisi yok').slice(0, 100)} · Son kullanım: ${Number.isNaN(seen.getTime()) ? 'bilinmiyor' : seen.toLocaleString('tr-TR')}`;
      const button = document.createElement('button'); button.type = 'button';
      button.textContent = device.current ? 'Bu cihazdan çıkış yap' : 'Bu cihazdan çıkış yaptır';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          const result = await request('/api/devices/revoke', {method:'POST', body:JSON.stringify({id:device.id})});
          if (!result.ok) throw new Error('Cihazdan çıkış yaptırılamadı. Tekrar dene.');
          if (device.current) { state.csrf = null; showLogin(); }
          else loadDevices();
        } catch (error) { status(error.message); button.disabled = false; }
      });
      card.append(title, detail, button); list.append(card);
    }
    if (!body.devices?.length) list.textContent = 'Açık cihaz oturumu yok.';
  } catch (error) { list.textContent = friendlyMessage(error.message); }
}
$('device-refresh').addEventListener('click', loadDevices);
$('device-revoke-all').addEventListener('click', async () => {
  if (!confirm('Telefon ve bilgisayarlardaki bütün oturumlar kapatılsın mı?')) return;
  try {
    const response = await request('/api/devices/revoke-all', {method:'POST', body:'{}'});
    if (!response.ok) throw new Error('Oturumlar kapatılamadı. Tekrar dene.');
    state.csrf = null; showLogin();
  } catch (error) { status(error.message); }
});
document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => {
  const tab = button.dataset.tab;
  const mainTab = ['system', 'settings', 'creative'].includes(tab) ? 'more' : tab;
  document.querySelectorAll('.tab-nav [data-tab]').forEach((item) => {
    const active = item.dataset.tab === mainTab;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  for (const name of ['home', 'chat', 'jobs', 'approvals', 'creative', 'system', 'settings', 'more']) $(`${name}-panel`).hidden = name !== tab;
  if (tab === 'home') { loadSystem(); loadDailySummary(); }
  if (tab === 'jobs') loadJobs();
  if (tab === 'approvals') loadApprovals();
  if (tab === 'creative') loadCreative();
  if (tab === 'system') loadSystem();
  if (tab === 'settings') loadDevices();
}));

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Recognition) {
  const recognizer = new Recognition(); recognizer.lang = 'tr-TR'; recognizer.continuous = false;
  $('mic').addEventListener('click', () => {
    try { $('mic').classList.add('listening'); status('Dinliyor'); recognizer.start(); }
    catch (_) { $('mic').classList.remove('listening'); }
  });
  recognizer.onresult = (event) => {
    const text = event.results[0][0].transcript.trim();
    if (text) { voiceMode = true; if (!commandAction(text)) sendMessage(text); else voiceMode = false; }
  };
  recognizer.onerror = () => status('Ses algılanamadı; klavye mikrofonunu kullanabilirsin');
  recognizer.onend = () => $('mic').classList.remove('listening');
} else $('mic').hidden = true;

checkSession();
