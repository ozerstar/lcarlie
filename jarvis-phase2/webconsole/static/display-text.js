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
  root.JarvisMetin = Object.freeze({jobTitle, source, safeTitle, needsSummary, errorText});
})(globalThis);
