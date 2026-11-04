// Sahte WhatsApp trafigi simulasyonu.
// Gercek kanala baglanmadan ajanin davranisini olcer.
const { akisMotoru, kararVer } = require('/tmp/akis-motoru.js');
const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');
const mesajlar = require('/tmp/sahte-mesajlar.js');

function boruHatti(mesaj) {
  const motor = akisMotoru({ mesaj, musteriId: 'sim', kanal: 'whatsapp' });
  const gelen = mevzuatFiltresi(mesaj, { kaynak: 'gelen' });
  const taslak = motor.taslakCevap ? mevzuatFiltresi(motor.taslakCevap, { kaynak: 'taslak' }) : null;
  return kararVer(motor, gelen, taslak);
}

const sinifSayaci = {};
const yanlisSinif = [];
const anlasilmayan = [];
let otomatik = 0, insana = 0, gonderilmedi = 0;

for (const [beklenen, mesaj] of mesajlar) {
  const r = boruHatti(mesaj);
  sinifSayaci[r.sinif] = (sinifSayaci[r.sinif] || 0) + 1;

  if (r.gonder && !r.insanaAktar) otomatik++;
  if (r.insanaAktar) insana++;
  if (!r.gonder) gonderilmedi++;

  if (beklenen && r.sinif !== beklenen) {
    yanlisSinif.push({ mesaj, beklenen, geldi: r.sinif });
  }
  if (r.sinif === 'ANLASILMADI') {
    anlasilmayan.push(mesaj);
  }
}

const N = mesajlar.length;
const y = (a) => (100 * a / N).toFixed(1) + '%';

console.log('='.repeat(72));
console.log(' SAHTE WHATSAPP TRAFIGI - ' + N + ' mesaj');
console.log('='.repeat(72));
console.log('');
console.log('  Tam otomatik cevaplanan : ' + String(otomatik).padStart(3) + '  (' + y(otomatik) + ')');
console.log('  Insana aktarilan        : ' + String(insana).padStart(3) + '  (' + y(insana) + ')');
console.log('  Hic cevap gonderilmeyen : ' + String(gonderilmedi).padStart(3) + '  (' + y(gonderilmedi) + ')');
console.log('');
console.log('--- Sinif dagilimi ---');
Object.entries(sinifSayaci).sort((a, b) => b[1] - a[1])
  .forEach(([s, n]) => console.log('  ' + s.padEnd(13) + String(n).padStart(3) + '  ' + y(n)));

if (yanlisSinif.length) {
  console.log('');
  console.log('--- YANLIS SINIFLANDIRMA (' + yanlisSinif.length + ') ---');
  yanlisSinif.forEach(h => console.log('  "' + h.mesaj + '"\n      beklenen=' + h.beklenen + '  geldi=' + h.geldi));
} else {
  console.log('');
  console.log('--- Beklenen siniflarin hepsi dogru ---');
}

console.log('');
console.log('--- ANLASILMADI (' + anlasilmayan.length + ' mesaj, ' + y(anlasilmayan.length) + ') ---');
anlasilmayan.forEach(m => console.log('  · ' + m));
