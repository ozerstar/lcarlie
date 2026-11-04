#!/usr/bin/env node
// =============================================================================
// L'CARLIE - YENI KANAL ISKELETI URETICI
//
// Satis ajani KANAL BAGIMSIZ. Yeni bir kanal eklemek (Instagram, Telegram,
// e-posta, site formu...) demek: yeni bir GIRIS KAPISI yazmak demek.
// Ajanin kendisi, mevzuat filtresi ve urun bilgi tabani aynen kullanilir.
//
// Bu uretici, 13.09.2026'ya kadar yasanan TUM tuzaklari iskelete gomer:
//   · $input.all()  (first() DEGIL - mesaj dusuruyordu, uc kez yasandi)
//   · executeWorkflow mode:'each'  ('once' birakilirsa sadece ilk mesaj islenir)
//   · $env YOK - n8n yasakliyor; anahtar yer tutucuyla konur
//   · hiz siniri (herkese acik uc nokta)
//   · gelen/giden filtre cagrilari ajan tarafinda zaten var
//
// Kullanim:
//   node yeni-kanal.js <kod> <ad> <webhookYolu>
//   node yeni-kanal.js Insta01 "INSTAGRAM KANALI" instagram
//
// Uretilen dosya: build-<yol>-workflow.js  (bu klasore yazilir)
// =============================================================================
const fs = require('fs');
const path = require('path');

const [, , kodArg, adArg, yolArg] = process.argv;

if (!kodArg || !adArg || !yolArg) {
  console.log('Kullanim: node yeni-kanal.js <kod> <ad> <webhookYolu>');
  console.log('Ornek   : node yeni-kanal.js Insta01 "INSTAGRAM KANALI" instagram');
  console.log('');
  console.log('  kod         : workflow ID\'sinin sonu. lcarlie<kod> olur (maks 9 karakter)');
  console.log('  ad          : n8n\'de gorunecek ad');
  console.log('  webhookYolu : /webhook/<yol> ve /webhook/<yol>-panel');
  process.exit(1);
}

const WID = ('lcarlie' + kodArg).slice(0, 16);
const YOL = yolArg.replace(/[^a-z0-9-]/gi, '').toLowerCase();
const AD = adArg;
const DOSYA = path.join(__dirname, `build-${YOL}-workflow.js`);

if (fs.existsSync(DOSYA)) {
  console.error(`HATA: ${path.basename(DOSYA)} zaten var. Uzerine yazilmadi.`);
  process.exit(1);
}

// UUID benzeri sabit onek - her kanal icin farkli olsun diye koddan turetilir
const onek = Buffer.from(WID).toString('hex').slice(0, 8).padEnd(8, '0');
const nid = (n) => `${onek}-0000-4000-8000-${String(n).padStart(12, '0')}`;

const icerik = `// =============================================================================
// ${AD}
//
// Uretildi: yeni-kanal.js · ${new Date().toLocaleDateString('tr-TR')}
// Workflow ID: ${WID}
//
// Satis ajani (lcarlieAkis0001) KANAL BAGIMSIZ - bu dosya sadece giris kapisi.
// Mevzuat filtresi ve urun bilgi tabani ajan tarafinda, burada TEKRARLANMAZ.
//
//   POST /webhook/${YOL}         { mesaj, musteriId } -> { cevap, insanaAktar }
//   GET  /webhook/${YOL}-panel?k=PILOT_TOKEN
// =============================================================================
const fs = require('fs');

// -----------------------------------------------------------------------------
// 1) Gelen istegi dogrula + hiz siniri
// -----------------------------------------------------------------------------
const kodGiris = \`
// 🔴 HIZ SINIRI - UC KATMAN. Herkese acik uc nokta, sinirsiz birakilmaz.
//
// musteriId ISTEMCIDEN geliyor. Sadece ona bakilirsa saldirgan her
// istekte yeni bir kimlik uretip siniri sonsuza kadar asar. IP katmani
// bunu keser. Global sinir yuksek tutulur ki tek bir saldirgan onu
// doldurup GERCEK MUSTERILERI kapatmak icin kullanamasin.
//
// ⚠️ Bu IP katmani SADECE dogrudan musteriden istek alan kanallar
//    icindir (site sohbeti gibi). Meta/WhatsApp/Instagram webhook'larinda
//    KULLANMAYIN: orada tum istekler Meta'nin birkac IP'sinden gelir,
//    hepsi ayni kovaya duser ve gercek trafik bogulur.
const KISI_LIMIT = 20,  KISI_PENCERE = 10 * 60 * 1000;
const IP_LIMIT   = 60,  IP_PENCERE   = 10 * 60 * 1000;
const TOPLAM_LIMIT = 1000, TOPLAM_PENCERE = 60 * 60 * 1000;

const stat = $getWorkflowStaticData('global');
stat.hiz = stat.hiz || {};
stat.ipHiz = stat.ipHiz || {};
stat.toplam = stat.toplam || [];
const simdi = Date.now();

stat.toplam = stat.toplam.filter(t => simdi - t < TOPLAM_PENCERE);
for (const k of Object.keys(stat.hiz)) {
  stat.hiz[k] = stat.hiz[k].filter(t => simdi - t < KISI_PENCERE);
  if (!stat.hiz[k].length) delete stat.hiz[k];
}
for (const k of Object.keys(stat.ipHiz)) {
  stat.ipHiz[k] = stat.ipHiz[k].filter(t => simdi - t < IP_PENCERE);
  if (!stat.ipHiz[k].length) delete stat.ipHiz[k];
}

// 🔴 X-Forwarded-For'un BASINI OKUMAYIN - Caddy o basliga ekleme yapar,
//    basindaki deger MUSTERININ yazdigi sahte deger olabilir.
//    Caddy 'header_up X-Gercek-IP {client_ip}' ile taklit edilemez
//    degeri koyuyor; yedek yol XFF'in SON degeridir.
const ipBul = (item) => {
  const h = (item.json && item.json.headers) || {};
  const gercek = String(h['x-gercek-ip'] || h['X-Gercek-IP'] || '').trim();
  if (gercek) return gercek;
  const xff = String(h['x-forwarded-for'] || h['X-Forwarded-For'] || '').trim();
  if (xff) {
    const p = xff.split(',').map(s => s.trim()).filter(Boolean);
    if (p.length) return p[p.length - 1];
  }
  return 'bilinmeyen';
};

const cikti = [];
// 🔴 all() - first() DEGIL. first() kullanilirsa diger musterilerin
//    mesajlari HATA VERMEDEN duser. Bu projede uc kez yasandi.
for (const item of $input.all()) {
  const b = item.json.body || item.json || {};
  const mesaj = String(b.mesaj ?? '').trim();
  const musteriId = String(b.musteriId ?? '').trim() || '${YOL}-anonim';

  if (!mesaj) { cikti.push({ json: { gecerli: false, hata: 'mesaj bos', musteriId } }); continue; }
  if (mesaj.length > 1000) { cikti.push({ json: { gecerli: false, hata: 'cok uzun', musteriId } }); continue; }

  const ip = ipBul(item);
  stat.hiz[musteriId] = stat.hiz[musteriId] || [];
  stat.ipHiz[ip] = stat.ipHiz[ip] || [];

  if (stat.hiz[musteriId].length >= KISI_LIMIT) {
    cikti.push({ json: { gecerli: false, hata: 'kisi hiz siniri', musteriId, hizSiniri: true } }); continue;
  }
  if (stat.ipHiz[ip].length >= IP_LIMIT) {
    cikti.push({ json: { gecerli: false, hata: 'ip hiz siniri', musteriId, hizSiniri: true } }); continue;
  }
  if (stat.toplam.length >= TOPLAM_LIMIT) {
    cikti.push({ json: { gecerli: false, hata: 'toplam hiz siniri', musteriId, hizSiniri: true } }); continue;
  }

  stat.hiz[musteriId].push(simdi);
  stat.ipHiz[ip].push(simdi);
  stat.toplam.push(simdi);
  cikti.push({ json: { gecerli: true, mesaj, musteriId, kanal: '${YOL}' } });
}
return cikti;
\`;

// -----------------------------------------------------------------------------
// 2) Ajan kararini cevaba cevir + kaydet
// -----------------------------------------------------------------------------
const kodCevap = \`
const stat = $getWorkflowStaticData('global');
stat.kayitlar = stat.kayitlar || [];

const VARSAYILAN =
  'Mesajınız için teşekkür ederiz. Bu konuda size en doğru bilgiyi ' +
  'ekip arkadaşımız verecek, en kısa sürede dönüş yapacağız. ' +
  'Bu arada tüm ürünlerimizi inceleyebilirsiniz: https://lcarlie.shop';

const cikti = [];
for (const item of $input.all()) {
  const k = item.json || {};
  const govde = (k.gonder && k.cevap) ? k.cevap : VARSAYILAN;

  const kayit = {
    zaman: new Date().toISOString(),
    musteri: k.musteriId || '-',
    sinif: k.sinif || '-',
    gelen: k.gelenMesaj || k.mesaj || '-',
    cevap: govde,
    otomatik: Boolean(k.gonder && k.cevap),
    insanaAktar: Boolean(k.insanaAktar)
  };
  stat.kayitlar.unshift(kayit);

  // 🔴 ESKALASYONLAR AYRI TUTULUR VE BUDANMAZ.
  // Bu iskelet dosyasi yeni kanallara ornek oluyor; eksik birakilirsa
  // acilan HER kanal insana aktarilan musteriyi 100 kayitlik listenin
  // sonunda kaybeder. Sohbet kanalinda yasandi, Instagram'a da eksik
  // kopyalanmisti (14.09.2026'da duzeltildi).
  if (kayit.insanaAktar) {
    stat.eskalasyonlar = stat.eskalasyonlar || [];
    stat.eskalasyonlar.unshift({ ...kayit, kapatildi: false });
    stat.eskalasyonToplam = (stat.eskalasyonToplam || 0) + 1;
    if (stat.eskalasyonlar.length > 500) stat.eskalasyonlar.length = 500;
  }

  cikti.push({ json: {
    cevap: govde,
    insanaAktar: Boolean(k.insanaAktar),
    otomatik: Boolean(k.gonder && k.cevap)
  }});
}
if (stat.kayitlar.length > 100) stat.kayitlar.length = 100;
return cikti;
\`;

// -----------------------------------------------------------------------------
// 3) Panel
// -----------------------------------------------------------------------------
const kodPanel = \`
// 🔴 $env KULLANILMAZ - n8n "access to env vars denied" hatasi verir.
// Anahtar, yayinlama hatti tarafindan bu yer tutucunun yerine konur.
const ANAHTAR = 'BURAYA_PILOT_ANAHTARI';

const q = $input.first().json.query || {};
if (!ANAHTAR || q.k !== ANAHTAR) {
  return [{ json: { html: '<!doctype html><meta charset=utf-8><body style="font-family:system-ui;padding:2rem">' +
    '<h3>Erişim reddedildi</h3></body>' } }];
}

const stat = $getWorkflowStaticData('global');
const kayitlar = (stat.kayitlar || []).slice(0, 60);
const kacis = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const saat = (t) => { try { return new Date(t).toLocaleString('tr-TR'); } catch(e) { return t; } };

const satirlar = kayitlar.map(r => {
  const rozet = r.otomatik
    ? '<span style="background:#dcfce7;color:#166534;padding:.1rem .45rem;border-radius:4px;font-size:.72rem">otomatik</span>'
    : '<span style="background:#fef3c7;color:#92400e;padding:.1rem .45rem;border-radius:4px;font-size:.72rem">insana</span>';
  return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:.8rem;margin-bottom:.7rem">' +
    '<div style="font-size:.78rem;color:#64748b">' + kacis(saat(r.zaman)) + ' · ' + kacis(r.musteri) + ' · ' + kacis(r.sinif) + ' ' + rozet + '</div>' +
    '<div style="margin-top:.4rem;font-weight:600">' + kacis(r.gelen) + '</div>' +
    '<div style="background:#f1f5f9;padding:.6rem .8rem;border-radius:6px;margin-top:.5rem;white-space:pre-wrap">' + kacis(r.cevap) + '</div>' +
    '</div>';
}).join('');

const html = '<!doctype html><html lang=tr><head><meta charset=utf-8>' +
  '<meta name=viewport content="width=device-width,initial-scale=1">' +
  '<meta http-equiv=refresh content=60><title>${AD}</title></head>' +
  '<body style="font-family:system-ui,-apple-system,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:1rem">' +
  '<div style="background:#0f172a;color:#fff;padding:.9rem 1rem;border-radius:10px;margin-bottom:1rem">' +
  '<div style="font-size:1.15rem;font-weight:700">${AD}</div></div>' +
  '<p style="font-size:.85rem;color:#475569">Son ' + kayitlar.length + ' konuşma.</p>' +
  (kayitlar.length ? satirlar : '<p style="color:#64748b">Henüz kayıt yok.</p>') +
  '</body></html>';

return [{ json: { html } }];
\`;

const kod = (ad, id, x, y, js) => ({
  parameters: { jsCode: js },
  id, name: ad, type: 'n8n-nodes-base.code', typeVersion: 2, position: [x, y]
});

const workflow = [{
  id: '${WID}',
  name: '${AD}',
  active: false,
  nodes: [
    {
      parameters: {
        httpMethod: 'POST', path: '${YOL}', responseMode: 'responseNode',
        options: { allowedOrigins: '*' }
      },
      id: '${nid(1)}',
      name: 'Gelen mesaj (POST)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 0],
      webhookId: '${nid(101)}'
    },
    kod('Girisi dogrula', '${nid(2)}', 240, 0, kodGiris),
    {
      parameters: {
        conditions: {
          options: { caseSensitive: true, leftValue: '', version: 2 },
          conditions: [{
            id: 'k1', operator: { type: 'boolean', operation: 'true', singleValue: true },
            leftValue: '={{ $json.gecerli }}', rightValue: ''
          }],
          combinator: 'and'
        },
        options: {}
      },
      id: '${nid(3)}',
      name: 'Gecerli mi?',
      type: 'n8n-nodes-base.if', typeVersion: 2, position: [480, 0]
    },
    {
      parameters: {
        workflowId: { __rl: true, value: 'lcarlieAkis0001', mode: 'id' },
        // 🔴 'each' SART. 'once' birakilirsa ajan sadece ILK mesaji isler,
        //    digerleri HATA VERMEDEN duser.
        mode: 'each',
        options: { waitForSubWorkflow: true }
      },
      id: '${nid(4)}',
      name: 'Satis ajanina sor',
      type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2, position: [720, -100]
    },
    kod('Cevabi hazirla', '${nid(5)}', 960, -100, kodCevap),
    {
      parameters: { respondWith: 'json', responseBody: '={{ JSON.stringify($json) }}', options: {} },
      id: '${nid(6)}',
      name: 'Cevabi dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [1200, -100]
    },
    {
      parameters: {
        respondWith: 'json',
        responseBody: '={{ JSON.stringify({ cevap: $json.hizSiniri' +
          ' ? "Çok sayıda mesaj aldık, birkaç dakika sonra tekrar yazabilirsiniz. Ürünlerimiz: https://lcarlie.shop"' +
          ' : "Mesajınızı alamadık, tekrar yazar mısınız?", insanaAktar: false }) }}',
        options: {}
      },
      id: '${nid(7)}',
      name: 'Gecersiz istek',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [720, 140]
    },
    {
      parameters: { httpMethod: 'GET', path: '${YOL}-panel', responseMode: 'responseNode', options: {} },
      id: '${nid(8)}',
      name: 'Panel (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 420],
      webhookId: '${nid(102)}'
    },
    kod('Panel HTML', '${nid(9)}', 240, 420, kodPanel),
    {
      parameters: { respondWith: 'text', responseBody: '={{ $json.html }}',
        options: { responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/html; charset=utf-8' }] } } },
      id: '${nid(10)}',
      name: 'Paneli dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [480, 420]
    }
  ],
  connections: {
    'Gelen mesaj (POST)': { main: [[{ node: 'Girisi dogrula', type: 'main', index: 0 }]] },
    'Girisi dogrula':     { main: [[{ node: 'Gecerli mi?', type: 'main', index: 0 }]] },
    'Gecerli mi?':        { main: [
                              [{ node: 'Satis ajanina sor', type: 'main', index: 0 }],
                              [{ node: 'Gecersiz istek', type: 'main', index: 0 }]
                            ] },
    'Satis ajanina sor':  { main: [[{ node: 'Cevabi hazirla', type: 'main', index: 0 }]] },
    'Cevabi hazirla':     { main: [[{ node: 'Cevabi dondur', type: 'main', index: 0 }]] },
    'Panel (GET)':        { main: [[{ node: 'Panel HTML', type: 'main', index: 0 }]] },
    'Panel HTML':         { main: [[{ node: 'Paneli dondur', type: 'main', index: 0 }]] }
  },
  settings: { executionOrder: 'v1' }
}];

fs.writeFileSync('/tmp/${YOL}-workflow.json', JSON.stringify(workflow, null, 2), 'utf8');
console.log('Yazildi. Node sayisi: ' + workflow[0].nodes.length);
`;

fs.writeFileSync(DOSYA, icerik, 'utf8');

console.log('');
console.log('='.repeat(70));
console.log(' YENI KANAL ISKELETI URETILDI');
console.log('='.repeat(70));
console.log('  Dosya       : ' + path.basename(DOSYA));
console.log('  Workflow ID : ' + WID);
console.log('  Uc nokta    : POST /webhook/' + YOL);
console.log('  Panel       : GET  /webhook/' + YOL + '-panel?k=<PILOT_TOKEN>');
console.log('');
console.log('  SIRADAKI ADIM - yayinlama hattina kaydet:');
console.log('  n8n-yayinla.sh icindeki WORKFLOWLAR dizisine su satiri ekle:');
console.log('');
console.log(`    "${WID}|build-${YOL}-workflow.js|${YOL}-workflow.json"`);
console.log('');
console.log('  Sonra:  .\\yayinla.ps1');
console.log('='.repeat(70));
