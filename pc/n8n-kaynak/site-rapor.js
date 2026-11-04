// Canli sitedeki (Wix) urun aciklamalarinda bulunan mevzuat ihlalleri icin rapor.
const fs = require('fs');
const v = JSON.parse(fs.readFileSync('/tmp/site-oneriler.json', 'utf8'));

const m = [];
m.push('# L’CARLIÉ — Canlı Sitede Düzeltilecek Cümleler');
m.push('');
m.push('Kaynak: **lcarlie.shop canlı ürün açıklamaları** (Wix Stores) · ' +
       new Date().toLocaleDateString('tr-TR'));
m.push('');
m.push('> 🔴 Bu metinler **şu anda yayında** ve müşteri tarafından okunuyor.');
m.push('> Kutu metinlerinden farklı olarak burası **yayımlanmış reklam** sayılır');
m.push('> (Ticari Reklam Yönetmeliği m.8 / m.16).');
m.push('');
m.push('36 ürün tarandı, **' + v.length + ' cümlede** mevzuata aykırı ifade bulundu.');
m.push('');
m.push('Uyarı cümleleri ("Açık yaralara uygulamayınız" vb.) doğru şekilde temiz çıktı —');
m.push('**onlara dokunulmayacak**, zorunlu güvenlik metnidir.');
m.push('');
m.push('⚠️ Öneriler **yazım önerisidir, hukuk onayı değildir.**');
m.push('');

const gruplar = {};
for (const o of v) { (gruplar[o.urun] = gruplar[o.urun] || []).push(o); }
const sirali = Object.keys(gruplar).sort((a, b) => gruplar[b].length - gruplar[a].length);

m.push('## Özet');
m.push('');
m.push('| Ürün | Cümle |');
m.push('|---|---|');
for (const u of sirali) m.push('| ' + u + ' | ' + gruplar[u].length + ' |');
m.push('');

const tik = String.fromCharCode(96);   // backtick - kabuk tirnak sorunundan kacinmak icin

for (const u of sirali) {
  m.push('---');
  m.push('');
  m.push('## ' + u + '  · ' + gruplar[u].length + ' cümle');
  m.push('');
  m.push('| Mevcut cümle | Önerilen | Sorun |');
  m.push('|---|---|---|');
  for (const o of gruplar[u]) {
    let on;
    if (o.durum === 'TEMIZ') on = '**' + o.oneri + '**';
    else if (o.durum === 'TAMAMEN_CIKAR') on = '_(cümle tamamen çıkarılmalı)_';
    else on = '_(elle yeniden yazılmalı)_';
    const sorun = o.ifade.map(x => tik + x + tik).join(', ');
    m.push('| ' + o.cumle.replace(/\|/g, '-') + ' | ' + on + ' | ' + sorun + ' |');
  }
  m.push('');
}

fs.writeFileSync('/tmp/site-duzeltme.md', m.join('\n'), 'utf8');
console.log('Rapor yazildi: ' + v.length + ' cumle, ' + sirali.length + ' urun');
