(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {csrf: '', documents: [], filter: 'review', insights: null, cardFilter: 'open', categories: {}};
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const money = (cents, currency = 'TRY') => cents === null || cents === undefined ? 'Tutar okunmadı' :
    (Number(cents) / 100).toLocaleString('tr-TR', {minimumFractionDigits:2,maximumFractionDigits:2}) + ' ' + currency;
  const todayMonth = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/Istanbul',year:'numeric',month:'2-digit'}).format(new Date()).slice(0,7);
  function error(message, target = 'error') {$(target).textContent = message; $(target).hidden = !message;}
  async function request(url, body) {
    const response = await fetch(url, {credentials:'same-origin',cache:'no-store',
      ...(body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify(body)})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'İşlem tamamlanamadı.');
    return data;
  }
  function matches(doc, filter) {return filter === 'review' ? ['uploaded','review'].includes(doc.status) : doc.company === filter;}
  function renderDispatch(dispatches) {
    const runs = dispatches.filter(item => item.period === $('period').value).sort((a,b) => a.part - b.part);
    $('dispatchStatus').innerHTML = runs.length ? runs.map(run => {
      const stale = run.status === 'sending' && Date.now() - Date.parse(run.created_at) > 30 * 60 * 1000;
      const label = run.status === 'sent' ? 'Gönderildi' : run.status === 'retry_requested' ? 'Yeniden gönderim sırada' :
        run.status === 'sending' && !stale ? 'Gönderiliyor' : 'Kontrol gerekli';
      const retry = run.status === 'failed' || stale;
      return `<div class="dispatch-row"><span>Paket ${run.part}: ${label} · ${run.document_count} belge</span>${retry ?
        `<button type="button" data-retry="${run.part}">Kontrol ettim, yeniden gönder</button>` : ''}</div>`;
    }).join('') : 'Bu ayın paketi henüz gönderilmedi.';
    document.querySelectorAll('[data-retry]').forEach(button => {button.onclick = async () => {
      if (!window.confirm('Alıcı kutusunu kontrol ettiniz mi? Önceki deneme teslim edilmiş olabilir. Yeniden gönderim isteği oluşturulsun mu?')) return;
      try {await request('/api/expenses/retry-dispatch', {period:$('period').value,part:Number(button.dataset.retry)}); await load();}
      catch (exc) {error(exc.message);}
    };});
  }
  function render() {
    const docs = state.documents;
    for (const [id, value] of [['countReview','review'],['countCommon','common'],['countLemos','lemos'],['countMoy','moy'],['countUnknown','unknown']]) {
      $(id).textContent = docs.filter(doc => matches(doc,value)).length;
    }
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.classList.toggle('active', button.dataset.filter === state.filter);
      button.setAttribute('aria-pressed', String(button.dataset.filter === state.filter));
    });
    const visible = docs.filter(doc => matches(doc,state.filter));
    $('documents').innerHTML = visible.length ? visible.map(doc => {
      const src = '/api/expenses/content?id=' + encodeURIComponent(doc.id);
      const image = doc.mime_type.startsWith('image/');
      const label = doc.status === 'ready' ? 'Kontrol edildi' : doc.status === 'excluded' ? 'Pakete alınmayacak' : doc.status === 'uploaded' ? 'Okunuyor' : !doc.gross_cents || !doc.document_date ? 'Bilgileri kontrol et' : 'İncelenecek';
      const linked = doc.related_document_id ? state.documents.find(item => item.id === doc.related_document_id) :
        state.documents.find(item => item.related_document_id === doc.id);
      const dup = doc.extracted && doc.extracted.duplicate;
      const dupNote = dup ? `<p class="dup">⚠️ ${dup.sure ? 'Tekrar yüklenmiş' : 'Tekrar olabilir'}: ${escape(dup.filename)} (${escape(new Date(dup.uploaded_at).toLocaleString('tr-TR'))}) · ${escape(dup.reason)}</p>` : '';
      const category = doc.category ? `<span class="chip">${escape(state.categories[doc.category] || doc.category)}</span>` : '';
      return `<article class="document"><div class="preview">${image ? `<img loading="lazy" src="${src}" alt="${escape(doc.filename)} önizleme">` : '<span class="pdf" aria-hidden="true">PDF</span>'}</div><div class="document-body"><h3>${escape(doc.filename)}</h3><p class="hint">Yüklendi: ${escape(new Date(doc.created_at).toLocaleString('tr-TR'))}</p><p>${escape(doc.supplier || 'Satıcı bilgisi girilmedi')} · ${escape(doc.document_date || 'Tarih bilinmiyor')}</p><p><strong>${escape(money(doc.gross_cents,doc.currency))}</strong>${doc.invoice_number ? ' · ' + escape(doc.invoice_number) : ''}</p>${category}${linked ? `<p>İlişkili belge: ${escape(linked.filename)}</p>` : ''}${dupNote}<span class="badge${doc.status === 'ready' ? ' ready' : ''}">${label}</span><div class="document-actions"><a href="${src}" target="_blank" rel="noopener">Aslına bak ↗</a><button type="button" data-edit="${doc.id}">Bilgileri düzenle</button></div></div></article>`;
    }).join('') : '<p class="hint">Bu klasörde henüz belge yok.</p>';
    document.querySelectorAll('[data-edit]').forEach(button => {button.onclick = () => edit(button.dataset.edit);});
  }
  const totalsText = items => items.map(item => money(item.gross, item.currency)).join(' + ') || money(0);
  function renderSummary(summary) {
    const rows = summary.categories.map(item => `<tr><td>${escape(item.label)}</td><td>${item.count}</td><td class="num">${escape(money(item.gross,item.currency))}</td><td class="num">${escape(money(item.tax,item.currency))}</td></tr>`).join('');
    const companies = summary.companies.map(item => `${escape({common:'Ortak fiş',lemos:'Lemos',moy:'MOY',unknown:'Şirketi belirsiz'}[item.company] || item.company)}: ${escape(money(item.gross,item.currency))}`).join(' · ');
    const tax = summary.totals.map(item => money(item.tax, item.currency)).join(' + ');
    $('summaryBox').innerHTML = rows ? `<p class="big">${escape(totalsText(summary.totals))}</p><p class="hint">KDV toplamı ${escape(tax)} · ${companies}</p><table class="mini"><thead><tr><th>Kategori</th><th>Belge</th><th class="num">Toplam</th><th class="num">KDV</th></tr></thead><tbody>${rows}</tbody></table>${summary.unread || summary.unchecked ? `<p class="dup">${summary.unread ? summary.unread + ' belgenin tutarı okunamadı. ' : ''}${summary.unchecked ? summary.unchecked + ' belge kontrol bekliyor.' : ''}</p>` : ''}` :
      '<p class="hint">Bu ay için tutarı okunmuş belge yok.</p>';
  }
  function renderSubscriptions(items) {
    $('subsBox').innerHTML = items.length ? `<table class="mini"><thead><tr><th>Ödeme</th><th>Son ay</th><th class="num">Son</th><th class="num">Değişim</th></tr></thead><tbody>${items.map(item => `<tr${item.increase ? ' class="up"' : ''}><td>${escape(item.name)}</td><td>${escape(item.last_month)}</td><td class="num">${escape(money(item.last,item.currency))}</td><td class="num">${item.change_pct === null ? '–' : (item.change_pct > 0 ? '▲ %' : item.change_pct < 0 ? '▼ %' : '%') + escape(Math.abs(item.change_pct))}</td></tr>`).join('')}</tbody></table>` :
      '<p class="hint">Henüz iki farklı ay faturası gelen bir abonelik yok.</p>';
  }
  function renderCard() {
    const card = state.insights ? state.insights.card : {lines: [], counts: {open:0,matched:0,ignored:0}};
    $('cardOpen').textContent = card.counts.open; $('cardMatched').textContent = card.counts.matched; $('cardIgnored').textContent = card.counts.ignored;
    document.querySelectorAll('[data-card]').forEach(button => {
      button.classList.toggle('active', button.dataset.card === state.cardFilter);
      button.setAttribute('aria-pressed', String(button.dataset.card === state.cardFilter));
    });
    const group = {needed:'open', matched:'matched', not_needed:'ignored', ignored:'ignored'};
    const lines = card.lines.filter(line => group[line.status] === state.cardFilter);
    $('cardLines').innerHTML = lines.length ? lines.map(line => {
      const candidates = state.documents.filter(doc => doc.status !== 'excluded' && doc.gross_cents !== null)
        .sort((a,b) => Math.abs(a.gross_cents - line.amount_cents) - Math.abs(b.gross_cents - line.amount_cents)).slice(0, 12);
      const actions = line.status === 'needed' ?
        `<select data-pick="${line.id}" aria-label="Belge seç"><option value="">Belgeyle eşleştir…</option>${candidates.map(doc => `<option value="${doc.id}">${escape(doc.supplier || doc.filename)} · ${escape(money(doc.gross_cents,doc.currency))}</option>`).join('')}</select><button type="button" data-line="${line.id}" data-action="ignore">Fişi gerekmiyor</button><button type="button" data-line="${line.id}" data-action="ignore" data-remember="1" title="Bu satıcı bir daha sorulmaz">Bu satıcı için hep</button>` :
        `<button type="button" data-line="${line.id}" data-action="reopen">${line.status === 'matched' ? 'Eşleşmeyi kaldır' : 'Geri al'}</button>`;
      return `<div class="card-line"><div><strong>${escape(line.merchant)}</strong><p class="hint">${escape(new Date(line.tx_date + 'T12:00:00').toLocaleDateString('tr-TR'))} · ${escape(line.account || '')}${line.note ? ' · ' + escape(line.note) : ''}${line.status === 'matched' ? ' · ' + escape(line.supplier || line.filename || 'belge') : ''}</p></div><span class="num">${escape(money(line.amount_cents))}</span><div class="document-actions">${actions}</div></div>`;
    }).join('') : `<p class="hint">${state.cardFilter === 'open' ? (card.lines.length ? 'Bu ay fişi eksik kart harcaması kalmadı. ✓' : 'Bu ay için kart hareketi yüklenmedi.') : 'Bu listede hareket yok.'}</p>`;
    document.querySelectorAll('[data-line]').forEach(button => {button.onclick = () => cardAction(button.dataset.line, button.dataset.action, null, Boolean(button.dataset.remember));});
    document.querySelectorAll('[data-pick]').forEach(select => {select.onchange = () => {if (select.value) cardAction(select.dataset.pick, 'match', select.value);};});
  }
  async function cardAction(id, action, documentId, remember) {
    try {await request('/api/money/receipt', {id, action, document_id: documentId || null, remember: Boolean(remember)}); await loadInsights();}
    catch (exc) {error(exc.message);}
  }
  async function loadInsights() {
    state.insights = await request('/api/expenses/insights?period=' + encodeURIComponent($('period').value));
    if (!Object.keys(state.categories).length) {
      state.categories = state.insights.categories;
      $('categorySelect').innerHTML = '<option value="">Belirlenmedi</option>' + Object.entries(state.categories).map(([key,label]) => `<option value="${key}">${escape(label)}</option>`).join('');
      render();
    }
    renderSummary(state.insights.summary); renderSubscriptions(state.insights.subscriptions); renderCard();
  }
  async function load() {
    const data = await request('/api/expenses?period=' + encodeURIComponent($('period').value));
    state.documents = data.documents;
    render();
    renderDispatch(data.dispatches);
    await loadInsights();
  }
  async function uploadCard(files) {
    if (!files.length) throw new Error('Önce ekstre veya ekran görüntüsü seçin.');
    const button = $('cardButton'); button.disabled = true;
    let read = 0, added = 0, matched = 0;
    try {
      for (const file of files) {
        if (file.size > 12 * 1024 * 1024) throw new Error(file.name + ': 12 MB sınırını aşıyor.');
        $('cardResult').textContent = `${file.name} okunuyor… (fotoğraf başına yaklaşık 15 sn)`;
        const response = await fetch('/api/money/upload', {method:'POST',credentials:'same-origin',
          headers:{'X-CSRF-Token':state.csrf,'X-File-Name':encodeURIComponent(file.name)},body:file});
        const result = await response.json();
        if (!response.ok) throw new Error(file.name + ': ' + (result.error || 'okunamadı'));
        read += result.read; added += result.added; matched += result.matched;
      }
      $('cardResult').textContent = `${read} harcama okundu, ${added} yeni kaydedildi${read - added ? ` (${read - added} zaten vardı)` : ''}, ${matched} tanesi fişle eşleşti.`;
      $('cardFiles').value = ''; state.cardFilter = 'open';
      await loadInsights();
    } finally {button.disabled = false;}
  }
  async function googleStatus() {
    const data = await request('/api/expenses/google');
    const ready = data.connected && data.gmail_read;
    $('mailStatus').textContent = ready ? 'Gmail fatura okuma bağlantısı hazır. Gelen ekler günlük taranır.' :
      'Gmail fatura okuma bağlantısı henüz hazır değil. E-postalardaki faturaları otomatik almak için bağlantıyı yenileyin.';
    $('connectGoogle').hidden = ready || !data.configured;
  }
  function edit(id) {
    const doc = state.documents.find(item => item.id === id);
    if (!doc) return;
    const form = $('editForm'); form.reset();
    const missing = [];
    if (!doc.supplier) missing.push('satıcı');
    if (!doc.document_date) missing.push('belge tarihi');
    if (doc.gross_cents === null) missing.push('toplam tutar');
    if (doc.kind === 'invoice' && doc.company === 'unknown') missing.push('fatura şirketi');
    $('missingFields').textContent = missing.length ? `Fotoğraftan okunamayan alanlar: ${missing.join(', ')}. Lütfen belgeye bakarak elle girin.` : '';
    $('missingFields').hidden = !missing.length;
    const url = '/api/expenses/content?id=' + encodeURIComponent(doc.id);
    $('documentPreview').src = '/api/expenses/preview?id=' + encodeURIComponent(doc.id);
    $('documentOriginal').href = url;
    for (const field of ['id','kind','company','document_date','supplier','buyer','invoice_number','currency','category','note']) {
      form.elements[field].value = doc[field] || (field === 'currency' ? 'TRY' : '');
    }
    form.elements.gross.value = doc.gross_cents === null ? '' : (doc.gross_cents / 100).toFixed(2);
    form.elements.tax.value = doc.tax_cents === null ? '' : (doc.tax_cents / 100).toFixed(2);
    form.elements.status.value = ['ready','excluded'].includes(doc.status) ? doc.status : 'review';
    form.elements.company.disabled = doc.kind === 'receipt';
    $('relatedLabel').hidden = doc.kind !== 'receipt';
    $('relatedHint').hidden = doc.kind !== 'receipt';
    const related = form.elements.related_document_id;
    const candidates = state.documents.filter(item => item.kind === 'invoice' &&
      !state.documents.some(other => other.id !== doc.id && other.related_document_id === item.id));
    candidates.sort((a,b) => Number(b.currency === doc.currency && b.gross_cents === doc.gross_cents) -
      Number(a.currency === doc.currency && a.gross_cents === doc.gross_cents));
    related.innerHTML = '<option value="">Eşleştirilmedi</option>' + candidates.map(item =>
      `<option value="${item.id}">${escape(item.filename)} · ${escape(money(item.gross_cents,item.currency))}</option>`).join('');
    related.value = doc.related_document_id || '';
    error('','editError'); $('editDialog').showModal();
  }
  async function uploadFiles(files) {
    if (!files.length) throw new Error('Önce fotoğraf veya dosya seçin.');
    const kind = $('uploadForm').elements.kind.value;
    const company = kind === 'receipt' ? 'common' : $('uploadForm').elements.company.value;
    const button = $('uploadButton'); button.disabled = true;
    let added = 0, reused = 0;
    try {
      for (const file of files) {
        if (file.size > 12 * 1024 * 1024) throw new Error(file.name + ': 12 MB sınırını aşıyor.');
        const response = await fetch('/api/expenses/upload', {method:'POST',credentials:'same-origin',
          headers:{'X-CSRF-Token':state.csrf,'X-File-Name':encodeURIComponent(file.name),
                   'X-Expense-Kind':kind,'X-Expense-Company':company},body:file});
        const result = await response.json();
        if (!response.ok) throw new Error(file.name + ': ' + (result.error || 'yüklenemedi'));
        if (result.reused) reused++; else added++;
      }
      $('uploadResult').textContent = `${added} belge kaydedildi${reused ? `, ${reused} tekrar atlandı` : ''}. Fotoğraf arşivde; okuma eksikse inceleme kuyruğundan düzenleyin, aynı fişi tekrar yüklemeyin.`;
      $('files').value = ''; $('camera').value = '';
      state.filter = 'review';
      await load();
    } finally {button.disabled = false;}
  }
  async function init() {
    try {
      const session = await request('/api/session');
      if (!session.authenticated) throw new Error('Belgeleri görmek için Jarvis’e giriş yapın.');
      state.csrf = session.csrf_token;
      $('period').value = todayMonth();
      await Promise.all([load(),googleStatus()]);
    } catch (exc) {error(exc.message);}
  }
  $('uploadForm').elements.kind.onchange = event => {$('companyLabel').hidden = event.target.value !== 'invoice';};
  $('uploadForm').onsubmit = async event => {event.preventDefault(); error('');
    try {await uploadFiles([...$('files').files,...$('camera').files]);}
    catch (exc) {error(exc.message);}};
  $('camera').onchange = () => {if ($('camera').files.length) $('uploadForm').requestSubmit();};
  $('period').onchange = () => load().catch(exc => error(exc.message));
  $('cardForm').onsubmit = async event => {event.preventDefault(); error('');
    try {await uploadCard([...$('cardFiles').files]);}
    catch (exc) {error(exc.message); $('cardResult').textContent = '';}};
  document.querySelectorAll('[data-card]').forEach(button => {button.onclick = () => {state.cardFilter = button.dataset.card; renderCard();};});
  document.querySelectorAll('[data-filter]').forEach(button => {button.onclick = () => {state.filter = button.dataset.filter; render();};});
  $('closeDialog').onclick = () => {$('editDialog').close(); $('documentPreview').removeAttribute('src');};
  $('editForm').elements.kind.onchange = event => {const isReceipt = event.target.value === 'receipt';
    $('editForm').elements.company.disabled = isReceipt;
    $('relatedLabel').hidden = !isReceipt; $('relatedHint').hidden = !isReceipt;
    if (!isReceipt) $('editForm').elements.related_document_id.value = '';
    if (isReceipt) $('editForm').elements.company.value = 'common';
    else if ($('editForm').elements.company.value === 'common') $('editForm').elements.company.value = 'unknown';};
  $('editForm').onsubmit = async event => {event.preventDefault(); error('','editError');
    const button = $('editForm').querySelector('[type=submit]'); button.disabled = true;
    try {const body = Object.fromEntries(new FormData($('editForm')));
      if (body.kind === 'receipt') body.company = 'common';
      await request('/api/expenses/update',body); $('editDialog').close(); await load();}
    catch (exc) {error(exc.message,'editError');}
    finally {button.disabled = false;}};
  init();
})();
