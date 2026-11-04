// =============================================================================
// L'CARLIE - TRAFIK SINIFLANDIRMA (test / production / unknown)
//
// CR-002.5 madde A · 15.09.2026
//
// Bu dosya n8n dugumlerine AYNEN GOMULUR (build-*-workflow.js tarafindan
// /tmp/kimlik.js olarak okunur). n8n Code node'unda require() yoktur;
// module.exports en altta ve korumali - build betikleri onu kirpar.
//
// 🔴 NEDEN VAR:
//    CR-002'de sinifllandirma bir REGEX RED LISTESI ile yapiliyordu
//    (TEST_KIMLIK_DESENI). Red listeleri her zaman GERIDEN GELIR: 15.09
//    23:37'de paralel bir oturum 'sinav-0-30197' kimlikleriyle 12 test
//    mesaji gonderdi, desende 'sinav' olmadigi icin hepsi URETIM
//    KONUSMASI sayildi ve panel bekleyen musteriyi 3 yerine 5 gosterdi.
//    Yeni bir test adi bulan herkes gostergeyi kirletebiliyordu.
//
//    Yeni kural: TEST TRAFIGI KENDINI BEYAN ETMEK ZORUNDA.
//    Zorunlu onek: 'test-'
//
// 🔴 UC SINIF - 'unknown' OTOMATIK URETIM SAYILMAZ:
//    production : gercek musteri trafigi
//    test       : sentetik / fixture / smoke / sinav / dogrulama
//    unknown    : kimlik yok veya atfedilemiyor  -> METRIGE GIRMEZ,
//                 ama KAYBEDILMEZ, ayri raporlanir
// =============================================================================

const TEST_ONEK = 'test-';

// -----------------------------------------------------------------------------
// trafikSinifi(musteriId, acikSinif)
//
// Oncelik sirasi (CR-002.5 madde A):
//   a) ACIK BEYAN  - yalnizca GUVENILIR cagiranlar verir (fixture, harness)
//   b) 'test-' ONEKI
//   c) kimliksiz   -> unknown
//   d) digerleri   -> production
//
// 🔴 ACIK BEYAN WEBHOOK GOVDESINDEN OKUNMAZ.
//    Instagram webhook'unun govdesi tamamen istemci kontrolunde. Eger
//    govdedeki 'is_test' alanina guvenseydik, herkes kendi mesajini
//    "test" isaretleyip panelden GIZLEYEBILIRDI - insana aktarilan
//    gercek bir konusma gorunmez olurdu. Kanal kodu bu yuzden acik
//    beyani HIC gecirmez; yalnizca onek belirleyicidir.
//    Acik beyan, kodun kendi ic testleri/fixture'lari icindir.
//
// 🔴 ESKI REGEX BURADA YOK. Tarihsel kayitlar icin geriye donuk uyum
//    yalnizca saglik.sh tarafinda, SON CARE olarak uygulanir.
// -----------------------------------------------------------------------------
function trafikSinifi(musteriId, acikSinif) {
  if (acikSinif === 'test' || acikSinif === true)  return 'test';
  if (acikSinif === 'production')                  return 'production';

  const id = String(musteriId == null ? '' : musteriId).trim();
  if (!id || id === '-')                           return 'unknown';
  // 🔴 toLowerCase() Turkce yerel ayarda 'I' -> 'ı' yapabilir; onek ASCII
  //    oldugu icin karsilastirma da ASCII kucuk harfle yapilir.
  if (id.slice(0, TEST_ONEK.length).toLowerCase() === TEST_ONEK) return 'test';
  return 'production';
}

// -----------------------------------------------------------------------------
// testKimligiUret(ad) - fixture/test kimligi uretici
//
// Yeni bir fixture yazan herkesin dogru oneki elle hatirlamasini beklemeyiz;
// uretici zaten dogrusunu verir (CR-002.5 madde A-4).
//   testKimligiUret('smoke')     -> 'test-smoke-m3kq8p7f'
//   testKimligiUret('test-x')    -> 'test-x-m3kq8p7f'   (cift onek eklenmez)
// -----------------------------------------------------------------------------
function testKimligiUret(ad) {
  let temiz = String(ad == null ? 'fixture' : ad).trim().replace(/[^A-Za-z0-9_-]/g, '-');
  if (!temiz) temiz = 'fixture';
  if (temiz.slice(0, TEST_ONEK.length).toLowerCase() === TEST_ONEK) {
    temiz = temiz.slice(TEST_ONEK.length);
  }
  const r = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  return TEST_ONEK + temiz + '-' + r;
}

function testKimligiMi(id) {
  return trafikSinifi(id) === 'test';
}

// -----------------------------------------------------------------------------
// kimlikDogrula(id) - test harness kapisi (CR-002.5 madde A-3)
//
// 🔴 CANLI UC NOKTAYA istek gonderen her test bunu cagirmali.
//    Onek yoksa TEST CALISMAZ - sessizce uretim metrigini kirletmek
//    yerine gurultulu bicimde durur.
// -----------------------------------------------------------------------------
function kimlikDogrula(id, nerede) {
  const s = trafikSinifi(id);
  if (s !== 'test') {
    throw new Error(
      'TEST KIMLIK STANDARDI IHLALI' + (nerede ? ' (' + nerede + ')' : '') +
      ': "' + id + '" kimligi "' + TEST_ONEK + '" ile baslamiyor. ' +
      'Sentetik trafik uretim metrigine giremez - testKimligiUret() kullanin.'
    );
  }
  return id;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { TEST_ONEK, trafikSinifi, testKimligiUret, testKimligiMi, kimlikDogrula };
}
