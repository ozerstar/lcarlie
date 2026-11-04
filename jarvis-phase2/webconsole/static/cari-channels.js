/* Read-only source and invoice board. A record is not proof of a live feed. */
(() => {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const amount = row => row.gross_cents === null ? 'Tutar bilinmiyor' :
    (row.gross_cents / 100).toLocaleString('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2}) + ' ' + escape(row.currency);
  const invoiceLabels = {unknown:'Bilgi doğrulanmadı',missing:'Fatura eksik',draft:'Taslak',issued:'Düzenlenmiş',cancelled:'İptal'};
  const uploadLabels = {unknown:'Aktarım doğrulanmadı',pending:'Aktarım bekliyor',uploaded:'Platforma aktarılmış',rejected:'Aktarım reddedilmiş',not_applicable:'Platform aktarımı uygulanmıyor'};
  const evidenceLabels = {manual:'Elle girilen kayıt',provider_api:'API kaynaklı kayıt',provider_export:'Kaynak raporu'};
  let generation = 0, data = null;

  function render() {
    const root = document.getElementById('cariChannels');
    if (!root || !data) return;
    const selected = root.querySelector('[data-channel-select]')?.value || '';
    const search = root.querySelector('[data-channel-search]')?.value || '';
    root.innerHTML = `<div class="cari-section-head"><div><h2>Kanallar ve faturalar</h2><small>Sipariş → müşteri → fatura → gönderi / POS eşleştirmesi</small></div><button type="button" data-channel-refresh>Yenile</button></div><div class="cari-channel-cards">${data.channels.map(channel => `<article><strong>${escape(channel.name)}</strong><span>${channel.records ? channel.records + ' kayıt · ' + channel.store_count + ' mağaza/hesap' : 'Henüz veri alınmadı'}</span><small>Canlı bağlantı doğrulanmadı</small></article>`).join('')}</div><p class="cari-alert">${escape(data.notice)}</p><div class="cari-toolbar"><label>Kaynak<select data-channel-select><option value="">Tüm kaynaklar</option>${data.channels.map(channel => `<option value="${escape(channel.id)}">${escape(channel.name)}</option>`).join('')}</select></label><label>Müşteri / mağaza / sipariş ara<input type="search" data-channel-search placeholder="İsim veya sipariş numarası"></label><span>${data.invoice_check_count} kayıtta fatura kontrolü gerekiyor</span></div><div class="cari-table-wrap"><table><thead><tr><th>Kaynak / mağaza</th><th>Sipariş / müşteri</th><th class="cari-money">Brüt tutar</th><th>Fatura</th><th>Bağlı kayıtlar</th></tr></thead><tbody data-channel-orders></tbody></table></div><details class="cari-due-reviews"><summary>Kargo ve POS kayıtları · ${data.other_records.length}</summary><p class="cari-muted">Bunlar ayrıca satış sayılmaz. Sipariş bağlantısı, tutar benzerliğiyle kurulmaz.</p><div class="cari-table-wrap"><table><thead><tr><th>Kaynak</th><th>İşlem / gönderi</th><th>Durum</th><th>Brüt tutar</th><th>Sipariş eşleşmesi</th></tr></thead><tbody data-channel-other></tbody></table></div></details><p class="cari-muted">QNB fiziksel POS için anlık aktarım henüz doğrulanmadı. Cihaz modeli ve bankanın raporlama/entegrasyon erişimi netleşince veri akışı bağlanabilir.</p>`;
    root.querySelector('[data-channel-select]').value = selected;
    root.querySelector('[data-channel-search]').value = search;
    root.querySelector('[data-channel-select]').onchange = filter;
    root.querySelector('[data-channel-search]').oninput = filter;
    root.querySelector('[data-channel-refresh]').onclick = load;
    filter();
  }

  function filter() {
    const root = document.getElementById('cariChannels');
    const selected = root.querySelector('[data-channel-select]').value;
    const search = root.querySelector('[data-channel-search]').value.toLocaleLowerCase('tr-TR');
    const names = Object.fromEntries(data.channels.map(row => [row.id,row.name]));
    const matches = row => (!selected || row.source === selected) &&
      [row.store_name,row.store_id,row.customer_name,row.customer_id,row.object_id].some(value => String(value || '').toLocaleLowerCase('tr-TR').includes(search));
    const rows = data.orders.filter(matches);
    root.querySelector('[data-channel-orders]').innerHTML = rows.map(row => `<tr><td>${escape(names[row.source])}<small>${escape(row.store_name || row.store_id)}</small><small>${escape(evidenceLabels[row.evidence_kind])}</small></td><td>${escape(row.object_id)}<small>${escape(row.customer_name || 'Müşteri adı kaynakta yok')}</small><small>Kaynak durumu: ${escape(row.status)}</small></td><td class="cari-money">${amount(row)}</td><td>${escape(invoiceLabels[row.invoice.status])}<small>${escape(row.invoice.number || row.invoice.uuid)}</small><small>${escape(uploadLabels[row.invoice.platform_status])}</small>${row.invoice_checks.map(note => '<small class="cari-channel-warning">' + escape(note) + '</small>').join('')}</td><td>${row.related.map(link => escape(names[link.source]) + ' · ' + escape(link.object_id)).join('<br>') || 'Henüz bağlı kayıt yok'}</td></tr>`).join('') || '<tr><td colspan="5">Gösterilecek sipariş/fatura kaydı yok. Mağaza bağlantıları doğrulanınca kaynak verileri buraya alınacak.</td></tr>';
    root.querySelector('[data-channel-other]').innerHTML = data.other_records.filter(matches).map(row => `<tr><td>${escape(names[row.source])}</td><td>${escape(row.object_id)}<small>${escape(row.customer_name)}</small></td><td>${escape(row.status)}</td><td class="cari-money">${amount(row)}</td><td>${row.order_matched ? escape(names[row.order_link.source]) + ' · ' + escape(row.order_link.object_id) : 'Eşleştirilmedi'}</td></tr>`).join('') || '<tr><td colspan="5">Kargo veya POS gözlemi alınmadı.</td></tr>';
  }

  async function load() {
    const root = document.getElementById('cariChannels');
    if (!root) return;
    const own = ++generation;
    try {
      const response = await fetch('/api/cari/channels',{credentials:'same-origin',cache:'no-store'});
      const result = await response.json();
      if (!response.ok) throw new Error(response.status === 401 ? 'Kaynakları görmek için Jarvis’e giriş yapın.' : result.error || 'Kanal kayıtları okunamadı.');
      if (own !== generation) return;
      data = result; render();
    } catch (exc) {
      if (own === generation) root.innerHTML = '<h2>Kanallar ve faturalar</h2><p class="cari-error" role="alert">' + escape(exc.message) + '</p>';
    }
  }
  window.JarvisCariChannels = {load};
})();
