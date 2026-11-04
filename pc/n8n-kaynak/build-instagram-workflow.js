// =============================================================================
// INSTAGRAM KANALI - DM
//
// Uretildi: yeni-kanal.js · 13.09.2026
// Workflow ID: lcarlieInsta01
//
// Satis ajani (lcarlieAkis0001) KANAL BAGIMSIZ - bu dosya sadece giris kapisi.
// Mevzuat filtresi ve urun bilgi tabani ajan tarafinda, burada TEKRARLANMAZ.
//
//   POST /webhook/instagram         { mesaj, musteriId } -> { cevap, insanaAktar }
//   GET  /webhook/instagram-panel?k=PILOT_TOKEN
// =============================================================================
const fs = require('fs');

// CR-002: ortak hata kaydi yardimcilari koda GOMULUR (n8n'de require yok).
let hataKaydiHam = fs.readFileSync('/tmp/hata-kaydi.js', 'utf8');
hataKaydiHam = hataKaydiHam.replace(/if \(typeof module[\s\S]*$/m, '').trimEnd();

// CR-002.5: trafik siniflandirma (test/production/unknown) yardimcilari.
let kimlikHam = fs.readFileSync('/tmp/kimlik.js', 'utf8');
kimlikHam = kimlikHam.replace(/if \(typeof module[\s\S]*$/m, '').trimEnd();

const ORTAK = kimlikHam + '\n\n' + hataKaydiHam;

// -----------------------------------------------------------------------------
// 1) Gelen istegi dogrula + hiz siniri
// -----------------------------------------------------------------------------
const kodGiris = ORTAK + `

// ===== n8n: giris dogrulama =====

// 🔴 HIZ SINIRI
//
// ⚠️ BURADA IP SINIRI YOK - BILEREK.
//    Site sohbetinde IP katmani var, cunku orada istek dogrudan
//    musterinin tarayicisindan gelir ve musteriId uydurulabilir.
//    Burada ise TUM istekler Meta'nin birkac IP'sinden gelir; IP'ye
//    sinir koymak reklam donen bir gunde GERCEK musterileri bogar.
//    Kimlik (musteriId) Meta'nin verdigi gonderen kimligidir.
//
// 🔴 Global sinir 400 -> 1000. 400, tek bir reklam patlamasinda
//    dolabilecek kadar dusuktu; dolunca kanal bir saat sessizlesir,
//    reklam parasi harcanip mesajlar cevapsiz kalirdi.
const KISI_LIMIT = 20, KISI_PENCERE = 10 * 60 * 1000;
const TOPLAM_LIMIT = 1000, TOPLAM_PENCERE = 60 * 60 * 1000;

const stat = $getWorkflowStaticData('global');
stat.hiz = stat.hiz || {};
stat.toplam = stat.toplam || [];
const simdi = Date.now();

stat.toplam = stat.toplam.filter(t => simdi - t < TOPLAM_PENCERE);
for (const k of Object.keys(stat.hiz)) {
  stat.hiz[k] = stat.hiz[k].filter(t => simdi - t < KISI_PENCERE);
  if (!stat.hiz[k].length) delete stat.hiz[k];
}

const cikti = [];
// 🔴 all() - first() DEGIL. first() kullanilirsa diger musterilerin
//    mesajlari HATA VERMEDEN duser. Bu projede uc kez yasandi.
for (const item of $input.all()) {
  const b = item.json.body || item.json || {};
  const mesaj = String(b.mesaj ?? '').trim();
  const musteriId = String(b.musteriId ?? '').trim() || 'instagram-anonim';

  // 🔴 KORELASYON KIMLIGI (CR-002 madde 2).
  // Her istege burada bir izleme kimligi verilir. Ajan cokerse
  // 'continueRegularOutput' giris ogesini GECIRMEDIGI icin musteriId dahil
  // her sey kaybolur; hata kaydinin hangi istege ait oldugunu ancak bu
  // kimlik ve sira numarasi soyler. PII icermez.
  const korelasyon = korelasyonUret('ig');

  // 🔴 TRAFIK SINIFI GIRISTE, BIR KEZ BELIRLENIR (CR-002.5 madde A).
  // Kayit yazildiktan SONRA regex ile tahmin etmek yerine, kaynakta
  // deterministik olarak karara baglanir ve kayda islenir. Boylece
  // yeni bir test adi bulundugunda hicbir desen guncellemesi gerekmez.
  // Govdedeki 'is_test' BILEREK okunmaz - bkz. kimlik.js aciklamasi.
  const trafik = trafikSinifi(musteriId);

  if (!mesaj) { cikti.push({ json: { gecerli: false, hata: 'mesaj bos', musteriId, korelasyon, trafik } }); continue; }
  if (mesaj.length > 1000) { cikti.push({ json: { gecerli: false, hata: 'cok uzun', musteriId, korelasyon, trafik } }); continue; }

  stat.hiz[musteriId] = stat.hiz[musteriId] || [];
  if (stat.hiz[musteriId].length >= KISI_LIMIT) {
    cikti.push({ json: { gecerli: false, musteriId, korelasyon, trafik, hizSiniri: true } }); continue;
  }
  if (stat.toplam.length >= TOPLAM_LIMIT) {
    cikti.push({ json: { gecerli: false, musteriId, korelasyon, trafik, hizSiniri: true } }); continue;
  }

  stat.hiz[musteriId].push(simdi);
  stat.toplam.push(simdi);
  cikti.push({ json: { gecerli: true, mesaj, musteriId, korelasyon, trafik, kanal: 'instagram' } });
}
return cikti;
`;

// -----------------------------------------------------------------------------
// 2) Ajan kararini cevaba cevir + kaydet
// -----------------------------------------------------------------------------
const kodCevap = ORTAK + `

// ===== n8n: ajan kararini cevaba cevir =====
const stat = $getWorkflowStaticData('global');
stat.kayitlar = stat.kayitlar || [];

const VARSAYILAN =
  'Mesajınız için teşekkür ederiz. Bu konuda size en doğru bilgiyi ' +
  'ekip arkadaşımız verecek, en kısa sürede dönüş yapacağız. ' +
  'Bu arada tüm ürünlerimizi inceleyebilirsiniz: https://lcarlie.shop';

// 🔴 AJAN COKERSE MUSTERI KIMLIGI KAYBOLUYOR (CR-002 madde 2).
// 'continueRegularOutput' giris ogesini GECIRMIYOR - yalnizca hata bilgisi
// iceren bir oge uretiyor. Web sohbetinde canli testte kayit
// 'musteri=-  gelen=-' olarak yazilmisti: konusma insana aktarildi ama
// KIMIN yazdigi kayitta yok, yani donus yapilamaz.
// Kimligi bir onceki dugumden, SIRA NUMARASIYLA aliyoruz.
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
  // Musteri yine notr bir cevap alir AMA konusma MUTLAKA insana aktarilir.
  const ajanCokti = Boolean(k.error) || (!k.sinif && !k.cevap && !k.gonder);

  if (ajanCokti) {
    // 🔴 PII YAZILMAZ: mesaj metni ve musteri kimligi hata kaydina girmez.
    hataKaydet(stat, {
      workflow_id: $workflow.id,
      execution_id: $execution.id,
      channel: 'instagram',
      stage: 'ajan',
      error_class: hataSinifi(k.error),
      error_summary: hataOzeti(k.error),
      correlation_id: onceki.korelasyon || k.korelasyon || '-'
    });
  }

  const govde = (k.gonder && k.cevap && !ajanCokti) ? k.cevap : VARSAYILAN;

  const kayit = {
    zaman: new Date().toISOString(),
    // Ajan coktuyse kimlik ve mesaj bir onceki dugumden alinir.
    musteri: k.musteriId || onceki.musteriId || '-',
    sinif: ajanCokti ? 'AJAN-HATASI' : (k.sinif || '-'),
    gelen: k.gelenMesaj || k.mesaj || onceki.mesaj || '-',
    cevap: govde,
    otomatik: Boolean(k.gonder && k.cevap && !ajanCokti),
    // Coktuyse HER ZAMAN insana aktarilir - yoksa mesaj sessizce kaybolur.
    insanaAktar: ajanCokti ? true : Boolean(k.insanaAktar),
    korelasyon: onceki.korelasyon || k.korelasyon || '-',
    // 🔴 SINIF GIRISTEN TASINIR, burada yeniden hesaplanmaz.
    // Ajan coktugunde 'k' bos gelir; girisde belirlenmis sinif
    // 'Gecerli mi?' dugumunden sira numarasiyla alinir. Boylece hata
    // yolunda bile kayit dogru siniflanir.
    traffic_class: onceki.trafik || k.trafik || trafikSinifi(k.musteriId || onceki.musteriId)
  };
  stat.kayitlar.unshift(kayit);

  // 🔴 ESKALASYONLAR AYRI TUTULUR VE BUDANMAZ.
  // Bu duzeltme once YALNIZ web sohbetine uygulanmisti; Instagram'da
  // insana aktarilan DM, 100 kayitlik genel listenin sonuna dusup
  // KALICI OLARAK kayboluyordu. Reklam donen bir gunde 100 mesaj birkac
  // saatte doluyor. Canlida dogrulandi: lcarlieInsta01 statik verisinde
  // 'eskalasyonlar' anahtari hic yoktu.
  if (kayit.insanaAktar) {
    stat.eskalasyonlar = stat.eskalasyonlar || [];
    stat.eskalasyonlar.unshift({ ...kayit, kapatildi: false });
    stat.eskalasyonToplam = (stat.eskalasyonToplam || 0) + 1;
    if (stat.eskalasyonlar.length > 500) stat.eskalasyonlar.length = 500;
  }

  // 🔴 KAYITTAKI DEGERLER ESAS ALINIR.
  // Dogrudan k.insanaAktar okunursa, ajan coktugunde bu alan hic gelmedigi
  // icin musteriye "insanaAktar:false" doner - oysa konusma gercekte insana
  // aktarilmistir. Iki yer arasindaki fark musteriye yanlis bilgi verir.
  cikti.push({ json: {
    cevap: govde,
    insanaAktar: kayit.insanaAktar,
    otomatik: kayit.otomatik
  }});
}
if (stat.kayitlar.length > 100) stat.kayitlar.length = 100;
return cikti;
`;

// -----------------------------------------------------------------------------
// 3) Panel
// -----------------------------------------------------------------------------
const kodPanel = `
// 🔴 $env KULLANILMAZ - n8n "access to env vars denied" hatasi verir.
// Anahtar, yayinlama hatti tarafindan bu yer tutucunun yerine konur.
const ANAHTAR = 'BURAYA_PILOT_ANAHTARI';

const q = $input.first().json.query || {};
if (!ANAHTAR || q.k !== ANAHTAR) {
  return [{ json: { html: '<!doctype html><meta charset=utf-8><body style="font-family:system-ui;padding:2rem">' +
    '<h3>Erişim reddedildi</h3></body>' } }];
}

const stat = $getWorkflowStaticData('global');

// 🔴 ESKALASYON KAPATMA - web sohbet paneliyle ayni mantik.
if (q.kapat) {
  const hedef = String(q.kapat);
  (stat.eskalasyonlar || []).forEach(e => {
    if (e && e.zaman === hedef) { e.kapatildi = true; e.kapanma = new Date().toISOString(); }
  });
}

const kayitlar = (stat.kayitlar || []).slice(0, 60);
// 🔴 Bu panel eskalasyonlari HIC gostermiyordu: insana aktarilan bir DM
// 100 kayitlik listede eriyip kayboluyordu ve paneli acan kisi bekleyen
// musteri oldugunu anlamiyordu.
const tumEsk = stat.eskalasyonlar || [];
const acikEsk = tumEsk.filter(e => !e.kapatildi);
const eskKapali = tumEsk.length - acikEsk.length;
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
  '<meta http-equiv=refresh content=60><title>INSTAGRAM KANALI - DM</title></head>' +
  '<body style="font-family:system-ui,-apple-system,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:1rem">' +
  '<div style="background:#0f172a;color:#fff;padding:.9rem 1rem;border-radius:10px;margin-bottom:1rem">' +
  '<div style="font-size:1.15rem;font-weight:700">INSTAGRAM KANALI - DM</div></div>' +
  (acikEsk.length
    ? '<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:10px;padding:.9rem;margin-bottom:1rem">' +
      '<div style="font-weight:700;color:#92400e">⚠ Dönüş bekleyen ' + acikEsk.length +
      ' konuşma <span style="font-weight:400">(kapatılan ' + eskKapali +
      ' · toplam ' + eskToplam + ')</span></div>' +
      acikEsk.slice(0, 40).map(r =>
        '<div style="background:#fff;border-radius:8px;padding:.6rem;margin-top:.6rem">' +
        '<div style="font-size:.76rem;color:#64748b">' + kacis(saat(r.zaman)) + ' · ' +
        kacis(r.musteri) + ' · ' + kacis(r.sinif) + '</div>' +
        '<div style="margin-top:.3rem;font-weight:600">' + kacis(r.gelen) + '</div>' +
        '<div style="margin-top:.5rem"><a href="?k=' + encodeURIComponent(q.k || '') +
        '&kapat=' + encodeURIComponent(r.zaman || '') + '" ' +
        'style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;' +
        'padding:.3rem .7rem;border-radius:6px;font-size:.78rem">Kapat</a></div>' +
        '</div>').join('') +
      '</div>'
    : '') +
  '<p style="font-size:.85rem;color:#475569">Son ' + kayitlar.length + ' konuşma.</p>' +
  (kayitlar.length ? satirlar : '<p style="color:#64748b">Henüz kayıt yok.</p>') +
  '</body></html>';

return [{ json: { html } }];
`;

const kod = (ad, id, x, y, js) => ({
  parameters: { jsCode: js },
  id, name: ad, type: 'n8n-nodes-base.code', typeVersion: 2, position: [x, y]
});

const workflow = [{
  id: 'lcarlieInsta01',
  name: 'INSTAGRAM KANALI - DM',
  active: false,
  nodes: [
    {
      parameters: {
        httpMethod: 'POST', path: 'instagram', responseMode: 'responseNode',
        options: { allowedOrigins: '*' }
      },
      id: '6c636172-0000-4000-8000-000000000001',
      name: 'Gelen mesaj (POST)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 0],
      webhookId: '6c636172-0000-4000-8000-000000000101'
    },
    kod('Girisi dogrula', '6c636172-0000-4000-8000-000000000002', 240, 0, kodGiris),
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
      id: '6c636172-0000-4000-8000-000000000003',
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
      id: '6c636172-0000-4000-8000-000000000004',
      name: 'Satis ajanina sor',
      type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2, position: [720, -100],
      // 🔴 HATA YOLU (CR-002 madde 2).
      // Onceki halinde bu dugum hata verdiginde calisma orada kopuyordu:
      // 'Cevabi dondur' hic calismiyor -> musteri HTTP 500 aliyor, kayit
      // yazilmiyor, eskalasyon olusmuyor, sayac artmiyor. Mesaj HICBIR IZ
      // birakmadan kayboluyordu.
      // Ayni duzeltme 15.09'da YALNIZCA web sohbetine uygulanmisti - ve o
      // workflow ayni gun devre disi birakildi. Yani koruma, kullanilmayan
      // tek yerde duruyordu; yayindaki iki kanal korumasizdi (CR-001 bulgusu).
      //
      // 🔴 RETRY MUSTERIYE IKI CEVAP GONDERMEZ:
      //    lcarlieAkis0001 saf bir karar fonksiyonudur - statik veri YAZMAZ
      //    (CR-001'de dogrulandi: staticData bos). Gonderim de bu kanalda
      //    hic yok. Bu yuzden yeniden deneme yan etkisizdir.
      onError: 'continueRegularOutput',
      retryOnFail: true, maxTries: 2, waitBetweenTries: 1000
    },
    kod('Cevabi hazirla', '6c636172-0000-4000-8000-000000000005', 960, -100, kodCevap),
    {
      parameters: { respondWith: 'json', responseBody: '={{ JSON.stringify($json) }}', options: {} },
      id: '6c636172-0000-4000-8000-000000000006',
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
      id: '6c636172-0000-4000-8000-000000000007',
      name: 'Gecersiz istek',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [720, 140]
    },
    {
      parameters: { httpMethod: 'GET', path: 'instagram-panel', responseMode: 'responseNode', options: {} },
      id: '6c636172-0000-4000-8000-000000000008',
      name: 'Panel (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 420],
      webhookId: '6c636172-0000-4000-8000-000000000102'
    },
    kod('Panel HTML', '6c636172-0000-4000-8000-000000000009', 240, 420, kodPanel),
    {
      parameters: { respondWith: 'text', responseBody: '={{ $json.html }}',
        options: { responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/html; charset=utf-8' }] } } },
      id: '6c636172-0000-4000-8000-000000000010',
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

fs.writeFileSync('/tmp/instagram-workflow.json', JSON.stringify(workflow, null, 2), 'utf8');
console.log('Yazildi. Node sayisi: ' + workflow[0].nodes.length);
