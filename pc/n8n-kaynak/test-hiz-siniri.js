// =====================================================================
// L'CARLIE - HIZ SINIRI TESTI
//
// Neden ayri bir test?
//   Hiz siniri kodu bir n8n Code dugumunun icinde metin olarak duruyor;
//   hicbir test onu calistirmiyordu. Yani sinir tamamen bozulsa bile
//   6 testin 6'si yesil yanip yayina cikiyordu.
//
// 🔴 Bu test URETILEN workflow JSON'undan kodu cikarip GERCEKTEN calistirir.
//    Kaynakta degil, YAYINLANACAK dosyada ne varsa onu olcer.
//
// Olculen davranis:
//   1. Normal musteri 10 dakikada 20 mesaj gonderebilir, 21. reddedilir
//   2. 🔴 Rastgele musteriId uretmek siniri ASMAZ (IP siniri devreye girer)
//   3. Farkli IP'ler birbirini etkilemez (bir saldirgan digerlerini kapatamaz)
//   4. X-Forwarded-For yoksa cokmez
//   5. Tek bir IP, global sinirin tamamini tek basina tuketemez
// =====================================================================
const fs = require('fs');
const path = require('path');

const KLASOR = __dirname;
const URETILEN = '/tmp/sohbet-workflow.json';

// Workflow'u uret (build betigi JSON'u diske yazar)
require(path.join(KLASOR, 'build-sohbet-workflow.js'));

const wf = JSON.parse(fs.readFileSync(URETILEN, 'utf8'));
const dugum = wf[0].nodes.find(n => n.name === 'Girisi dogrula');
if (!dugum || !dugum.parameters || !dugum.parameters.jsCode) {
  console.error('HATA: "Girisi dogrula" dugumu veya kodu bulunamadi.');
  process.exit(1);
}
const kod = dugum.parameters.jsCode;

// Sinir degerlerini kodun KENDISINDEN oku - test ile kod ayrismasin
const sayi = (ad) => {
  const m = kod.match(new RegExp(ad + '\\s*=\\s*(\\d+)'));
  if (!m) { console.error('HATA: ' + ad + ' kodda bulunamadi.'); process.exit(1); }
  return parseInt(m[1], 10);
};
const KISI_LIMIT = sayi('KISI_LIMIT');
const IP_LIMIT = sayi('IP_LIMIT');
const TOPLAM_LIMIT = sayi('TOPLAM_LIMIT');

// --- n8n ortamini taklit et -----------------------------------------
let statik = {};
const calistir = (istekler) => {
  const $getWorkflowStaticData = () => statik;
  const $input = { all: () => istekler };
  const fn = new Function('$getWorkflowStaticData', '$input', kod);
  return fn($getWorkflowStaticData, $input);
};

// Tek bir sohbet istegi uret.
// gercekIp : Caddy'nin yazdigi X-Gercek-IP (taklit edilemez)
// sahteXff : musterinin kendi eklemeye calistigi X-Forwarded-For degeri
const istek = (mesaj, musteriId, gercekIp, sahteXff) => {
  const headers = {};
  if (gercekIp !== null) headers['x-gercek-ip'] = gercekIp;
  if (sahteXff) {
    // Caddy gelen basliga EKLEME yapar: once musterinin yazdigi,
    // sonra Caddy'nin gordugu gercek adres gelir.
    headers['x-forwarded-for'] = sahteXff + ', ' + (gercekIp || '10.0.0.1');
  }
  return { json: { body: { mesaj, musteriId }, headers } };
};

// Bir mesaj gonder, gecti mi dondur
const gonder = (musteriId, gercekIp, sahteXff) => {
  const s = calistir([istek('merhaba fiyat nedir', musteriId, gercekIp, sahteXff)])[0];
  return { gecti: s.json.gecerli === true, hata: s.json.hata || null };
};

// --- Test cercevesi --------------------------------------------------
let basarili = 0, basarisiz = 0;
const kontrol = (ad, kosul, ayrinti) => {
  if (kosul) { basarili++; console.log('  GECTI      ' + ad); }
  else { basarisiz++; console.log('  BASARISIZ  ' + ad + (ayrinti ? '  -> ' + ayrinti : '')); }
};

console.log('\n=== HIZ SINIRI TESTI ===');
console.log('Kodda okunan sinirlar: kisi=' + KISI_LIMIT +
            '  ip=' + IP_LIMIT + '  toplam=' + TOPLAM_LIMIT + '\n');

// --- 1) Normal musteri ----------------------------------------------
statik = {};
let gecen = 0;
for (let i = 0; i < KISI_LIMIT; i++) {
  if (gonder('musteri-A', '85.100.1.1').gecti) gecen++;
}
const asim = gonder('musteri-A', '85.100.1.1');
kontrol('Normal musteri ' + KISI_LIMIT + ' mesaj gonderebiliyor',
        gecen === KISI_LIMIT, gecen + ' gecti');
kontrol('Sinir asilinca reddediliyor',
        !asim.gecti && asim.hata === 'kisi hiz siniri', asim.hata);

// --- 2) 🔴 ASIL SORU: rastgele musteriId ile sinir asilabiliyor mu? --
statik = {};
let sahteGecen = 0;
const DENEME = IP_LIMIT * 5;   // saldirgan cok fazla deniyor
for (let i = 0; i < DENEME; i++) {
  // Her istekte YENI bir kimlik - eski kod bunu sinirsiz kabul ediyordu
  const sahte = 'web-' + Math.random().toString(36).slice(2);
  if (gonder(sahte, '203.0.113.99').gecti) sahteGecen++;
}
kontrol('Rastgele musteriId ile sinir ASILAMIYOR',
        sahteGecen === IP_LIMIT,
        DENEME + ' denemeden ' + sahteGecen + ' gecti (beklenen ' + IP_LIMIT + ')');

const sahteHata = gonder('web-' + Math.random(), '203.0.113.99');
kontrol('Reddin sebebi IP siniri olarak kaydediliyor',
        sahteHata.hata === 'ip hiz siniri', sahteHata.hata);

// --- 3) Saldirgan gercek musterileri kapatamiyor ---------------------
// (2. adimdan gelen statik veri duruyor: 203.0.113.99 kapali)
const temizMusteri = gonder('musteri-B', '78.180.5.5');
kontrol('Baska IP\'deki gercek musteri etkilenmiyor',
        temizMusteri.gecti, temizMusteri.hata);

// --- 3b) 🔴 BASLIK SAHTECILIGI ---------------------------------------
// Saldirgan her istekte hem yeni bir musteriId hem de yeni bir sahte
// X-Forwarded-For yaziyor. Kod XFF'in BASINI okusaydi her istek yeni bir
// "IP" sayilir ve sinir tamamen etkisiz kalirdi.
statik = {};
let sahteIpGecen = 0;
for (let i = 0; i < IP_LIMIT * 3; i++) {
  const kimlik = 'web-' + Math.random().toString(36).slice(2);
  const uydurma = '10.' + (i % 250) + '.' + (i % 99) + '.' + (i % 77);
  if (gonder(kimlik, '198.51.100.7', uydurma).gecti) sahteIpGecen++;
}
kontrol('Sahte X-Forwarded-For ile sinir ASILAMIYOR',
        sahteIpGecen === IP_LIMIT,
        (IP_LIMIT * 3) + ' denemeden ' + sahteIpGecen + ' gecti (beklenen ' + IP_LIMIT + ')');

// X-Gercek-IP yoksa bile XFF'in SON degeri (Caddy'nin ekledigi) kullanilmali
statik = {};
let xffSonGecen = 0;
for (let i = 0; i < IP_LIMIT * 3; i++) {
  const kimlik = 'web-' + Math.random().toString(36).slice(2);
  const uydurma = '10.' + (i % 250) + '.' + (i % 99) + '.' + (i % 77);
  const s = calistir([{
    json: {
      body: { mesaj: 'fiyat', musteriId: kimlik },
      headers: { 'x-forwarded-for': uydurma + ', 198.51.100.8' }
    }
  }])[0];
  if (s.json.gecerli === true) xffSonGecen++;
}
kontrol('X-Gercek-IP yoksa XFF\'in SON degeri esas aliniyor',
        xffSonGecen === IP_LIMIT,
        (IP_LIMIT * 3) + ' denemeden ' + xffSonGecen + ' gecti (beklenen ' + IP_LIMIT + ')');

// --- 4) Basliksiz istek cokmuyor -------------------------------------
statik = {};
let hataMesaji = null;
let basliksiz = null;
try { basliksiz = gonder('musteri-C', null); }
catch (e) { hataMesaji = e.message; }
kontrol('Hicbir IP basligi yokken cokmuyor', hataMesaji === null, hataMesaji);
kontrol('Basliksiz istek yine de islenebiliyor',
        basliksiz && basliksiz.gecti, basliksiz && basliksiz.hata);

// --- 5) Global sinir silaha donusemiyor ------------------------------
// Tek IP 10 dakikada en fazla IP_LIMIT gonderebilir -> saatte 6 pencere.
const tekIpSaatlik = IP_LIMIT * 6;
kontrol('Tek IP global siniri tek basina tuketemiyor',
        tekIpSaatlik < TOPLAM_LIMIT,
        'tek IP saatte en fazla ' + tekIpSaatlik + ', global sinir ' + TOPLAM_LIMIT);

// --- 6) Sayaclar sinirsiz buyumuyor ----------------------------------
statik = {};
for (let i = 0; i < 50; i++) gonder('kisi-' + i, '9.9.9.' + i);
const ipAnahtar = Object.keys(statik.ipHiz || {}).length;
kontrol('IP sayaci tutuluyor', ipAnahtar === 50, ipAnahtar + ' IP kaydi');

// Pencere disi kayitlar temizleniyor mu?
const eski = Date.now() - (60 * 60 * 1000);
statik.ipHiz['bayat.ip'] = [eski, eski];
statik.hiz['bayat-kisi'] = [eski, eski];
gonder('musteri-D', '1.2.3.4');
kontrol('Bayat IP kayitlari temizleniyor', !statik.ipHiz['bayat.ip']);
kontrol('Bayat kisi kayitlari temizleniyor', !statik.hiz['bayat-kisi']);

// --- Ozet ------------------------------------------------------------
console.log('\n----------------------------------------');
console.log('Basarili: ' + basarili);
console.log('Basarisiz: ' + basarisiz);
console.log('----------------------------------------\n');
process.exit(basarisiz > 0 ? 1 : 0);
