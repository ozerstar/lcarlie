// Kutu metnindeki sorunlu cumleler icin UYGUN ALTERNATIF uretir.
// Her oneri, yazildiktan sonra mevzuat filtresine GERI SOKULUR.
// Temiz cikmayan oneri rapora girmez - boylece oneri "ezbere" degil kanitli olur.
const fs = require('fs');
const path = require('path');
const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');

const KLASOR = '/tmp/kutu-metin';
const ATLA = new Set([
  'kanal-disi-urun', 'motor-disi-urun', 'onay-bekleyen-urun',
  'gunes-zorunlu-ibare', 'sunacnea-lockup', 'yumusak-liste'
]);

const inciSatiriMi = (s) => {
  const t = s.toLocaleLowerCase('tr-TR');
  return /inci|i̇çindekiler|icindekiler|ingredients|aqua,|su \(aqua\)|saf su,/.test(t) && s.length > 80;
};

// =============================================================
// KAVRAM BAZLI ESDEGER SOZLUGU
// Anahtar: filtrenin yakaladigi ifade.
// Deger : yerine yazilabilecek kozmetik iddia, ya da null = tamamen cikarilmali.
//
// Ilke (bkz. iddia kurali): FIIL degil, cumlenin NESNESI denetlenir.
// "yenileyici" serbesttir; "hucre yenileyici" degildir.
// Bu yuzden esdegerlerin nesnesi daima "cilt gorunumu / his / aroma" olur.
// =============================================================
const ESDEGER = {
  // --- Hastalik / tibbi durum: karsiligi yok, cikarilir ---
  'migren': null, 'anksiyete': null, 'iltihap': null, 'yatak yarasi': null,
  'yara': null, 'egzama': null, 'sedef': null, 'mantar': null, 'hemoroid': null,
  'varis': null, 'selulit': null, 'akne': null, 'dermatit': null, 'psoriasis': null,
  'bagimlilik': null, 'hormon': null, 'depresyon': null, 'uykusuzluk': null,
  'astim': null, 'romatizma': null, 'artrit': null, 'siyatik': null,
  'enfeksiyon': null, 'alerji': null, 'odem': null, 'agri': null, 'aft': null,

  // --- Ilac karinesi yaratan bilesen iddialari ---
  'antibakteriyel': 'temizleyici',
  'antiviral': null,
  'antiseptik': 'temizleyici',
  'antifungal': null,
  'antienflamatuar': null,
  'mikrop': 'temizleyici',
  'bakteri': 'temizleyici',

  // --- Fizyolojik etki iddialari: hisse cevrilir ---
  'dolasim': 'canlandırıcı his veren',
  'kan akisi': 'canlandırıcı his veren',
  'lenfatik': null,
  'oksijenlenme': 'canlandırıcı his veren',
  'kas': 'masaj sonrası rahatlama hissi veren',
  'sinir': null,
  'damar': null,
  'doku': 'cilt görünümünü destekleyen',
  'hucre yenilenmesi': 'cilt görünümünü destekleyen',
  'hucre': 'cilt görünümünü destekleyen',
  'kolajen': 'cilt görünümünü destekleyen',
  'elastikiyet': 'cilt görünümüne katkı sağlayan',
  'metabolizma': null,
  'bagisiklik': null,
  'detoks': null,
  'savunma': null,

  // --- Tedavi fiilleri: bakim diline cevrilir ---
  'onarim': 'bakım',
  'onarici': 'bakım sağlayan',
  'tedavi': 'bakım',
  'iyilestir': 'bakım sağlayan',
  'gecirir': null,
  'yok eder': null,
  'engeller': null,
  'onler': null,

  // --- Belgesiz / ustunluk ---
  'en iyi': null, 'en etkili': null, 'birebir': null, 'kesin': null,
  'mucizevi': null, 'aninda': null, 'kanitlanmis': null, 'klinik': null,
};

// Parcada gecen ifadeye gore esdeger bul
const esdegerBul = (parca, ifadeler) => {
  for (const i of ifadeler) {
    const k = i.toLocaleLowerCase('tr-TR');
    if (Object.prototype.hasOwnProperty.call(ESDEGER, k)) return ESDEGER[k];
  }
  return null; // tanimsizsa guvenli taraf: cikar
};

const buyukHarfle = (s) => s.charAt(0).toLocaleUpperCase('tr-TR') + s.slice(1);

// =============================================================
// Bir cumle icin oneri uretir.
// Strateji: cumleyi iddia parcalarina bol, sorunlu parcayi at veya
// esdegeriyle degistir, temiz parcalari koru.
// =============================================================
function oneriUret(cumle) {
  // DUZ YAZI CUMLESI parcalanmaz. "A ve B olur, C sağlar" gibi bir cumleden
  // parca cikarinca ortaya bozuk Turkce cikiyor ("...olur, katkı sağlayan").
  // Boyle cumlelerde otomatik oneri uretmek yerine ELLE YAZILMALI demek dogru.
  // Fiil LISTESI tutmak yetmiyor - "destekler", "bulunur" gibi biçimler kaçıyordu.
  // Turkce genis zaman 3. tekil EKINE bakmak daha saglam: -ir/-ır/-ur/-ür/-er/-ar.
  // Kisa parca listeleri ("Bolgesel dolasimi destekler, canlilik kazandirir" = 54
  // karakter) zaten 70 esigini gecmedigi icin etkilenmiyor.
  const duzYazi = cumle.length > 70 &&
    /(ir|ır|ur|ür|er|ar)\s*[.!?]?\s*$/i.test(cumle.trim());

  // Basliksi satirlari (urun adi vb.) ayri ele al
  const parcalar = cumle.split(/\s*[,;/•·]\s*|\s+–\s+|\s+-\s+/).map(s => s.trim()).filter(Boolean);

  const tutulan = [];
  const cikarilan = [];
  let degistirilen = 0;   // esdegeriyle DEGISTIRILEN parca sayisi

  for (const p of parcalar) {
    const r = mevzuatFiltresi(p, { kaynak: 'kutu' });
    const kotu = r.bulgular.filter(b => b.sonuc === 'BLOKLU' && !ATLA.has(b.tur));
    if (!kotu.length) { tutulan.push(p); continue; }

    const ifadeler = kotu.map(b => b.ifade);
    const es = esdegerBul(p, ifadeler);
    if (es) {
      // Esdegeri de dogrula - kirli esdeger kabul edilmez
      const rr = mevzuatFiltresi(es, { kaynak: 'kutu' });
      const kotu2 = rr.bulgular.filter(b => b.sonuc === 'BLOKLU' && !ATLA.has(b.tur));
      if (!kotu2.length && !tutulan.includes(es)) { tutulan.push(es); degistirilen++; continue; }
    }
    cikarilan.push({ parca: p, ifadeler: [...new Set(ifadeler)] });
  }

  if (!tutulan.length) return { oneri: null, cikarilan, durum: 'TAMAMEN_CIKAR' };

  // Duz yazi cumlesine dokunulduysa (cikarma VEYA degistirme) dikis tutmaz.
  // "...yardimci olur, cilt gorunumune katki saglayan" gibi bozuk Turkce cikiyor.
  if (duzYazi && (cikarilan.length || degistirilen)) {
    // Not icin: cumlenin TAMAMINDA hangi ifadeler sorunluydu?
    const tumu = mevzuatFiltresi(cumle, { kaynak: 'kutu' }).bulgular
      .filter(b => b.sonuc === 'BLOKLU' && !ATLA.has(b.tur)).map(b => b.ifade);
    return { oneri: null, cikarilan, durum: 'DOGRULANAMADI',
             kalan: [...new Set(tumu)], duzYazi: true };
  }

  let oneri = buyukHarfle(tutulan.join(', '));

  // ONERIYI GERI DOGRULA - butun cumle olarak
  const son = mevzuatFiltresi(oneri, { kaynak: 'kutu' });
  const kalan = son.bulgular.filter(b => b.sonuc === 'BLOKLU' && !ATLA.has(b.tur));
  if (kalan.length) {
    return { oneri: null, cikarilan, durum: 'DOGRULANAMADI',
             kalan: [...new Set(kalan.map(b => b.ifade))] };
  }
  return { oneri, cikarilan, durum: 'TEMIZ' };
}

// =============================================================
// Tarama
// =============================================================
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

const md = [];
md.push('# L\'CARLIÉ — Kutu Metni Düzeltme Önerileri');
md.push('');
md.push('Üretim: ' + new Date().toLocaleDateString('tr-TR') + ' · L\'CARLIÉ mevzuat filtresi');
md.push('');
md.push('> Bu dosya `KUTU-DUZELTME-RAPORU.md`\'nin devamıdır. O rapor **neyin**');
md.push('> düzeltileceğini söylüyordu; bu dosya **ne yazılacağını** söylüyor.');
md.push('');
md.push('**Önerilerin hepsi mevzuat filtresinden geri geçirilerek doğrulanmıştır.**');
md.push('Filtreden temiz çıkmayan hiçbir öneri bu dosyaya girmedi.');
md.push('');
md.push('Yöntem: cümle iddia parçalarına ayrılır → sorunlu parça ya kozmetik');
md.push('karşılığıyla değiştirilir ya da çıkarılır → temiz parçalar korunur →');
md.push('ortaya çıkan cümle filtreye geri sokulur.');
md.push('');
md.push('⚠️ Öneriler **yazım önerisidir, hukuk onayı değildir.** Yayımlanmadan önce');
md.push('sorumlu teknik eleman / hukuk tarafından teyit edilmelidir.');
md.push('');
const OZET_YERI = md.length;

let sayac = { TEMIZ: 0, TAMAMEN_CIKAR: 0, DOGRULANAMADI: 0 };
const urunOzet = [];

for (const dosya of dosyalar) {
  const metin = fs.readFileSync(path.join(KLASOR, dosya), 'utf8');
  const parcalar = metin.split(/\n/)
    .flatMap(s => s.split(/(?<=[.!?])\s+/))
    .map(s => s.trim()).filter(s => s.length > 12);

  const satirlar = [];
  const gorulen = new Set();

  for (const p of parcalar) {
    if (inciSatiriMi(p) || bilesenSatiriMi(p)) continue;
    const r = mevzuatFiltresi(p, { kaynak: 'kutu' });
    const onemli = r.bulgular.filter(b => b.sonuc === 'BLOKLU' && !ATLA.has(b.tur));
    if (!onemli.length) continue;
    const anahtar = p.slice(0, 60);
    if (gorulen.has(anahtar)) continue;
    gorulen.add(anahtar);
    satirlar.push({ cumle: p, sonuc: oneriUret(p) });
  }

  if (!satirlar.length) continue;

  const urunAdi = dosya.replace(/\.txt$/, '').replace(/^\d+-?\s*/, '')
    .replace(/_/g, '+').toUpperCase().trim();
  urunOzet.push({ urun: urunAdi, adet: satirlar.length });

  md.push('---');
  md.push('');
  md.push('## ' + urunAdi + '  · ' + satirlar.length + ' cümle');
  md.push('');
  md.push('| Mevcut cümle | Önerilen cümle | Not |');
  md.push('|---|---|---|');

  for (const s of satirlar) {
    sayac[s.sonuc.durum]++;
    const mevcut = (s.cumle.length > 150 ? s.cumle.slice(0, 150) + '…' : s.cumle).replace(/\|/g, '\\|');
    let oneri, not;

    if (s.sonuc.durum === 'TEMIZ') {
      oneri = '**' + s.sonuc.oneri.replace(/\|/g, '\\|') + '**';
      not = s.sonuc.cikarilan.length
        ? 'çıkarılan: ' + s.sonuc.cikarilan.map(c => '`' + c.ifadeler.join('`, `') + '`').join(' · ')
        : '—';
    } else if (s.sonuc.durum === 'TAMAMEN_CIKAR') {
      oneri = '_(cümle tamamen çıkarılmalı)_';
      not = 'kozmetik karşılığı yok: ' +
        [...new Set(s.sonuc.cikarilan.flatMap(c => c.ifadeler))].map(i => '`' + i + '`').join(', ');
    } else if (s.sonuc.duzYazi) {
      oneri = '_(elle yeniden yazılmalı)_';
      not = 'düz yazı cümlesi — parça çıkarınca cümle bozuluyor. Çıkarılacak: `' +
            (s.sonuc.kalan || []).join('`, `') + '`';
    } else {
      oneri = '_(elle yazılmalı)_';
      not = 'otomatik öneri doğrulanamadı: `' + (s.sonuc.kalan || []).join('`, `') + '`';
    }
    md.push('| ' + mevcut + ' | ' + oneri + ' | ' + not + ' |');
  }
  md.push('');
}

const toplam = sayac.TEMIZ + sayac.TAMAMEN_CIKAR + sayac.DOGRULANAMADI;
const bas = [];
bas.push('## Özet');
bas.push('');
bas.push('| | |');
bas.push('|---|---|');
bas.push('| Ele alınan cümle | **' + toplam + '** |');
bas.push('| ✅ Doğrulanmış öneri üretildi | **' + sayac.TEMIZ + '** |');
bas.push('| ✂️ Cümle tamamen çıkarılmalı | **' + sayac.TAMAMEN_CIKAR + '** |');
bas.push('| ✍️ Elle yazılmalı | **' + sayac.DOGRULANAMADI + '** |');
bas.push('');

const cikti = md.slice(0, OZET_YERI).concat(bas).concat(md.slice(OZET_YERI)).join('\n');
fs.writeFileSync('/tmp/kutu-duzeltme-onerileri.md', cikti, 'utf8');

console.log('='.repeat(70));
console.log('Ele alinan cumle       : ' + toplam);
console.log('Dogrulanmis oneri      : ' + sayac.TEMIZ);
console.log('Tamamen cikarilmali    : ' + sayac.TAMAMEN_CIKAR);
console.log('Elle yazilmali         : ' + sayac.DOGRULANAMADI);
console.log('Rapor: /tmp/kutu-duzeltme-onerileri.md (' + cikti.length + ' karakter)');
console.log('='.repeat(70));

// Baska betiklerin (ornek: site taramasi) ayni oneri motorunu kullanabilmesi icin
module.exports = { oneriUret, ESDEGER };

