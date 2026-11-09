/* Shared desktop/mobile ledger. No financial data is stored in the browser. */
(() => {
  'use strict';
  const root = document.getElementById('cariRoot');
  if (!root) return;
  const back = document.getElementById('cariBack');
  if (back && window.matchMedia('(max-width: 720px)').matches) back.href = '/mobile/';
  const labels = {
    sale: 'Ürün verdik / satış', purchase: 'Ürün aldık / alış',
    sale_return: 'Müşteriden iade aldık', purchase_return: 'Tedarikçiye iade verdik',
    collection: 'Tahsilat aldık', payment: 'Ödeme yaptık',
    opening_receivable: 'Açılış alacağımız', opening_payable: 'Açılış borcumuz',
    gift_out: 'Bedelsiz ürün verdik', gift_in: 'Bedelsiz ürün aldık'
  };
  const roles = {customer: 'Müşteri', supplier: 'Tedarikçi', both: 'Müşteri ve tedarikçi'};
  const cash = new Set(['collection', 'payment', 'opening_receivable', 'opening_payable']);
  const state = {accounts: [], selected: null, statement: null, csrf: null, pending: null, editing: null, editingDraft: null, drafts: [], editAccount: false, generation: 0, reportDate: null, reportGeneration: 0, productFamily: 'sale', catalog: [], catalogError: '', documents: [], filter: {from: '', to: '', kind: '', product: ''}};
  const money = cents => (Number(cents) / 100).toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' TL';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Istanbul'}).format(new Date());
  const day = value => value ? value.split('-').reverse().join('.') : '—';
  const isoDate = value => /^\d{2}\.\d{2}\.\d{4}$/.test(String(value || '')) ? String(value).split('.').reverse().join('-') : String(value || '');
  const key = () => crypto.randomUUID();
  const el = id => root.querySelector('#' + id);
  const decimal = value => String(value).trim().replace(',', '.');
  const suffix = summary => summary.unknown_tax_documents > 0 ? ' + belirlenecek KDV' : '';

  const icons = {
    wallet: '<path d="M5 9V6l14-3v6M4 9h17v14H4z"/><path d="M17 14h6v5h-6z"/>',
    arrow: '<path d="M13 3v21M5 16l8 8 8-8"/>',
    calculator: '<rect x="5" y="3" width="17" height="23" rx="2"/><path d="M8 7h11v5H8zM9 16h1m6 0h1m-8 5h1m6 0h1"/>',
    chart: '<path d="M14 2v12h12A12 12 0 0 0 14 2Z"/><path d="M10 5a11 11 0 1 0 13 13H10Z"/>',
    calendar: '<rect x="3" y="5" width="22" height="21" rx="2"/><path d="M8 2v6m12-6v6M3 12h22m-17 5h1m5 0h1m5 0h1M8 22h1m5 0h1"/>',
    document: '<path d="M7 2h13l6 6v25H7zM20 2v7h6M11 15h10m-10 6h10m-10 6h6"/><circle cx="26" cy="30" r="8"/><path d="m22 30 3 3 5-6"/>'
  };
  const icon = name => `<svg viewBox="0 0 ${name === 'document' ? '38 40' : '28 28'}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
  const stat = (label, value, color, symbol, note = '') => `<article class="cari-stat cari-stat-${color}"><span class="cari-stat-icon">${icon(symbol)}</span><div><span class="cari-stat-label">${label}</span><strong>${value}</strong>${note ? `<small>${note}</small>` : ''}</div></article>`;

  const productAliases = {
    'hair-nouriher': ['hair nourisher'],
    'sunacnea-30-spf': ['sunacnea'],
    'vireon-for-men': ['vireon'],
    kinesis: ['kinesis']
  };
  const productWords = value => String(value || '').toLocaleLowerCase('tr-TR').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').replace(/ı/g, 'i').replace(/[^a-z0-9]+/g, ' ').trim();
  function mentionsProduct(text, product) {
    const haystack = ` ${productWords(text)} `;
    const headline = product.name.split(/[|(·]/)[0].trim();
    return [product.slug.replace(/-/g, ' '), headline, ...(productAliases[product.slug] || [])]
      .some(term => productWords(term).length > 4 && haystack.includes(` ${productWords(term)} `));
  }
  const catalogProduct = name => state.catalog.find(product => mentionsProduct(name, product));
  const selectedCover = product => state.statement?.account?.covers?.[product.slug] || product.cover;
  const productPhoto = product => product && selectedCover(product)
    ? `<img src="/katalog-gorsel/${encodeURIComponent(selectedCover(product))}" alt="${escape(product.name)} kapak görseli" loading="lazy">` : '';
  function productNameWithPhoto(name) {
    const product = catalogProduct(name);
    return `<span class="cari-product-name">${productPhoto(product)}<span>${escape(name)}</span></span>`;
  }
  function renderCatalogGallery(account, entries) {
    const mentioned = [account.note || '', ...entries.flatMap(entry => entry.payload.items.map(item => item.name))].join(' ');
    const products = state.catalog.filter(product => selectedCover(product) && mentionsProduct(mentioned, product));
    if (!products.length) return state.catalogError
      ? `<p class="cari-alert">${escape(state.catalogError)}</p>` : '';
    return `<section class="cari-card cari-catalog" aria-label="Bu caride adı geçen ürünler"><div class="cari-section-head"><div><h3>Bu caride adı geçen ürünler</h3><p class="cari-muted">E-ticaret kataloğundaki kapak görselleri. Görsel, teslim veya satış kaydı anlamına gelmez.</p></div></div><div class="cari-catalog-grid">${products.map(product => `<figure><div class="cari-catalog-photo">${productPhoto(product)}</div><figcaption><strong>${escape(product.name)}</strong><small>E-ticaret kapak görseli</small></figcaption></figure>`).join('')}</div></section>`;
  }

  async function loadCatalog() {
    try {
      const data = await request('/api/katalog');
      if (!Array.isArray(data.urunler)) throw new Error('Katalog ürünleri bulunamadı.');
      state.catalog = data.urunler.map(product => ({
        slug: String(product.slug || ''), name: String(product.ad || ''),
        images: (product.gorseller || []).filter(name => /^[a-z0-9-]+\.webp$/.test(name)),
        cover: /^[a-z0-9-]+\.webp$/.test(product.gorseller?.[0] || '') ? product.gorseller[0] : ''
      }));
      state.catalogError = '';
    } catch (exc) {
      state.catalogError = 'Ürün kapak görselleri yüklenemedi. Cari kayıtları kullanılabilir.';
    }
    if (state.statement) renderStatement();
  }

  function switchTab(id, focus = false) {
    root.querySelectorAll('[data-cari-tab]').forEach(button => {
      const active = button.dataset.cariTab === id;
      button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1;
      if (active && focus) button.focus();
    });
    root.querySelectorAll('[data-cari-panel]').forEach(panel => {panel.hidden = panel.dataset.cariPanel !== id;});
  }

  async function request(path, payload) {
    const response = await fetch(path, {
      credentials: 'same-origin', cache: 'no-store',
      ...(payload === undefined ? {} : {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf || ''},
        body: JSON.stringify(payload)
      })
    });
    const body = await response.json();
    if (!response.ok) throw new Error(response.status === 401 ? 'Cari hesapları görmek için Jarvis’e giriş yapın.' : body.error || 'İşlem tamamlanamadı.');
    return body;
  }

  function error(message, target = 'cariError') {
    const node = el(target);
    node.textContent = message || '';
    node.hidden = !message;
  }

  function shell() {
    root.innerHTML = `
      <header class="cari-heading"><div><img class="cari-brand" src="/img/lcarlie-mark-dark.png" alt="L’CARLIÉ"><h1>CARİ HESAP</h1></div><div class="cari-date">${icon('calendar')}<div><span>TARİH</span><time datetime="${today()}">${day(today())}</time></div></div></header>
      <p id="cariError" class="cari-error" role="alert" hidden></p>
      <div class="cari-workspace cari-no-print"><div class="cari-tabs" role="tablist" aria-label="Cari bölümleri"><button id="cariTabAccount" type="button" role="tab" data-cari-tab="account" aria-controls="cariAccountPanel" aria-selected="true">Cari hesap</button><button id="cariTabInfo" type="button" role="tab" data-cari-tab="info" aria-controls="cariInfoPanel" aria-selected="false" tabindex="-1">Cari bilgileri</button><button id="cariTabOverview" type="button" role="tab" data-cari-tab="overview" aria-controls="cariOverviewPanel" aria-selected="false" tabindex="-1">Genel durum</button><button id="cariTabInvoice" type="button" role="tab" data-cari-tab="invoice" aria-controls="cariInvoicePanel" aria-selected="false" tabindex="-1">Fatura aktar</button><button id="cariTabChannels" type="button" role="tab" data-cari-tab="channels" aria-controls="cariChannelPanel" aria-selected="false" tabindex="-1">E-ticaret ve faturalar</button></div><button type="button" id="cariRefresh">Yenile</button></div>
      <section id="cariAccountPanel" data-cari-panel="account" role="tabpanel" aria-labelledby="cariTabAccount"><div class="cari-account-toolbar cari-no-print"><details class="cari-picker" id="cariPicker"><summary><span id="cariSelectedName">Cari seçin</span><span aria-hidden="true">⌄</span></summary><div class="cari-picker-menu"><label>Cari ara<input id="cariSearch" type="search" placeholder="Kişi veya firma adı" autocomplete="off"></label><nav id="cariAccounts" class="cari-accounts" aria-label="Cari hesaplar"></nav></div></details><button type="button" id="cariNewAccount">+ Yeni cari</button></div><div id="cariStatement" class="cari-stack"><div class="cari-card cari-empty"><h2>Cari hesabınızı oluşturun</h2><p>Ürün, tahsilat ve ödeme hareketlerini takip etmek için yeni cari ekleyin.</p></div></div></section>
      <section id="cariInfoPanel" data-cari-panel="info" role="tabpanel" aria-labelledby="cariTabInfo" class="cari-no-print" hidden><div id="cariInfoContent" class="cari-card"><p>Cari seçin.</p></div></section>
      <section id="cariOverviewPanel" data-cari-panel="overview" role="tabpanel" aria-labelledby="cariTabOverview" class="cari-no-print" hidden><section class="cari-card cari-overview" aria-label="Genel cari durumu"><div class="cari-section-head"><div><h2>Genel cari durumu</h2><small>Cariler arası alacak ve borçlar ayrı izlenir.</small></div><label>Rapor tarihi<input type="date" id="cariReportDate" required></label></div><div class="cari-toolbar"><button type="button" data-cari-export="pdf" data-export-scope="portfolio">Cari listesi PDF</button><button type="button" data-cari-export="xlsx" data-export-scope="portfolio">Cari listesi Excel</button></div><div id="cariOverview"><p>Özet yükleniyor…</p></div></section></section>
      <section id="cariInvoicePanel" data-cari-panel="invoice" role="tabpanel" aria-labelledby="cariTabInvoice" class="cari-no-print" hidden><section class="cari-card"><h2>Fatura ve belgeler</h2><p class="cari-muted">JPG, PNG, WebP veya PDF fatura yükleyin. Satıcı, alıcı, ürünler, KDV ve toplam tutar okunur. Kesin eşleşen fatura kaydedilir; eksik veya uyuşmayan alanlar incelemeye düşer.</p><form id="cariInvoiceForm" class="cari-form"><label>Fatura dosyası<input name="file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" required></label><button class="cari-primary" type="submit">Faturayı oku ve aktar</button></form><p id="cariInvoiceError" class="cari-error" role="alert" hidden></p><div id="cariInvoiceResult"></div><div id="cariDocuments"></div></section></section>
      <section id="cariChannelPanel" data-cari-panel="channels" role="tabpanel" aria-labelledby="cariTabChannels" class="cari-no-print" hidden><section id="cariChannels" class="cari-card" aria-label="E-ticaret, kargo, POS ve fatura takibi"><p>Kaynaklar yükleniyor…</p></section></section>
      <nav class="cari-integrations cari-no-print" aria-label="İlgili Jarvis bölümleri"><a href="/?view=satislar">Satışlar ve stok ↗</a><a href="/?view=musteri">Müşteriler ↗</a><a href="/?view=fiyat">Fiyatlar ↗</a><a href="/?view=kargo">Kargo ↗</a><a href="/?view=saha">Saha ↗</a></nav>
      <dialog id="cariAccountDialog" aria-labelledby="cariAccountTitle"><div class="cari-section-head"><h2 id="cariAccountTitle">Yeni cari hesap</h2><button type="button" data-close="cariAccountDialog" aria-label="Kapat">×</button></div><form id="cariAccountForm" class="cari-form"><label>Kişi / firma adı<input name="name" maxlength="160" required autocomplete="organization"></label><label>Cari türü<select name="role"><option value="customer">Müşteri</option><option value="supplier">Tedarikçi</option><option value="both">Müşteri ve tedarikçi</option></select></label><label>Vergi / kimlik numarası<input name="tax_id" maxlength="20" inputmode="numeric"></label><label>Vergi dairesi<input name="tax_office" maxlength="160"></label><label>Adres<textarea name="address" maxlength="1000" rows="2"></textarea></label><label>E-posta<input name="email" maxlength="200" type="email"></label><label>Telefon<input name="phone" maxlength="50"></label><label>İletişim<input name="contact" maxlength="200"></label><label>Not<textarea name="note" maxlength="2000" rows="2"></textarea></label><div id="cariCoverChoices" hidden></div><p id="cariAccountError" class="cari-error" role="alert" hidden></p><button class="cari-primary" type="submit">Cariyi oluştur</button></form></dialog>
      <dialog id="cariEntryDialog" aria-labelledby="cariEntryTitle"><div class="cari-section-head"><h2 id="cariEntryTitle">Yeni hareket</h2><button type="button" data-close="cariEntryDialog" aria-label="Kapat">×</button></div><form id="cariEntryForm" class="cari-form"><div class="cari-fields"><label>Hareket türü<select name="kind">${Object.entries(labels).map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></label><label>İşlem tarihi<input name="date" type="date" required></label><label>Vade (isteğe bağlı)<input name="due_date" type="date"></label><label>Belge / fatura numarası<input name="reference" maxlength="100"></label></div><div id="cariGoods"><p class="cari-muted">Birim fiyatları KDV hariç girin. İskonto bu fiyat üzerinden uygulanır.</p><div id="cariLines"></div><button type="button" id="cariAddLine">+ Ürün satırı</button></div><label id="cariCash" hidden>Tutar (TL)<input name="amount" inputmode="decimal" placeholder="0,00"></label><div id="cariPaymentFields" class="cari-fields" hidden><label>Ödeme yöntemi<select name="payment_method"><option value="">Belirtilmedi</option><option value="pos">POS</option><option value="havale">Havale / EFT</option><option value="elden">Elden</option><option value="other">Diğer</option></select></label><label>Hangi belgeye?<select name="applies_to"><option value="">Eşleştirilmedi</option></select></label></div><label>Açıklama<textarea name="note" rows="2" maxlength="2000"></textarea></label><div id="cariCorrectionFields" hidden><p class="cari-alert">Eski hareket ve düzeltme birlikte korunur. Kaydetme işlemi tek seferde yapılır.</p><div class="cari-fields"><label>Düzeltme tarihi<input name="correction_date" type="date"></label><label>Düzeltme gerekçesi<input name="reason" maxlength="500"></label></div></div><p id="cariEntryError" class="cari-error" role="alert" hidden></p><div id="cariPreview" class="cari-preview" aria-live="polite" hidden></div><div class="cari-form-actions"><button type="submit">Hesapla ve kontrol et</button><button type="button" id="cariSaveEntry" class="cari-primary" hidden>Hareketi kaydet</button></div></form></dialog>
      <dialog id="cariReverseDialog" aria-labelledby="cariReverseTitle"><div class="cari-section-head"><h2 id="cariReverseTitle">Hareketi ters kayıtla düzelt</h2><button type="button" data-close="cariReverseDialog" aria-label="Kapat">×</button></div><p>Asıl kayıt korunur; tutarı ve ürün adetlerini dengeleyen bir ters kayıt eklenir.</p><form id="cariReverseForm" class="cari-form"><input name="entry_id" type="hidden"><label>Düzeltme tarihi<input name="date" type="date" required></label><label>Gerekçe<textarea name="reason" required maxlength="500" rows="3"></textarea></label><p id="cariReverseError" class="cari-error" role="alert" hidden></p><button class="cari-primary" type="submit">Ters kaydı oluştur</button></form></dialog>
      <dialog id="cariPaymentDialog" aria-labelledby="cariPaymentTitle"><div class="cari-section-head"><h2 id="cariPaymentTitle">Ödeme kaydet</h2><button type="button" data-close="cariPaymentDialog" aria-label="Kapat">×</button></div><form id="cariPaymentForm" class="cari-form"><input name="applies_to" type="hidden"><label>Tarih<input name="date" type="date" required></label><label>Alınan / ödenen tutar (TL)<input name="amount" inputmode="decimal" required></label><label>Yöntem<select name="payment_method"><option value="pos">POS</option><option value="havale">Havale / EFT</option><option value="elden">Elden</option><option value="other">Diğer</option></select></label><label>Not<textarea name="note" maxlength="2000" rows="2"></textarea></label><p id="cariPaymentError" class="cari-error" role="alert" hidden></p><button class="cari-primary" type="submit">Ödemeyi kaydet</button></form></dialog>`;
    el('cariGoods').querySelector('p').insertAdjacentHTML('afterend', '<div class="cari-fields cari-bulk-discount"><label>Toplu iskonto %<input id="cariBulkDiscount" inputmode="decimal" placeholder="Ör. 30"></label><button type="button" id="cariApplyDiscount">Tüm ürünlere uygula</button></div>');
    el('cariSaveEntry').insertAdjacentHTML('afterend', '<button type="button" id="cariSaveDraft" hidden>Taslak olarak kaydet</button>');
    const tabs = [...root.querySelectorAll('[data-cari-tab]')];
    tabs.forEach((button, index) => {
      button.onclick = () => switchTab(button.dataset.cariTab);
      button.onkeydown = event => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next !== undefined) {event.preventDefault(); switchTab(tabs[next].dataset.cariTab, true);}
      };
    });
    el('cariNewAccount').onclick = () => {state.editAccount = false; el('cariAccountForm').reset(); el('cariCoverChoices').hidden = true; el('cariAccountTitle').textContent = 'Yeni cari hesap'; el('cariAccountForm').querySelector('[type=submit]').textContent = 'Cariyi oluştur'; error('', 'cariAccountError'); el('cariAccountDialog').showModal();};
    el('cariSearch').oninput = renderAccounts;
    state.reportDate = today(); el('cariReportDate').value = state.reportDate;
    el('cariReportDate').onchange = async event => {
      if (!event.target.value) return;
      state.reportDate = event.target.value;
      try {await loadOverview();} catch (exc) {error(exc.message);}
    };
    el('cariRefresh').onclick = () => refresh().catch(exc => error(exc.message));
    root.querySelectorAll('[data-close]').forEach(button => {button.onclick = () => el(button.dataset.close).close();});
    el('cariAccountForm').onsubmit = createAccount;
    el('cariEntryForm').onsubmit = preview;
    el('cariEntryForm').oninput = clearPreview;
    el('cariEntryForm').elements.kind.onchange = () => {clearPreview(); switchKind();};
    el('cariAddLine').onclick = () => {clearPreview(); addLine();};
    el('cariSaveEntry').onclick = saveEntry;
    el('cariSaveDraft').onclick = saveDraft;
    el('cariApplyDiscount').onclick = () => {
      const value = decimal(el('cariBulkDiscount').value);
      if (!/^\d{1,3}(?:\.\d{1,2})?$/.test(value) || Number(value) > 100) {
        error('İskonto 0 ile 100 arasında olmalı.', 'cariEntryError'); return;
      }
      el('cariLines').querySelectorAll('[name=discount]').forEach(input => {input.value = value;});
      clearPreview(); error('', 'cariEntryError');
    };
    el('cariReverseForm').onsubmit = reverseEntry;
    el('cariPaymentForm').onsubmit = savePayment;
    el('cariInvoiceForm').onsubmit = uploadInvoice;
    bindGiftEditors();
  }

  function renderAccounts() {
    const query = el('cariSearch').value.trim().toLocaleLowerCase('tr-TR');
    const accounts = state.accounts.filter(account => account.name.toLocaleLowerCase('tr-TR').includes(query));
    el('cariAccounts').innerHTML = accounts.map(account => `<button type="button" data-id="${escape(account.id)}" aria-pressed="${account.id === state.selected}"><strong>${escape(account.name)}</strong><small>${roles[account.role]} · ${account.balance_cents < 0 ? 'Borç' : 'Alacak'}: ${money(Math.abs(account.balance_cents))}${account.unknown_tax_documents > 0 ? ' + KDV' : ''}</small></button>`).join('') || '<p class="cari-muted">Cari hesap bulunamadı.</p>';
    el('cariAccounts').querySelectorAll('[data-id]').forEach(button => {button.onclick = () => select(button.dataset.id).catch(exc => error(exc.message));});
  }

  async function refresh() {
    const body = await request('/api/cari/accounts');
    state.accounts = body.accounts;
    renderAccounts();
    if (!state.selected && state.accounts.length) state.selected = state.accounts[0].id;
    if (state.selected) await select(state.selected, false);
    await loadOverview();
    await loadDocuments();
    if (window.JarvisCariChannels) await window.JarvisCariChannels.load();
    error('');
  }

  async function loadOverview() {
    const generation = ++state.reportGeneration;
    const report = await request('/api/cari/overview?as_of=' + encodeURIComponent(state.reportDate));
    if (generation !== state.reportGeneration) return;
    const t = report.totals;
    el('cariOverview').innerHTML = `<div class="cari-stats"><div class="cari-stat"><span>TOPLAM ALACAĞIMIZ</span><strong>${money(t.receivable_cents)}</strong></div><div class="cari-stat"><span>TOPLAM BORCUMUZ</span><strong>${money(t.payable_cents)}</strong></div><div class="cari-stat"><span>GİRİLEN TAHSİLATLAR</span><strong>${money(t.collections_cents)}</strong></div><div class="cari-stat"><span>GİRİLEN ÖDEMELER</span><strong>${money(t.payments_cents)}</strong></div></div><p class="cari-muted">${day(report.as_of)} tarihine kadar · ${t.account_count} cari. ${escape(report.cash_note)}</p>${t.unknown_tax_documents ? '<p class="cari-alert">' + t.unknown_tax_documents + ' belgede KDV belirsiz; toplamlar bilinen tutarları gösterir.</p>' : ''}<details class="cari-due-reviews" open><summary>Yaklaşan ve geciken vadeler · ${report.due_reviews.length} belge</summary><p class="cari-alert">${escape(report.due_review_note)}</p><div class="cari-table-wrap"><table><thead><tr><th>Cari</th><th>Vade</th><th>Belge</th><th>Açık tutar</th><th>Durum</th></tr></thead><tbody>${report.due_reviews.map(row => `<tr><td><button type="button" data-review-account="${escape(row.account_id)}">${escape(row.account_name)}</button></td><td>${day(row.due_date)}</td><td>${escape(row.reference || 'Belge no girilmedi')}</td><td>${money(row.remaining_cents)}${row.unknown_tax ? ' + KDV belirsiz' : ''}</td><td>${row.overdue ? 'Gecikti' : 'Yaklaşıyor'}</td></tr>`).join('') || '<tr><td colspan="5">Açık vadeli belge yok.</td></tr>'}</tbody></table></div></details><details class="cari-due-reviews"><summary>Eksik bilgiler · ${(report.missing_information || []).length} belge</summary><div class="cari-table-wrap"><table><thead><tr><th>Cari</th><th>Tarih</th><th>Eksik alan</th></tr></thead><tbody>${(report.missing_information || []).map(row => `<tr><td><button type="button" data-review-account="${escape(row.account_id)}">${escape(row.account_name)}</button></td><td>${day(row.date)}</td><td>${row.unknown_tax ? 'KDV oranı ' : ''}${row.missing_reference ? 'Fatura numarası' : ''}</td></tr>`).join('') || '<tr><td colspan="3">Eksik alan yok.</td></tr>'}</tbody></table></div></details>`;
    el('cariOverview').querySelectorAll('[data-review-account]').forEach(button => {button.onclick = () => select(button.dataset.reviewAccount).catch(exc => error(exc.message));});
  }

  async function loadDocuments() {
    const result = await request('/api/cari/documents');
    const previous = state.documents;
    state.documents = result.documents || [];
    const container = el('cariDocuments');
    container.innerHTML = `<h3>Yüklenen faturalar ve ekler</h3><div class="cari-table-wrap"><table><thead><tr><th>Dosya</th><th>Durum</th><th>İşlem</th></tr></thead><tbody>${state.documents.map(doc => `<tr><td><a href="/api/cari/documents/content?id=${encodeURIComponent(doc.id)}" target="_blank" rel="noopener">${escape(doc.filename)}</a><small>${day(String(doc.created_at).slice(0, 10))}</small></td><td>${doc.status === 'posted' ? 'Cari ve hareket kaydedildi' : doc.status === 'review' ? 'İnceleme gerekli' : doc.source === 'invoice' ? 'Okunuyor' : 'Yüklendi'}</td><td>${doc.status === 'review' ? `<button type="button" data-review="${doc.id}">İncele ve kaydet</button>` : doc.status === 'uploaded' && doc.source === 'invoice' ? `<button type="button" data-reprocess="${doc.id}">Yeniden oku</button>` : doc.account_id ? `<button type="button" data-open-doc-account="${doc.account_id}">Cariyi aç</button>` : '—'}</td></tr>`).join('') || '<tr><td colspan="3">Henüz belge yüklenmedi.</td></tr>'}</tbody></table></div>`;
    container.querySelectorAll('[data-review]').forEach(button => {button.onclick = () => reviewInvoice(button.dataset.review);});
    container.querySelectorAll('[data-reprocess]').forEach(button => {button.onclick = async () => {try {await request('/api/cari/documents/process', {id: button.dataset.reprocess}); button.textContent = 'Okunuyor…';} catch (exc) {error(exc.message, 'cariInvoiceError');}};});
    container.querySelectorAll('[data-open-doc-account]').forEach(button => {button.onclick = () => select(button.dataset.openDocAccount).catch(exc => error(exc.message));});
    if (state.statement && JSON.stringify(previous.map(d => [d.id, d.status])) !== JSON.stringify(state.documents.map(d => [d.id, d.status]))) renderStatement();
    if (state.documents.some(doc => doc.status === 'uploaded' && doc.source === 'invoice')) {
      if (!state.documentTimer) state.documentTimer = setInterval(() => loadDocuments().catch(exc => error(exc.message, 'cariInvoiceError')), 5000);
    } else if (state.documentTimer) {clearInterval(state.documentTimer); state.documentTimer = null;}
    if (previous.some(doc => doc.status === 'uploaded' && state.documents.some(next => next.id === doc.id && next.status === 'posted'))) await refresh();
  }

  async function uploadFile(file, source, accountId, entryId) {
    if (!file || file.size > 8 * 1024 * 1024) throw new Error('Dosya 8 MB veya daha küçük olmalı.');
    const headers = {'X-CSRF-Token': state.csrf, 'X-File-Name': encodeURIComponent(file.name),
      'X-Document-Source': source};
    if (accountId) headers['X-Account-Id'] = accountId;
    if (entryId) headers['X-Entry-Id'] = entryId;
    const response = await fetch('/api/cari/documents/upload', {method: 'POST', credentials: 'same-origin',
      cache: 'no-store', headers, body: file});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Belge yüklenemedi.');
    return result;
  }

  async function uploadInvoice(event) {
    event.preventDefault();
    const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true;
    error('', 'cariInvoiceError');
    try {
      const result = await uploadFile(form.elements.file.files[0], 'invoice');
      form.reset();
      await refresh();
      el('cariInvoiceResult').textContent = result.status === 'posted'
        ? 'Fatura okundu; cari ve ürün hareketi kaydedildi.'
        : result.status === 'uploaded' ? 'Fatura yüklendi. Okuma arka planda sürüyor; sonuç listede güncellenecek.'
        : 'Fatura yüklendi. Alanları inceleyip kaydedin: ' + (result.reason || 'Okuma kontrolü gerekli.');
      if (result.status === 'review') reviewInvoice(result.id);
    } catch (exc) {error(exc.message, 'cariInvoiceError');}
    finally {button.disabled = false;}
  }

  function reviewInvoice(id) {
    const doc = state.documents.find(item => item.id === id);
    if (!doc) return;
    switchTab('invoice');
    const raw = doc.extracted || {};
    el('cariInvoiceResult').innerHTML = `<section class="cari-card"><h3>${escape(doc.filename)} · İnceleme</h3><p class="cari-alert">${raw.error ? escape(raw.error) + ' ' : ''}Faturadaki satırları ve toplamı dosyayla karşılaştırın. Kaydetme, cari ve mali hareket oluşturur. Çağrı hareketleri otomatik oluşturulmaz; bu ekranda elle onaylanabilir.</p><form id="cariReviewForm" class="cari-form"><label>Satıcı adı<input name="seller" value="${escape(raw.seller?.name || '')}" required></label><label>Alıcı adı<input name="buyer" value="${escape(raw.buyer?.name || '')}" required></label><label>Fatura numarası<input name="number" value="${escape(raw.invoice_number || '')}" required></label><label>Tarih<input name="date" type="date" value="${escape(isoDate(raw.date))}" required></label><label>Vade<input name="due_date" type="date" value="${escape(isoDate(raw.due_date))}"></label><label>Genel toplam TL<input name="total" inputmode="decimal" value="${escape(raw.total || '')}" required></label><label>Ürün satırları · JSON<textarea name="items" rows="8" required>${escape(JSON.stringify(raw.items || [], null, 2))}</textarea></label><p class="cari-muted">Her satır: name, quantity, unit_price (KDV hariç), discount, tax_rate. Vergi numaralarını yukarıda kontrol edin; iletişim bilgilerini cari düzenlemeden değiştirebilirsiniz.</p><button class="cari-primary" type="submit">Kontrol ettim, cariye kaydet</button></form></section>`;
    el('cariReviewForm').elements.number.closest('label').insertAdjacentHTML('beforebegin',
      ['seller', 'buyer'].map(side => `<fieldset><legend>${side === 'seller' ? 'Satıcı' : 'Alıcı'} ek bilgileri</legend><label>Vergi / kimlik no<input name="${side}_tax_id" inputmode="numeric" value="${escape(raw[side]?.tax_id || '')}"></label><label>Vergi dairesi<input name="${side}_tax_office" value="${escape(raw[side]?.tax_office || '')}"></label><label>Adres<textarea name="${side}_address" rows="2">${escape(raw[side]?.address || '')}</textarea></label><label>E-posta<input name="${side}_email" type="email" value="${escape(raw[side]?.email || '')}"></label><label>Telefon<input name="${side}_phone" value="${escape(raw[side]?.phone || '')}"></label></fieldset>`).join(''));
    el('cariReviewForm').onsubmit = async event => {
      event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true;
      try {
        const data = Object.fromEntries(new FormData(form));
        const extracted = {...raw,
          seller: {...raw.seller, name: data.seller, tax_id: data.seller_tax_id, tax_office: data.seller_tax_office, address: data.seller_address, email: data.seller_email, phone: data.seller_phone},
          buyer: {...raw.buyer, name: data.buyer, tax_id: data.buyer_tax_id, tax_office: data.buyer_tax_office, address: data.buyer_address, email: data.buyer_email, phone: data.buyer_phone}, invoice_number: data.number,
          date: data.date, due_date: data.due_date, total: decimal(data.total), currency: 'TRY',
          items: JSON.parse(data.items)};
        await request('/api/cari/documents/approve', {id, extracted});
        await refresh(); el('cariInvoiceResult').textContent = 'Fatura cariye kaydedildi.';
      } catch (exc) {error(exc.message, 'cariInvoiceError');}
      finally {button.disabled = false;}
    };
  }

  function openPayment(entryId) {
    const entry = state.statement.entries.find(item => item.id === entryId);
    const settlement = state.statement.settlements[entryId];
    if (!entry || !settlement || !settlement.remaining_cents) return;
    const form = el('cariPaymentForm'); form.reset(); form.elements.applies_to.value = entryId;
    form.elements.date.value = today(); form.elements.amount.value = (settlement.remaining_cents / 100).toFixed(2);
    form.dataset.kind = ['sale', 'opening_receivable'].includes(entry.payload.kind) ? 'collection' : 'payment';
    el('cariPaymentTitle').textContent = form.dataset.kind === 'collection' ? 'Ödeme alındı' : 'Ödeme yapıldı';
    error('', 'cariPaymentError'); el('cariPaymentDialog').showModal();
  }

  async function savePayment(event) {
    event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button'); button.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(form));
      data.kind = form.dataset.kind; data.account_id = state.selected; data.request_id = key();
      data.amount = decimal(data.amount); data.reference = '';
      await request('/api/cari/entries', data);
      el('cariPaymentDialog').close(); await refresh();
    } catch (exc) {error(exc.message, 'cariPaymentError');}
    finally {button.disabled = false;}
  }

  function attachEntry(entryId) {
    const input = document.createElement('input'); input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp,application/pdf';
    input.onchange = async () => {
      try {await uploadFile(input.files[0], 'attachment', state.selected, entryId); await loadDocuments();}
      catch (exc) {error(exc.message);}
    };
    input.click();
  }

  async function select(id, activate = true) {
    const generation = ++state.generation;
    state.selected = id;
    el('cariPicker').open = false;
    el('cariSelectedName').textContent = state.accounts.find(account => account.id === id)?.name || 'Cari seçin';
    if (activate) switchTab('account');
    state.statement = null;
    state.accountDocuments = [];
    renderAccounts();
    el('cariStatement').innerHTML = '<p class="cari-empty">Hesap yükleniyor…</p>';
    const result = await request('/api/cari/statement?id=' + encodeURIComponent(id));
    if (generation !== state.generation) return;
    state.statement = result;
    const draftResult = await request('/api/cari/drafts?account_id=' + encodeURIComponent(id));
    if (generation !== state.generation) return;
    state.drafts = draftResult.drafts || [];
    const accountDocs = await request('/api/cari/documents?account_id=' + encodeURIComponent(id));
    if (generation !== state.generation) return;
    state.accountDocuments = accountDocs.documents || [];
    if (state.productAccount !== id) state.productFamily = result.account.role === 'supplier' ? 'purchase' : 'sale';
    state.productAccount = id;
    renderStatement();
    renderAccountInfo();
    error('');
  }

  function renderDrafts() {
    if (!state.drafts.length) return '';
    return `<section class="cari-card cari-drafts cari-no-print" aria-label="Onay bekleyen hareket taslakları"><h3>Onay bekleyen taslaklar</h3><p class="cari-muted">Taslaklar bakiyeyi değiştirmez. Ürün fiyatlarını ve iskontolarını kontrol edip cariye işleyin.</p>${state.drafts.map(draft => {
      const p = draft.body, quantity = (p.items || []).reduce((sum, item) => sum + Number(item.quantity || 0), 0);
      return `<article class="cari-draft"><div class="cari-section-head"><div><strong>${escape(labels[p.kind])} · ${quantity} adet</strong><p class="cari-muted">${day(p.date)} · ${escape(p.note || 'Ürün ve tutar onayı bekliyor')}</p><p><strong>Taslak toplamı: ${money(draft.preview.net_cents)}${draft.preview.unknown_tax ? ' + belirlenecek KDV' : ''}</strong></p></div><button type="button" data-open-draft="${draft.id}">Satırları düzenle</button></div><div class="cari-table-wrap"><table><thead><tr><th>Ürün</th><th>Adet</th><th>Liste fiyatı</th><th>İskonto</th></tr></thead><tbody>${(p.items || []).map(item => `<tr><td>${productNameWithPhoto(item.name)}</td><td>${item.quantity}</td><td>${money(Math.round(Number(item.unit_price) * 100))}</td><td>%${escape(item.discount || '0')}</td></tr>`).join('')}</tbody></table></div><div class="cari-fields"><label>Tüm satırlara iskonto %<input data-bulk-input="${draft.id}" inputmode="decimal" placeholder="Ör. 30"></label><button type="button" data-bulk-draft="${draft.id}">Toplu iskontoyu kaydet</button></div><button type="button" class="cari-primary" data-post-draft="${draft.id}">Onayla ve cari hareketine işle</button></article>`;
    }).join('')}</section>`;
  }

  function reconciliationDocuments() {
    return (state.accountDocuments || []).filter(doc => doc.account_id === state.selected &&
      doc.source === 'attachment' && doc.extracted?.cari_reconciliation?.version === 1 &&
      doc.extracted.cari_reconciliation.status === 'pending');
  }

  function renderGiftEditor(doc, r) {
    if (!r.price_comparison) return '';
    const c=r.price_comparison,amount=n=>Number.isSafeInteger(n)?money(n):'Fiyat eksik';
    const gap=n=>!Number.isSafeInteger(n)?'Hesaplanamadı':n===0?'Tutarlar eşit':money(Math.abs(n))+(n>0?' daha az ödeme':' daha fazla ödeme');
    return `<section aria-label="Satış fiyatı ve ödeme karşılaştırması"><h3>Satış fiyatı ve ödeme karşılaştırması</h3><div class="cari-table-wrap"><table><thead><tr><th>İşlem</th><th>Hesaplanan</th><th>Gelen ödeme</th><th>Fark</th></tr></thead><tbody><tr><td>İlk liste · seçilen iskontolar</td><td>${amount(c.initial_cents)}</td><td>${amount(c.initial_received_cents)}</td><td>${gap(c.gap_cents)}</td></tr><tr><td>Ürün iskontosu ardından %5 senaryosu</td><td>${amount(c.initial_alternative_cents)}</td><td>${amount(c.initial_received_cents)}</td><td>${gap(c.alternative_gap_cents)}</td></tr><tr><td>Ek ücretli teslim</td><td>${amount(c.extra_cents)}</td><td>${amount(c.extra_received_cents)}</td><td>${gap(c.extra_cents===null?null:c.extra_cents-c.extra_received_cents)}</td></tr></tbody></table></div><p class="cari-muted">Liste içi hediyeler satış tutarından düşer. Ayrıca verilen hediyeler satış tutarını azaltmaz. Bu karşılaştırma kesin cari alacak değildir.</p></section>`;
  }
  function bindGiftEditors() {
    root.querySelectorAll('[data-edit-reconciliation]').forEach(b=>b.onclick=()=>openReconciliationEditor(b.dataset.editReconciliation,b.dataset.editSku));
    root.querySelectorAll('[data-cari-export]').forEach(b=>b.onclick=()=>downloadCari(b.dataset.cariExport,b.dataset.exportScope||'account'));
    root.querySelectorAll('.cari-table-wrap').forEach(w=>{w.tabIndex=0;w.setAttribute('role','region');w.setAttribute('aria-label','Tablo; sütunları görmek için sağa sola kaydırın');});
  }
  let reconciliationEditor = null;
  window.addEventListener('beforeunload', event => {if(reconciliationEditor?.dirty){event.preventDefault();event.returnValue='';}});
  const centsInput = value => value === null || value === undefined ? '' : String(value / 100);
  const readCents = value => String(value).trim() === '' ? null : Math.round(Number(String(value).replace(',', '.')) * 100);
  function normalizeEditorProduct(p) {
    return {...p, initial_gift_quantity:p.initial_gift_quantity || 0,
      additional_gift_quantity:p.additional_gift_quantity ?? p.known_gift_quantity ?? 0,
      discount_bps:p.discount_bps ?? 4000,
      return_price_mode:p.return_price_mode || (p.additional_unit_price_cents !== null ? 'fixed' : 'discounted'),
      fixed_return_unit_cents:p.fixed_return_unit_cents ?? p.return_unit_estimate_cents ?? null};
  }
  function editorCalculation(products, extraBps) {
    let sale=0,refund=0,extra=0,missingSale=false,missingRefund=false,missingExtra=false;
    products.forEach(p=>{
      const base=p.reference_psf_cents===null ? null : Math.round(p.reference_psf_cents*(10000-p.discount_bps)/10000);
      const unit=base===null ? null : Math.round(base*(10000-extraBps)/10000);
      const paid=Math.max(0,p.initial_quantity-p.initial_gift_quantity);
      const returned=Math.max(0,p.return_quantity-p.initial_gift_quantity-p.additional_gift_quantity);
      if(paid && unit===null) missingSale=true; else sale+=paid*(unit||0);
      if(p.additional_quantity && p.additional_unit_price_cents===null) missingExtra=true;else extra+=p.additional_quantity*(p.additional_unit_price_cents||0);
      const retUnit=p.return_price_mode==='fixed'?p.fixed_return_unit_cents:unit;
      if(returned && retUnit===null) missingRefund=true;else refund+=returned*(retUnit||0);
    });
    return {sale:missingSale?null:sale,refund:missingRefund?null:refund,extra:missingExtra?null:extra};
  }
  function openReconciliationEditor(documentId, sku) {
    const doc=reconciliationDocuments().find(d=>d.id===documentId);
    if(!doc)return;
    let dialog=el('cariReconciliationDrawer');
    if(!dialog){dialog=document.createElement('dialog');dialog.id='cariReconciliationDrawer';dialog.className='cari-editor-drawer';root.appendChild(dialog);}
    reconciliationEditor={docId:doc.id,accountId:doc.account_id,revision:doc.extracted.cari_reconciliation.revision||0,
      products:structuredClone(doc.extracted.cari_reconciliation.products).map(normalizeEditorProduct),
      extraBps:doc.extracted.cari_reconciliation.extra_discount_bps||0,active:sku||doc.extracted.cari_reconciliation.products[0]?.sku,
      dirty:false,removed:[],pending:null};
    dialog.innerHTML=`<header class="cari-drawer-head"><div><small>CARİ MUTABAKAT</small><h2 id="cariDrawerTitle">Ürünler ve iskontolar</h2></div><button type="button" data-drawer-close aria-label="Paneli kapat">×</button></header>
      <div class="cari-drawer-body"><p class="cari-muted">Değişiklikleri burada hazırla, kontrol edip kaydet. Kesinleşmiş hesap hareketleri değişmez.</p>
      <div class="cari-drawer-tools"><button type="button" data-add-product>+ Ürün ekle</button><button type="button" data-undo-remove disabled>Son çıkarmayı geri al</button></div>
      <label>Ürün ara<input data-editor-search type="search" placeholder="Ürün adı yaz"></label>
      <label>Düzenlenecek ürün<select data-editor-picker aria-label="Düzenlenecek ürün"></select></label>
      <form id="cariEditorProduct" class="cari-form"></form>
      <section class="cari-editor-bulk"><h3>Toplu iskonto</h3><div class="cari-fields"><label>Ürün iskontosu %<input data-bulk-rate type="number" min="0" max="100" step="0.01" value="40"></label><button type="button" data-apply-rate>Tüm ürünlere uygula</button><label>Ardından ek iskonto %<input data-extra-rate type="number" min="0" max="100" step="0.01" value="${centsInput(reconciliationEditor.extraBps)}"></label></div><small>İskontolar art arda uygulanır. Ek teslim ve sabit iade fiyatı bu iskontolardan etkilenmez.</small></section>
      <details><summary>Hediye alanlarının anlamı</summary><p><b>Liste içi hediye:</b> İlk listedeki adet içinde ücretsiz verilenler. <b>İlave hediye:</b> Bunların dışında ayrıca verilenler. İkisi de aynı ürünün ücretli iade adedinden düşülür. Aynı hediyeyi iki kez yazma.</p></details>
      </div><footer class="cari-drawer-foot"><div data-editor-totals aria-live="polite"></div><p data-editor-message role="status"></p><div class="cari-drawer-tools"><button type="button" data-drawer-close>Vazgeç</button><button type="button" class="cari-primary" data-save-editor>Değişiklikleri kaydet</button></div></footer>`;
    dialog.setAttribute('aria-labelledby','cariDrawerTitle');
    const close=()=>{if(reconciliationEditor.saving)return;if(reconciliationEditor.dirty && !window.confirm('Kaydedilmeyen değişikliklerden vazgeçilsin mi?'))return;dialog.close();reconciliationEditor=null;};
    dialog.querySelectorAll('[data-drawer-close]').forEach(b=>b.onclick=close);dialog.oncancel=e=>{e.preventDefault();close();};
    dialog.querySelector('[data-editor-search]').oninput=()=>renderEditorPicker();
    dialog.querySelector('[data-editor-picker]').onchange=e=>{if(!captureEditorProduct()){e.target.value=reconciliationEditor.active;return;}reconciliationEditor.active=e.target.value;renderEditorProduct();};
    dialog.querySelector('[data-add-product]').onclick=()=>{
      if(!captureEditorProduct())return;
      const p={sku:'manual-'+crypto.randomUUID(),name:'Yeni ürün',initial_quantity:1,additional_quantity:0,return_quantity:0,initial_gift_quantity:0,additional_gift_quantity:0,reference_psf_cents:null,additional_unit_price_cents:null,discount_bps:4000,return_price_mode:'discounted',fixed_return_unit_cents:null};
      reconciliationEditor.products.push(p);reconciliationEditor.active=p.sku;markEditorDirty();dialog.querySelector('[data-editor-search]').value='';renderEditorPicker();renderEditorProduct();el('cariEditorProduct').elements.name.focus();
    };
    dialog.querySelector('[data-undo-remove]').onclick=()=>{if(!captureEditorProduct())return;const p=reconciliationEditor.removed.pop();if(p){reconciliationEditor.products.push(p);reconciliationEditor.active=p.sku;markEditorDirty();renderEditorPicker();renderEditorProduct();}dialog.querySelector('[data-undo-remove]').disabled=!reconciliationEditor.removed.length;};
    dialog.querySelector('[data-apply-rate]').onclick=()=>{const input=dialog.querySelector('[data-bulk-rate]');if(!input.reportValidity()||input.value==='')return;if(!captureEditorProduct())return;reconciliationEditor.products.forEach(p=>p.discount_bps=readCents(input.value));markEditorDirty();renderEditorProduct();};
    dialog.querySelector('[data-extra-rate]').oninput=e=>{if(e.target.checkValidity()&&e.target.value!==''){reconciliationEditor.extraBps=readCents(e.target.value);markEditorDirty();updateEditorTotals();}};
    dialog.querySelector('[data-save-editor]').onclick=saveReconciliationEditor;
    renderEditorPicker();renderEditorProduct();dialog.showModal();
  }
  function markEditorDirty(){reconciliationEditor.dirty=true;reconciliationEditor.pending=null;}
  function renderEditorPicker(){
    const dialog=el('cariReconciliationDrawer'),q=dialog.querySelector('[data-editor-search]').value.toLocaleLowerCase('tr-TR');
    const items=reconciliationEditor.products.filter(p=>p.name.toLocaleLowerCase('tr-TR').includes(q)||p.sku===reconciliationEditor.active);
    dialog.querySelector('[data-editor-picker]').innerHTML=items.map(p=>`<option value="${escape(p.sku)}"${p.sku===reconciliationEditor.active?' selected':''}>${escape(p.name)}</option>`).join('');
  }
  function renderEditorProduct(){
    const form=el('cariEditorProduct'),p=reconciliationEditor.products.find(p=>p.sku===reconciliationEditor.active);
    if(!p){form.innerHTML='<p>Liste boş. Ürün ekleyebilirsin.</p>';updateEditorTotals();return;}
    const field=(name,label,value,max=10000,step=1)=>`<label>${label}<input name="${name}" type="number" min="0" max="${max}" step="${step}" value="${value??''}"${['reference_psf_cents','additional_unit_price_cents','fixed_return_unit_cents'].includes(name)?'':' required'}></label>`;
    const quantity=(name,label,value,max=10000)=>`<label>${label}<span class="cari-stepper"><button type="button" data-step="${name}" data-delta="-1" aria-label="${label} azalt">−</button><input name="${name}" type="number" min="0" max="${max}" step="1" required value="${value}"><button type="button" data-step="${name}" data-delta="1" aria-label="${label} artır">+</button></span></label>`;
    form.innerHTML=`<label>Ürün adı<input name="name" list="cariEditorCatalog" maxlength="160" required value="${escape(p.name)}"></label><datalist id="cariEditorCatalog">${state.catalog.map(c=>`<option value="${escape(c.name)}"></option>`).join('')}</datalist>
      <div class="cari-fields">${quantity('initial_quantity','İlk listedeki adet',p.initial_quantity)}${quantity('initial_gift_quantity','Liste içi hediye',p.initial_gift_quantity,p.initial_quantity)}${quantity('additional_quantity','Ek ücretli adet',p.additional_quantity)}${quantity('additional_gift_quantity','İlave hediye',p.additional_gift_quantity)}${quantity('return_quantity','İstenen iade adedi',p.return_quantity)}</div>
      <h3>Fiyat ve iskonto</h3><div class="cari-fields">${field('reference_psf_cents','PSF / liste fiyatı · TL',centsInput(p.reference_psf_cents),10000000,.01)}${field('discount_bps','Ürün iskontosu %',centsInput(p.discount_bps),100,.01)}${field('additional_unit_price_cents','Ek ücretli teslim birim fiyatı · TL',centsInput(p.additional_unit_price_cents),10000000,.01)}
      <label>İade fiyatı<select name="return_price_mode"><option value="discounted"${p.return_price_mode==='discounted'?' selected':''}>İndirimli PSF üzerinden</option><option value="fixed"${p.return_price_mode==='fixed'?' selected':''}>Sabit birim fiyat üzerinden</option></select></label>${field('fixed_return_unit_cents','Sabit iade birim fiyatı · TL',centsInput(p.fixed_return_unit_cents),10000000,.01)}</div>
      <p class="cari-muted">Boş fiyat sıfır sayılmaz; hesapta “Fiyat eksik” gösterilir.</p><button type="button" class="cari-danger" data-remove-product>Bu ürünü listeden çıkar</button>`;
    form.onsubmit=e=>e.preventDefault();
    form.oninput=event=>{form.elements.initial_gift_quantity.max=form.elements.initial_quantity.value;if(captureEditorProduct(false)){markEditorDirty();if(event.target.name==='name')renderEditorPicker();updateEditorTotals();}};
    form.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>{const input=form.elements[b.dataset.step],next=Math.max(0,Math.min(Number(input.max),Number(input.value||0)+Number(b.dataset.delta)));input.value=next;input.dispatchEvent(new Event('input',{bubbles:true}));});
    form.querySelector('[data-remove-product]').onclick=()=>{reconciliationEditor.removed.push(p);reconciliationEditor.products=reconciliationEditor.products.filter(x=>x.sku!==p.sku);reconciliationEditor.active=reconciliationEditor.products[0]?.sku;markEditorDirty();el('cariReconciliationDrawer').querySelector('[data-undo-remove]').disabled=false;renderEditorPicker();renderEditorProduct();};
    updateEditorTotals();
  }
  function captureEditorProduct(report=true){
    const form=el('cariEditorProduct'),p=reconciliationEditor.products.find(p=>p.sku===reconciliationEditor.active);if(!p)return true;
    if(!(report?form.reportValidity():form.checkValidity()))return false;
    p.name=form.elements.name.value.trim();if(!p.name)return false;
    for(const k of ['initial_quantity','initial_gift_quantity','additional_quantity','additional_gift_quantity','return_quantity'])p[k]=Number(form.elements[k].value);
    for(const k of ['reference_psf_cents','additional_unit_price_cents','fixed_return_unit_cents','discount_bps'])p[k]=readCents(form.elements[k].value);
    p.return_price_mode=form.elements.return_price_mode.value;return true;
  }
  function updateEditorTotals(){
    const totals=editorCalculation(reconciliationEditor.products,reconciliationEditor.extraBps),show=v=>v===null?'Fiyat eksik':money(v);
    el('cariReconciliationDrawer').querySelector('[data-editor-totals]').innerHTML=`<span>İlk liste <strong>${show(totals.sale)}</strong></span><span>Ek satış <strong>${show(totals.extra)}</strong></span><span>İade ön hesabı <strong>${show(totals.refund)}</strong></span>`;
  }
  async function saveReconciliationEditor(){
    if(!captureEditorProduct())return;
    const editor=reconciliationEditor,dialog=el('cariReconciliationDrawer'),extra=dialog.querySelector('[data-extra-rate]'),message=dialog.querySelector('[data-editor-message]');
    if(!extra.reportValidity()||extra.value==='')return;
    if(editor.products.length>200){message.textContent='En fazla 200 ürün kaydedilebilir.';return;}
    if(!editor.pending)editor.pending={mode:'full',account_id:editor.accountId,document_id:editor.docId,revision:editor.revision,request_id:key(),extra_discount_bps:editor.extraBps,products:editor.products.map(p=>Object.fromEntries(['sku','name','initial_quantity','initial_gift_quantity','additional_quantity','additional_gift_quantity','return_quantity','reference_psf_cents','additional_unit_price_cents','discount_bps','return_price_mode','fixed_return_unit_cents'].map(k=>[k,p[k]])))};
    editor.saving=true;dialog.querySelectorAll('input,select,button').forEach(e=>e.disabled=true);message.textContent='Kaydediliyor…';
    try{await request('/api/cari/reconciliation/update',editor.pending);editor.dirty=false;dialog.close();reconciliationEditor=null;if(state.selected===editor.accountId)await select(editor.accountId,false);}
    catch(exc){message.textContent=/fetch|network|json|unexpected/i.test(exc.message||'')?'Bağlantı nedeniyle sonuç alınamadı. Aynı kaydı yeniden deneyebilirsin.':exc.message||'Kayıt tamamlanamadı.';}
    finally{editor.saving=false;dialog.querySelectorAll('input,select,button').forEach(e=>e.disabled=false);}
  }

  async function downloadCari(format, scope='account') {
    const params=new URLSearchParams({format,scope});
    if(scope==='portfolio'){if(state.reportDate)params.set('as_of',state.reportDate);}else if(state.selected)params.set('account_id',state.selected);else return;
    try{
      const response=await fetch('/api/cari/export?'+params,{credentials:'same-origin',cache:'no-store'});
      if(!response.ok){const body=await response.json();throw new Error(body.error||'Dosya hazırlanamadı.');}
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=(scope==='portfolio'?'cari-hesaplar':'cari-'+(state.statement?.account.name||'rapor').replace(/[^\p{L}\p{N} -]/gu,'')) + '.' + format;
      document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    }catch(exc){error(/fetch|network|json|unexpected/i.test(exc.message||'')?'İndirme tamamlanamadı. Bağlantıyı kontrol edip yeniden dene.':exc.message);}
  }
  function renderReconciliations() {
    return reconciliationDocuments().map(doc => {
      const r = doc.extracted.cari_reconciliation;
      const number = n => Number.isSafeInteger(n) && n >= 0 ? n : null;
      const price = n => number(n) === null ? 'Belirlenmedi' : money(n);
      const products = Array.isArray(r.products) ? r.products : [];
      const payments = Array.isArray(r.payments) ? r.payments : [];
      const returns = products.filter(p => number(p.return_quantity) > 0);
      const sum = (items, key) => items.reduce((n, p) => n + (number(p[key]) || 0), 0);
      const total = payments.every(p => number(p.amount_cents) !== null) ? sum(payments, 'amount_cents') : null;
      const estimate = returns.length && returns.every(p => number(p.return_estimate_cents) !== null) ? sum(returns, 'return_estimate_cents') : null;
      const alternative = returns.length && returns.every(p => number(p.return_alternative_cents) !== null) ? sum(returns, 'return_alternative_cents') : null;
      const quantity = p => (number(p.initial_quantity) || 0) + (number(p.additional_quantity) || 0) + (number(p.additional_gift_quantity ?? p.known_gift_quantity) || 0);
      return `<section class="cari-card cari-reconciliation" aria-label="Satış ve iade mutabakatı">
        <div class="cari-section-head"><h3>Satış, ödeme ve iade talebi</h3><div class="cari-toolbar cari-no-print"><button type="button" class="cari-primary" data-edit-reconciliation="${escape(doc.id)}">Ürün, hediye ve iskonto düzenle</button><button type="button" data-cari-export="pdf" data-export-scope="reconciliation">Liste PDF</button><button type="button" data-cari-export="xlsx" data-export-scope="reconciliation">Liste Excel</button></div></div><p class="cari-scroll-hint">Tüm sütunlar için tabloyu sağa sola kaydırabilirsin →</p>
        <p class="cari-alert"><strong>Mutabakat bekliyor.</strong> Kullanıcı beyanı ve ürün listeleri kaydedildi. Bu bölüm kesinleşmiş muhasebe hareketi değildir; ekstre bakiyesine eklenmez. Tarih, hediye ayrımı ve kesin iade fiyatları bekleniyor.</p>
        <div class="cari-stats"><div class="cari-stat"><span>BİLDİRİLEN TOPLAM ÖDEME</span><strong>${price(total)}</strong></div><div class="cari-stat"><span>İSTENEN İADE</span><strong>${sum(returns, 'return_quantity')} adet</strong><small>${returns.length} ürün çeşidi</small></div><div class="cari-stat"><span>TAHMİNİ İADE TUTARI</span><strong>${price(estimate)}</strong><small>Bilinen hediyeler düşüldü; kalanlar bekleniyor</small></div></div>
        <p>${escape(r.invoice_note)}</p>
        <div class="cari-table-wrap"><table><caption>Ödeme bilgileri · Kullanıcı tarafından bildirildi</caption><thead><tr><th>Açıklama</th><th>Tutar</th><th>İşlem tarihi</th></tr></thead><tbody>${payments.map(p => `<tr><td>${escape(p.label)}</td><td>${price(p.amount_cents)}</td><td>${escape(p.date || 'Henüz bildirilmedi')}</td></tr>`).join('')}</tbody></table></div>
        <p class="cari-table-note">${escape(r.payment_note)}</p>
        ${renderGiftEditor(doc, r)}
        <details open><summary>Satılan / teslim edilen ürünler · ${products.reduce((n, p) => n + quantity(p), 0)} adet</summary><p>${escape(r.delivery_note)}</p><div class="cari-table-wrap"><table><thead><tr><th>Ürün</th><th>İlk liste</th><th>Ek ücretli teslim</th><th>Bilinen hediye</th><th>Toplam teslim</th><th>Ek satış birim fiyatı</th><th class="cari-no-print">İşlem</th></tr></thead><tbody>${products.filter(p => quantity(p) > 0).map(p => `<tr><td>${productNameWithPhoto(p.name)}</td><td>${number(p.initial_quantity) || 0}</td><td>${number(p.additional_quantity) || 0}</td><td>${number(p.known_gift_quantity) || 0}</td><td>${quantity(p)}</td><td>${price(p.additional_unit_price_cents)}</td><td class="cari-no-print"><button type="button" data-edit-reconciliation="${escape(doc.id)}" data-edit-sku="${escape(p.sku)}" aria-label="${escape(p.name)} düzenle">Düzenle</button></td></tr>`).join('')}</tbody></table></div></details>
        <details open><summary>İadesi istenen ürünler · ${sum(returns, 'return_quantity')} adet</summary><p class="cari-alert">İade talebidir; ürünlerin geri alındığı veya para iadesi yapıldığı henüz doğrulanmadı.</p><div class="cari-table-wrap"><table><thead><tr><th>Ürün</th><th>İstenen adet</th><th>Hediye mahsubu</th><th>Ücret hesabına kalan adet</th><th>Tahmini birim tutarı</th><th>Tahmini satır tutarı</th><th>Ek %5 senaryosu</th><th class="cari-no-print">İşlem</th></tr></thead><tbody>${returns.map(p => `<tr><td>${productNameWithPhoto(p.name)}</td><td>${p.return_quantity}</td><td>${number(p.return_gift_offset_quantity) || 0}</td><td>${Math.max(0,p.return_quantity-(number(p.return_gift_offset_quantity) || 0))}</td><td>${price(p.return_unit_estimate_cents)}</td><td>${price(p.return_estimate_cents)}</td><td>${price(p.return_alternative_cents)}</td><td class="cari-no-print"><button type="button" data-edit-reconciliation="${escape(doc.id)}" data-edit-sku="${escape(p.sku)}" aria-label="${escape(p.name)} düzenle">Düzenle</button></td></tr>`).join('')}</tbody><tfoot><tr><th>TAHMİNİ TOPLAM</th><td>${sum(returns, 'return_quantity')}</td><td>${sum(returns, 'return_gift_offset_quantity')}</td><td>${returns.reduce((n,p)=>n+Math.max(0,p.return_quantity-(number(p.return_gift_offset_quantity)||0)),0)}</td><td></td><td>${price(estimate)}</td><td>${price(alternative)}</td><td class="cari-no-print"></td></tr></tfoot></table></div></details>
        <p class="cari-alert">${escape(r.estimate_note)}</p>
        <p>${escape(r.pending_note)}</p>
        <a href="/api/cari/documents/content?id=${encodeURIComponent(doc.id)}" target="_blank" rel="noopener">İlk hesap raporunu aç — sonraki hediye değişikliklerini içermez</a>
      </section>`;
    }).join('');
  }

  function renderStatement() {
    const {account, entries, summary, settlements: allocated} = state.statement;
    const reversed = new Set(entries.filter(entry => entry.reverses).map(entry => entry.reverses));
    let balance = 0;
    const shown = entries.filter(entry => (!state.filter.from || entry.payload.date >= state.filter.from) &&
      (!state.filter.to || entry.payload.date <= state.filter.to) &&
      (!state.filter.kind || entry.payload.kind === state.filter.kind) &&
      (!state.filter.product || entry.payload.items.some(item => item.name.toLocaleLowerCase('tr-TR').includes(state.filter.product.toLocaleLowerCase('tr-TR')))));
    const rows = shown.map(entry => {
      const p = entry.payload;
      const signed = (entry.reverses ? -1 : 1) * p.signed_cents;
      balance += signed;
      const items = p.items.length ? `<details class="cari-details"><summary>${p.items.length} ürün satırı</summary>${p.items.map(item => `<p>${escape(item.name)} · ${item.quantity} adet × ${money(item.unit_price_cents)} · iskonto %${escape(item.discount)} · KDV ${item.tax_rate === null ? 'belirlenmedi' : '%' + escape(item.tax_rate)}<br>Net: ${money(item.net_cents)} · KDV: ${item.tax_rate === null ? 'belirlenecek' : money(item.tax_cents)}</p>`).join('')}</details>` : '';
      const settlement = allocated?.[entry.id];
      const paymentText = settlement ? `<small>Ödeme: ${settlement.status === 'paid' ? 'Alındı / ödendi' : settlement.status === 'partial' ? 'Kısmi' : 'Alınmadı / ödenmedi'} · ${money(settlement.paid_cents)} / ${money(settlement.paid_cents + settlement.remaining_cents)}${settlement.unknown_tax ? ' + KDV belirsiz' : ''}</small>` : p.applies_to ? `<small>${{pos: 'POS', havale: 'Havale / EFT', elden: 'Elden', other: 'Diğer'}[p.payment_method] || 'Yöntem belirtilmedi'} · Belgeye eşleşti</small>` : '';
      const docLinks = state.documents.filter(doc => doc.entry_id === entry.id).map(doc => `<a href="/api/cari/documents/content?id=${encodeURIComponent(doc.id)}" target="_blank" rel="noopener">${escape(doc.filename)}</a>`).join(' ');
      return `<tr${reversed.has(entry.id) ? ' class="cari-reversed"' : ''}><td>${day(p.date)}${p.due_date ? '<small>Vade: ' + day(p.due_date) + '</small>' : ''}</td><td>${entry.reverses ? 'Ters kayıt · ' : ''}${labels[p.kind]}${reversed.has(entry.id) ? '<small>Ters kayıtla düzeltildi</small>' : ''}<small>${escape(p.reference)}${p.note ? ' · ' + escape(p.note) : ''}</small>${paymentText}${docLinks ? `<small>Ek: ${docLinks}</small>` : ''}${items}</td><td class="cari-money">${signed > 0 ? money(signed) : '—'}</td><td class="cari-money">${signed < 0 ? money(-signed) : '—'}</td><td class="cari-money">${money(balance)}${p.unknown_tax ? '<small>Bu belgede KDV belirsiz</small>' : ''}</td><td class="cari-no-print">${!entry.reverses && !reversed.has(entry.id) ? `${settlement && settlement.remaining_cents > 0 ? `<button type="button" data-pay="${entry.id}">${p.kind === 'sale' || p.kind === 'opening_receivable' ? 'Ödeme alındı' : 'Ödeme yapıldı'}</button> ` : ''}<button type="button" data-attach="${entry.id}">Belge ekle</button> <button type="button" data-edit="${entry.id}">${p.items.length ? 'Ürün / iskonto düzenle' : 'Düzenle'}</button> <button class="cari-danger" type="button" data-reverse="${entry.id}">İptal et</button>` : ''}</td></tr>`;
    }).join('');
    const unknown = summary.unknown_tax_documents > 0;
    const amountNote = unknown ? ' + KDV' : '';
    const receivable = Math.max(summary.balance_cents, 0), payable = Math.max(-summary.balance_cents, 0);
    const reversedIds = new Set(entries.filter(entry => entry.reverses).map(entry => entry.reverses));
    const effective = entries.filter(entry => !entry.reverses && !reversedIds.has(entry.id));
    const collections = effective.filter(entry => entry.payload.kind === 'collection');
    const payments = effective.filter(entry => entry.payload.kind === 'payment');
    const pendingReview = reconciliationDocuments().length > 0;
    const info = pendingReview ? 'Aşağıdaki bakiye yalnız kesinleşmiş hareketleri içerir. Satış, ödeme ve iade mutabakatı henüz tamamlanmadı.' : summary.balance_cents > 0 ? `Toplam alacak tutarımız ${money(receivable)}${amountNote}’dir.` : summary.balance_cents < 0 ? `Toplam borç tutarımız ${money(payable)}${amountNote}’dir.` : unknown ? 'Bilinen tutarlar dengede; kesin bakiye için KDV oranları bekleniyor.' : 'Hesap bakiyesi sıfırdır.';
    const cashInfo = pendingReview ? 'Bildirilen ödemeler yukarıdaki satış ve iade bölümündedir; tarih ve belge eşleştirmesi bekleniyor.' : account.role === 'supplier' ? (payments.length ? `Kaydedilen ödemeler: ${money(payments.reduce((n, entry) => n + entry.payload.net_cents, 0))}.` : 'Henüz kesinleşmiş ödeme kaydı girilmedi.') : (collections.length ? `Kaydedilen tahsilatlar: ${money(collections.reduce((n, entry) => n + entry.payload.net_cents, 0))}.` : 'Henüz kesinleşmiş tahsilat kaydı girilmedi.');
    el('cariStatement').innerHTML = `<section class="cari-account-head"><div><h2>${escape(account.name)}</h2><p class="cari-muted">${roles[account.role]}${account.contact ? ' · ' + escape(account.contact) : ''}</p>${account.tax_id ? `<p class="cari-muted">Vergi / kimlik no: ${escape(account.tax_id)}</p>` : ''}${account.tax_office ? `<p class="cari-muted">Vergi dairesi: ${escape(account.tax_office)}</p>` : ''}${account.address ? `<p class="cari-muted">${escape(account.address)}</p>` : ''}${account.email || account.phone ? `<p class="cari-muted">${escape([account.email, account.phone].filter(Boolean).join(' · '))}</p>` : ''}${account.note ? '<p class="cari-muted">' + escape(account.note) + '</p>' : ''}</div><div class="cari-toolbar cari-no-print"><button type="button" id="cariEditAccount">Cari bilgilerini düzenle</button><button type="button" id="cariNewEntry" class="cari-primary">+ Hareket ekle</button><button type="button" id="cariPrint">Yazdır</button><button type="button" data-cari-export="pdf">PDF indir</button><button type="button" data-cari-export="xlsx">Excel indir</button><button type="button" id="cariCsv">CSV indir</button></div></section>
      <section class="cari-stats cari-account-stats" aria-label="Hesap durumu">${stat('TOPLAM BORÇ', money(payable) + (payable ? amountNote : ''), 'blue', 'wallet')}${stat('TOPLAM ALACAK', money(receivable) + (receivable ? amountNote : ''), 'green', 'arrow')}${stat('BAKİYE', money(Math.abs(summary.balance_cents)) + amountNote, 'orange', 'calculator')}${stat('CARİ DURUMU', escape(pendingReview ? 'Mutabakat bekliyor' : summary.status), 'purple', 'chart')}</section>
      ${renderReconciliations()}
      ${renderDrafts()}
      ${renderCatalogGallery(account, effective)}
      <section class="cari-product-section" aria-label="Ürün ve fiyat özeti"><div class="cari-product-controls cari-no-print"><div class="cari-product-tabs" role="group" aria-label="Ürün hareket türü"><button type="button" data-product-family="sale">Satışlar</button><button type="button" data-product-family="purchase">Alışlar</button><button type="button" data-product-family="gift">Bedelsiz ürünler</button></div><span>İadeler düşülmüştür · KDV hariç</span></div><div id="cariProductTable"></div></section>
      <aside class="cari-info" aria-label="Hesap bilgisi"><span class="cari-info-symbol" aria-hidden="true">i</span><div><h3>BİLGİ</h3><p>${info}</p><p>${cashInfo}</p>${unknown ? `<p class="cari-tax-note">${summary.unknown_tax_documents} belgede KDV oranı belirlenmedi. Gösterilen bakiye kesin KDV dahil tutar değildir.</p>` : '<p class="cari-tax-note">Bakiye, belgelerdeki KDV ve kaydedilen ödemeler dahil hesaplanır.</p>'}</div><span class="cari-info-document">${icon('document')}</span></aside>
      ${renderDeliveryHistory(effective)}
      <details class="cari-card cari-secondary"><summary>Ürün giriş / çıkış ayrıntıları</summary><p class="cari-muted">Bedelsiz teslimler ve ters kayıtlar dahil ürün adedi hareketleri.</p><div class="cari-table-wrap"><table><thead><tr><th>Ürün</th><th class="cari-money">Verdik</th><th class="cari-money">Aldık</th><th class="cari-money">Net verilen</th></tr></thead><tbody>${summary.products.map(p => `<tr><td>${productNameWithPhoto(p.name)}</td><td class="cari-money">${p.given}</td><td class="cari-money">${p.received}</td><td class="cari-money">${p.given - p.received}</td></tr>`).join('') || '<tr><td colspan="4">Henüz ürün hareketi yok.</td></tr>'}</tbody></table></div></details>
      <details class="cari-card cari-secondary cari-ledger" open><summary>Hesap ekstresi</summary><p class="cari-muted">Pozitif bakiye alacağımız, negatif bakiye borcumuzdur. Filtreli görünümde satır bakiyesi filtreye göredir; güncel bakiye tam hesaptır.</p><div class="cari-fields cari-no-print"><label>Başlangıç<input id="cariFilterFrom" type="date" value="${escape(state.filter.from)}"></label><label>Bitiş<input id="cariFilterTo" type="date" value="${escape(state.filter.to)}"></label><label>Hareket<select id="cariFilterKind"><option value="">Tümü</option>${Object.entries(labels).map(([value, label]) => `<option value="${value}"${state.filter.kind === value ? ' selected' : ''}>${label}</option>`).join('')}</select></label><label>Ürün<input id="cariFilterProduct" value="${escape(state.filter.product)}" placeholder="Ürün ara"></label></div><div class="cari-table-wrap"><table><thead><tr><th>Tarih</th><th>Hareket / açıklama</th><th class="cari-money">Alacak artışı</th><th class="cari-money">Alacak azalışı</th><th class="cari-money">Bakiye</th><th class="cari-no-print"></th></tr></thead><tbody>${rows || '<tr><td colspan="6">Bu filtrede hareket yok.</td></tr>'}</tbody><tfoot><tr class="cari-total"><td colspan="4">GÜNCEL BAKİYE</td><td class="cari-money">${money(summary.balance_cents)}${suffix(summary)}</td><td class="cari-no-print"></td></tr></tfoot></table></div></details>`;
    renderProductTable();
    bindGiftEditors();
    root.querySelectorAll('[data-product-family]').forEach(button => {button.onclick = () => {state.productFamily = button.dataset.productFamily; renderProductTable();};});
    el('cariNewEntry').onclick = openEntry;
    el('cariEditAccount').onclick = openAccountEditor;
    el('cariPrint').onclick = () => window.print();
    el('cariCsv').onclick = csv;
    for (const [id, field] of [['cariFilterFrom', 'from'], ['cariFilterTo', 'to'], ['cariFilterKind', 'kind'], ['cariFilterProduct', 'product']]) {
      el(id).onchange = event => {state.filter[field] = event.target.value; renderStatement();};
    }
    root.querySelectorAll('[data-pay]').forEach(button => {button.onclick = () => openPayment(button.dataset.pay);});
    root.querySelectorAll('[data-attach]').forEach(button => {button.onclick = () => attachEntry(button.dataset.attach);});
    root.querySelectorAll('[data-open-draft]').forEach(button => {button.onclick = () => openDraft(button.dataset.openDraft);});
    root.querySelectorAll('[data-post-draft]').forEach(button => {button.onclick = () => postDraft(button.dataset.postDraft);});
    root.querySelectorAll('[data-bulk-draft]').forEach(button => {button.onclick = () => bulkDraft(button.dataset.bulkDraft);});
    root.querySelectorAll('[data-edit]').forEach(button => {button.onclick = () => openCorrection(button.dataset.edit);});
    root.querySelectorAll('[data-reverse]').forEach(button => {button.onclick = () => {
      const form = el('cariReverseForm'); form.reset(); form.elements.entry_id.value = button.dataset.reverse;
      form.elements.date.value = today(); form.dataset.requestId = key(); form.dataset.accountId = state.selected;
      error('', 'cariReverseError'); el('cariReverseDialog').showModal();
    };});
  }

  function renderDeliveryHistory(entries) {
    const descriptions = {
      sale: ['Ürün teslimi', 'Verdik'], purchase: ['Ürün alımı', 'Aldık'],
      sale_return: ['Müşteriden iade', 'Geri aldık'], purchase_return: ['Tedarikçiye iade', 'Geri verdik'],
      gift_out: ['Bedelsiz teslim', 'Verdik'], gift_in: ['Bedelsiz ürün alımı', 'Aldık']
    };
    const deliveries = entries.filter(entry => descriptions[entry.payload.kind]);
    return `<section class="cari-card cari-deliveries" aria-label="Tarihli teslim ve iade geçmişi"><div class="cari-section-head"><div><h3>Teslim ve iade geçmişi</h3><p class="cari-muted">Hangi gün, hangi üründen kaç adet verdik veya geri aldık?</p></div><span class="cari-delivery-count">${deliveries.length} hareket</span></div>${deliveries.length ? `<ol class="cari-timeline">${deliveries.map(entry => {
      const p = entry.payload, [title, direction] = descriptions[p.kind];
      const returned = p.kind.endsWith('_return');
      return `<li class="cari-delivery${returned ? ' cari-delivery-return' : ''}"><div class="cari-delivery-date"><span class="cari-delivery-dot" aria-hidden="true">${returned ? '↩' : '↓'}</span><time datetime="${p.date}">${day(p.date)}</time></div><article><div class="cari-section-head"><h4>${title}</h4><span class="cari-delivery-direction">${direction} · ${p.items.reduce((n, item) => n + item.quantity, 0)} adet</span></div><ul class="cari-delivery-products">${p.items.map(item => `<li>${productNameWithPhoto(item.name)}<strong>${item.quantity} adet</strong></li>`).join('')}</ul><div class="cari-delivery-footer"><span>${p.kind.startsWith('gift_') ? 'Bedelsiz' : `${money(p.net_cents)} · KDV hariç`}</span>${p.reference ? `<span>Belge: ${escape(p.reference)}</span>` : ''}</div>${p.note ? `<p class="cari-delivery-note">${escape(p.note)}</p>` : ''}</article></li>`;
    }).join('')}</ol>` : '<p class="cari-muted">Henüz teslim veya iade kaydı yok.</p>'}<p class="cari-table-note">Geçerli teslim ve iadeler işlem tarihine göre gösterilir. Ters kayıtla iptal edilen hareketler hesap ekstresinde korunur.</p></section>`;
  }

  function renderProductTable() {
    const family = state.productFamily;
    const data = state.statement.product_tables?.[family];
    root.querySelectorAll('[data-product-family]').forEach(button => {button.setAttribute('aria-pressed', String(button.dataset.productFamily === family));});
    if (!data) {
      el('cariProductTable').innerHTML = '<p class="cari-alert">Ürün fiyat özeti alınamadı. Uygulama sürümünü ve bağlantıyı kontrol edin.</p>';
      return;
    }
    const heading = family === 'sale' ? 'SATIŞLAR' : family === 'purchase' ? 'ALIŞLAR' : 'BEDELSİZ ÜRÜNLER';
    const discountedPriceSum = data.rows.reduce((total, item) => total + item.discounted_unit_price_cents, 0);
    const recommendedRows = data.rows.filter(item => item.recommended_price_cents !== null);
    const recommendedPriceSum = recommendedRows.reduce((total, item) => total + item.recommended_price_cents, 0);
    const missingRecommended = data.rows.length - recommendedRows.length;
    const recommendedFooter = recommendedRows.length ? `${money(recommendedPriceSum)}${missingRecommended ? '<small>Eksik fiyat var</small>' : ''}` : '—';
    el('cariProductTable').innerHTML = `<div class="cari-product-quick cari-no-print"><button type="button" class="cari-primary" data-product-step="add">+ Ürün ekle</button><button type="button" data-product-step="remove">− Ürün çıkar</button></div><p class="cari-scroll-hint">Fiyat ve tutarlar için tabloyu yana kaydırın →</p><div class="cari-table-wrap cari-reference-wrap" tabindex="0" role="region" aria-label="${heading} ürün tablosu, küçük ekranda yana kaydırılabilir"><table class="cari-reference-table"><caption class="cari-print-title">${heading} · Ürün toplamı, tahsilatlar düşülmeden</caption><thead><tr><th scope="col">ÜRÜN</th><th scope="col" class="cari-quantity">ADET</th><th scope="col" class="cari-money">TAVSİYE EDİLEN PİYASA SATIŞ FİYATI</th><th scope="col" class="cari-money">İSKONTOLU KDV HARİÇ FİYAT</th><th scope="col" class="cari-money">TUTAR (KDV HARİÇ)</th></tr></thead><tbody>${data.rows.map((item, index) => `<tr><td>${productNameWithPhoto(item.name)}</td><td class="cari-quantity"><span class="cari-qty-step"><button type="button" class="cari-no-print" data-product-step="remove" data-product-row="${index}" aria-label="${escape(item.name)} ürününden çıkar" title="Ürün çıkar">−</button><span>${item.quantity}</span><button type="button" class="cari-no-print" data-product-step="add" data-product-row="${index}" aria-label="${escape(item.name)} ürününden ekle" title="Ürün ekle">+</button></span></td><td class="cari-money">${item.recommended_price_cents === null ? '<span class="cari-muted" title="Bu belgede tavsiye fiyatı girilmedi">—</span>' : money(item.recommended_price_cents)}</td><td class="cari-money">${money(item.discounted_unit_price_cents)}</td><td class="cari-money"><strong>${money(item.net_cents)}</strong></td></tr>`).join('') || '<tr><td colspan="5" class="cari-empty">Bu türde ürün hareketi yok.</td></tr>'}</tbody><tfoot><tr><th scope="row">GENEL TOPLAM (KDV HARİÇ)</th><td class="cari-quantity">${data.quantity}</td><td class="cari-money">${recommendedFooter}</td><td class="cari-money">${money(discountedPriceSum)}</td><td class="cari-money">${money(data.net_cents)}</td></tr></tfoot></table></div><p class="cari-table-note">Fiyat sütunlarının altındaki tutarlar görünen satırların birim fiyat toplamıdır; son sütun adet ve iadeler dikkate alınarak hesaplanır. ${missingRecommended ? `${missingRecommended} satırda tavsiye edilen fiyat eksik. ` : ''}Ürün toplamından tahsilatlar düşülmez. Farklı fiyatlı işlemler ayrı satırlarda gösterilir. Birim fiyat yuvarlaması satır tutarını değiştirmez. Kaydedilmiş ürünleri ve iskontoları değiştirmek için aşağıdaki hesap ekstresindeki ilgili hareketi düzenleyin.${family === 'gift' ? ' Eksi adet, bedelsiz ürün girişini gösterir.' : ''}</p>`;
    el('cariProductTable').querySelectorAll('[data-product-step]').forEach(button => {
      button.onclick = () => openProductStep(button.dataset.productStep === 'add',
        button.dataset.productRow === undefined ? null : data.rows[Number(button.dataset.productRow)]);
    });
  }

  // Ürün tablosundan hızlı ekle/çıkar. Kayıt değiştirilmez: ekleme yeni bir
  // satış/alış/bedelsiz teslim, çıkarma ise iade hareketi olarak aynı onaylı
  // formdan (Hesapla ve kontrol et → Kaydet) geçer.
  const productSteps = {sale: ['sale', 'sale_return'], purchase: ['purchase', 'purchase_return'], gift: ['gift_out', 'gift_in']};
  function openProductStep(add, item) {
    openEntry();
    const form = el('cariEntryForm');
    form.elements.kind.value = productSteps[state.productFamily][add ? 0 : 1];
    if (item) {
      const row = el('cariLines').lastElementChild;
      const field = name => row.querySelector('[name=' + name + ']');
      field('product').value = item.name;
      field('quantity').value = 1;
      if (item.unit_price_cents !== undefined) field('price').value = (item.unit_price_cents / 100).toFixed(2);
      if (item.discount !== undefined) field('discount').value = item.discount;
      if (item.tax_rate !== null && item.tax_rate !== undefined) {
        if (['0', '1', '10', '20'].includes(String(item.tax_rate))) field('tax').value = String(item.tax_rate);
        else {field('tax').value = 'custom'; field('customTax').hidden = false; field('customTax').required = true; field('customTax').value = item.tax_rate;}
      }
      if (item.recommended_price_cents !== null && item.recommended_price_cents !== undefined) field('recommendedPrice').value = (item.recommended_price_cents / 100).toFixed(2);
    }
    switchKind();
    el('cariEntryTitle').textContent = add ? 'Ürün ekle' : 'Ürün çıkar (iade)';
    if (item) el('cariLines').lastElementChild.querySelector('[name=quantity]').focus();
  }

  function renderAccountInfo() {
    const account = state.statement?.account;
    const box = el('cariInfoContent');
    if (!account) {box.innerHTML = '<p>Cari seçin.</p>'; return;}
    box.innerHTML = `<div class="cari-section-head"><div><h2>${escape(account.name)} · Cari bilgileri</h2><p class="cari-muted">Faturadan okunan alıcı bilgilerini burada kontrol edip tamamlayabilirsiniz.</p></div></div>
      <form id="cariInfoForm" class="cari-form"><div class="cari-fields"><label>Kişi / firma adı<input name="name" maxlength="160" required value="${escape(account.name)}"></label><label>Cari türü<select name="role"><option value="customer">Müşteri</option><option value="supplier">Tedarikçi</option><option value="both">Müşteri ve tedarikçi</option></select></label><label>Vergi / kimlik numarası<input name="tax_id" maxlength="20" inputmode="numeric" value="${escape(account.tax_id || '')}"></label><label>Vergi dairesi<input name="tax_office" maxlength="160" value="${escape(account.tax_office || '')}"></label><label>E-posta<input name="email" type="email" maxlength="200" value="${escape(account.email || '')}"></label><label>Telefon<input name="phone" maxlength="50" value="${escape(account.phone || '')}"></label></div><label>Adres<textarea name="address" maxlength="1000" rows="3">${escape(account.address || '')}</textarea></label><label>İletişim<input name="contact" maxlength="200" value="${escape(account.contact || '')}"></label><label>Not<textarea name="note" maxlength="2000" rows="3">${escape(account.note || '')}</textarea></label><p id="cariInfoError" class="cari-error" role="alert" hidden></p><button type="submit" class="cari-primary">Bilgileri kaydet</button></form>`;
    const form = el('cariInfoForm');
    form.elements.role.value = account.role;
    form.onsubmit = async event => {
      event.preventDefault();
      const button = form.querySelector('[type=submit]'); button.disabled = true;
      try {
        const data = Object.fromEntries(new FormData(form));
        await request('/api/cari/accounts/update', {...data, account_id: state.selected, covers: account.covers || {}});
        await refresh(); switchTab('info');
      } catch (exc) {error(exc.message, 'cariInfoError');}
      finally {button.disabled = false;}
    };
  }

  function openAccountEditor() {
    const account = state.statement.account, form = el('cariAccountForm');
    state.editAccount = true; form.reset();
    for (const field of ['name', 'role', 'contact', 'note', 'tax_id', 'tax_office', 'address', 'email', 'phone']) form.elements[field].value = account[field] || '';
    el('cariAccountTitle').textContent = 'Cariyi düzenle';
    form.querySelector('[type=submit]').textContent = 'Değişiklikleri kaydet';
    const mentioned = [account.note || '', ...state.statement.entries.flatMap(entry => entry.payload.items.map(item => item.name))].join(' ');
    const products = state.catalog.filter(product => product.images.length &&
      (mentionsProduct(mentioned, product) || account.covers?.[product.slug]));
    const choices = el('cariCoverChoices');
    choices.innerHTML = products.length ? `<h3>Ürün kapak görselleri</h3><p class="cari-muted">E-ticaret kataloğundaki fotoğraflardan seçim yapın.</p>${products.map(product => `<div class="cari-cover-choice"><img src="/katalog-gorsel/${encodeURIComponent(account.covers?.[product.slug] || product.cover)}" alt="${escape(product.name)} seçili görseli"><label>${escape(product.name)}<select data-cover="${escape(product.slug)}">${product.images.map((image, index) => `<option value="${escape(image)}"${image === (account.covers?.[product.slug] || product.cover) ? ' selected' : ''}>Kapak ${index + 1}</option>`).join('')}</select></label></div>`).join('')}` : '<p class="cari-muted">Bu caride katalog ürünü bulunamadı.</p>';
    choices.hidden = false;
    choices.querySelectorAll('[data-cover]').forEach(select => {select.onchange = () => {select.closest('.cari-cover-choice').querySelector('img').src = '/katalog-gorsel/' + encodeURIComponent(select.value);};});
    error('', 'cariAccountError'); el('cariAccountDialog').showModal();
  }

  async function createAccount(event) {
    event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button');
    button.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(form));
      if (state.editAccount) {
        data.account_id = state.selected;
        data.covers = {...(state.statement.account.covers || {})};
        el('cariCoverChoices').querySelectorAll('[data-cover]').forEach(select => {
          const product = state.catalog.find(item => item.slug === select.dataset.cover);
          if (select.value === product?.cover) delete data.covers[select.dataset.cover];
          else data.covers[select.dataset.cover] = select.value;
        });
      }
      const result = await request(state.editAccount ? '/api/cari/accounts/update' : '/api/cari/accounts', data);
      state.selected = result.id; el('cariAccountDialog').close(); await refresh();
    } catch (exc) {error(exc.message, 'cariAccountError');}
    finally {button.disabled = false;}
  }

  function clearPreview() {state.pending = null; el('cariPreview').hidden = true; el('cariSaveEntry').hidden = true; el('cariSaveDraft').hidden = true;}
  function addLine() {
    const row = document.createElement('div'); row.className = 'cari-line';
    row.innerHTML = `<label>Ürün adı<input name="product" maxlength="160" required></label><label>Adet<input name="quantity" type="number" min="1" max="100000" step="1" value="1" required></label><label>Birim fiyat (TL)<input name="price" inputmode="decimal" required placeholder="0,00"></label><label>İskonto %<input name="discount" inputmode="decimal" value="0" required></label><label class="cari-line-tax">KDV oranı<select name="tax"><option value="">Belirlenmedi</option><option value="0">%0</option><option value="1">%1</option><option value="10">%10</option><option value="20">%20</option><option value="custom">Diğer oran</option></select><input name="customTax" inputmode="decimal" placeholder="Oran %" aria-label="Diğer KDV oranı" hidden></label><label class="cari-line-recommended">Tavsiye satış fiyatı (TL)<input name="recommendedPrice" inputmode="decimal" placeholder="İsteğe bağlı"></label><button type="button" aria-label="Ürün satırını kaldır">×</button>`;
    row.querySelector('button').onclick = () => {row.remove(); clearPreview();};
    row.querySelector('[name=tax]').onchange = event => {const custom = row.querySelector('[name=customTax]'); custom.hidden = event.target.value !== 'custom'; custom.required = !custom.hidden;};
    el('cariLines').appendChild(row); switchKind();
  }

  function openEntry() {
    const form = el('cariEntryForm'); form.reset(); form.elements.date.value = today();
    state.editing = null; state.editingDraft = null; el('cariCorrectionFields').hidden = true;
    form.elements.correction_date.required = false; form.elements.reason.required = false;
    el('cariEntryTitle').textContent = 'Yeni hareket'; el('cariSaveEntry').textContent = 'Hareketi kaydet';
    form.dataset.accountId = state.selected; el('cariLines').replaceChildren(); addLine(); clearPreview();
    error('', 'cariEntryError'); el('cariEntryDialog').showModal();
  }

  function openDraft(draftId) {
    const draft = state.drafts.find(item => item.id === draftId);
    if (!draft) return;
    openEntry(); state.editingDraft = draftId;
    const form = el('cariEntryForm'), p = draft.body;
    for (const field of ['kind', 'date', 'due_date', 'reference', 'note']) form.elements[field].value = p[field] || '';
    if (cash.has(p.kind)) form.elements.amount.value = p.amount || '';
    else {
      el('cariLines').replaceChildren();
      for (const item of p.items || []) {
        addLine(); const row = el('cariLines').lastElementChild;
        const field = name => row.querySelector('[name=' + name + ']');
        field('product').value = item.name;
        field('quantity').value = item.quantity;
        field('price').value = item.unit_price;
        field('discount').value = item.discount || '0';
        field('recommendedPrice').value = item.recommended_price || '';
        if (item.tax_rate !== null && item.tax_rate !== undefined) {
          if (['0', '1', '10', '20'].includes(String(item.tax_rate))) field('tax').value = String(item.tax_rate);
          else {field('tax').value = 'custom'; field('customTax').hidden = false; field('customTax').required = true; field('customTax').value = item.tax_rate;}
        }
      }
    }
    switchKind();
    if (p.payment_method) form.elements.payment_method.value = p.payment_method;
    if (p.applies_to) form.elements.applies_to.value = p.applies_to;
    el('cariEntryTitle').textContent = 'Cari taslağını düzenle';
    el('cariSaveEntry').textContent = 'Taslağı kaydet';
    clearPreview();
  }

  async function bulkDraft(draftId) {
    const draft = state.drafts.find(item => item.id === draftId);
    const input = root.querySelector(`[data-bulk-input="${draftId}"]`);
    if (!draft || !input || !Array.isArray(draft.body.items)) return;
    const discount = decimal(input.value);
    if (!/^\d{1,3}(?:\.\d{1,2})?$/.test(discount) || Number(discount) > 100) {
      error('Toplu iskonto 0 ile 100 arasında olmalı.'); return;
    }
    try {
      await request('/api/cari/drafts/update', {...draft.body, account_id: state.selected,
        draft_id: draftId, items: draft.body.items.map(item => ({...item, discount}))});
      await select(state.selected, false);
    } catch (exc) {error(exc.message);}
  }

  async function postDraft(draftId) {
    const draft = state.drafts.find(item => item.id === draftId);
    if (!draft) return;
    try {
      const preview = await request('/api/cari/preview', draft.body);
      const question = `${state.statement.account.name}: ${money(Math.abs(preview.signed_cents))}${preview.unknown_tax ? ' + belirlenecek KDV' : ''} tutarlı taslak cari hareketine kaydedilecek. Ürün fiyatları ve iskontoları kontrol edildi mi?`;
      if (!window.confirm(question)) return;
      await request('/api/cari/drafts/post', {account_id: state.selected, draft_id: draftId});
      await refresh();
    } catch (exc) {error(exc.message);}
  }

  function openCorrection(entryId) {
    const entry = state.statement.entries.find(item => item.id === entryId);
    if (!entry) return;
    openEntry(); state.editing = entryId;
    const form = el('cariEntryForm'), p = entry.payload;
    form.elements.kind.value = p.kind;
    form.elements.date.value = p.date;
    form.elements.due_date.value = p.due_date || '';
    form.elements.reference.value = p.reference || '';
    form.elements.note.value = p.note || '';
    if (cash.has(p.kind)) form.elements.amount.value = (p.net_cents / 100).toFixed(2);
    else {
      el('cariLines').replaceChildren();
      for (const item of p.items) {
        addLine(); const row = el('cariLines').lastElementChild;
        const field = name => row.querySelector('[name=' + name + ']');
        field('product').value = item.name;
        field('quantity').value = item.quantity;
        field('price').value = (item.unit_price_cents / 100).toFixed(2);
        field('discount').value = item.discount;
        if (item.tax_rate !== null) {
          if (['0', '1', '10', '20'].includes(item.tax_rate)) field('tax').value = item.tax_rate;
          else {field('tax').value = 'custom'; field('customTax').hidden = false; field('customTax').required = true; field('customTax').value = item.tax_rate;}
        }
        if (item.recommended_price_cents !== undefined) field('recommendedPrice').value = (item.recommended_price_cents / 100).toFixed(2);
      }
    }
    switchKind();
    if (p.payment_method) form.elements.payment_method.value = p.payment_method;
    if (p.applies_to) form.elements.applies_to.value = p.applies_to;
    form.elements.correction_date.value = today() < p.date ? p.date : today(); form.elements.reason.value = '';
    form.elements.correction_date.required = true; form.elements.reason.required = true;
    el('cariCorrectionFields').hidden = false;
    el('cariEntryTitle').textContent = p.items.length ? 'Ürün ve iskontoyu düzenle' : 'Hareketi düzenle';
    el('cariSaveEntry').textContent = 'Düzeltmeyi kaydet';
    clearPreview();
  }

  function switchKind() {
    const kind = el('cariEntryForm').elements.kind.value;
    const isCash = cash.has(kind); const gift = kind.startsWith('gift_');
    el('cariGoods').hidden = isCash; el('cariCash').hidden = !isCash;
    const isPayment = kind === 'collection' || kind === 'payment';
    el('cariPaymentFields').hidden = !isPayment;
    const select = el('cariEntryForm').elements.applies_to;
    const current = select.value;
    select.innerHTML = '<option value="">Eşleştirilmedi</option>' + Object.entries(state.statement?.settlements || {})
      .filter(([id, s]) => (s.remaining_cents > 0 || (state.editing && state.statement.entries.find(e => e.id === state.editing)?.payload.applies_to === id)) && state.statement.entries.some(e => e.id === id &&
        (kind === 'collection' ? ['sale', 'opening_receivable'] : ['purchase', 'opening_payable']).includes(e.payload.kind)))
      .map(([id, s]) => {const e = state.statement.entries.find(row => row.id === id); return `<option value="${id}">${escape(e.payload.reference || day(e.payload.date))} · ${money(s.remaining_cents)}</option>`;}).join('');
    if ([...select.options].some(option => option.value === current)) select.value = current;
    el('cariEntryForm').elements.amount.required = isCash;
    el('cariLines').querySelectorAll('input,select').forEach(input => {input.disabled = isCash;});
    el('cariLines').querySelectorAll('.cari-line').forEach(row => {
      for (const name of ['price', 'discount', 'tax']) {
        const input = row.querySelector('[name=' + name + ']');
        if (gift) input.value = '0';
        input.disabled = isCash || gift;
      }
      if (gift || isCash) {const custom = row.querySelector('[name=customTax]'); custom.hidden = true; custom.required = false;}
    });
  }

  function payload() {
    const form = el('cariEntryForm');
    const data = Object.fromEntries(new FormData(form));
    const isCash = cash.has(data.kind), gift = data.kind.startsWith('gift_');
    data.account_id = form.dataset.accountId; data.request_id = key();
    if (isCash) data.amount = decimal(data.amount);
    if (data.kind !== 'collection' && data.kind !== 'payment') {delete data.payment_method; delete data.applies_to;}
    else {if (!data.payment_method) delete data.payment_method; if (!data.applies_to) delete data.applies_to;}
    if (!isCash) data.items = [...el('cariLines').children].map(row => {
      const get = name => row.querySelector('[name=' + name + ']').value;
      const rate = get('tax');
      return {name: get('product'), quantity: Number(get('quantity')), unit_price: gift ? '0' : decimal(get('price')),
        discount: gift ? '0' : decimal(get('discount')), recommended_price: get('recommendedPrice').trim() ? decimal(get('recommendedPrice')) : null, tax_rate: gift ? '0' : rate === '' ? null : decimal(rate === 'custom' ? get('customTax') : rate)};
    });
    return data;
  }

  async function preview(event) {
    event.preventDefault(); clearPreview(); error('', 'cariEntryError');
    const form = el('cariEntryForm'), data = payload(); const button = event.submitter; button.disabled = true;
    const correction = state.editing ? {
      account_id: state.selected, entry_id: state.editing, request_id: key(),
      correction_date: form.elements.correction_date.value,
      reason: form.elements.reason.value.trim(), replacement: data
    } : null;
    if (correction && (!correction.reason || correction.correction_date < state.statement.entries.find(entry => entry.id === state.editing).payload.date)) {
      error('Düzeltme gerekçesi gerekli; düzeltme tarihi asıl işlemden önce olamaz.', 'cariEntryError'); button.disabled = false; return;
    }
    const encoded = JSON.stringify({data, correction: correction && {
      date: correction.correction_date, reason: correction.reason}});
    try {
      const result = await request('/api/cari/preview', data);
      // Any edit made while the request was running invalidates this preview.
      const current = payload(); current.request_id = data.request_id;
      const currentCorrection = correction && {
        date: form.elements.correction_date.value, reason: form.elements.reason.value.trim()};
      if (JSON.stringify({data: current, correction: currentCorrection}) !== encoded) return;
      state.pending = correction || data;
      el('cariPreview').innerHTML = `<p>${escape(state.statement.account.name)} · ${labels[result.kind]}</p><strong>${money(result.net_cents + result.tax_cents)}${result.unknown_tax ? ' + belirlenecek KDV' : ''}</strong><p>Net: ${money(result.net_cents)} · KDV: ${result.unknown_tax ? 'Oran girilmedi' : money(result.tax_cents)}</p><small>${correction ? 'Eski kayıt terslenip bu tutarla değiştirilecek.' : result.signed_cents > 0 ? 'Alacağımız artacak / borcumuz azalacak.' : result.signed_cents < 0 ? 'Alacağımız azalacak / borcumuz artacak.' : 'Yalnız ürün adedi değişecek.'} Henüz kaydedilmedi.</small>`;
      el('cariPreview').hidden = false; el('cariSaveEntry').hidden = false;
      el('cariSaveDraft').hidden = Boolean(state.editing || state.editingDraft);
    } catch (exc) {error(exc.message, 'cariEntryError');}
    finally {button.disabled = false;}
  }

  async function saveEntry() {
    if (!state.pending) return;
    const button = el('cariSaveEntry'); button.disabled = true;
    try {
      if (state.editingDraft) await request('/api/cari/drafts/update', {...state.pending,
        account_id: state.selected, draft_id: state.editingDraft});
      else await request(state.editing ? '/api/cari/correct' : '/api/cari/entries', state.pending);
      el('cariEntryDialog').close(); state.pending = null; state.editing = null;
      state.editingDraft = null; await refresh();
    }
    catch (exc) {error(exc.message, 'cariEntryError');}
    finally {button.disabled = false;}
  }

  async function saveDraft() {
    if (!state.pending || state.editing || state.editingDraft) return;
    const button = el('cariSaveDraft'); button.disabled = true;
    try {
      await request('/api/cari/drafts/create', state.pending);
      el('cariEntryDialog').close(); state.pending = null; await refresh();
    } catch (exc) {error(exc.message, 'cariEntryError');}
    finally {button.disabled = false;}
  }

  async function reverseEntry(event) {
    event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button');
    button.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(form));
      data.account_id = form.dataset.accountId; data.request_id = form.dataset.requestId;
      await request('/api/cari/reverse', data); el('cariReverseDialog').close(); await refresh();
    } catch (exc) {error(exc.message, 'cariReverseError');}
    finally {button.disabled = false;}
  }

  function csv() {
    const {account, entries, summary} = state.statement;
    const rows = [['Cari', account.name], ['Para birimi', 'TRY'],
      ['KDV durumu', summary.unknown_tax_documents > 0 ? 'Belirlenmemiş KDV var' : 'KDV dahil / girilen tutar'],
      ['Tarih', 'Tür', 'Belge', 'Açıklama', 'Ürün', 'Adet', 'Birim fiyat TL', 'Tavsiye satış fiyatı TL', 'İskonto %', 'KDV %', 'Net TL', 'KDV TL', 'İmzalı tutar TL']];
    for (const entry of entries.filter(entry => (!state.filter.from || entry.payload.date >= state.filter.from) &&
      (!state.filter.to || entry.payload.date <= state.filter.to) &&
      (!state.filter.kind || entry.payload.kind === state.filter.kind) &&
      (!state.filter.product || entry.payload.items.some(item => item.name.toLocaleLowerCase('tr-TR').includes(state.filter.product.toLocaleLowerCase('tr-TR')))))) {
      const p = entry.payload, sign = entry.reverses ? -1 : 1;
      rows.push([p.date, (entry.reverses ? 'Ters kayıt: ' : '') + labels[p.kind], p.reference, p.note, '', '', '', '', '', '', p.net_cents / 100, p.unknown_tax ? 'Belirlenecek' : p.tax_cents / 100, sign * p.signed_cents / 100]);
      for (const item of p.items) rows.push(['', '', '', '', item.name, item.quantity, item.unit_price_cents / 100, item.recommended_price_cents === undefined ? '' : item.recommended_price_cents / 100, item.discount, item.tax_rate === null ? 'Belirlenecek' : item.tax_rate, item.net_cents / 100, item.tax_rate === null ? 'Belirlenecek' : item.tax_cents / 100, '']);
    }
    const cell = value => {
      if (typeof value === 'number') return String(value).replace('.', ',');
      let text = String(value ?? '');
      if (/^[\s]*[=+@\-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    const blob = new Blob(['\uFEFF' + rows.map(row => row.map(cell).join(';')).join('\r\n')], {type: 'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'cari-ekstre-' + today() + '.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  let loading = null;
  async function load() {
    if (loading) return loading;
    loading = (async () => {
      if (!el('cariAccounts')) shell();
      try {
        const session = await request('/api/session');
        if (!session.authenticated) throw new Error('Cari hesapları görmek için Jarvis’e giriş yapın.');
        state.csrf = session.csrf_token; await refresh(); await loadCatalog();
      } catch (exc) {error(exc.message);}
    })();
    try {await loading;} finally {loading = null;}
  }
  window.JarvisCari = {load};
  if (root.dataset.standalone === 'true') load();
})();
