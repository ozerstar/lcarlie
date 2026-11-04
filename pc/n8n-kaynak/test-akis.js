const { akisMotoru, kararVer, SABLON } = require('/tmp/akis-motoru.js');
const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');

// n8n'deki akisin birebir aynisi
function boruHatti(mesaj) {
  const motor = akisMotoru({ mesaj, musteriId: 'test', kanal: 'test' });
  const gelenFiltre = mevzuatFiltresi(mesaj, { kaynak: 'gelen' });
  const taslakFiltre = motor.taslakCevap
    ? mevzuatFiltresi(motor.taslakCevap, { kaynak: 'taslak' })
    : null;
  return kararVer(motor, gelenFiltre, taslakFiltre);
}

console.log('============================================================');
console.log(' BOLUM 1 - SABLONLARIN KENDISI FILTREDEN GECIYOR MU?');
console.log(' (Kendi urettigimiz cevap mevzuata aykiri olamaz)');
console.log('============================================================');
let sablonHata = 0;
for (const [ad, s] of Object.entries(SABLON)) {
  if (!s.cevap) { console.log('ATLA  ' + ad.padEnd(12) + '(sablon yok, insana gider)'); continue; }
  const r = mevzuatFiltresi(s.cevap);
  const ok = r.sonuc === 'TEMIZ';
  if (!ok) sablonHata++;
  console.log((ok ? 'OK    ' : 'HATA  ') + ad.padEnd(12) + r.sonuc +
    (r.bulgular.length ? '  -> ' + r.bulgular.map(b => b.tur + ':' + b.ifade).join(', ') : ''));
}

console.log('\n============================================================');
console.log(' BOLUM 2 - SENARYOLAR');
console.log('============================================================');

const senaryolar = [
  // [beklenenSinif, beklenenGonder, aciklama, mesaj]
  ['SELAMLAMA',   true,  'Selamlama',              'Merhaba'],
  ['FIYAT',       true,  'Fiyat sorusu',           'Bu krem ne kadar?'],
  ['SIPARIS',     true,  'Siparis',                'Nasil siparis verebilirim'],
  ['ICERIK',      true,  'Icerik sorusu',          'Icindekiler neler, paraben var mi'],
  ['KULLANIM',    true,  'Kullanim sorusu',        'Gunde kac kere surulur'],
  ['KARGO',       false, 'Kargo (insana)',         'Kargo ne zaman gelir'],
  ['IADE',        false, 'Iade (insana)',          'Urunu iade etmek istiyorum'],
  ['SIKAYET',     false, 'Sikayet (insana)',       'Rezalet, kimse cevap vermiyor'],
  ['SAGLIK',      true,  'Saglik - egzama',        'Egzamam var, bu urun iyi gelir mi'],
  ['SAGLIK',      true,  'Saglik - hamile',        'Hamileyim kullanabilir miyim'],
  ['SAGLIK',      true,  'Saglik - akne',          'Akneli cildim var ne onerirsiniz'],
  // GEVSEK DAVRANIS: siniflandiramadigimiz mesaja da yardimci cevap gonderilir
  ['ANLASILMADI', true,  'Anlasilmadi -> genel cevap', 'asdfghjkl qwerty'],
  // Turkce k->g yumusamasi (icerik / icerigi) ve diger cekimler
  ['ICERIK',      true,  'Yumusama: icerigi',      'Hydravie icerigi nedir'],
  ['ICERIK',      true,  'Yumusama: iceriginde',   'Bu kremin iceriginde ne var'],
  ['KULLANIM',    true,  'Cekim: kullanimi',       'Kullanimi nasil'],
  ['FIYAT',       true,  'Cekim: fiyati',          'Hydravie fiyati nedir'],
  // "ne kadar" hem fiyat hem kullanim sorusunda geciyor - dogru ayrilmali
  ['KULLANIM',    true,  'Ayrim: ne kadar SURULUR','Ne kadar surulur'],
  ['FIYAT',       true,  'Ayrim: ne kadar (fiyat)','Bu urun ne kadar'],
  ['DURDURMA',    true,  'Opt-out uzun',           'Artik mesaj istemiyorum'],
  ['DURDURMA',    true,  'Opt-out kisa',           'dur'],
  ['FIYAT',       true,  'KANAL DISI URUN - VIREON (link verilir, anlatilmaz)', 'Vireon kremi ne kadar'],
  ['FIYAT',       true,  'KANAL DISI URUN - Femisia (link verilir, anlatilmaz)','Femisia fiyati nedir'],
];

let ok = 0, hata = 0;
const hatalar = [];

for (const [bekSinif, bekGonder, ad, mesaj] of senaryolar) {
  const r = boruHatti(mesaj);
  const gecti = r.sinif === bekSinif && r.gonder === bekGonder;
  if (gecti) ok++; else { hata++; hatalar.push({ ad, mesaj, bekSinif, bekGonder, geldi: { sinif: r.sinif, gonder: r.gonder }, gerekceler: r.gerekceler }); }
  console.log(
    (gecti ? 'OK   ' : 'HATA ') +
    r.sinif.padEnd(12) +
    'gonder=' + String(r.gonder).padEnd(6) +
    'insan=' + String(r.insanaAktar).padEnd(6) +
    ad
  );
}

console.log('\n============================================================');
console.log(' BOLUM 3 - KRITIK GUVENLIK KONTROLLERI');
console.log('============================================================');

const kritik = [];

// 1. Kanal disi urun adi cevapta ASLA gecmemeli
const v = boruHatti('Vireon kremi ne kadar');
// 🔴 14.09.2026: VIREON sitede SATISTA. Urun hala ANLATILMIYOR ama
// "ekip arkadasimiz donecek" deyip kapatmak yerine sayfa linki veriliyor.
// Musteri urunu tek tikla alabiliyorken sessiz kalmak satis kaybiydi.
kritik.push(['Kanal disi (satista) urunde sayfa linki veriliyor',
  v.gonder === true && /lcarlie\.shop\/vireon/.test(v.cevap || '')]);
kritik.push(['Kanal disi urunde insana aktariliyor', v.insanaAktar === true]);
kritik.push(['🔴 Kanal disi urun ANLATILMIYOR (iddia/aciklama yok)',
  !/(cilt|nem|formul|icerik|yardimci olur|destekler|canlilik)/i.test(v.cevap || '')]);

// 2. Saglik sorusunda urun onerilmiyor
const s = boruHatti('Egzamam var iyi gelir mi');
kritik.push(['Saglik sorusunda insan bilgilendiriliyor', s.insanaAktar === true]);
kritik.push(['Saglik cevabinda "iyi gelir" yok', !/iyi gelir/i.test(s.cevap || '')]);
kritik.push(['Saglik cevabinda "oneririm" (urun) yok', !/urunu oneririm|denemenizi/i.test(s.cevap || '')]);

// 3. Opt-out
const o = boruHatti('mesaj istemiyorum');
kritik.push(['Opt-out kaydi aciliyor', o.optOutKaydi === true]);
kritik.push(['Opt-out cevabinda CTA/link YOK', !/lcarlie\.shop/.test(o.cevap || '')]);

// 4. Hicbir otomatik cevap soru ile bitmiyor
for (const [ad, sb] of Object.entries(SABLON)) {
  if (!sb.cevap) continue;
  kritik.push([ad + ' soru ile bitmiyor', !/\?\s*$/.test(sb.cevap)]);
}

// 5. Gonderilen her cevap site linki ile bitiyor (opt-out haric)
for (const [ad, sb] of Object.entries(SABLON)) {
  if (!sb.cevap || ad === 'DURDURMA') continue;
  kritik.push([ad + ' CTA link ile bitiyor', /lcarlie\.shop\s*$/.test(sb.cevap)]);
}

// ---- URUN BILGI TABANI ----
const hyd  = boruHatti('Hydravie ne kadar');
const hydI = boruHatti('Hydravie icerigi nedir');
// 🔴 ICERIK CEVABI ARTIK IKI KIPLI (27.09.2026).
//    Genel soru -> one cikanlar + sayfaya yonlendirme (kisa, okunur).
//    Alerjen sorusu -> TAM INCI. Sebep: eksik liste hassasiyeti olan
//    musteri icin risk; o musteri listeyi KANALDA gormeli.
//    Asagidaki iki fixture bu ayrimi kilitler.
const hydAlerjen = boruHatti('Hydravie paraben iceriyor mu');
// 🔴 'alerjim var' KULLANILMAZ: o bir SAGLIK beyanidir, ajan urun
//    cevabi vermez ve insana aktarir -- dogru davranis. Burada sinanan
//    sey ALERJEN ICERIK sorusu; o yuzden duz 'koku var mi'.
const calAlerjen = boruHatti('Calmaros koku var mi');
const sun  = boruHatti('Sunacnea ne kadar');
const sunK = boruHatti('Gunes koruyucu nasil kullanilir');

kritik.push(['HYDRAVIE fiyat cevabi gonderiliyor', hyd.gonder === true]);
kritik.push(['HYDRAVIE cevabinda fiyat var', /1\.200 TL/.test(hyd.cevap || '')]);
kritik.push(['HYDRAVIE cevabinda hacim var', /50 ml/.test(hyd.cevap || '')]);
// Resmi kutu icerik metni "El & Yuz Nemlendirici Krem" diyor - ajan onu kullanir
kritik.push(['HYDRAVIE adi kutu metniyle ayni', /El & Yüz Nemlendirici Krem/.test(hyd.cevap || '')]);
// 🔴 Kutu "tum cilt tipleri", sise "kuru ve hassas" diyor - celiski cozulene
// kadar ajan CILT TIPI iddiasinda bulunmamali
kritik.push(['🔴 HYDRAVIE cevabinda cilt TIPI iddiasi yok',
  !/kuru ve hassas|tüm cilt tipleri/i.test(hydI.cevap || '')]);
kritik.push(['SUNACNEA cevabinda hacim var (etiketten)', /50 ml/.test(sun.cevap || '')]);
kritik.push(['🔴 HYDRAVIE cevabinda SERAMID YOK', !/seramid|ceramide/i.test(hyd.cevap || '')]);
kritik.push(['🔴 GENEL icerik cevabinda tam INCI YOK (duvar gonderilmez)',
             !/Aqua, Aloe/.test(hydI.cevap || '')]);
kritik.push(['GENEL icerik cevabinda one cikanlar var',
             /öne çıkan içerikleri/.test(hydI.cevap || '')]);
kritik.push(['GENEL icerik cevabi tam listeye YONLENDIRIYOR',
             /Tam içerik listesini \(INCI\) ürün sayfasında/.test(hydI.cevap || '')]);
kritik.push(['🔴 ALERJEN sorusunda TAM INCI veriliyor',
             /Aqua, Aloe/.test(hydAlerjen.cevap || '')]);
kritik.push(['🔴 HYDRAVIE INCI cevabinda seramid YOK', !/ceramide/i.test(hydI.cevap || '')]);

kritik.push(['SUNACNEA fiyat cevabi gonderiliyor', sun.gonder === true]);
kritik.push(['🔴 SUNACNEA cevabinda tam lockup var', /SUNACNEA · SPF 30 Günlük Güneş Koruyucu/.test(sun.cevap || '')]);
kritik.push(['🔴 SUNACNEA cevabinda "akne" YOK', !/akne/i.test(sun.cevap || '')]);
kritik.push(['🔴 SUNACNEA zorunlu ibare 1', /Yeterli miktarda uygulanmaması/.test(sun.cevap || '')]);
kritik.push(['🔴 SUNACNEA zorunlu ibare 2', /Aşırı güneş maruziyeti/.test(sun.cevap || '')]);
kritik.push(['🔴 SUNACNEA zorunlu ibare 3', /Bebek ve küçük çocuklar/.test(sun.cevap || '')]);
kritik.push(['🔴 SUNACNEA zorunlu ibare 4', /Hiçbir ürün %100 koruma sağlamaz/.test(sun.cevap || '')]);
kritik.push(['SUNACNEA kullanim cevabi da zorunlu ibare iceriyor', /Hiçbir ürün %100 koruma/.test(sunK.cevap || '')]);

// Urun cevaplarinin KENDISI mevzuat filtresinden gecmeli
for (const [ad, r] of [['HYDRAVIE fiyat', hyd], ['HYDRAVIE icerik', hydI], ['SUNACNEA fiyat', sun], ['SUNACNEA kullanim', sunK]]) {
  if (!r.cevap) { kritik.push([ad + ' cevabi uretildi', false]); continue; }
  const f = mevzuatFiltresi(r.cevap);
  kritik.push([ad + ' cevabi FILTREDEN TEMIZ geciyor', f.sonuc === 'TEMIZ']);
  if (f.sonuc !== 'TEMIZ') console.log('    !! ' + ad + ' -> ' + f.bulgular.map(b => b.tur + ':' + b.ifade).join(', '));
}

// Urun cevaplari dogrudan URUN SAYFASINA yonlendirmeli (ana sayfaya degil)
kritik.push(['HYDRAVIE CTA urun sayfasina gidiyor', /product-page\/hydravie/.test(hyd.cevap || '')]);
kritik.push(['SUNACNEA CTA urun sayfasina gidiyor', /product-page\/sunacnea-30-spf/.test(sun.cevap || '')]);

// --- MASTER MATRIX KAPILARI (v12.1.1) ---
//
// 🔴 14.09.2026 DAVRANIS DEGISIKLIGI:
// Bu urunlerin ANLATILMAMA karari duruyor, ama bir kismi SITEDE SATISTA.
// Satista olan urunde "ekip arkadasimiz donecek" demek musteri gozunde
// sacma - urun zaten tek tikla alinabiliyor. Artik:
//   · SATISTA olanlar  -> urun ANLATILMADAN sayfa linki verilir + insana aktarilir
//   · SATISTA OLMAYAN  -> cevap gonderilmez + insana aktarilir (eskisi gibi)
// Her iki halde de urun ANLATILMAZ: aciklama, icerik, iddia YOK.

// Satista olanlar: link verilir ama ANLATILMAZ
for (const [ad, mesaj, slug] of [
  ['BUGUARD (satista)',    'Buguard spreyi ne kadar', 'buguard'],
  ['SOFTGUARD (satista)',  'Softguard var mi',        'softguard'],
  ['VIREON (satista)',     'Vireon fiyati nedir',     'lcarlie.shop/vireon'],
  ['FEMISIA (satista)',    'Femisia kac para',        'femisia-for-women'],
  ['INTIMBLANC (satista)', 'Intimblanc nedir',        'intimblanc'],
  ['LIFTELLE (satista)',   'Liftelle hakkinda bilgi', 'liftelle'],
]) {
  const r = boruHatti(mesaj);
  const c = r.cevap || '';
  kritik.push([ad + ' -> sayfa linki veriliyor', r.gonder === true && c.includes(slug)]);
  kritik.push([ad + ' -> insana da aktariliyor', r.insanaAktar === true]);
  // 🔴 EN ONEMLISI: urun ANLATILMIYOR. Cevapta iddia/aciklama olmamali.
  kritik.push([ad + ' -> urun ANLATILMIYOR',
    !/(cilt|nem|bakim hissi|formul|icerik|yardimci olur|destekler)/i.test(c)]);
}

// Satista OLMAYANLAR: cevap gonderilmez (eskisi gibi)
for (const [ad, mesaj] of [
  ['BEBEPUR (EXCLUDED)',   'Bebepur sampuan fiyati'],
  ['EARCLIA (onay bekler)','Earclia roll on ne kadar'],
  ['NOMORE (onay bekler)', 'Nomore roll on fiyati'],
  ['AUROLIS (onay bekler)','Aurolis fiyati'],
]) {
  const r = boruHatti(mesaj);
  kritik.push([ad + ' -> cevap gonderilmiyor', r.gonder === false]);
  kritik.push([ad + ' -> insana aktariliyor', r.insanaAktar === true]);
}

// --- UCLU RITUEL CAPRAZ SATIS ---
const luc = boruHatti('Luciderm ne kadar');
kritik.push(['LUCIDERM taniniyor ve cevap gonderiliyor', luc.gonder === true && luc.urun === 'LUCIDERM']);
kritik.push(['LUCIDERM fiyati dogru', /1\.200 TL/.test(luc.cevap || '')]);
kritik.push(['Fiyat sorusunda uclu rituel teklif ediliyor', /checkout-templates/.test(hyd.cevap || '')]);
kritik.push(['LUCIDERM cevabinda da rituel var', /checkout-templates/.test(luc.cevap || '')]);
// 🔴 Rituel cumlesi gunes urunu ADINI anmamali (yoksa zorunlu ibare seti gerekir)
kritik.push(['🔴 Rituel cumlesinde SUNACNEA/SPF adi gecmiyor',
  !/SUNACNEA|SPF/.test((luc.cevap || '').split('Üç adımlı')[1] || '')]);
// Icerik/kullanim sorusunda rituel teklif EDILMEZ (satin alma niyeti yok)
kritik.push(['Icerik sorusunda rituel teklifi yok', !/checkout-templates/.test(hydI.cevap || '')]);
// Rituel eklenmis cevaplar da filtreden temiz gecmeli
for (const [ad, r] of [['LUCIDERM fiyat', luc], ['HYDRAVIE fiyat+rituel', hyd]]) {
  const f = mevzuatFiltresi(r.cevap || '');
  kritik.push([ad + ' cevabi FILTREDEN TEMIZ', f.sonuc === 'TEMIZ']);
  if (f.sonuc !== 'TEMIZ') console.log('    !! ' + ad + ' -> ' + f.bulgular.map(b => b.tur + ':' + b.ifade).join(', '));
}
// INCI eksiksiz olmali (hassasiyeti olan musteri icin kritik)
kritik.push(['🔴 ALERJEN: HYDRAVIE INCI tam (Potassium Sorbate dahil)',
             /Potassium Sorbate/.test(hydAlerjen.cevap || '')]);
kritik.push(['🔴 ALERJEN: HYDRAVIE INCI tam (Decyl Glucoside dahil)',
             /Decyl Glucoside/.test(hydAlerjen.cevap || '')]);

// --- CALMAROS ---
const cal = boruHatti('Calmaros ne kadar');
const calI = boruHatti('Calmaros icerigi nedir');
kritik.push(['CALMAROS taniniyor', cal.urun === 'CALMAROS' && cal.gonder === true]);
kritik.push(['CALMAROS fiyati dogru (1.850)', /1\.850 TL/.test(cal.cevap || '')]);
kritik.push(['CALMAROS CTA urun sayfasina gidiyor', /product-page\/calmaros/.test(cal.cevap || '')]);
kritik.push(['CALMAROS cevabinda rituel teklifi var', /checkout-templates/.test(cal.cevap || '')]);
// 🔴 Kutu ile site cilt tipinde ayrisiyor - ajan iddia etmemeli
kritik.push(['🔴 CALMAROS cevabinda cilt TIPI iddiasi yok',
  !/hassas|kızarıklığa|kizarikliga/i.test((cal.cevap || '') + (calI.cevap || ''))]);
kritik.push(['🔴 ALERJEN: CALMAROS INCI tam',
             /Cinnamomum Zeylanicum Bark Oil/.test(calAlerjen.cevap || '')]);
kritik.push(['GENEL: CALMAROS cevabinda tam INCI YOK',
             !/Cinnamomum Zeylanicum Bark Oil/.test(calI.cevap || '')]);
for (const [ad, r] of [['CALMAROS fiyat', cal], ['CALMAROS icerik', calI]]) {
  const f = mevzuatFiltresi(r.cevap || '');
  kritik.push([ad + ' cevabi FILTREDEN TEMIZ', f.sonuc === 'TEMIZ']);
  if (f.sonuc !== 'TEMIZ') console.log('    !! ' + ad + ' -> ' + f.bulgular.map(b => b.tur + ':' + b.ifade).join(', '));
}

// 🔴 Musteri gunes urunu sordugunda GEREKSIZ yere insana aktarilmamali.
// (Zorunlu ibare yukumlulugu bizim metnimize ait, musterinin mesajina degil)
kritik.push(['SUNACNEA fiyat sorusunda GEREKSIZ insan aktarimi yok', sun.insanaAktar === false]);
kritik.push(['SUNACNEA kullanim sorusunda gereksiz insan aktarimi yok', sunK.insanaAktar === false]);
kritik.push(['HYDRAVIE fiyat sorusunda gereksiz insan aktarimi yok', hyd.insanaAktar === false]);
// Ama BIZIM metnimizde ibare eksikse hala yakalanmali
const eksikIbare = mevzuatFiltresi('SUNACNEA SPF 30 gunes koruyucu fiyati 990 TL.', { kaynak: 'taslak' });
kritik.push(['🔴 Giden metinde eksik zorunlu ibare hala yakalaniyor', eksikIbare.sonuc !== 'TEMIZ']);

// Saglik sorusunda urun anlatilmamali
const sagUrun = boruHatti('Hydravie egzamaya iyi gelir mi');
kritik.push(['🔴 Saglik sorusunda urun cevabi verilmiyor', !/1\.200 TL|INCI/.test(sagUrun.cevap || '')]);
kritik.push(['Saglik sorusunda insana aktariliyor', sagUrun.insanaAktar === true]);

let kOk = 0;
for (const [ad, sonuc] of kritik) {
  console.log((sonuc ? 'OK   ' : 'HATA ') + ad);
  if (sonuc) kOk++;
}

console.log('\n============================================================');
console.log(' Sablon filtresi : ' + (sablonHata === 0 ? 'HEPSI TEMIZ' : sablonHata + ' SABLON KIRLI'));
console.log(' Senaryolar      : ' + ok + '/' + senaryolar.length);
console.log(' Kritik kontrol  : ' + kOk + '/' + kritik.length);
console.log('============================================================');
if (hatalar.length) {
  console.log('\n--- SENARYO HATALARI ---');
  console.log(JSON.stringify(hatalar, null, 2));
}
