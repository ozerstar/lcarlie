const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');

const testler = [
  // [beklenen, aciklama, metin]
  ['TEMIZ',  'Temiz urun cevabi',
   'HYDRAVIE el ve yuz nemlendirici krem, 50 ml, 1.200 TL. Nem dengesi ve uzun sureli konfor hissi icin gunluk kullanima uygundur.'],

  ['TEMIZ',  'Temiz fiyat/kargo cevabi',
   'Siparisiniz icin lcarlie.shop adresinden odeme yapabilirsiniz. Kargo ucreti alinmamaktadir.'],

  ['BLOKLU', 'Hastalik adi + tedavi fiili',
   'Bu krem akneyi tedavi eder ve sivilceleri gecirir.'],

  ['BLOKLU', 'Yasak nesne - dolasim',
   'Urun bolgesel dolasimi destekler ve kan akisini artirir.'],

  ['BLOKLU', 'Kanal disi urun - VIREON',
   'VIREON for MEN hakkinda bilgi almak ister misiniz?'],

  ['BLOKLU', 'Kanal disi urun - FEMISIA',
   'Femisia gece serisi urunumuz 2400 TL.'],

  ['BLOKLU', 'Ilac karinesi bileseni',
   'Iceriginde Epimedium ve Tribulus bulunur.'],

  ['BLOKLU', 'Icermez kalibi',
   'Formulumuz paraben, silikon ve SLS icermez.'],

  ['BLOKLU', 'Sure iddiasi',
   'Duzenli kullanimda 14 gunde farki goreceksiniz.'],

  ['BLOKLU', 'Ustunluk iddiasi',
   'Turkiyenin en iyi nemlendirici kremi.'],

  ['BLOKLU', 'Tibbi onay cumlesi',
   'Evet iyi gelir, denemenizi oneririm.'],

  ['BLOKLU', 'Belgesiz ifade',
   'Dermatolojik olarak test edilmis ve %100 dogal bir urundur.'],

  ['BLOKLU', 'HYDRAVIE seramid tutarsizligi',
   'HYDRAVIE seramid kompleksi ile cilt bariyerini destekler.'],

  ['BLOKLU', 'SUNACNEA lockup eksik',
   'SUNACNEA gunes koruyucumuz her cilt tipine uygundur.'],

  ['INCELE', 'Yumusak liste - leke',
   'Cildimdeki leke gorunumu icin ne onerirsiniz?'],

  ['INCELE', 'Gunes urunu zorunlu ibare eksik',
   'SUNACNEA SPF 30 Gunluk Gunes Koruyucu, mineral filtrelidir.'],

  ['BLOKLU', 'Yapisal degisim - kolajen',
   'Kolajen uretimini destekleyerek elastikiyeti artirir.'],

  ['BLOKLU', 'Musteri sikayeti - egzama',
   'Egzamam var, bu urun ise yarar mi?'],

  // --- YANLIS POZITIF TESTLERI (bloklanmamali) ---
  ['TEMIZ',  'YP: odeme != odem',
   'Odemenizi kredi karti ile yapabilirsiniz, odeme sonrasi kargoya verilir.'],

  ['TEMIZ',  'YP: yarar != yara',
   'Bu urun cilt bakiminda ise yarar mi diye soruyorsunuz, gunluk kullanima uygundur.'],

  ['TEMIZ',  'YP: kasim != kas',
   'Kasim ayinda kampanyamiz devam ediyor.'],

  ['TEMIZ',  'YP: sinirli != sinir',
   'Sinirli sayida stok kalmistir.'],

  ['TEMIZ',  'YP: macar != maca',
   'Macaristan icin kargo gonderimi yapiyoruz.'],

  // --- Gercek eslesmeler hala yakalanmali ---
  ['BLOKLU', 'Gercek: kas + agri',
   'Kaslarinizdaki agriyi hafifletir.'],

  ['BLOKLU', 'Gercek: akne eki ile',
   'Akneli ciltler icin gelistirilmistir.'],
];

let basarili = 0, basarisiz = 0;
const hatalar = [];

for (const [beklenen, aciklama, metin] of testler) {
  const r = mevzuatFiltresi(metin, { kaynak: 'test' });
  const ok = r.sonuc === beklenen;
  if (ok) { basarili++; }
  else {
    basarisiz++;
    hatalar.push({ aciklama, beklenen, gelen: r.sonuc, metin,
                   bulgular: r.bulgular.map(b => b.tur + ':' + b.ifade) });
  }
  console.log(
    (ok ? 'OK   ' : 'HATA ') +
    r.sonuc.padEnd(7) + '[' + r.etiket + '] ' +
    aciklama +
    (r.bulgular.length ? '  -> ' + r.bulgular.map(b => b.tur + '(' + b.ifade + ')').join(', ') : '')
  );
}

console.log('\n==================================');
console.log('Basarili: ' + basarili + ' / ' + testler.length);
console.log('Basarisiz: ' + basarisiz);
if (hatalar.length) {
  console.log('\n--- HATALAR ---');
  console.log(JSON.stringify(hatalar, null, 2));
}
