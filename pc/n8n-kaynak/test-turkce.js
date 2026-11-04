const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');
console.log('ICU:', typeof Intl !== 'undefined' ? (Intl.DateTimeFormat().resolvedOptions().locale) : 'YOK');
console.log('toLocaleLowerCase tr testi: "İLTİHAP" ->', 'İLTİHAP'.toLocaleLowerCase('tr-TR'));
const t = [
  ['BLOKLU', 'Gerçek Türkçe: iltihap', 'Cildinizdeki İLTİHAP görünümünü azaltır.'],
  ['BLOKLU', 'Gerçek Türkçe: dolaşım', 'Bölgesel dolaşımı destekler.'],
  ['BLOKLU', 'Gerçek Türkçe: sivilce', 'Sivilcelerinize iyi gelir.'],
  ['BLOKLU', 'Gerçek Türkçe: içermez', 'Paraben içermeyen formül.'],
  ['TEMIZ',  'Türkçe temiz', 'Ödemenizi kredi kartı ile yapabilirsiniz. Kargo ücreti yoktur.'],
  ['TEMIZ',  'Türkçe temiz 2', 'HYDRAVIE 50 ml, günlük kullanıma uygun nemlendirici kremdir.'],
  ['BLOKLU', 'Büyük harf VİREON', 'VİREON ürünü hakkında bilgi'],
];
let ok=0;
for (const [bek, ad, m] of t) {
  const r = mevzuatFiltresi(m);
  const gecti = r.sonuc === bek;
  if (gecti) ok++;
  console.log((gecti?'OK   ':'HATA ') + r.sonuc.padEnd(7) + ad + (r.bulgular.length? '  -> '+r.bulgular.map(b=>b.ifade).join(', '):''));
}
console.log('\nTurkce test: ' + ok + '/' + t.length);
