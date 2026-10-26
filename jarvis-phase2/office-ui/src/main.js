import './style.css';
import { OfficeScene, departmentStatus, statusKind } from './office-scene.js';

const $ = (id) => document.getElementById(id);
const state = { departments: [], selectedCode: null, selectedMember: null, scene: null, loading: false, lastLoaded: null, cycleAt: null, live: {}, eventSource: null, csrfToken: null, conversations: new Map(), drafts: new Map(), asking: new Set() };
const STATUS_LABELS = {
  'KONUŞTU': 'Son ölçümde konuştu', 'VERİ YOK': 'Veri yok',
  'ARAŞTIRMA GEREKİR': 'Araştırma gerekir', 'GİRDİ BEKLER': 'Girdi bekler',
  'İŞLEV YAZILMADI': 'İşlev yazılmadı', 'İŞLEM HATASI': 'İşlem hatası'
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function timeText(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' });
}

async function fetchJson(path) {
  const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
  if (response.status === 401) throw new Error('AUTH');
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

function syncDepartments(agentsData, ekipData) {
  const detailed = new Map((ekipData?.departmanlar || []).map((d) => [d.kod, d]));
  const items = (agentsData?.departmanlar || []).filter((d) => d && d.kod);
  const roster = items.map((d) => {
    const extra = detailed.get(d.kod) || {};
    const extraMembers = new Map((extra.uyeler || []).map((m) => [m.key, m]));
    return {
      ...d, aile: extra.aile || '', misyon: extra.misyon || d.misyon || '',
      birim_durumu: extra.birim_durumu || '', veri_kaynagi: extra.veri_kaynagi || '',
      otonomi_tavani: extra.otonomi_tavani || '', renk: extra.renk || '',
      kadro: (d.kadro || []).map((m) => ({ ...extraMembers.get(m.key), ...m }))
    };
  });
  // Preserve departments that have no roster, so the company map stays complete.
  for (const d of ekipData?.departmanlar || []) {
    if (!items.some((item) => item.kod === d.kod)) {
      roster.push({ ...d, kisi: d.uye_sayisi || 0, kadro: (d.uyeler || []).map((m) => ({
        key: m.key, name: m.ad, job: m.gorev, status: m.durum,
        statement: m.soyledigi, reads: m.okur, sorumlu_mu: false
      })) });
    }
  }
  return roster.sort((a, b) => (a.kod === 'EXEC' ? -1 : b.kod === 'EXEC' ? 1 : (a.aile || '').localeCompare(b.aile || '', 'tr') || (a.ad || '').localeCompare(b.ad || '', 'tr')));
}

function showLogin() {
  $('connection').textContent = 'Oturum gerekli';
  $('summaryText').textContent = 'Kadroyu görmek için Jarvis konsolunda oturum açın.';
  $('departments').replaceChildren();
  const link = el('a', 'login-link', 'Jarvis’e giriş yap ↗');
  link.href = '/'; $('departments').append(link);
}

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  $('connection').textContent = 'Güncelleniyor';
  try {
    const session = await fetchJson('/api/session');
    if (!session.authenticated) { showLogin(); return; }
    state.csrfToken = session.csrf_token;
    const [agentsResult, ekipResult, flowResult, actionsResult, activityResult] = await Promise.allSettled([
      fetchJson('/api/panel/ajanlar'), fetchJson('/api/panel/ekip'),
      fetchJson('/api/orchestration'), fetchJson('/api/actions'), fetchJson('/api/office/activity')
    ]);
    const agents = agentsResult.status === 'fulfilled' ? agentsResult.value : null;
    const ekip = ekipResult.status === 'fulfilled' ? ekipResult.value : null;
    if (!agents && !ekip) throw new Error('Kadro uçları yanıt vermedi');
    const previousShape = state.departments.map((d) => `${d.kod}:${d.kadro?.map((m) => m.key).join(',')}`).join('|');
    state.departments = syncDepartments(agents, ekip);
    const activity = activityResult.status === 'fulfilled' ? activityResult.value : null;
    state.cycleAt = activity?.generated_at || null;
    if (activity?.active) state.live = activity.active;
    for (const d of state.departments) {
      for (const m of d.kadro || []) m.activity = activity?.members?.[m.key] || null;
    }
    if (!state.departments.length) throw new Error('Kadro verisi boş');
    const newShape = state.departments.map((d) => `${d.kod}:${d.kadro?.map((m) => m.key).join(',')}`).join('|');
    if (state.scene && previousShape !== newShape) state.scene.renderDepartments(state.departments);
    else state.scene?.updateStatuses(state.departments);
    state.scene?.updateLive(state.live);
    if (!state.scene) initializeScene();
    if (!state.eventSource) connectLive();
    state.lastLoaded = new Date();
    $('updated').textContent = `Güncelleme ${state.lastLoaded.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}`;
    $('connection').textContent = 'Canlı bağlantı';
    document.querySelector('.live-led').classList.add('connected');
    renderSummary(); renderDepartments();
    if (state.selectedCode) renderDetail(state.selectedCode, state.selectedMember, false);
    renderFlow(flowResult.status === 'fulfilled' ? flowResult.value : null,
      actionsResult.status === 'fulfilled' ? actionsResult.value : null);
  } catch (error) {
    if (error.message === 'AUTH') return showLogin();
    $('connection').textContent = 'Veri alınamadı';
    document.querySelector('.live-led').classList.remove('connected');
    if (!state.departments.length) $('summaryText').textContent = 'Ofis verileri yüklenemedi. Yenile düğmesini kullanın.';
  } finally { state.loading = false; }
}

function initializeScene() {
  try {
    state.scene = new OfficeScene($('scene'), (code, member) => renderDetail(code, member, true), (walking) => {
      $('walkHint').hidden = !walking;
      $('walkMode').classList.toggle('active', walking);
      $('walkMode').querySelector('span').textContent = walking ? 'Dolaşmadan çık' : 'Ofiste dolaş';
    });
    state.scene.renderDepartments(state.departments);
    state.scene.updateLive(state.live);
  } catch (error) {
    $('sceneFallback').hidden = false;
    $('scene').replaceChildren();
    state.scene = null;
  }
}

function connectLive() {
  if (!('EventSource' in window) || state.eventSource) return;
  const source = new EventSource('/api/office/events');
  state.eventSource = source;
  source.addEventListener('snapshot', (event) => {
    try { state.live = JSON.parse(event.data).active || {}; state.scene?.updateLive(state.live); renderLiveCount(); } catch (_) { /* a malformed stream cannot invent activity */ }
  });
  source.addEventListener('office', (event) => {
    try {
      const change = JSON.parse(event.data);
      if (change.member_key) {
        if (change.status === 'WORKING') state.live[change.member_key] = change;
        else delete state.live[change.member_key];
        state.scene?.updateLive(state.live);
        if (state.selectedCode) renderDetail(state.selectedCode, state.selectedMember, false);
      }
      if (change.kind === 'cycle' && change.status === 'COMPLETED') refresh();
      renderLiveCount();
    } catch (_) { /* Keep the last verified state. */ }
  });
}

function renderLiveCount() {
  const count = Object.keys(state.live).length;
  $('connection').textContent = count ? `${count} kişi görevde` : 'Canlı bağlantı';
}

function renderSummary() {
  const departments = state.departments;
  const members = departments.reduce((n, d) => n + (d.kadro?.length || 0), 0);
  const managers = departments.filter((d) => d.sorumlu).length;
  $('departmentCount').textContent = departments.length;
  $('memberCount').textContent = members;
  $('managerCount').textContent = managers;
  $('summaryText').textContent = 'Yönetimden uzman ekiplere bütün kadro. Durumlar son ölçüme dayanır.';
  renderLiveCount();
}

function renderDepartments() {
  const query = $('search').value.trim().toLocaleLowerCase('tr-TR');
  const visible = state.departments.filter((d) => {
    if (!query) return true;
    return [d.kod, d.ad, d.aile, d.sorumlu?.name, ...(d.kadro || []).flatMap((m) => [m.name, m.job])]
      .some((value) => String(value || '').toLocaleLowerCase('tr-TR').includes(query));
  });
  $('filteredCount').textContent = `${visible.length} / ${state.departments.length}`;
  const list = $('departments'); list.replaceChildren();
  let lastFamily = null;
  for (const d of visible) {
    const family = d.aile || 'DİĞER BİRİMLER';
    if (family !== lastFamily) {
      list.append(el('div', 'family-label', family)); lastFamily = family;
    }
    const button = el('button', `department-row ${state.selectedCode === d.kod ? 'selected' : ''}`);
    button.type = 'button'; button.addEventListener('click', () => renderDetail(d.kod, null, true));
    const status = departmentStatus(d);
    button.append(el('span', `department-indicator ${status}`));
    const copy = el('span', 'department-copy');
    copy.append(el('strong', '', d.ad || d.kod), el('small', '', d.sorumlu?.name || 'Sorumlu atanmamış'));
    button.append(copy, el('span', 'department-size', d.kadro?.length || 0));
    list.append(button);
  }
  if (!visible.length) list.append(el('p', 'empty', 'Bu aramayla eşleşen birim veya çalışan yok.'));
}

function addMeta(label, value) {
  if (value === null || value === undefined || value === '') return;
  const item = el('div', 'meta-item');
  item.append(el('span', '', label), el('strong', '', value));
  $('detailMeta').append(item);
}

function renderDetail(code, memberKey, focusScene) {
  const d = state.departments.find((item) => item.kod === code);
  if (!d) return;
  const changedDepartment = state.selectedCode !== code;
  state.selectedCode = code;
  if (memberKey) state.selectedMember = memberKey;
  else if (changedDepartment) state.selectedMember = d.kadro?.find((m) => m.sorumlu_mu)?.key || null;
  $('detail').classList.add('open');
  $('detailCode').textContent = `${d.aile || 'ORGANİZASYON'} / ${d.kod}`;
  $('detailName').textContent = d.ad || d.kod;
  $('detailMission').textContent = d.misyon || 'Bu birim için açıklama bulunmuyor.';
  $('detailMeta').replaceChildren();
  addMeta('Birim sorumlusu', d.sorumlu?.name || 'Atanmamış');
  addMeta('Kadrodaki kişi', `${d.kadro?.length || 0}`);
  addMeta('Birim durumu', d.birim_durumu || 'Belirtilmedi');
  addMeta('Otonomi sınırı', d.otonomi_tavani || 'Belirtilmedi');
  renderOrgTree(d);
  const grid = $('memberGrid'); grid.replaceChildren();
  grid.append(el('h3', 'section-title', 'MÜDÜR VE EKİP'));
  for (const m of d.kadro || []) {
    const button = el('button', `member-card ${m.sorumlu_mu ? 'manager' : ''} ${state.selectedMember === m.key ? 'active' : ''}`);
    button.type = 'button'; button.addEventListener('click', () => selectMember(d, m));
    const icon = el('span', `member-avatar ${statusKind(m.status)}`, m.name?.split(/\s+/).slice(0, 2).map((s) => s[0]).join('') || '?');
    const copy = el('span', 'member-copy');
    copy.append(el('strong', '', m.name || m.key), el('small', '', m.sorumlu_mu ? 'BİRİM SORUMLUSU' : 'EKİP ÜYESİ'));
    const badge = state.live[m.key]
      ? el('span', 'status-badge live', 'ŞİMDİ GÖREVDE')
      : el('span', `status-badge ${statusKind(m.status)}`, STATUS_LABELS[m.status] || m.status || 'Ölçüm yok');
    button.append(icon, copy, badge); grid.append(button);
    if (m.activity?.finished_at) button.append(el('span', 'last-activity', `Son faaliyet ${timeText(m.activity.finished_at)}`));
  }
  if (!(d.kadro || []).length) grid.append(el('p', 'empty', 'Bu birime henüz çalışan atanmadı.'));
  if (state.selectedMember) {
    const m = d.kadro?.find((person) => person.key === state.selectedMember);
    if (m) renderMemberDetail(d, m); else { state.selectedMember = null; $('memberDetail').hidden = true; }
  } else $('memberDetail').hidden = true;
  $('sceneTitle').textContent = d.ad || d.kod;
  $('sceneSubtitle').textContent = `${d.kadro?.length || 0} kişi · ${d.sorumlu?.name || 'Sorumlu atanmamış'}`;
  if (focusScene) state.scene?.focus(code);
  state.scene?.selectMember(state.selectedMember);
  if (changedDepartment || !$('managerDesk').firstChild) renderManagerDesk(d);
  renderDepartments();
}

function selectMember(d, m) {
  state.selectedMember = m.key;
  renderDetail(d.kod, m.key, false);
  $('memberDetail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderOrgTree(department) {
  const tree = $('orgTree'); tree.replaceChildren();
  tree.append(el('h3', 'org-tree-heading', 'BAĞLILIK YAPISI'));
  const manager = department.kadro?.find((m) => m.sorumlu_mu);
  const root = el('div', 'org-root');
  root.append(el('span', 'member-avatar', '★'));
  const info = el('span');
  info.append(el('strong', '', manager?.name || department.sorumlu?.name || 'Sorumlu atanmadı'), el('small', '', 'BİRİM SORUMLUSU'));
  root.append(info); tree.append(root);
  const staff = (department.kadro || []).filter((m) => !m.sorumlu_mu);
  if (staff.length) {
    tree.append(el('div', 'org-stem'));
    const children = el('div', 'org-children');
    for (const member of staff) {
      const child = el('div', 'org-child');
      child.append(el('strong', '', member.name || member.key), el('small', '', member.job || 'Ekip üyesi'));
      children.append(child);
    }
    tree.append(children);
  }
}

function renderMemberDetail(department, m) {
  const box = $('memberDetail'); box.hidden = false; box.replaceChildren();
  const title = el('div', 'member-detail-title');
  title.append(el('p', 'eyebrow', m.sorumlu_mu ? 'BİRİM SORUMLUSU' : 'EKİP ÜYESİ'), el('h3', '', m.name || m.key));
  box.append(title);
  if (m.job || m.gorev) box.append(el('p', 'member-job', m.job || m.gorev));
  if (m.statement || m.soyledigi) {
    const quote = el('div', 'member-statement');
    quote.append(el('small', '', 'SON ÖLÇÜMDEKİ GÖRÜŞÜ'), el('p', '', m.statement || m.soyledigi));
    box.append(quote);
  }
  const status = el('div', 'member-data-row');
  status.append(el('span', '', 'Veri okuma durumu'), el('strong', `status-text ${statusKind(m.status || m.durum)}`, STATUS_LABELS[m.status || m.durum] || m.status || m.durum || 'Ölçüm yok'));
  box.append(status);
  if (state.live[m.key]) {
    const active = el('div', 'member-active');
    active.append(el('strong', '', 'ŞİMDİ GÖREVDE'), el('span', '', state.live[m.key].task || 'Görev sürüyor'));
    box.append(active);
  }
  if (m.activity) {
    const activity = el('div', 'member-activity');
    activity.append(el('small', '', `KAYITLI SON FAALİYET · ${timeText(m.activity.finished_at || m.activity.started_at)}`));
    activity.append(el('strong', '', m.activity.task || 'Görev belirtilmedi'));
    activity.append(el('p', '', m.activity.result || 'Sonuç kaydı yok.'));
    box.append(activity);
  }
  if (Array.isArray(m.reads || m.okur) && (m.reads || m.okur).length) {
    box.append(el('h4', '', 'OKUDUĞU KAYNAKLAR'));
    const chips = el('div', 'chips');
    (m.reads || m.okur).forEach((source) => chips.append(el('span', 'chip', source)));
    box.append(chips);
  }
  if (Array.isArray(m.eksik) && m.eksik.length) {
    box.append(el('h4', '', 'EKSİK / BEKLENEN'));
    const chips = el('div', 'chips'); m.eksik.forEach((source) => chips.append(el('span', 'chip warning', source))); box.append(chips);
  }
}

const QUICK_QUESTIONS = [
  'Şu anda ne üzerinde çalışıyorsun?',
  'Neden şu anda aktif çalışma görünmüyor?',
  'Ekibin son ölçümde ne yaptı, neyi tamamlayamadı?',
  'Bu birimin güncel durumu ve öncelikleri nedir?'
];

function renderManagerDesk(department) {
  const desk = $('managerDesk'); desk.replaceChildren();
  const manager = department.kadro?.find((m) => m.sorumlu_mu);
  desk.hidden = !manager;
  if (!manager) return;
  const heading = el('div', 'manager-desk-heading');
  heading.append(el('p', 'eyebrow', 'MÜDÜRE DOĞRUDAN SOR'), el('h3', '', manager.name || department.sorumlu?.name || 'Birim sorumlusu'));
  const note = el('p', 'manager-desk-note', 'Yanıt son ölçüm, faaliyet kaydı ve okunabilen kaynaklara dayanır. Canlı kayıt yokluğu tek başına boş durduğunu göstermez.');
  const history = el('div', 'manager-conversation'); history.setAttribute('aria-live', 'polite');
  const messages = state.conversations.get(department.kod) || [];
  if (!messages.length) history.append(el('p', 'conversation-empty', 'Müdüre bir soru seçin veya kendi sorunuzu yazın.'));
  for (const message of messages) {
    const item = el('div', `conversation-item ${message.role}`);
    item.append(el('small', '', message.role === 'user' ? 'SİZ' : manager.name || 'MÜDÜR'));
    item.append(el('p', '', message.text));
    if (message.role === 'manager') {
      if (message.warning) item.append(el('p', 'answer-warning', message.warning));
      if (message.sources) item.append(el('small', 'answer-sources', message.sources));
    }
    history.append(item);
  }
  if (state.asking.has(department.kod)) history.append(el('p', 'answer-pending', 'Müdür kaynakları inceliyor…'));
  const quick = el('div', 'manager-quick');
  const field = el('textarea', 'manager-question'); field.rows = 3; field.maxLength = 600;
  field.placeholder = `${manager.name || 'Müdür'} için sorunuzu yazın…`;
  field.value = state.drafts.get(department.kod) || '';
  field.addEventListener('input', () => state.drafts.set(department.kod, field.value));
  for (const question of QUICK_QUESTIONS) {
    const button = el('button', '', question); button.type = 'button';
    button.addEventListener('click', () => { field.value = question; state.drafts.set(department.kod, question); field.focus(); });
    quick.append(button);
  }
  const form = el('form', 'manager-form');
  const send = el('button', 'manager-send', state.asking.has(department.kod) ? 'Yanıt bekleniyor…' : 'Müdüre sor →');
  send.type = 'submit'; send.disabled = state.asking.has(department.kod);
  form.append(field, send);
  form.addEventListener('submit', (event) => { event.preventDefault(); askManager(department.kod, field.value); });
  desk.append(heading, note, history, quick, form);
  history.scrollTop = history.scrollHeight;
}

async function askManager(code, rawQuestion) {
  const question = rawQuestion.trim().slice(0, 600);
  if (!question || state.asking.has(code)) return;
  const department = state.departments.find((d) => d.kod === code);
  if (!department) return;
  const messages = state.conversations.get(code) || [];
  messages.push({ role: 'user', text: question });
  state.conversations.set(code, messages);
  state.drafts.set(code, ''); state.asking.add(code);
  if (state.selectedCode === code) renderManagerDesk(department);
  try {
    const response = await fetch('/api/ekip/sor', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrfToken || '' },
      body: JSON.stringify({ kod: code, soru: question })
    });
    if (response.status === 401) throw new Error('Oturum sona erdi. Jarvis’e yeniden giriş yapın.');
    if (response.status === 403) throw new Error('Oturum doğrulaması yenilenmeli. Sayfayı yenileyip tekrar deneyin.');
    const result = await response.json();
    if (!response.ok || result.hata) throw new Error(result.hata || result.error || 'Yanıt alınamadı.');
    const unverified = result.dogrulanmayan_sayilar || [];
    const unread = result.okunamayan || [];
    messages.push({
      role: 'manager', text: result.cevap || 'Bu soru için doğrulanmış yanıt üretilemedi.',
      warning: [
        unverified.length ? `Doğrulanmayan sayılar: ${unverified.join(', ')}` : '',
        unread.length ? `Okunamayan kaynaklar: ${unread.join(', ')}` : ''
      ].filter(Boolean).join(' · '),
      sources: `${result.kanit_sayisi || 0} kanıt parçası · ${(result.kanit_kaynaklari || []).join(' · ') || 'Kaynak yok'}`
    });
  } catch (error) {
    messages.push({ role: 'manager', text: error.message || 'Yanıt alınamadı. Tekrar deneyin.', warning: 'Soru işlenemedi.' });
  } finally {
    state.asking.delete(code);
    if (state.selectedCode === code) renderManagerDesk(department);
  }
}

function renderFlow(flow, actions) {
  const runs = Array.isArray(flow?.runs) ? flow.runs : [];
  const active = runs.filter((r) => ['RUNNING', 'IN_PROGRESS', 'PENDING', 'WAITING'].includes(String(r.status || '').toUpperCase()));
  const pending = Array.isArray(actions?.pending) ? actions.pending.length : null;
  $('activityTitle').textContent = active.length ? `${active.length} çalışma sürüyor` : 'Şu anda aktif çalışma görünmüyor';
  const recent = runs[0];
  $('activityDetail').textContent = `${runs.length} kayıtlı çalışma${pending === null ? '' : ` · ${pending} bekleyen onay`}${recent ? ` · Son: ${timeText(recent.started_at)}` : ''}${state.cycleAt ? ` · Ekip ölçümü: ${timeText(state.cycleAt)}` : ' · Son ekip ölçümü yok'}`;
}

function renderChart() {
  const body = $('chartBody'); body.replaceChildren();
  const executive = state.departments.find((d) => d.kod === 'EXEC');
  const chief = el('div', 'chart-ceo');
  chief.append(el('small', '', 'ŞİRKET YÖNETİMİ'), el('strong', '', executive?.sorumlu?.name || 'Genel Müdür'));
  body.append(chief, el('div', 'chart-trunk'));
  const grid = el('div', 'chart-groups');
  for (const department of state.departments) {
    const button = el('button', 'chart-unit'); button.type = 'button';
    button.append(el('small', '', department.aile || 'BİRİM'), el('strong', '', department.ad || department.kod),
      el('span', '', `${department.sorumlu?.name || 'Sorumlu atanmamış'} · ${department.kadro?.length || 0} kişi`));
    button.addEventListener('click', () => { $('chartDialog').hidden = true; renderDetail(department.kod, null, true); });
    grid.append(button);
  }
  body.append(grid);
}

$('search').addEventListener('input', renderDepartments);
$('clearSearch').addEventListener('click', () => { $('search').value = ''; renderDepartments(); $('search').focus(); });
$('refresh').addEventListener('click', refresh);
$('resetCamera').addEventListener('click', () => state.scene?.resetCamera());
$('walkMode').addEventListener('click', () => {
  if (state.scene?.walking) state.scene.stopWalk();
  else state.scene?.startWalk(state.selectedCode);
});
$('showChart').addEventListener('click', () => { renderChart(); $('chartDialog').hidden = false; });
$('closeChart').addEventListener('click', () => { $('chartDialog').hidden = true; });
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !$('chartDialog').hidden) $('chartDialog').hidden = true;
});
window.addEventListener('pagehide', () => state.eventSource?.close());
$('closeDetail').addEventListener('click', () => { $('detail').classList.remove('open'); state.selectedCode = null; state.selectedMember = null; state.scene?.selectMember(null); $('sceneTitle').textContent = 'Tüm şirket'; $('sceneSubtitle').textContent = 'Birime tıklayarak kadroyu inceleyin'; renderDepartments(); });
refresh();
setInterval(refresh, 30000);
