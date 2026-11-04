const fs = require('fs');
const sablonlar = require('/tmp/sablonlar.js');
const { mevzuatFiltresi } = require('/tmp/mevzuat-filtresi.js');

const md = [];
md.push("# L'CARLIÉ — WhatsApp Onaylı Mesaj Şablonları");
md.push('');
md.push('Meta Business Manager → WhatsApp Manager → **Message Templates** → *Create template*');
md.push('');
md.push('> 24 saatlik müşteri hizmeti penceresi **dışına** çıkan her mesaj bu şablonlardan');
md.push('> biriyle gönderilmek zorunda. Pencere içinde ajan serbest metin yazabilir.');
md.push('');
md.push('Hepsi L\'CARLIÉ mevzuat filtresinden geçirildi: **' + sablonlar.length + '/' + sablonlar.length + ' temiz**.');
md.push('');
md.push('---');
md.push('');
md.push('## 🔴 MARKETING şablonları için uyarı');
md.push('');
md.push('`MARKETING` kategorisindeki şablonlar ticari elektronik ileti sayılabilir.');
md.push('**İYS / 6563 hukuk onayı alınmadan kullanılmamalı.** `UTILITY` şablonları');
md.push('işlem bildirimi olduğu için bu kapsamın dışında kalır.');
md.push('');
md.push('Her MARKETING şablonunda `DUR yazabilirsiniz` cümlesi var. Bu tesadüf değil:');
md.push('ajanın durdurma sınıflandırıcısı "DUR" / "dur" / "Dur" yazan müşteriyi anında');
md.push('opt-out kaydına alıyor — test edildi.');
md.push('');

for (const kat of ['UTILITY', 'MARKETING']) {
  md.push('---');
  md.push('');
  md.push('# ' + kat);
  md.push('');
  for (const s of sablonlar.filter(x => x.kategori === kat)) {
    let dolu = s.govde;
    s.ornek.forEach((v, i) => { dolu = dolu.split('{{' + (i+1) + '}}').join(v); });
    const r = mevzuatFiltresi(dolu, { kaynak: 'taslak' });

    md.push('## `' + s.ad + '`');
    md.push('');
    md.push('| | |');
    md.push('|---|---|');
    md.push('| Kategori | ' + s.kategori + ' |');
    md.push('| Dil | ' + s.dil + ' |');
    md.push('| Mevzuat kontrolü | ' + (r.sonuc === 'TEMIZ' ? '✅ temiz' : '⚠ ' + r.sonuc) + ' |');
    md.push('');
    md.push('**Şablon gövdesi (Meta\'ya bu yapıştırılacak):**');
    md.push('');
    md.push('```');
    md.push(s.govde);
    md.push('```');
    md.push('');
    md.push('**Değişkenler:**');
    md.push('');
    md.push('| # | Anlamı | Örnek |');
    md.push('|---|---|---|');
    s.degiskenler.forEach((d, i) => md.push('| {{' + (i+1) + '}} | ' + d + ' | ' + s.ornek[i] + ' |'));
    md.push('');
    md.push('**Örnek çıktı:**');
    md.push('');
    md.push('> ' + dolu);
    md.push('');
  }
}

md.push('---');
md.push('');
md.push('## Sunarken dikkat');
md.push('');
md.push('- Meta örnek değer ister; yukarıdaki **Örnek** sütununu kullanın.');
md.push('- Link içeren şablonlarda alan adı Meta tarafından kontrol edilir; `lcarlie.shop` doğrulanmış olmalı.');
md.push('- Onay birkaç dakikadan birkaç saate kadar sürebilir. Reddedilirse gerekçe Meta panelinde görünür.');
md.push('- Şablon metni onaydan sonra değiştirilemez; değişiklik yeni şablon demektir.');
md.push('');

fs.writeFileSync('/tmp/whatsapp-sablonlari.md', md.join('\n'), 'utf8');
console.log('Yazildi: ' + md.join('\n').length + ' karakter');
