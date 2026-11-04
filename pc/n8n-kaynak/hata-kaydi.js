// =============================================================================
// L'CARLIE - ORTAK HATA KAYDI YARDIMCILARI
//
// CR-002 madde 2 · 15.09.2026
//
// Bu dosya bir n8n dugumune AYNEN GOMULUR (build-*-workflow.js tarafindan
// /tmp/hata-kaydi.js olarak okunur ve kodun basina yapistirilir).
// n8n Code node'unda require() yoktur; bu yuzden module.exports en altta
// ve korumali - build betikleri onu kirpar.
//
// 🔴 NEDEN VAR:
//    CR-001'de aktif Instagram ve WhatsApp workflow'larinda HICBIR hata
//    yolu olmadigi bulundu. Ajan bir istisna firlattiginda musteri HTTP 500
//    aliyor; kayit yazilmiyor, eskalasyon olusmuyor, sayac artmiyor -
//    mesaj IZSIZ kayboluyordu. Bu yardimcilar, her kanalda AYNI sekilde
//    calisan tek bir hata kaydi bicimi saglar.
//
// 🔴 PII YASAGI:
//    Hata kaydina musteri mesaji, telefon, e-posta YAZILMAZ.
//    Kimlik yerine 'correlation_id' tutulur; gercek musteri kimligi zaten
//    eskalasyon/kayit listelerinde var. Hata kaydi operasyonel bir kayittir,
//    konusma kaydi degildir.
// =============================================================================

// Kac hata kaydi saklanacak. Statik veri her calistirmada TAMAMEN yeniden
// yazildigi icin bu liste sinirsiz buyuyemez.
const HATA_KAYIT_SINIRI = 200;

// -----------------------------------------------------------------------------
// PII temizleme
//
// 🔴 Hata metinleri bazen girdiyi yankilar (ornegin JSON ayristirma hatalari
//    "unexpected token ... at position" ile birlikte govdeyi basabilir).
//    Bu yuzden ozet kaydedilmeden ONCE temizlenir, sonra kirpilir.
// -----------------------------------------------------------------------------
function piiTemizle(metin) {
  let t = String(metin == null ? '' : metin);
  // e-posta
  t = t.replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '<eposta>');
  // 6+ haneli rakam dizileri (telefon, wamid, sipariş no, kart benzeri)
  t = t.replace(/\d{6,}/g, '<sayi>');
  // Meta mesaj kimlikleri (wamid.*) - rakamsiz da olabiliyor
  t = t.replace(/wamid\.[A-Za-z0-9_=-]+/gi, '<mesajId>');
  // Uzun base64/token benzeri diziler
  t = t.replace(/\b[A-Za-z0-9_-]{32,}\b/g, '<uzun-deger>');
  // Satir sonlarini tek satira indir
  t = t.replace(/\s+/g, ' ').trim();
  return t.slice(0, 200);
}

// -----------------------------------------------------------------------------
// Hata sinifi
//
// 'continueRegularOutput' ile gelen oge farkli bicimlerde olabilir:
//   { error: 'metin' } · { error: { name, message } } · { error: { message } }
// Hangisi gelirse gelsin kararli bir sinif adi uretilir.
// -----------------------------------------------------------------------------
function hataSinifi(hata) {
  if (!hata) return 'BILINMEYEN';
  if (typeof hata === 'string') {
    if (/not found|bulunamad/i.test(hata))            return 'ALT_AKIS_BULUNAMADI';
    if (/active version|not active|yayinda degil/i.test(hata)) return 'ALT_AKIS_YAYINDA_DEGIL';
    if (/timeout|zaman asimi/i.test(hata))            return 'ZAMAN_ASIMI';
    if (/birden fazla|multiple items/i.test(hata))    return 'COKLU_OGE';
    return 'CALISMA_HATASI';
  }
  const ad = hata.name || hata.errorName || '';
  const mesaj = hata.message || hata.description || '';
  if (ad) return String(ad).replace(/[^A-Za-z0-9_]/g, '_').slice(0, 40).toUpperCase();
  return hataSinifi(String(mesaj || 'BILINMEYEN'));
}

function hataOzeti(hata) {
  if (!hata) return '';
  if (typeof hata === 'string') return piiTemizle(hata);
  return piiTemizle(hata.message || hata.description || JSON.stringify(hata));
}

// -----------------------------------------------------------------------------
// Korelasyon kimligi
//
// 🔴 PII ICERMEZ. Musteri kimliginden TUREMEZ - yoksa telefon numarasi
//    dolayli olarak hata kaydina sizardi.
//    Bicim: <kanal>-<zaman36>-<rastgele4>   ornek: ig-m3kq8p-7f2a
// -----------------------------------------------------------------------------
function korelasyonUret(kanal) {
  const k = String(kanal || 'x').slice(0, 4);
  const z = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 6);
  return k + '-' + z + '-' + r;
}

// -----------------------------------------------------------------------------
// Hata kaydi yaz
//
// Zorunlu alanlar (CR-002 madde 2):
//   timestamp · workflow_id · execution_id · channel · stage
//   error_class · error_summary · correlation_id
// -----------------------------------------------------------------------------
function hataKaydet(sd, a) {
  if (!sd) return null;
  if (!Array.isArray(sd.hatalar)) sd.hatalar = [];
  const kayit = {
    ts: new Date().toISOString(),
    workflow_id: String(a.workflow_id || '-'),
    execution_id: String(a.execution_id || '-'),
    channel: String(a.channel || '-'),
    stage: String(a.stage || '-'),
    error_class: String(a.error_class || 'BILINMEYEN').slice(0, 60),
    error_summary: piiTemizle(a.error_summary || ''),
    correlation_id: String(a.correlation_id || '-')
  };
  sd.hatalar.unshift(kayit);
  if (sd.hatalar.length > HATA_KAYIT_SINIRI) sd.hatalar.length = HATA_KAYIT_SINIRI;
  sd.hataToplam = (sd.hataToplam || 0) + 1;
  return kayit;
}

// n8n'e gomulurken bu blok build betigi tarafindan kirpilir.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { piiTemizle, hataSinifi, hataOzeti, korelasyonUret, hataKaydet, HATA_KAYIT_SINIRI };
}
