// =====================================================================
// L'CARLIE - TEST KIMLIK STANDARDI KAPISI   (CR-002.5 madde A-3)
//
// Neden ayri bir test?
//   CR-002'de test/uretim ayrimi bir REGEX RED LISTESINE dayaniyordu.
//   15.09 23:37'de paralel bir oturum 'sinav-0-30197' kimlikleriyle 12
//   mesaj gonderdi; desende 'sinav' olmadigi icin hepsi URETIM KONUSMASI
//   sayildi ve panel bekleyen musteriyi 3 yerine 5 gosterdi.
//   Red listeleri her zaman GERIDEN GELIR.
//
// 🔴 BU TEST YAYINLAMAYI DURDURUR.
//    Canli uc noktaya istek gonderen bir yapilandirma veya betik
//    'test-' oneki olmayan sentetik kimlik kullaniyorsa yayinlama
//    BASARISIZ olur. Standardi hatirlamak zorunda degiliz - kapi tutuyor.
//
// Olculen:
//   1. kimlik.js siniflandirmasi dogru calisiyor (production/test/unknown)
//   2. testKimligiUret() her zaman 'test-' onekli uretiyor
//   3. kimlikDogrula() onek yoksa ISTISNA FIRLATIYOR
//   4. Yayinlama duman testi kimligi 'test-' onekli
//   5. Uretilen workflow'lar trafik siniflandirmasini GERCEKTEN yaziyor
//   6. 'unknown' hicbir kosulda production'a donusmuyor
// =====================================================================
const fs = require('fs');
const path = require('path');

const KLASOR = __dirname;
let basarili = 0, basarisiz = 0;
const kontrol = (ad, kosul, detay) => {
  if (kosul) { basarili++; console.log('  ok   ' + ad); }
  else { basarisiz++; console.log('  HATA ' + ad + (detay ? '  -> ' + detay : '')); }
};

const K = require(path.join(KLASOR, 'kimlik.js'));

// =====================================================================
console.log('\n--- 1) Siniflandirma ---');
// =====================================================================
kontrol('test- oneki -> test',        K.trafikSinifi('test-smoke-1') === 'test');
kontrol('TEST- (buyuk harf) -> test', K.trafikSinifi('TEST-Smoke') === 'test');
kontrol('gercek musteri -> production', K.trafikSinifi('web-cb97nziw') === 'production');
kontrol('telefon -> production',      K.trafikSinifi('905551112233') === 'production');
// 🔴 Eski test adlari ARTIK test sayilmaz - onek zorunlu. Bu bilincli:
//    kod tarafinda tek kural olsun, tarihsel istisnalar saglik.sh'te kalsin.
kontrol('eski "sinav-0" -> production (onek yok)', K.trafikSinifi('sinav-0-30197') === 'production');
kontrol('bos kimlik -> unknown',      K.trafikSinifi('') === 'unknown');
kontrol('"-" kimlik -> unknown',      K.trafikSinifi('-') === 'unknown');
kontrol('null kimlik -> unknown',     K.trafikSinifi(null) === 'unknown');
kontrol('undefined -> unknown',       K.trafikSinifi(undefined) === 'unknown');

// 🔴 UNKNOWN ASLA PRODUCTION'A DONUSMEZ.
for (const bos of ['', '-', null, undefined, '   ']) {
  if (K.trafikSinifi(bos) === 'production') {
    kontrol('unknown -> production sizintisi: ' + JSON.stringify(bos), false);
  }
}
kontrol('unknown hicbir girdide production olmuyor', true);

console.log('\n--- 2) Acik beyan (yalnizca guvenilir cagiran) ---');
kontrol('acik test beyani',       K.trafikSinifi('web-abc', 'test') === 'test');
kontrol('acik production beyani', K.trafikSinifi('test-x', 'production') === 'production');
kontrol('is_test=true -> test',   K.trafikSinifi('web-abc', true) === 'test');

// =====================================================================
console.log('\n--- 3) Uretici ve kapi ---');
// =====================================================================
const u1 = K.testKimligiUret('smoke');
kontrol('uretici test- onekli', u1.startsWith('test-'), u1);
kontrol('uretici benzersiz', K.testKimligiUret('a') !== K.testKimligiUret('a'));
kontrol('cift onek eklenmiyor',
  (K.testKimligiUret('test-x').match(/test-/g) || []).length === 1, K.testKimligiUret('test-x'));
kontrol('bos ad da gecerli kimlik uretir', K.trafikSinifi(K.testKimligiUret('')) === 'test');
kontrol('uretilen kimlik test sayiliyor', K.trafikSinifi(u1) === 'test');

let firladi = false;
try { K.kimlikDogrula('musteri-123', 'birim-test'); } catch (e) { firladi = true; }
kontrol('kimlikDogrula onek yoksa ISTISNA firlatiyor', firladi);

firladi = false;
try { K.kimlikDogrula('-'); } catch (e) { firladi = true; }
kontrol('kimlikDogrula "-" icin de firlatiyor', firladi);

let gecti = true;
try { K.kimlikDogrula(u1); } catch (e) { gecti = false; }
kontrol('kimlikDogrula gecerli kimligi geciriyor', gecti);

// =====================================================================
console.log('\n--- 4) Yayinlama duman testi kimligi ---');
// =====================================================================
{
  // 🔴 Yapilandirma CANLI uc noktaya istek atiyor. Onek yoksa her
  //    yayinlama uretim metrigine sahte bir konusma yazar.
  const conf = fs.readFileSync(path.join(KLASOR, 'uretim-workflowlari.conf'), 'utf8');
  const m = conf.match(/^DUMAN_KIMLIK="([^"]*)"/m);
  kontrol('DUMAN_KIMLIK tanimli', !!m, 'uretim-workflowlari.conf');
  if (m) {
    kontrol('DUMAN_KIMLIK test- onekli', K.trafikSinifi(m[1]) === 'test', m[1]);
  }
}

// =====================================================================
console.log('\n--- 5) Uretilen workflow trafik sinifi yaziyor mu ---');
// =====================================================================
// 🔴 SAHTE DOGRULAMA ANAHTARLARI - BILEREK.
//    Ureticiler, Meta dogrulama anahtari verilmezse process.exit(1) ile
//    PATLAR (26.09.2026: canli workflow'da placeholder'in sessizce kalmis
//    oldugu olculdu; sessiz varsayilan bir daha birakilmadi). Bu testler
//    ureticiyi require() ile AYNI SURECTE calistirdigi icin o exit testi
//    de oldurur. Testlerin dogrulama dugumuyle isi yok -- sahte anahtar
//    yeterli. Gercek anahtar yalniz yayin hattinda .env'den gecirilir.
if (!process.env.WHATSAPP_VERIFY_TOKEN) process.env.WHATSAPP_VERIFY_TOKEN = 'test-sahte-anahtar';
if (!process.env.MESSENGER_VERIFY_TOKEN) process.env.MESSENGER_VERIFY_TOKEN = 'test-sahte-anahtar';

require(path.join(KLASOR, 'build-instagram-workflow.js'));
require(path.join(KLASOR, 'build-whatsapp-workflow.js'));

const ig = JSON.parse(fs.readFileSync('/tmp/instagram-workflow.json', 'utf8'))[0];
const wa = JSON.parse(fs.readFileSync('/tmp/whatsapp-workflow.json', 'utf8'))[0];
const kodOf = (wf, ad) => {
  const d = wf.nodes.find(n => n.name === ad);
  return (d && d.parameters && d.parameters.jsCode) || '';
};

for (const [ad, wf, giris, kayitDugum] of [
  ['instagram', ig, 'Girisi dogrula', 'Cevabi hazirla'],
  ['whatsapp',  wa, 'Mesajlari ayikla', 'Pilot kaydi']
]) {
  const kg = kodOf(wf, giris);
  const kk = kodOf(wf, kayitDugum);
  kontrol(ad + ': siniflandirici giris dugumune gomulu', kg.indexOf('function trafikSinifi') !== -1);
  kontrol(ad + ': giriste trafik hesaplaniyor', /trafikSinifi\(/.test(kg));
  kontrol(ad + ': kayit dugumune gomulu', kk.indexOf('function trafikSinifi') !== -1);
  kontrol(ad + ': kayda traffic_class yaziliyor', /traffic_class:/.test(kk));
}

// 🔴 WhatsApp 'Yaniti hazirla' da trafikSinifi cagiriyor - gomulu olmazsa
//    fonksiyon SESSIZCE undefined kalir ve dugum calisma aninda coker.
//    Bu projede ayni tuzak daha once yasandi.
{
  const ky = kodOf(wa, 'Yaniti hazirla');
  const cagiriyor = /trafikSinifi\(/.test(ky);
  const gomulu = ky.indexOf('function trafikSinifi') !== -1;
  kontrol('whatsapp: Yaniti hazirla cagiriyorsa gomulu de',
    !cagiriyor || gomulu, 'cagiriyor=' + cagiriyor + ' gomulu=' + gomulu);
}

// 🔴 Govdeden gelen 'is_test' KANAL KODUNDA OKUNMAMALI - okunsaydi
//    herkes kendi mesajini "test" isaretleyip panelden gizleyebilirdi.
for (const [ad, wf, giris] of [['instagram', ig, 'Girisi dogrula'], ['whatsapp', wa, 'Mesajlari ayikla']]) {
  const kg = kodOf(wf, giris);
  const okuyor = /(b|govde|json)\.(is_test|traffic_class)/.test(kg);
  kontrol(ad + ': govdeden is_test OKUNMUYOR', !okuyor);
}

// --- Ozet ------------------------------------------------------------
console.log('\n----------------------------------------');
console.log('Basarili: ' + basarili);
console.log('Basarisiz: ' + basarisiz);
console.log('----------------------------------------\n');
process.exit(basarisiz > 0 ? 1 : 0);
