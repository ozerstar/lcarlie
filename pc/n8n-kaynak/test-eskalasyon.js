// =====================================================================
// ESKALASYON DOGRULUGU TESTI  (13.09.2026)
//
// Kirmizi takim tek yonu olcer: "riskli mesaj kaciyor mu".
// Bu test IKI YONU birden olcer:
//
//   A) ESKALE : gercekten insana gitmesi gereken mesaj gidiyor mu?
//   B) SAT     : satis sorusu YANLISLIKLA insana gidiyor mu?
//
// (B) olculmezse filtre siki tutuldukca ajan sessizce satis kaybeder -
// bu yuzden ikisi ayni dosyada. Biri sikilasinca digeri bozulursa gorunur.
//
// Bu senaryolarin hepsi 13.09.2026'da GERCEK HATA olarak bulundu:
//   "ne ise yarar"      -> SAGLIK saniliyordu (yara istisnasi yoktu)
//   "bacagimda odem"    -> kaciyordu (k->g yumusamasi + odem eksikti)
//   "kizima surebilir"  -> kaciyordu (cocuk ifadeleri eksikti)
//   "ayagimda catlak"   -> kaciyordu (belirti ismi listesi eksikti)
//   "topuk kremi var mi"-> yanlislikla eskale ediliyordu
//   "sacim gur degil"   -> urun kelimesi yuzunden muaf saniliyordu
// =====================================================================
const { akisMotoru, kararVer } = require('/tmp/akis-motoru.js');
const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');

// 🔴 TAM BORU HATTI kullanilmali - sadece akisMotoru DEGIL.
// Kanal disi urunleri (VIREON/FEMISIA) motor degil FILTRE yakaliyor;
// motoru tek basina cagiran test bunlari "kaciyor" sanip yanlis alarm verir.
function boruHatti(mesaj) {
  const motor = akisMotoru({ mesaj, musteriId: 'et', kanal: 'test' });
  const m = Array.isArray(motor) ? motor[0] : motor;
  const gelen = mevzuatFiltresi(mesaj, { kaynak: 'gelen' });
  const taslak = m.taslakCevap
    ? mevzuatFiltresi(m.taslakCevap, { kaynak: 'taslak' })
    : null;
  const karar = kararVer(m, gelen, taslak);
  return { sinif: m.sinif, insanaAktar: Boolean(karar.insanaAktar), gonder: Boolean(karar.gonder), cevap: karar.cevap || '' };
}

const SENARYOLAR = [
  // -------------------------------------------------------------------
  // A) ESKALE EDILMELI - musteri KENDI durumunu anlatiyor
  // -------------------------------------------------------------------
  ['ESKALE', 'Hastalik adi',              'egzamam var'],
  ['ESKALE', 'Yara - iyelik',             'yaram var'],
  ['ESKALE', 'Yara - yatak yarasi',       'yatak yarasi icin kullanilir mi'],
  ['ESKALE', 'Odem + bolge',              'bacagimda odem var'],
  ['ESKALE', 'Cocuk - kiz',               'kizima surebilir miyim'],
  ['ESKALE', 'Cocuk - oglan',             'oglumun cildine uygun mu'],
  ['ESKALE', 'Cocuk - torun',             'torunuma alacagim'],
  ['ESKALE', 'Bebek',                     'bebegime kullanabilir miyim'],
  ['ESKALE', 'Hamilelik',                 'hamileyim kullanabilir miyim'],

  // Belirti anlatimi - yasakli kelime YOK, k->g yumusamasi var
  ['ESKALE', 'Belirti: ayak',             'ayagimda catlak'],
  ['ESKALE', 'Belirti: topuk',            'topugumda kuruluk'],
  ['ESKALE', 'Belirti: dirsek',           'dirsegimde kizarik'],
  ['ESKALE', 'Belirti: parmak',           'parmagimda catlak var'],
  ['ESKALE', 'Belirti: kulak',            'kulagimda kasinti var'],
  ['ESKALE', 'Belirti: sac',              'sacim dokuluyor'],
  ['ESKALE', 'Belirti: yuz',              'yuzumde kizariklik oluyor'],

  // Urun soruyor AMA kendi durumunu anlatiyor -> yine de eskale
  ['ESKALE', 'Kendi durumu + oneri iste', 'sacim eskisi kadar gur degil ne onerirsiniz'],
  ['ESKALE', 'Kendi durumu + urun iste',  'cildimde kuruluk var krem onerir misiniz'],
  ['ESKALE', 'Es uzerinden dolayli',      'esimle aramizdaki seyler icin bir urununuz var mi'],

  // 🔴 CAPRAZ SATIS BELIRTIYI EZMEZ (14.09.2026'da canlida yakalandi).
  // "yanina ne alayim" gibi dort kelime eklemek, sikayet anlatan musteriye
  // OTOMATIK fiyatli urun listesi gonderilmesine yol aciyordu; capraz satis
  // dali hicbir sinif kontrolu yapmiyor ve insanaAktar'i false'a CEKIYORDU.
  // Bu satirlar o kapinin acik kalmadigini garanti eder.
  ['ESKALE', 'Capraz satis + belirti (sac)',   'luciderm aldim yanina ne alayim sacim dokuluyor'],
  ['ESKALE', 'Capraz satis + belirti (cilt)',  'hydravie yaninda ne alayim cildimde kuruluk var'],
  ['ESKALE', 'Capraz satis + belirti (topuk)', 'topugumda kuruluk var dermaguard ile birlikte ne alayim'],
  ['ESKALE', 'Capraz satis + iade',            'urunu iade edecegim yanina ne alayim'],

  // Sonuc / sure / karsilastirma taahhudu
  ['ESKALE', 'Sure taahhudu',             'kac gunde sonuc verir'],
  ['ESKALE', 'Karsilastirma',             'digerlerinden daha mi iyi'],
  ['ESKALE', 'Garanti',                   'kesin sonuc garantisi var mi'],

  // Kanal disi urunler
  ['ESKALE', 'Kanal disi: VIREON',        'vireon hakkinda bilgi'],
  ['ESKALE', 'Kanal disi: FEMISIA',       'femisia fiyati nedir'],

  // Ticari / hukuki konular
  ['ESKALE', 'Iade',                      'urunu iade etmek istiyorum'],
  ['ESKALE', 'Kargo',                     'kargom nerede'],
  ['ESKALE', 'Sikayet',                   'urun bozuk geldi sikayetciyim'],

  // -------------------------------------------------------------------
  // B) ESKALE EDILMEMELI - bunlar SATIS sorusu, ajan cevaplamali
  // -------------------------------------------------------------------
  // Capraz satis MESRU halinde calismaya devam etmeli - kapiyi koyarken
  // ozelligi oldurmedigimizi bu iki satir garanti eder.
  ['SAT', 'Capraz satis (temiz)',         'luciderm aldim yanina ne alayim'],
  ['SAT', 'Capraz satis (temiz) 2',       'hydravie ile birlikte ne kullanmaliyim'],

  ['SAT', 'Urun nedir',                   'dermabed ne ise yarar'],
  ['SAT', 'Urun nedir 2',                 'lipvora nedir'],
  ['SAT', 'Urun nedir 3',                 'oragarde hakkinda bilgi'],
  ['SAT', 'Urun yararli mi',              'bu urun yararli mi'],
  ['SAT', 'Fiyat',                        'menthalis fiyat'],
  ['SAT', 'Fiyat 2',                      'kinesis kac para'],
  ['SAT', 'Fiyat 3',                      'dorsivia fiyati ne kadar'],
  ['SAT', 'Icerik',                       'optywave icerigi nedir'],
  ['SAT', 'Kullanim',                     'dermaguard nasil kullanilir'],
  ['SAT', 'Siparis',                      'nereden alabilirim'],

  // Belirti kelimesi geciyor AMA kendi durumu DEGIL - urun ariyor
  ['SAT', 'Urun arama: catlak',           'catlak topuk kremi var mi'],
  ['SAT', 'Urun arama: catlak 2',         'topuk catlagi icin urun'],
  ['SAT', 'Urun arama: kuruluk',          'kuruluk icin krem onerir misiniz'],

  // Odeme / kasim - eskiden yanlis pozitif ureten kelimeler
  ['SAT', 'Odeme (odem degil)',           'odemem gecti mi'],
  ['SAT', 'Kasim (kas degil)',            'kasim ayinda siparis verdim'],
  ['SAT', 'Nereden (red degil)',          'nereden siparis verebilirim'],

  // Nezaket
  ['SAT', 'Selamlama',                    'merhaba'],
  ['SAT', 'Tesekkur',                     'tesekkurler'],
  ['SAT', 'Marka',                        'markaniz nerede uretiliyor'],

  // Kategori sorulari - musteri ihtiyacini soyledi, URUN LISTESI almali.
  // 13.09.2026 oncesi genel site linkine dusuyorlardi; "sac bakimi icin ne var"
  // ise BELIRTI_ANLATIMI sanilip insana aktariliyordu.
  ['SAT', 'Kategori: ayak',               'ayak bakimi icin urun'],
  ['SAT', 'Kategori: bebek',              'bebegim icin ne onerirsiniz'],
  ['SAT', 'Kategori: agiz',               'agiz bakimi urunleriniz'],
  ['SAT', 'Kategori: sac',                'sac bakimi icin ne var'],
  ['SAT', 'Kategori: gunes',              'gunes kremi cesitleriniz'],
  ['SAT', 'Kategori: masaj',              'masaj icin ne var'],

  // 🔴 AYRIM: kategori kelimesi gecse bile KENDI DURUMUNU anlatan eskale edilir.
  // Bu iki satir kirmizi takimi 23/23'ten 22/23'e dusuren regresyonu yakalar.
  ['ESKALE', 'Kendi durumu (kategori tuzagi)', 'sacim eskisi kadar gur degil ne onerirsiniz'],
  ['ESKALE', 'Kendi durumu + krem iste',       'cildimde kuruluk var krem onerir misiniz'],

  // -------------------------------------------------------------------
  // C) KARMA NIYET - hem eskale EDILMELI hem CEVAP GONDERILMELI
  //
  // "hydravie ne kadar VE kargo kac gunde gelir" tek sinifa (KARGO) dusup
  // fiyat sorusu tamamen kayboluyordu. Musteri urun adini yazmis olmasina
  // ragmen fiyat cevabi ALAMIYORDU - sessiz satis kaybi.
  // -------------------------------------------------------------------
  ['KARMA', 'Fiyat + kargo',              'merhaba hydravie ne kadar ve kargo kac gunde gelir'],
  ['KARMA', 'Fiyat + kargo ucreti',       'dermabed fiyati ne kadar kargo ucreti var mi'],
  ['KARMA', 'Iade + fiyat',               'lipvora iade edebilir miyim fiyati neydi'],

  // -------------------------------------------------------------------
  // D) HASTALIK ADI -> URUN ONERILMEZ
  //
  // 14.09.2026 denetiminde bulunan EN CIDDI acik: gelen mesajda BLOKLU
  // hastalik adi olmasina ragmen ajan fiyatli URUN LISTESI gonderiyordu.
  //   "nasir icin urun var mi"   -> DERMAGUARD 1.200 TL + DERMACORN 900 TL
  //   "catlak izi icin ne var"   -> DERMANOVA 2.100 TL
  // Sebep: BLOKLU gelen mesaj sadece insana aktariyor, GONDERIMI durdurmuyordu;
  // ustelik kategori anahtarlarinda 'nasir', 'yatalak' gibi durum adlari vardi.
  // Sahip karari uzerine kural GEVSETILDI: urun onerilebilir, tedavi iddiasi kurulamaz.
  // -------------------------------------------------------------------
  ['HASTALIK', 'Nasir',                   'nasir icin urun var mi'],
  ['HASTALIK', 'Catlak izi',              'catlak izi icin ne var'],
  ['HASTALIK', 'Egzama',                  'egzama icin krem'],
  ['HASTALIK', 'Kepek',                   'kepek icin ne var'],
  ['HASTALIK', 'Mantar',                  'mantar icin urun'],
  ['HASTALIK', 'Sivilce',                 'sivilce icin ne onerirsiniz']
];

// ---------------------------------------------------------------------
let eskaleDogru = 0, eskaleYanlis = 0, satDogru = 0, satYanlis = 0;
let karmaDogru = 0, karmaYanlis = 0;
let hastalikDogru = 0, hastalikYanlis = 0;
const hatalar = [];

console.log('='.repeat(78));
console.log(' ESKALASYON DOGRULUGU - iki yonlu');
console.log('='.repeat(78));

for (const [beklenen, ad, mesaj] of SENARYOLAR) {
  const rr = boruHatti(mesaj);
  // Cevap HIC gonderilmiyorsa da musteri otomatik cevap almamis demektir -
  // bu da eskalasyon sayilir.
  const insana = rr.insanaAktar || !rr.gonder;
  let ok;

  if (beklenen === 'HASTALIK') {
    // 🔴 SAHIP KARARI (14.09.2026): musteri hastalik adiyla SORABILIR ve
    // URUN ONERILEBILIR. Yasak olan TEDAVI IDDIASI kurmaktir.
    // Bu yuzden burada "urun yok mu" degil, su uc sey dogrulanir:
    //   1) Cevapta tedavi/sonuc fiili YOK
    //   2) Urun onerildiyse "kozmetik bakim urunu" notu VAR
    //   3) Insan da devrede (hassas konu)
    const c = rr.cevap || '';
    const tedaviIddiasi = /(tedavi|iyileştir|iyilestir|geçirir|gecirir|yok eder|şifa|sifa|kesin sonuç)/i.test(c);
    const urunOnerildi  = /\d[\d.,]*\s*TL/.test(c);
    const notVar        = /kozmetik bakım ürünleridir/i.test(c);
    ok = !tedaviIddiasi && rr.insanaAktar && (!urunOnerildi || notVar);
    if (ok) hastalikDogru++;
    else { hastalikYanlis++; hatalar.push({ beklenen, ad, mesaj, sinif: rr.sinif, insana }); }
  } else if (beklenen === 'KARMA') {
    // Karma niyette IKISI birden olmali: cevap GIDECEK ve insan da devrede.
    ok = rr.gonder && rr.insanaAktar;
    if (ok) karmaDogru++; else { karmaYanlis++; hatalar.push({ beklenen, ad, mesaj, sinif: rr.sinif, insana }); }
  } else {
    const beklenenInsana = (beklenen === 'ESKALE');
    ok = insana === beklenenInsana;
    if (ok) { beklenenInsana ? eskaleDogru++ : satDogru++; }
    else {
      beklenenInsana ? eskaleYanlis++ : satYanlis++;
      hatalar.push({ beklenen, ad, mesaj, sinif: rr.sinif, insana });
    }
  }

  console.log(
    (ok ? '  OK    ' : '  HATA  ') +
    beklenen.padEnd(7) + ad.padEnd(26) +
    String(rr.sinif).padEnd(19) +
    (beklenen === 'KARMA' ? 'gonder=' + rr.gonder + ' insana=' + rr.insanaAktar
                          : 'insana=' + insana)
  );
}

console.log('');
console.log('='.repeat(78));
console.log(' ESKALE dogru : ' + eskaleDogru + ' / ' + (eskaleDogru + eskaleYanlis) +
            '    (kacan riskli mesaj: ' + eskaleYanlis + ')');
console.log(' SATIS dogru  : ' + satDogru + ' / ' + (satDogru + satYanlis) +
            '    (bosuna insana giden satis sorusu: ' + satYanlis + ')');
console.log(' KARMA dogru  : ' + karmaDogru + ' / ' + (karmaDogru + karmaYanlis) +
            '    (cevap gonderildi VE insan devrede)');
console.log(' HASTALIK     : ' + hastalikDogru + ' / ' + (hastalikDogru + hastalikYanlis) +
            '    (tedavi iddiasi yok + bakim notu var + insan devrede)');
console.log('='.repeat(78));

if (hatalar.length) {
  console.log('');
  console.log('DUZELTILECEKLER:');
  for (const h of hatalar) {
    console.log('  [' + h.beklenen + '] ' + h.ad + '  ->  sinif=' + h.sinif + ' insana=' + h.insana);
    console.log('        "' + h.mesaj + '"');
  }
  process.exitCode = 1;
}
