/* Kullanıcıya gösterilen iş adları. Üretim komutları kuyrukta aynen kalır. */
(function (root) {
  'use strict';
  const sections = {
    ritual: 'Ritüel', bebek: 'Bebek', mahrem: 'Mahrem bakım', bariyer: 'Cilt bariyeri',
    vucut: 'Vücut', yuz: 'Yüz', kapak: 'Kapak',
  };
  const technical = /\b(?:extreme macro|editorial|texture|continuous surface|shallow focus|photorealistic|soft diffused light|soft even light|fine water film|matte silk|muslin weave|render|live capability|data contract|step\(s\)|internal server error|traceback|syntaxerror|typeerror|HTTP\s*\d+)\b|\b(?:SUCCEEDED|PENDING|PROPOSED|FAILED|RUNNING)\b|\{\s*"/i;
  function needsSummary(value) { return technical.test(String(value || '')) || /\b[a-z]+(?:_[a-z]+)+\b/.test(String(value || '')); }
  function safeTitle(value, fallback) {
    const title = String(value || '').trim();
    return !title ? fallback : needsSummary(title) ? fallback : title;
  }
  function jobTitle(job) {
    const request = String(job?.istem || '').trim();
    if (String(job?.isteyen || '').startsWith('katalog/bolum-acilisi')) {
      const section = sections[String(job?.id || '').replace(/^ktb?-/, '')];
      return section ? `Katalog görseli: ${section}` : 'Katalog bölüm görseli';
    }
    if (!needsSummary(request)) return request || 'Başlıksız iş';
    if (/sage green|eucalyptus|mineral surface/i.test(request)) return 'Adaçayı tonlarında mineral yüzey görseli';
    if (/cotton muslin|milk white fibres|muslin weave/i.test(request)) return 'Beyaz pamuklu kumaş görseli';
    if (/matte silk|muted plum|deep rose/i.test(request)) return 'Gül ve erik tonlarında ipek kumaş görseli';
    if (/terracotta clay|burnt ochre|fine fissures/i.test(request)) return 'Toprak tonlarında çatlak kil görseli';
    return 'Görsel hazırlama işi';
  }
  function source(job) {
    const value = String(job?.isteyen || '');
    if (value.startsWith('katalog/')) return 'Katalog çalışması';
    if (value === 'mobil-operator') return 'Telefondan istendi';
    if (value === 'panel' || value === 'operator') return 'Panelden istendi';
    return value ? 'Otomatik çalışma' : '';
  }
  function errorText(value, fallback) {
    const message = String(value || '').trim();
    return message && !needsSummary(message) && (/[çğıöşüİ]/i.test(message) || /\b(?:hatalı|eksik|geçersiz|bulunamadı|zorunlu|lütfen|izin|erişim|başarısız)\b/i.test(message))
      ? message : fallback;
  }
  const codes = {
    OK:'Hazır', PASS:'Geçti', FAIL:'Tamamlanamadı', FAILED:'Tamamlanamadı',
    CONNECTED:'Bağlı', DISCONNECTED:'Bağlı değil', PRODUCED:'Üretildi',
    CURRENT:'Güncel', FRESH:'Güncel', STALE:'Güncel değil', UNKNOWN:'Bilinmiyor',
    READY:'Hazır', ACTIVE:'Etkin', INACTIVE:'Etkin değil', UNAVAILABLE:'Kullanılamıyor',
    NEEDS_DATA:'Veri gerekli', DATA_UNAVAILABLE:'Veri yok',
    LOW:'Düşük', MEDIUM:'Orta', HIGH:'Yüksek', CRITICAL:'Kritik',
    ecommerce:'E-ticaret', advertising:'Reklam', crm:'Müşteri ilişkileri',
    operations:'Operasyon', finance:'Finans', sales:'Satış',
  };
  function label(value, fallback = 'Bilgi') {
    const raw = String(value || '').trim();
    if (!raw) return fallback;
    if (codes[raw]) return codes[raw];
    if (/^[A-Z][A-Z0-9_ -]+$/.test(raw) || /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/.test(raw)) return fallback;
    return safeTitle(raw, fallback);
  }
  root.JarvisMetin = Object.freeze({jobTitle, source, safeTitle, needsSummary, errorText, label});
})(globalThis);
