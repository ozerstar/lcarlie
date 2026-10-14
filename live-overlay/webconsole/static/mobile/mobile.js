'use strict';

const $ = (id) => document.getElementById(id);
const state = { csrf: null, busy: false, audio: null, audioUrl: null, audioGeneration: 0, action: null };
let voiceMode = false;
let selectedProposal = null;

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
  if (['approvals', 'creative'].includes(tab)) document.querySelector(`[data-tab="${tab}"]`).click();
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
  $('messages').append(node);
  node.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return { node, content };
}

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

async function sendMessage(text) {
  if (!state.csrf || state.busy || !text) return;
  state.busy = true;
  $('send').disabled = true;
  status('Düşünüyor');
  bubble('user', text);
  const row = bubble('jarvis', 'Yanıt hazırlanıyor…');
  let answer = '';
  try {
    const response = await request('/api/chat/stream', { method: 'POST', body: JSON.stringify({ message: text }) });
    if (!response.ok || !response.body) throw new Error('Sohbet bağlantısı açılamadı.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    let streamed = '';
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
        catch (_) { throw new Error('Yanıt tamamlanamadı. Lütfen tekrar deneyin.'); }
        if (item.type === 'stage') row.content.textContent = `${item.label}…`;
        if (item.type === 'token') { streamed += item.delta || ''; row.content.textContent = streamed; }
        if (item.type === 'done') {
          answer = item.result?.text || item.result?.message || streamed;
          if (item.result?.source === 'operator.list_pending') {
            const count = Array.isArray(item.result.data) ? item.result.data.length : 0;
            answer = count ? `${count} öneri onayınızı bekliyor. Onaylar bölümünden inceleyebilirsiniz.` : 'Bekleyen onay yok.';
          }
          answer = friendlyMessage(answer, 'Jarvis yanıt veremedi. Lütfen tekrar deneyin.');
          row.content.textContent = answer;
          if (item.result?.source === 'kreatif.inceleme') {
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
        if (item.type === 'error') { answer = friendlyMessage(item.message, 'Yanıt tamamlanamadı. Tekrar deneyin.'); row.content.textContent = answer; }
      }
      row.node.scrollIntoView({ block: 'end' });
    }
    if (!answer) { answer = streamed || 'Yanıt alınamadı.'; row.content.textContent = answer; }
    const playButton = addPlayButton(row, answer);
    if (voiceMode && playButton) { voiceMode = false; playAnswer(answer, playButton); }
    status('Bağlı');
  } catch (error) { row.content.textContent = friendlyMessage(error.message, 'Bağlantı kesildi. Tekrar deneyin.'); status('Bağlantı hatası'); voiceMode = false; }
  finally { state.busy = false; $('send').disabled = false; }
}

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

$('chat-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const text = $('chat-input').value.trim();
  if (!text) return;
  $('chat-input').value = '';
  if (!commandAction(text)) sendMessage(text);
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
  const body = await response.json();
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
        gallery.append(tile);
      }
      section.append(heading, count, gallery); list.append(section);
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

async function loadJobs() {
  loadOrchestration();
  try {
    const data = await readApi('/api/isler');
    const counts = data.sayilar || {};
    $('job-count').textContent = `Sırada ${counts.bekleyen ?? 0} · hazırlanan ${counts.calisan ?? 0} · tamamlanan ${counts.biten ?? 0} · tamamlanamayan ${counts.hata ?? 0}`;
    const list = $('job-list'); list.replaceChildren();
    for (const job of (data.isler || []).slice(0, 50)) {
      const phase = {bekleyen: 'Sırada', calisan: 'Hazırlanıyor', biten: 'Tamamlandı', hata: 'Tamamlanamadı'}[job.asama] || 'Durum belirlenemedi';
      list.append(mobileCard(job.istem || 'İş', phase, job.isteyen ? `İsteyen: ${job.isteyen}` : ''));
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
    const data = await readApi('/api/proposals');
    const list = $('approval-list'); list.replaceChildren();
    const pending = data.pending || [];
    $('approval-count').textContent = String(pending.length);
    $('approval-count').hidden = pending.length === 0;
    $('home-approval-count').textContent = String(pending.length);
    for (const proposal of pending) {
      const card = mobileCard(approvalTitle(proposal), 'Ayrıntıları inceleyip karar verin.',
        `Risk: ${approvalRisk(proposal.risk_class)} · ${approvalDate(proposal.proposed_at)}`);
      const button = document.createElement('button'); button.textContent = 'Öneriyi incele';
      button.addEventListener('click', () => openMobileProposal(proposal.action_id));
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
    const proposal = await readApi(`/api/proposals/${id}`);
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
    $('approval-approve').disabled = !reason;
    $('approval-reason').value = '';
    $('approval-dialog').showModal();
  } catch (error) { status(friendlyMessage(error.message)); }
}

$('approval-close').addEventListener('click', () => $('approval-dialog').close());
async function decideMobile(decision) {
  if (!selectedProposal) return;
  const id = selectedProposal.action_id;
  const title = approvalTitle(selectedProposal);
  if (!window.confirm(`#${id} · ${title}\n\n${decision === 'APPROVED' ? 'Bu öneriyi onaylayıp kabul etmek istiyor musun?' : 'Bu öneriyi reddetmek istiyor musun?'}`)) return;
  const reason = $('approval-reason').value.trim() || (decision === 'APPROVED' ? 'Mobil operatör onayı' : 'Mobil operatör reddi');
  try {
    await readApi(`/api/proposals/${id}/decide`, { method: 'POST', body: JSON.stringify({ decision, reason }) });
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

function refreshMobile() { loadJobs(); loadApprovals(); loadSystem(); }
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
  if (tab === 'home') loadSystem();
  if (tab === 'jobs') loadJobs();
  if (tab === 'approvals') loadApprovals();
  if (tab === 'creative') loadCreative();
  if (tab === 'system') loadSystem();
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
