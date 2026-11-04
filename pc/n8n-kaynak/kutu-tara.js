// Kutu icerik metinlerini mevzuat filtresinden gecirir.
// Cikti: urun -> duzeltilecek CUMLE listesi.
const fs = require('fs');
const path = require('path');
const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');

const KLASOR = '/tmp/kutu-metin';

// Bu kategoriler bu taramada ANLAMSIZ - haric tutuluyor:
//  - kanal/motor/onay: kutu zaten kendi urununun adini yazar
//  - gunes zorunlu ibare + lockup: bizim pazarlama metnimize ait kural
//  - yumusak liste: "doktorunuza danisiniz" gibi mesru UYARI cumleleri
const ATLA = new Set([
  'kanal-disi-urun', 'motor-disi-urun', 'onay-bekleyen-urun',
  'gunes-zorunlu-ibare', 'sunacnea-lockup', 'yumusak-liste'
]);

// INCI satirinda bilesen adi gecmesi ZORUNLU - orada bulgu sayilmaz.
const inciSatiriMi = (s) => {
  const t = s.toLocaleLowerCase('tr-TR');
  return /inci|i̇çindekiler|icindekiler|ingredients|aqua,|su \(aqua\)|saf su,/.test(t) && s.length > 80;
};

// --- BILESEN BEYANI SATIRI MI? ---
// "Epimedium Ekstresi" / "Maca Root Extract" gibi satirlar ICERIK BEYANIDIR.
// Ilac-karinesi kurali bu bileseni PAZARLAMADA one cikarmayi yasaklar;
// kutudaki icerik listesinden silmeyi DEGIL (kuralin kendi gerekcesi:
// "INCI listesinde kalir"). Bunlari "cikarilmali" diye isaretlemek
// ureticiye yasal icerik beyanini sildirmek olurdu.
const bilesenSatiriMi = (s) => {
  if (s.length > 70) return false;
  const t = s.toLocaleLowerCase('tr-TR');
  if (!/(ekstre|ekstresi|extract|ozu|özü|yagi|yağı|oil|tozu|powder|suyu|water|butter|yag)\b/.test(t)) return false;
  // Iddia fiili varsa bilesen beyani degil, pazarlama cumlesidir
  return !/(artir|azalt|destekle|onle|gider|yenile|onar|guclendir|duzenle|sagla|etkili|karsi|icin)/.test(t);
};

const dosyalar = fs.readdirSync(KLASOR).filter(f => f.endsWith('.txt')).sort((a, b) => {
  const n = s => parseInt(s.match(/^\d+/)?.[0] || '999', 10);
  return n(a) - n(b);
});

let toplamBulgu = 0;
const ozet = [];
const md = [];
const temizUrunler = [];
const turSayaci = {};

md.push('# L\'CARLIÉ — Kutu Metinlerinde Düzeltilecek Cümleler');
md.push('');
md.push('Kaynak: `02 LEMOS-MOY\\lemos\\kutu-icerik-son\\` (39 ürünün resmî kutu içerik metni)');
md.push('Tarama: L\'CARLIÉ mevzuat filtresi · ' + new Date().toLocaleDateString('tr-TR'));
md.push('');
md.push('> Bu bir **ürün listesi değildir**. Listelenen şey, kutu metninde geçen ve');
md.push('> kozmetik mevzuatında kullanılamayan **cümlelerdir**. Hepsi yazım düzeltmesiyle çözülür.');
md.push('');
md.push('**Taramaya dahil edilmeyenler:** INCI satırları (bileşen adı yazmak zorunlu),');
md.push('raf ömrü ve kullanım süresi ifadeleri (yasal zorunluluk), "doktorunuza danışınız"');
md.push('tipi uyarı cümleleri.');
md.push('');
// Ozet bolumu tam buraya girecek - sabit satir sayisina guvenme
const OZET_YERI = md.length;

for (const dosya of dosyalar) {
  const metin = fs.readFileSync(path.join(KLASOR, dosya), 'utf8');
  const urun = dosya.replace(/\.txt$/, '');

  // Satir + cumle bazli bol
  const parcalar = metin
    .split(/\n/)
    .flatMap(satir => satir.split(/(?<=[.!?])\s+/))
    .map(s => s.trim())
    .filter(s => s.length > 12);

  const bulgular = [];
  const gorulen = new Set();

  for (const p of parcalar) {
    if (inciSatiriMi(p) || bilesenSatiriMi(p)) continue;
    const r = mevzuatFiltresi(p, { kaynak: 'kutu' });
    const onemli = r.bulgular.filter(b => b.sonuc === 'BLOKLU' && !ATLA.has(b.tur));
    if (!onemli.length) continue;
    const anahtar = p.slice(0, 60);
    if (gorulen.has(anahtar)) continue;
    gorulen.add(anahtar);
    bulgular.push({ cumle: p, bulgular: onemli });
  }

  const urunAdi = urun.replace(/^\d+-?\s*/, '').replace(/_/g, '+').toUpperCase().trim();

  if (bulgular.length) {
    toplamBulgu += bulgular.length;
    ozet.push({ urun: urunAdi, adet: bulgular.length });
    console.log('\n### ' + urunAdi + '   (' + bulgular.length + ' cumle)');

    md.push('---');
    md.push('');
    md.push('## ' + urunAdi + '  · ' + bulgular.length + ' cümle');
    md.push('');
    md.push('| Düzeltilecek cümle | Sorun | Dayanak |');
    md.push('|---|---|---|');
    for (const b of bulgular) {
      for (const x of b.bulgular) { turSayaci[x.tur] = (turSayaci[x.tur] || 0) + 1; }
      const etiketler = [...new Set(b.bulgular.map(x => '`' + x.ifade + '`'))].join(', ');
      const cumle = (b.cumle.length > 260 ? b.cumle.slice(0, 260) + '…' : b.cumle).replace(/\|/g, '\\|');
      md.push('| ' + cumle + ' | ' + etiketler + ' | ' + b.bulgular[0].dayanak + ' |');
      console.log('  - ' + b.cumle.slice(0, 90));
    }
    md.push('');
  } else {
    temizUrunler.push(urunAdi);
  }
}

ozet.sort((a, b) => b.adet - a.adet);

// --- Ozet bolumunu basa ekle ---
const bas = [];
bas.push('## Özet');
bas.push('');
bas.push('| | |');
bas.push('|---|---|');
bas.push('| Taranan ürün | **' + dosyalar.length + '** |');
bas.push('| Düzeltme gereken ürün | **' + ozet.length + '** |');
bas.push('| Temiz çıkan ürün | **' + temizUrunler.length + '** |');
bas.push('| Toplam düzeltilecek cümle | **' + toplamBulgu + '** |');
bas.push('');
bas.push('### Sorun türüne göre');
bas.push('');
bas.push('| Tür | Adet |');
bas.push('|---|---|');
Object.entries(turSayaci).sort((a, b) => b[1] - a[1])
  .forEach(([t, n]) => bas.push('| ' + t + ' | ' + n + ' |'));
bas.push('');
bas.push('### Ürüne göre (çoktan aza)');
bas.push('');
bas.push('| Ürün | Cümle |');
bas.push('|---|---|');
ozet.forEach(o => bas.push('| ' + o.urun + ' | ' + o.adet + ' |'));
bas.push('');
bas.push('### Hiç düzeltme gerekmeyen ürünler');
bas.push('');
bas.push(temizUrunler.length ? temizUrunler.map(u => '`' + u + '`').join(' · ') : '(yok)');
bas.push('');

const cikti = md.slice(0, OZET_YERI).concat(bas).concat(md.slice(OZET_YERI)).join('\n');
fs.writeFileSync('/tmp/kutu-duzeltme-raporu.md', cikti, 'utf8');

console.log('\n' + '='.repeat(78));
console.log('Duzeltilecek cumle : ' + toplamBulgu);
console.log('Duzeltme gereken   : ' + ozet.length + ' / ' + dosyalar.length + ' urun');
console.log('Temiz cikan        : ' + temizUrunler.join(', '));
console.log('Rapor              : /tmp/kutu-duzeltme-raporu.md (' + cikti.length + ' karakter)');
console.log('='.repeat(78));
