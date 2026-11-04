// =====================================================================
// L'CARLIE - WEB SOHBET KANALI
//
// Amac: Meta erisim bilgisi beklemeden ajani BUGUN satisa sokmak.
// Satis ajani kanal bagimsiz; bu workflow sadece yeni bir giris kapisi.
//
// POST /webhook/sohbet   -> { mesaj, musteriId } => { cevap, insanaAktar }
// GET  /webhook/sohbet-panel?k=PILOT_TOKEN -> son kararlar
//
// 🔴 WhatsApp'tan FARKI: burada cevap ANINDA donuyor (responseNode).
//    Gonderim icin harici kimlik bilgisi GEREKMIYOR - kendi sitemiz.
// =====================================================================
const fs = require('fs');

// ---------------------------------------------------------------------
// 1) Gelen istegi dogrula ve normalize et
// ---------------------------------------------------------------------
const kodGiris = `
// 🔴 HIZ SINIRI - UC KATMAN
//
// Uc nokta herkese acik ve CORS '*'.
//
// Onceki hali SADECE musteriId'ye bakiyordu; musteriId tamamen
// ISTEMCIDEN geliyor, yani her istekte rastgele bir kimlik uretip
// sinir SONSUZA KADAR asilabiliyordu. Ustelik tek bir saldirgan
// saniyeler icinde global sayaci doldurup GERCEK MUSTERILERE bir saat
// boyunca "cok mesaj aldik" dedirtebiliyordu - satis kanalini kapatmak
// bir kabuk dongusune bakiyordu.
//
// Simdi:
//   1) Kisi (musteriId) : 10 dakikada 20  - normal kullanim siniri
//   2) IP               : 10 dakikada 60  - rastgele kimlik uretmeyi keser
//   3) Toplam           : saatte 1000     - son care emniyet supabi
//      (yuksek tutuldu: saldirgan once KENDI IP sinirina takilsin,
//       global sinir digerlerini kapatan bir silaha donusmesin)
const KISI_LIMIT = 20,  KISI_PENCERE  = 10 * 60 * 1000;
const IP_LIMIT   = 60,  IP_PENCERE    = 10 * 60 * 1000;
const TOPLAM_LIMIT = 1000, TOPLAM_PENCERE = 60 * 60 * 1000;

const stat = $getWorkflowStaticData('global');
stat.hiz = stat.hiz || {};
stat.ipHiz = stat.ipHiz || {};
stat.toplam = stat.toplam || [];
const simdi = Date.now();

// Eski kayitlari temizle - sinirsiz buyumesin
stat.toplam = stat.toplam.filter(t => simdi - t < TOPLAM_PENCERE);
for (const k of Object.keys(stat.hiz)) {
  stat.hiz[k] = stat.hiz[k].filter(t => simdi - t < KISI_PENCERE);
  if (!stat.hiz[k].length) delete stat.hiz[k];
}
for (const k of Object.keys(stat.ipHiz)) {
  stat.ipHiz[k] = stat.ipHiz[k].filter(t => simdi - t < IP_PENCERE);
  if (!stat.ipHiz[k].length) delete stat.ipHiz[k];
}

// 🔴 IP'yi X-Forwarded-For'un BASINDAN OKUMAYIN.
//
// Caddy bu basliga EKLEME yapar. Musteri kendi istegine
// "X-Forwarded-For: 1.2.3.4" koyarsa listenin basinda O durur; her
// istekte farkli bir sahte deger yazip IP sinirini sonsuza kadar asar.
// Yani ilk degeri okumak, siniri saldirganin denetimine birakir.
//
// Caddy 'header_up X-Gercek-IP {client_ip}' ile kendi gordugu baglanti
// adresini yaziyor; header_up SET eder, musterinin gonderdigi ayni isimli
// baglik EZILIR. Bu deger taklit edilemez.
//
// Yedek yol olarak X-Forwarded-For'un SON degeri kullanilir: zinciri
// Caddy olusturdugu icin sondaki daima gercek baglanti adresidir.
const ipBul = (item) => {
  const h = (item.json && item.json.headers) || {};
  const gercek = String(h['x-gercek-ip'] || h['X-Gercek-IP'] || '').trim();
  if (gercek) return gercek;
  const xff = String(h['x-forwarded-for'] || h['X-Forwarded-For'] || '').trim();
  if (xff) {
    const parcalar = xff.split(',').map(s => s.trim()).filter(Boolean);
    if (parcalar.length) return parcalar[parcalar.length - 1];
  }
  return 'bilinmeyen';
};

const cikti = [];
// 🔴 all() - first() DEGIL. Bu projede uc kez mesaj dusuruldu.
for (const item of $input.all()) {
  const b = item.json.body || item.json || {};
  const mesaj = String(b.mesaj ?? '').trim();
  // Oturum kimligi: tarayici uretir, kisisel veri degil.
  const musteriId = String(b.musteriId ?? '').trim() || 'web-anonim';

  if (!mesaj) {
    cikti.push({ json: { gecerli: false, hata: 'mesaj bos', musteriId } });
    continue;
  }
  if (mesaj.length > 1000) {
    cikti.push({ json: { gecerli: false, hata: 'mesaj cok uzun', musteriId } });
    continue;
  }

  const ip = ipBul(item);

  stat.hiz[musteriId] = stat.hiz[musteriId] || [];
  stat.ipHiz[ip] = stat.ipHiz[ip] || [];

  if (stat.hiz[musteriId].length >= KISI_LIMIT) {
    cikti.push({ json: { gecerli: false, hata: 'kisi hiz siniri', musteriId, hizSiniri: true } });
    continue;
  }
  // 🔴 IP siniri: rastgele musteriId uretip siniri asmayi keser
  if (stat.ipHiz[ip].length >= IP_LIMIT) {
    cikti.push({ json: { gecerli: false, hata: 'ip hiz siniri', musteriId, hizSiniri: true } });
    continue;
  }
  if (stat.toplam.length >= TOPLAM_LIMIT) {
    cikti.push({ json: { gecerli: false, hata: 'toplam hiz siniri', musteriId, hizSiniri: true } });
    continue;
  }

  stat.hiz[musteriId].push(simdi);
  stat.ipHiz[ip].push(simdi);
  stat.toplam.push(simdi);
  cikti.push({ json: { gecerli: true, mesaj, musteriId, kanal: 'web' } });
}
return cikti;
`;

// ---------------------------------------------------------------------
// 2) Ajan kararini musteriye gonderilecek cevaba cevir + kaydet
// ---------------------------------------------------------------------
const kodCevap = `
const stat = $getWorkflowStaticData('global');
stat.kayitlar = stat.kayitlar || [];

const VARSAYILAN =
  'Mesajınız için teşekkür ederiz. Bu konuda size en doğru bilgiyi ' +
  'ekip arkadaşımız verecek, en kısa sürede dönüş yapacağız. ' +
  'Bu arada tüm ürünlerimizi inceleyebilirsiniz: https://lcarlie.shop';

// 🔴 AJAN COKERSE MUSTERI KIMLIGI KAYBOLUYOR.
// 'continueRegularOutput' giris ogesini GECIRMIYOR - yalnizca hata bilgisi
// iceren bir oge uretiyor. Canli testte kayit 'musteri=-  gelen=-' olarak
// yazildi: konusma insana aktarildi ama KIMIN yazdigi kayitta yok, yani
// donus yapilamaz. Kimligi bir onceki dugumden, sira numarasiyla aliyoruz.
let oncekiler = [];
try { oncekiler = $('Gecerli mi?').all(); } catch (e) { oncekiler = []; }

const cikti = [];
const hepsi = $input.all();
for (let i = 0; i < hepsi.length; i++) {
  const item = hepsi[i];
  const k = item.json || {};
  const onceki = (oncekiler[i] && oncekiler[i].json) || {};

  // 🔴 AJAN COKTU MU?
  // 'Satis ajanina sor' dugumu onError:'continueRegularOutput' ile
  // yapilandirildi; coktugunde oge 'error' alaniyla buraya gelir.
  // Bu durumda musteri yine notr bir cevap alir AMA konusma mutlaka
  // INSANA AKTARILIR - yoksa mesaj sessizce kaybolur (13.09.2026'da oldu).
  const ajanCokti = Boolean(k.error) || (!k.sinif && !k.cevap && !k.gonder);

  // Ajan cevap uretmediyse (eskalasyon) musteri bosluga bakmaz -
  // notr bir karsilik doner, konusma kopmaz.
  const govde = (k.gonder && k.cevap && !ajanCokti) ? k.cevap : VARSAYILAN;

  const kayit = {
    zaman: new Date().toISOString(),
    // Ajan coktuyse kimlik ve mesaj bir onceki dugumden alinir.
    musteri: k.musteriId || onceki.musteriId || '-',
    sinif: ajanCokti ? 'AJAN-HATASI' : (k.sinif || '-'),
    gelen: k.gelenMesaj || k.mesaj || onceki.mesaj || '-',
    cevap: govde,
    otomatik: Boolean(k.gonder && k.cevap && !ajanCokti),
    // Coktuyse HER ZAMAN insana aktarilir.
    insanaAktar: ajanCokti ? true : Boolean(k.insanaAktar)
  };
  stat.kayitlar.unshift(kayit);

  // 🔴 ESKALASYONLAR AYRI TUTULUR VE BUDANMAZ.
  // Genel kayit listesi son 100 ile sinirli; yogun bir gunde "bana bir
  // insan yazsin" diyen musteri listeden dusup KALICI OLARAK kayboluyordu.
  // Insana aktarilan her konusma ayri listede, cok daha genis tutulur ve
  // bekleyen sayaci panelde gorunur.
  if (kayit.insanaAktar) {
    stat.eskalasyonlar = stat.eskalasyonlar || [];
    stat.eskalasyonlar.unshift({ ...kayit, kapatildi: false });
    stat.eskalasyonToplam = (stat.eskalasyonToplam || 0) + 1;
    if (stat.eskalasyonlar.length > 500) stat.eskalasyonlar.length = 500;
  }

  // 🔴 KAYITTAKI DEGERLER ESAS ALINIR.
  // Onceki hali dogrudan k.insanaAktar okuyordu; ajan coktugunde bu alan
  // hic gelmedigi icin musteriye "insanaAktar:false" donuyordu - oysa
  // konusma gercekte insana aktarilmisti. Iki yer arasindaki bu fark,
  // widget'in "ekip donus yapacak" bilgisini gostermemesine yol aciyordu.
  cikti.push({ json: {
    cevap: govde,
    insanaAktar: kayit.insanaAktar,
    otomatik: kayit.otomatik
  }});
}

// Statik veri Postgres'te workflow satirinda durur ve gece yedegine girer.
// Sinirsiz buyumesin diye son 100 kayit tutulur.
if (stat.kayitlar.length > 100) stat.kayitlar.length = 100;
return cikti;
`;

// ---------------------------------------------------------------------
// 3) Panel - ajanin web sohbette ne dedigi
// ---------------------------------------------------------------------
const kodPanel = `
// 🔴 $env KULLANILMAZ - n8n "access to env vars denied" hatasi veriyor.
// Anahtar sunucuda, iceri aktarma sirasinda bu yer tutucunun yerine konur:
//   TOK=$(grep ^PILOT_TOKEN= .env | cut -d= -f2)
//   sed -i "s/BURAYA_PILOT_ANAHTARI/$TOK/" sohbet-workflow.json
const ANAHTAR = 'BURAYA_PILOT_ANAHTARI';

const q = $input.first().json.query || {};
const beklenen = ANAHTAR;
if (!beklenen || beklenen === 'BURAYA_PILOT' + '_ANAHTARI' || q.k !== beklenen) {
  return [{ json: { html: '<!doctype html><meta charset=utf-8><body style="font-family:system-ui;padding:2rem">' +
    '<h3>Erişim reddedildi</h3><p>Geçerli anahtar gerekli.</p></body>' } }];
}

const stat = $getWorkflowStaticData('global');

// 🔴 ESKALASYON KAPATMA.
// Once hicbir yerde 'kapatildi' true yapilmiyordu: donus yapilan musteri
// listede sonsuza kadar kaliyor, 40 satir dolduktan sonra GERCEKTEN
// bekleyen musteri altta kaliyor ve cozulmuslerden ayirt edilemiyordu.
// Panelde her satirin yanindaki baglanti buraya '?k=...&kapat=<zaman>'
// olarak geliyor; zaman damgasi ISO ve milisaniyeli oldugu icin tekil.
if (q.kapat) {
  const hedef = String(q.kapat);
  (stat.eskalasyonlar || []).forEach(e => {
    if (e && e.zaman === hedef) { e.kapatildi = true; e.kapanma = new Date().toISOString(); }
  });
}

const kayitlar = (stat.kayitlar || []).slice(0, 60);
// Insana aktarilanlar ayri, budanmayan listede - panelin EN USTUNDE gosterilir.
// Kapatilanlar listeden DUSER; sayilar ayri tutulur.
const tumEsk = stat.eskalasyonlar || [];
const eskalasyonlar = tumEsk.filter(e => !e.kapatildi).slice(0, 40);
const eskAcik = tumEsk.filter(e => !e.kapatildi).length;
const eskKapali = tumEsk.filter(e => e.kapatildi).length;
const eskToplam = stat.eskalasyonToplam || 0;
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
  '<meta http-equiv=refresh content=60>' +
  '<title>L\\'CARLIÉ · Web Sohbet</title></head>' +
  '<body style="font-family:system-ui,-apple-system,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:1rem">' +
  '<div style="background:#0f172a;color:#fff;padding:.9rem 1rem;border-radius:10px;margin-bottom:1rem">' +
  '<div style="font-size:.75rem;opacity:.8">L\\'CARLIÉ</div>' +
  '<div style="font-size:1.15rem;font-weight:700">Web Sohbet Kayıtları</div></div>' +
  // 🔴 EN USTE: insana aktarilan konusmalar. Bunlar cevap BEKLIYOR.
  (eskalasyonlar.length
    ? '<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:10px;padding:.9rem;margin-bottom:1rem">' +
      '<div style="font-weight:700;color:#92400e">⚠ Dönüş bekleyen ' + eskAcik +
      ' konuşma <span style="font-weight:400">(kapatılan ' + eskKapali +
      ' · toplam ' + eskToplam + ')</span></div>' +
      '<div style="font-size:.8rem;color:#92400e;margin-top:.2rem">' +
      'Dönüş yaptığınız konuşmayı <b>Kapat</b> ile listeden düşürün.</div>' +
      eskalasyonlar.map(r =>
        '<div style="background:#fff;border-radius:8px;padding:.6rem;margin-top:.6rem">' +
        '<div style="font-size:.76rem;color:#64748b">' + kacis(saat(r.zaman)) + ' · ' +
        kacis(r.musteri) + ' · ' + kacis(r.sinif) + '</div>' +
        '<div style="margin-top:.3rem;font-weight:600">' + kacis(r.gelen) + '</div>' +
        // 🔴 KAPAT baglantisi: anahtari da tasimali, yoksa panel erisimi reddeder.
        '<div style="margin-top:.5rem"><a href="?k=' + encodeURIComponent(q.k || '') +
        '&kapat=' + encodeURIComponent(r.zaman || '') + '" ' +
        'style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;' +
        'padding:.3rem .7rem;border-radius:6px;font-size:.78rem">Kapat</a></div>' +
        '</div>').join('') +
      '</div>'
    : (eskKapali
        ? '<div style="background:#dcfce7;border:1px solid #86efac;border-radius:10px;padding:.8rem;margin-bottom:1rem;color:#166534">' +
          '<b>Bekleyen konuşma yok.</b> ' + eskKapali + ' konuşma kapatıldı, toplam ' + eskToplam + '.</div>'
        : '')) +
  '<p style="font-size:.85rem;color:#475569">Son ' + kayitlar.length + ' konuşma. 60 saniyede bir yenilenir.</p>' +
  (kayitlar.length ? satirlar : '<p style="color:#64748b">Henüz kayıt yok.</p>') +
  '</body></html>';

return [{ json: { html } }];
`;

const kod = (ad, id, x, y, js) => ({
  parameters: { jsCode: js },
  id, name: ad, type: 'n8n-nodes-base.code', typeVersion: 2, position: [x, y]
});

const workflow = [{
  id: 'lcarlieSohbet01',
  name: 'WEB SOHBET - site canli destek',
  active: false,
  nodes: [
    {
      // 🔴 allowedOrigins: tarayicidan cagrilacagi icin CORS sart.
      //    n8n webhook v2 preflight (OPTIONS) istegini de bu ayarla karsilar.
      //
      //    '*' SECILDI cunku Wix HTML gomme kutusu sayfayi KENDI iframe
      //    origin'inden calistirir (ornek: www-lcarlie-shop.filesusr.com),
      //    lcarlie.shop'tan degil. Domain listesi yazilirsa widget calismaz.
      //    Uc nokta bu ucu zararsiz kiliyor: sir tutmuyor, veri yazmiyor,
      //    ajanin uretebilecegi her cevap mevzuat filtresinden geciyor.
      //    Yine de gomme origin'i netlesince daraltilmali (YAPILACAKLAR).
      parameters: {
        httpMethod: 'POST', path: 'sohbet', responseMode: 'responseNode',
        options: { allowedOrigins: '*' }
      },
      id: 'dddddddd-0000-4000-8000-000000000001',
      name: 'Site mesaji (POST)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 0],
      webhookId: 'dddddddd-0000-4000-8000-0000000000a1'
    },
    kod('Girisi dogrula', 'dddddddd-0000-4000-8000-000000000002', 240, 0, kodGiris),
    {
      parameters: {
        conditions: {
          options: { caseSensitive: true, leftValue: '', version: 2 },
          conditions: [{
            id: 'g1', operator: { type: 'boolean', operation: 'true', singleValue: true },
            leftValue: '={{ $json.gecerli }}', rightValue: ''
          }],
          combinator: 'and'
        },
        options: {}
      },
      id: 'dddddddd-0000-4000-8000-000000000003',
      name: 'Gecerli mi?',
      type: 'n8n-nodes-base.if', typeVersion: 2, position: [480, 0]
    },
    {
      parameters: {
        workflowId: { __rl: true, value: 'lcarlieAkis0001', mode: 'id' },
        mode: 'each',                       // 🔴 'once' birakilirsa mesaj duser
        options: { waitForSubWorkflow: true }
      },
      id: 'dddddddd-0000-4000-8000-000000000004',
      name: 'Satis ajanina sor',
      type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2, position: [720, -100],
      // 🔴 AJAN COKERSE MUSTERI BOSLUGA BAKMASIN.
      // Onceki halinde bu dugum hata verdiginde calisma orada kopuyordu:
      // 'Cevabi dondur' hic calismiyor -> musteri HTTP 500 aliyor, kayit
      // yazilmiyor, eskalasyon olusmuyor, sayac artmiyor. Mesaj HICBIR IZ
      // birakmadan kayboluyordu.
      // Canlida yasandi (13.09.2026, calisma 323): ajan alt workflow'u
      // yayinda degilken gelen musteri mesaji kayboldu.
      // 'continueRegularOutput' ogeye 'error' alani ekleyip akisi surdurur;
      // 'Cevabi hazirla' bunu gorup notr cevap verir ve INSANA AKTARIR.
      onError: 'continueRegularOutput',
      retryOnFail: true, maxTries: 2, waitBetweenTries: 1000
    },
    kod('Cevabi hazirla', 'dddddddd-0000-4000-8000-000000000005', 960, -100, kodCevap),
    {
      parameters: {
        respondWith: 'json',
        responseBody: '={{ JSON.stringify($json) }}',
        options: {}
      },
      id: 'dddddddd-0000-4000-8000-000000000006',
      name: 'Cevabi dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [1200, -100]
    },
    {
      parameters: {
        respondWith: 'json',
        // Hiz sinirinda farkli mesaj - musteri "sistem bozuk" sanmasin.
        responseBody: '={{ JSON.stringify({ cevap: $json.hizSiniri' +
          ' ? "Çok sayıda mesaj aldık, birkaç dakika sonra tekrar yazabilirsiniz. Bu arada ürünlerimiz: https://lcarlie.shop"' +
          ' : "Mesajınızı alamadık, tekrar yazar mısınız?", insanaAktar: false }) }}',
        options: {}
      },
      id: 'dddddddd-0000-4000-8000-000000000007',
      name: 'Gecersiz istek',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [720, 140]
    },

    // --- Panel ---
    {
      parameters: { httpMethod: 'GET', path: 'sohbet-panel', responseMode: 'responseNode', options: {} },
      id: 'dddddddd-0000-4000-8000-000000000008',
      name: 'Panel (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 420],
      webhookId: 'dddddddd-0000-4000-8000-0000000000a2'
    },
    kod('Panel HTML', 'dddddddd-0000-4000-8000-000000000009', 240, 420, kodPanel),
    {
      parameters: { respondWith: 'text', responseBody: '={{ $json.html }}',
        options: { responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/html; charset=utf-8' }] } } },
      id: 'dddddddd-0000-4000-8000-00000000000a',
      name: 'Paneli dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [480, 420]
    }
  ],
  connections: {
    'Site mesaji (POST)': { main: [[{ node: 'Girisi dogrula', type: 'main', index: 0 }]] },
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

fs.writeFileSync('/tmp/sohbet-workflow.json', JSON.stringify(workflow, null, 2), 'utf8');
console.log('Yazildi. Node sayisi: ' + workflow[0].nodes.length);
