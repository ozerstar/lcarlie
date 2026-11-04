// Gecmis musteri mesajlarini URETIMDEKI motorla siniflandirir.
//
// 🔴 YENIDEN YAZILMADI. akis-motoru.js'in kendisi cagriliyor -- bu projede
//    kural kopyalamak defalarca sessiz kaymaya yol acti (F-1). Sinif kararini
//    veren kod, musteriye canli cevap uretirken calisan kodun ta kendisi.
//
// Cikti: her satir {"id":N,"sinif":"..."} -- yan etki yok, DB'ye dokunmaz.
const fs = require('fs');
const path = require('path');

const KAYNAK = process.argv[2];   // akis-motoru.js'in bulundugu klasor
const GIRDI = process.argv[3];
const CIKTI = process.argv[4];

const { akisMotoru } = require(path.join(KAYNAK, 'akis-motoru.js'));

const satirlar = fs.readFileSync(GIRDI, 'utf8')
  .split(/\r?\n/).filter(s => s.trim().startsWith('{'));

const cikti = [];
const sayim = {};
let hata = 0;

for (const s of satirlar) {
  let row;
  try { row = JSON.parse(s); } catch (e) { hata++; continue; }
  let sinif;
  try {
    const r = akisMotoru({ mesaj: row.metin, musteriId: 'backfill', kanal: 'gecmis' });
    sinif = r && r.sinif ? r.sinif : 'ANLASILMADI';
  } catch (e) {
    // 🔴 Motor patlarsa o mesaj SINIFSIZ kalir -- uydurma sinif yazilmaz.
    hata++;
    continue;
  }
  sayim[sinif] = (sayim[sinif] || 0) + 1;
  cikti.push(JSON.stringify({ id: row.id, sinif }));
}

fs.writeFileSync(CIKTI, cikti.join('\n') + '\n', 'utf8');

const sirali = Object.entries(sayim).sort((a, b) => b[1] - a[1]);
console.log('girdi satir     : ' + satirlar.length);
console.log('siniflandirilan : ' + cikti.length);
console.log('hata/atlanan    : ' + hata);
console.log('--- dagilim ---');
for (const [ad, n] of sirali) {
  console.log(String(n).padStart(4) + '  ' + ad + '  (%' + (100 * n / cikti.length).toFixed(1) + ')');
}
