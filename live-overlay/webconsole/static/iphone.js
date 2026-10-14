'use strict';

const $ = (id) => document.getElementById(id);
const state = { csrf: null, busy: false, audio: null, audioUrl: null, audioGeneration: 0, action: null };

function status(message) { $('status').textContent = message; }
function showLogin() { $('login').hidden = false; $('app').hidden = true; $('logout').hidden = true; status('Giriş gerekli'); }
function showApp() { $('login').hidden = true; $('app').hidden = false; $('logout').hidden = false; status('Bağlı'); }

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
  if (!text) return;
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
        const item = JSON.parse(line);
        if (item.type === 'stage') row.content.textContent = `${item.label}…`;
        if (item.type === 'token') { streamed += item.delta || ''; row.content.textContent = streamed; }
        if (item.type === 'done') { answer = item.result?.text || item.result?.message || streamed; row.content.textContent = answer || 'Yanıt yok.'; }
        if (item.type === 'error') { answer = item.message || 'Bir hata oluştu.'; row.content.textContent = answer; }
      }
      row.node.scrollIntoView({ block: 'end' });
    }
    if (!answer) { answer = streamed || 'Yanıt alınamadı.'; row.content.textContent = answer; }
    addPlayButton(row, answer);
    status('Bağlı');
  } catch (error) { row.content.textContent = error.message || 'Bağlantı kesildi.'; status('Bağlantı hatası'); }
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

checkSession();
