const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');
const { akisMotoru, kararVer } = require('/tmp/akis-motoru.js');
const sablonlar = require('/tmp/sablonlar.js');

console.log('='.repeat(74));
console.log(' META SABLONLARI - MEVZUAT KONTROLU');
console.log('='.repeat(74));
let temiz = 0, kirli = 0;
for (const s of sablonlar) {
  // Degiskenleri ornek degerlerle doldurup GERCEK metni denetle
  let metin = s.govde;
  s.ornek.forEach((v, i) => { metin = metin.split('{{' + (i+1) + '}}').join(v); });
  const r = mevzuatFiltresi(metin, { kaynak: 'taslak' });
  const ok = r.sonuc === 'TEMIZ';
  ok ? temiz++ : kirli++;
  console.log('\n' + (ok ? 'OK   ' : 'HATA ') + s.ad.padEnd(22) + '[' + s.kategori + ']  ' + r.sonuc);
  if (!ok) console.log('       -> ' + r.bulgular.map(b => b.tur + ':' + b.ifade).join(', '));
}
console.log('\n' + '='.repeat(74));
console.log(' Temiz: ' + temiz + ' / ' + sablonlar.length);
console.log('='.repeat(74));

// Opt-out zinciri: sablondaki "DUR" ajanda gercekten durdurma sayiliyor mu?
console.log('\n--- OPT-OUT ZINCIRI TESTI ---');
for (const m of ['DUR', 'dur', 'Dur']) {
  const motor = akisMotoru({ mesaj: m, musteriId: 't', kanal: 'whatsapp' });
  const k = kararVer(motor, mevzuatFiltresi(m, {kaynak:'gelen'}), null);
  console.log('  "' + m + '" -> sinif=' + k.sinif + '  optOutKaydi=' + k.optOutKaydi);
}

// =====================================================================
// SATISTA ANLATILMAYAN URUNLER - CEVAPLARI FILTREDEN GECIYOR MU?
//
// 🔴 NEDEN BU TEST VAR:
// akis-motoru.js icinde bu cevaplari filtreye sokmaya calisan bir blok
// var ama 'mevzuatFiltresi' o dosyada tanimli degil - kontrol HIC
// calismiyor ve cevap erken return ile taslak filtresi dugumune de
// ugramadan musteriye gidiyor. Yani calisma aninda ACIK KAPI.
//
// Kapatmanin dogru yeri burasi: metin, slug veya urun adi degistigi anda
// bu test kirilir, yayinlama hatti durur ve denetlenmemis metin canliya
// HIC cikamaz. (Calisma anindaki blok kaldirilmadi cunku "taslaga birak"
// denemesi VIREON/FEMISIA/SOFTGUARD sorularini satis linkinden mahrum
// birakip genel cevaba dusurdu - canli testte goruldu, geri alindi.)
// =====================================================================
const { satisLinkiCevabi, SATISTA_ANLATILMAYAN } = require('/tmp/urunler.js');
const SITE = 'https://lcarlie.shop';

console.log('\n--- SATISTA ANLATILMAYAN URUN CEVAPLARI ---');
let sTemiz = 0, sKirli = 0;
const MUAF = ['kanal-disi-urun', 'motor-disi-urun', 'onay-bekleyen-urun',
              'katalog-disi-urun', 'ilac-karinesi-bileseni'];

if (typeof satisLinkiCevabi !== 'function' || !SATISTA_ANLATILMAYAN) {
  console.log('  HATA: satisLinkiCevabi / SATISTA_ANLATILMAYAN urunler.js icinde bulunamadi');
  sKirli++;
} else {
  for (const anahtar of Object.keys(SATISTA_ANLATILMAYAN)) {
    const metin = satisLinkiCevabi(anahtar, SITE);
    if (!metin) { console.log('  ATLANDI ' + anahtar + ' (cevap uretilmedi)'); continue; }
    const r = mevzuatFiltresi(metin, { kaynak: 'taslak' });
    const kalan = (r.bulgular || []).filter(b => b.sonuc === 'BLOKLU' && !MUAF.includes(b.tur));
    if (kalan.length === 0) {
      sTemiz++;
      console.log('  OK   ' + anahtar.padEnd(14) + r.sonuc);
    } else {
      sKirli++;
      console.log('  HATA ' + anahtar.padEnd(14) + kalan.map(b => b.tur + ':' + b.ifade).join(', '));
    }
  }
}
console.log('  Temiz: ' + sTemiz + '  Basarisiz: ' + sKirli);
if (sKirli > 0) {
  console.log('\n  🔴 Bu cevaplar CALISMA ANINDA denetlenmiyor - yayinlanmamali.');
  process.exit(1);
}
