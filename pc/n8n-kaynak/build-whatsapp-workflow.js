const fs = require('fs');

// CR-002: ortak hata kaydi yardimcilari koda GOMULUR (n8n'de require yok).
let hataKaydiHam = fs.readFileSync('/tmp/hata-kaydi.js', 'utf8');
hataKaydiHam = hataKaydiHam.replace(/if \(typeof module[\s\S]*$/m, '').trimEnd();

// CR-002.5: trafik siniflandirma (test/production/unknown) yardimcilari.
let kimlikHam = fs.readFileSync('/tmp/kimlik.js', 'utf8');
kimlikHam = kimlikHam.replace(/if \(typeof module[\s\S]*$/m, '').trimEnd();

const ORTAK = kimlikHam + '\n\n' + hataKaydiHam;

// ---------------------------------------------------------------------
// 1) META WEBHOOK DOGRULAMASI (GET)
// Meta, webhook'u kaydederken GET ile gelir ve hub.challenge bekler.
// ---------------------------------------------------------------------
// 🔴 DOGRULAMA ANAHTARI URETIM ANINDA GOMULUR, KAYNAKTA DURMAZ.
//
//    n8n'de `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` -- Code dugumu ortam
//    degiskeni OKUYAMAZ, yani anahtar calisma aninda alinamaz. Tek
//    secenek uretim aninda gommek.
//
//    🔴 OLCULEN HATA (26.09.2026): CANLI workflow'da bu deger HALA
//    'BURAYA_META_DOGRULAMA_ANAHTARI' placeholder'iydi. Yani bu kanalin
//    Meta dogrulamasi hicbir zaman tamamlanamazdi; kanal "aktif"
//    gorunurken ise yaramaz durumdaydi. Sayfanin `subscribed_apps`
//    listesinin bos olmasi da bununla tutarli -- hicbir kanal icin el
//    sikisma bitirilmemis.
//
//    Bu yuzden burada varsayilan YOK: anahtar verilmezse uretici PATLAR.
//    Sessizce bozuk bir workflow uretmekten iyidir.
const DOGRULAMA = process.env.WHATSAPP_VERIFY_TOKEN || '';
if (!DOGRULAMA) {
  console.error('HATA: WHATSAPP_VERIFY_TOKEN verilmedi.');
  console.error('Okumak icin: grep WHATSAPP_VERIFY_TOKEN /opt/lcarlie/n8n/.env');
  console.error('Yayin hatti bunu .env den okuyup docker exec -e ile gecirir.');
  process.exit(1);
}

const kodDogrula = `
// Meta webhook dogrulama. Anahtar uretim aninda gomuldu (bkz. uretici).
const DOGRULAMA_ANAHTARI = ${JSON.stringify(DOGRULAMA)};

const q = $input.first().json.query || {};
const mod  = q['hub.mode'];
const tok  = q['hub.verify_token'];
const chal = q['hub.challenge'];

if (mod === 'subscribe' && tok === DOGRULAMA_ANAHTARI) {
  // Meta sadece challenge degerini duz metin bekler
  return [{ json: { dogrulandi: true, cevap: String(chal ?? '') } }];
}
return [{ json: { dogrulandi: false, cevap: 'dogrulama basarisiz' } }];
`;

// ---------------------------------------------------------------------
// 2) GELEN MESAJLARI AYIKLA (POST)
// Meta tek webhook cagrisinda BIRDEN COK mesaj gonderebilir.
// Her mesaj AYRI item olarak cikarilir - ajan tek mesaj varsayiyor.
// ---------------------------------------------------------------------
const kodAyikla = ORTAK + `

// ===== n8n: Meta payload'ini ayikla =====

// Meta WhatsApp Cloud API payload -> ajanin bekledigi sade yapi
const cikti = [];

// 🔴 TEKRAR GONDERIM KORUMASI (idempotency).
//
// Meta, 200 alamazsa AYNI mesaji yeniden gonderir. 'mesajId' ayikla-
// niyordu ama hicbir yerde saklanmiyor ve karsilastirilmiyordu. Gonderim
// acildigi anda bir zaman asimi tekrari, ajani tekrar calistirip
// MUSTERIYE AYNI CEVABI IKI KEZ gonderirdi.
//
// Her mesaj kimligi bir kez islenir. Webhook 'onReceived' oldugu icin
// Meta'ya 200 zaten hemen doner; yani tekrar yalnizca agi kaybettigimizde
// gelir ve o durumda mesaji bir kez islemis olmak dogru davranistir.
//
// Eszamanlilik 1 oldugu icin bu kontrol yarissizdir (bkz. docker-compose
// icindeki N8N_CONCURRENCY_PRODUCTION_LIMIT aciklamasi).
const sd = $getWorkflowStaticData('global');
if (!Array.isArray(sd.islenenMesajlar)) sd.islenenMesajlar = [];
let tekrarSayisi = 0;

for (const item of $input.all()) {
  const govde = item.json.body ?? item.json;
  for (const giris of (govde.entry ?? [])) {
    for (const degisim of (giris.changes ?? [])) {
      const d = degisim.value ?? {};
      const rehber = {};
      for (const k of (d.contacts ?? [])) rehber[k.wa_id] = k.profile?.name;

      for (const m of (d.messages ?? [])) {
        // Bu mesaj daha once islendiyse ATLA - musteriye ikinci kez cevap gitmez.
        if (m.id && sd.islenenMesajlar.indexOf(m.id) !== -1) {
          tekrarSayisi++;
          continue;
        }
        if (m.id) {
          sd.islenenMesajlar.unshift(m.id);
          if (sd.islenenMesajlar.length > 2000) sd.islenenMesajlar.length = 2000;
        }

        // Sadece metin mesajlarini isle. Gorsel/ses/konum insana gider.
        const metin = m.text?.body
          ?? m.button?.text
          ?? m.interactive?.button_reply?.title
          ?? m.interactive?.list_reply?.title
          ?? null;

        cikti.push({
          json: {
            mesaj: metin ?? '',
            musteriId: m.from,
            musteriAdi: rehber[m.from] ?? null,
            kanal: 'whatsapp',
            // 🔴 KORELASYON KIMLIGI (CR-002 madde 2).
            // Ajan cokerse 'continueRegularOutput' giris ogesini gecirmez;
            // hata kaydinin hangi istege ait oldugunu bu kimlik soyler.
            // 🔴 wamid KULLANILMAZ - o bir PII tasiyicisi sayilir ve hata
            //    kaydina girmemelidir. Korelasyon kimligi bagimsiz uretilir.
            korelasyon: korelasyonUret('wa'),
            // 🔴 TRAFIK SINIFI GIRISTE BELIRLENIR (CR-002.5 madde A).
            // Kaynakta bir kez karara baglanir; sonradan regex ile tahmin
            // edilmez. Yeni bir test adi hicbir desen guncellemesi
            // gerektirmez. 'm.from' Meta'nin verdigi gonderen kimligidir.
            trafik: trafikSinifi(m.from),
            mesajId: m.id,
            mesajTipi: m.type,
            metinMi: Boolean(metin),
            telefonNoId: d.metadata?.phone_number_id ?? null,
            zaman: m.timestamp
          }
        });
      }
    }
  }
}

// Tekrar gelen mesajlari say - panelde gorunur, sessizce yutulmaz.
if (tekrarSayisi > 0) {
  sd.tekrarEdilenMesaj = (sd.tekrarEdilenMesaj || 0) + tekrarSayisi;
}

// Hic mesaj yoksa (durum bildirimi vb.) bos don - akis durur
return cikti;
`;

// ---------------------------------------------------------------------
// 3) GONDERILECEK YANITI HAZIRLA
// ---------------------------------------------------------------------
// 🔴 ORTAK KOD BU DUGUME DE GOMULMELI.
// Bu dugum trafikSinifi() cagiriyor. Gomulmezse fonksiyon SESSIZCE
// undefined kalir ve dugum calisma aninda coker - bu projede ayni tuzak
// daha once yasandi (yeni yardimci eklenip gomme satiri unutulmustu).
const kodYanit = ORTAK + `

// ===== n8n: gonderilecek yaniti hazirla =====
// 🔴 first() DEGIL all(): alt-workflow 'each' modunda calistigi icin buraya
// BIRDEN COK karar gelir. first() kullanilirsa diger musterilerin cevaplari
// sessizce duser (test ederken yakalandi).
// Isletmenin WhatsApp numara kimligi - gelen payload'dan alinir, sabit degil.
const telefonNoId = $('Mesajlari ayikla').first().json.telefonNoId;

// 🔴 AJAN COKERSE KIMLIK VE KORELASYON KAYBOLUR (CR-002 madde 2).
// 'continueRegularOutput' giris ogesini gecirmez. Bir onceki dugumden
// SIRA NUMARASIYLA geri aliyoruz - Instagram ve web sohbetiyle ayni desen.
let oncekiler = [];
try { oncekiler = $('Metin mi?').all(); } catch (e) { oncekiler = []; }

const hepsi = $input.all();
return hepsi.map((item, i) => {
const karar = item.json;
const onceki = (oncekiler[i] && oncekiler[i].json) || {};

// 🔴 AJAN COKTU MU? Coktuyse mesaj ASLA sessizce dusmez:
//    gonderim yapilmaz, kayit yazilir, konusma insana aktarilir.
const ajanCokti = Boolean(karar && karar.error) ||
                  (!karar.sinif && !karar.cevap && !karar.gonder);

if (ajanCokti) {
  return {
    json: {
      gonderilecek: false,
      ajanCokti: true,
      hataHam: karar.error || null,
      sebep: 'AJAN-HATASI',
      insanaAktar: true,
      musteriId: onceki.musteriId || karar.musteriId || '-',
      korelasyon: onceki.korelasyon || '-',
      trafik: onceki.trafik || trafikSinifi(onceki.musteriId),
      kayit: null
    }
  };
}

// Ajan gondermeyecekse veya metin yoksa: gonderme, insana birak
if (!karar.gonder || !karar.cevap) {
  return {
    json: {
      gonderilecek: false,
      sebep: (karar.gerekceler || []).join(' | '),
      insanaAktar: karar.insanaAktar,
      musteriId: karar.musteriId || onceki.musteriId,
      korelasyon: onceki.korelasyon || '-',
      trafik: onceki.trafik || trafikSinifi(onceki.musteriId),
      kayit: karar.kayit
    }
  };
}

return {
  json: {
    gonderilecek: true,
    telefonNoId,
    musteriId: karar.musteriId,
    korelasyon: onceki.korelasyon || '-',
    trafik: onceki.trafik || trafikSinifi(onceki.musteriId),
    // Meta Graph API govdesi
    govde: {
      messaging_product: 'whatsapp',
      recipient_type: 'individual',
      to: karar.musteriId,
      type: 'text',
      text: { preview_url: true, body: karar.cevap }
    },
    insanaAktar: karar.insanaAktar,
    kayit: karar.kayit
  }
};
});
`;

// ---------------------------------------------------------------------
// 4) PILOT KAYDI - her karar kalici olarak saklanir (son 60 adet)
// n8n'in workflow static data'si kullaniliyor; ek veritabani/kimlik gerekmiyor.
// ---------------------------------------------------------------------
const kodPilotKayit = ORTAK + `

// ===== n8n: pilot kaydi =====
const sd = $getWorkflowStaticData('global');
if (!Array.isArray(sd.pilot)) sd.pilot = [];

for (const item of $input.all()) {
  const j = item.json;
  const k = j.kayit || {};

  // 🔴 AJAN HATASI OPERASYONEL KAYDA GECER (CR-002 madde 2).
  // PII yazilmaz: musteri kimligi ve mesaj metni hata kaydina GIRMEZ,
  // yalnizca korelasyon kimligi tutulur. Konusma kaydi ayri (sd.pilot).
  if (j.ajanCokti) {
    hataKaydet(sd, {
      workflow_id: $workflow.id,
      execution_id: $execution.id,
      channel: 'whatsapp',
      stage: 'ajan',
      error_class: hataSinifi(j.hataHam),
      error_summary: hataOzeti(j.hataHam),
      correlation_id: j.korelasyon || '-'
    });
  }

  const kayit = {
    zaman: k.zaman || new Date().toISOString(),
    musteri: k.musteriId || j.musteriId || '-',
    gelen: k.gelenMesaj || '-',
    sinif: j.ajanCokti ? 'AJAN-HATASI' : (k.sinif || '-'),
    gonderildi: Boolean(j.gonderilecek),
    cevap: j.govde?.text?.body || k.gonderilenCevap || null,
    // 🔴 Ajan coktuyse HER ZAMAN insana aktarilir.
    insanaAktar: j.ajanCokti ? true : Boolean(j.insanaAktar),
    sebep: j.sebep || (k.gerekceler || []).join(' | '),
    korelasyon: j.korelasyon || '-',
    // 🔴 Sinif giristen tasinir, burada yeniden hesaplanmaz (CR-002.5).
    traffic_class: j.trafik || trafikSinifi(k.musteriId || j.musteriId)
  };
  sd.pilot.unshift(kayit);

  // 🔴 ESKALASYONLAR AYRI TUTULUR VE BUDANMAZ.
  // Bu duzeltme once yalnizca web sohbetine, sonra Instagram'a uygulandi;
  // WhatsApp farkli bir yapi (sd.pilot, 60 kayit) kullandigi icin
  // atlanmisti. Insana aktarilan bir WhatsApp mesaji 60 mesaj sonra
  // listeden dusup KALICI OLARAK kayboluyordu - ve WhatsApp gonderimi
  // acildiginda hacim web sohbetinden yuksek olacak.
  if (kayit.insanaAktar) {
    if (!Array.isArray(sd.eskalasyonlar)) sd.eskalasyonlar = [];
    sd.eskalasyonlar.unshift({ ...kayit, kapatildi: false });
    sd.eskalasyonToplam = (sd.eskalasyonToplam || 0) + 1;
    if (sd.eskalasyonlar.length > 500) sd.eskalasyonlar.length = 500;
  }
}
sd.pilot = sd.pilot.slice(0, 60);   // sinirsiz buyumesin
return $input.all();
`;

// ---------------------------------------------------------------------
// 5) PILOT PANELI - tarayicidan okunabilir sayfa
// ---------------------------------------------------------------------
const kodPilotPanel = `
// 🔴 Erisim anahtari. .env icindeki PILOT_TOKEN ile ayni olmali.
const ANAHTAR = 'BURAYA_PILOT_ANAHTARI';

const q = $input.first().json.query || {};
if (q.k !== ANAHTAR) {
  return [{ json: { html: '<!doctype html><meta charset="utf-8">' +
    '<body style="font-family:system-ui;padding:2rem">Erişim anahtarı geçersiz.</body>' } }];
}

const sd = $getWorkflowStaticData('global');

// 🔴 ESKALASYON KAPATMA - web sohbet paneliyle ayni mantik.
const q2 = $input.first().json.query || {};
if (q2.kapat) {
  const hedef2 = String(q2.kapat);
  (sd.eskalasyonlar || []).forEach(e => {
    if (e && e.zaman === hedef2) { e.kapatildi = true; e.kapanma = new Date().toISOString(); }
  });
}

const kayitlar = Array.isArray(sd.pilot) ? sd.pilot : [];
const tumEsk = Array.isArray(sd.eskalasyonlar) ? sd.eskalasyonlar : [];
const acikEsk = tumEsk.filter(e => !e.kapatildi);
const eskKapali = tumEsk.length - acikEsk.length;
const eskToplam = sd.eskalasyonToplam || 0;
const tekrarEdilen = sd.tekrarEdilenMesaj || 0;

const kacis = (s) => String(s ?? '')
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

const saat = (iso) => {
  try {
    return new Date(iso).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul' });
  } catch (e) { return iso; }
};

const satirlar = kayitlar.map(function (r) {
  const durum = r.gonderildi
    ? '<span style="color:#16a34a;font-weight:600">GÖNDERİLECEK</span>'
    : '<span style="color:#dc2626;font-weight:600">GÖNDERİLMEZ</span>';
  const insan = r.insanaAktar
    ? ' <span style="color:#d97706">· insana aktarıldı</span>' : '';
  const cevap = r.cevap
    ? '<div style="background:#f1f5f9;padding:.6rem .8rem;border-radius:6px;margin-top:.5rem;white-space:pre-wrap">' + kacis(r.cevap) + '</div>'
    : '<div style="color:#64748b;margin-top:.5rem">(cevap üretilmedi)</div>';
  return '<div style="border:1px solid #e2e8f0;border-radius:10px;padding:1rem;margin-bottom:1rem;background:#fff">' +
    '<div style="font-size:.8rem;color:#64748b">' + kacis(saat(r.zaman)) + ' · ' + kacis(r.musteri) + ' · ' + kacis(r.sinif) + '</div>' +
    '<div style="font-weight:600;margin-top:.4rem">' + kacis(r.gelen) + '</div>' +
    cevap +
    '<div style="font-size:.8rem;margin-top:.6rem">' + durum + insan + '</div>' +
    (r.sebep ? '<div style="font-size:.75rem;color:#64748b;margin-top:.3rem">' + kacis(r.sebep) + '</div>' : '') +
    '</div>';
}).join('');

const html = '<!doctype html><html lang="tr"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>L\\'CARLIÉ · Pilot Paneli</title></head>' +
  '<body style="font-family:system-ui,-apple-system,sans-serif;background:#f8fafc;margin:0;padding:1rem;color:#0f172a">' +
  '<h1 style="font-size:1.1rem;margin:.5rem 0">L\\'CARLIÉ · Pilot Paneli</h1>' +
  '<p style="font-size:.85rem;color:#64748b;margin:0 0 1rem">' +
  'Gönderim kapalı. Ajanın <b>ne cevap vereceği</b> burada görünür. Son ' + kayitlar.length + ' karar.</p>' +
  // 🔴 EN USTE: donus bekleyen konusmalar. Kayit listesi 60 ile sinirli,
  // bunlar ayri ve budanmayan listede tutuluyor.
  (acikEsk.length
    ? '<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:10px;padding:.9rem;margin-bottom:1rem">' +
      '<div style="font-weight:700;color:#92400e">⚠ Dönüş bekleyen ' + acikEsk.length +
      ' konuşma <span style="font-weight:400">(kapatılan ' + eskKapali +
      ' · toplam ' + eskToplam + ')</span></div>' +
      acikEsk.slice(0, 40).map(function (r) {
        return '<div style="background:#fff;border-radius:8px;padding:.6rem;margin-top:.6rem">' +
          '<div style="font-size:.76rem;color:#64748b">' + kacis(saat(r.zaman)) + ' · ' +
          kacis(r.musteri) + ' · ' + kacis(r.sinif) + '</div>' +
          '<div style="margin-top:.3rem;font-weight:600">' + kacis(r.gelen) + '</div>' +
          '<div style="margin-top:.5rem"><a href="?k=' + encodeURIComponent(q2.k || '') +
          '&kapat=' + encodeURIComponent(r.zaman || '') + '" ' +
          'style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;' +
          'padding:.3rem .7rem;border-radius:6px;font-size:.78rem">Kapat</a></div>' +
          '</div>';
      }).join('') +
      '</div>'
    : '') +
  // Tekrar gelen (Meta'nin yeniden gonderdigi) mesaj sayisi - sessiz kalmasin
  (tekrarEdilen
    ? '<p style="font-size:.8rem;color:#64748b">Meta tarafından tekrar gönderilip ' +
      '<b>yeniden cevaplanmayan</b> mesaj: ' + tekrarEdilen + '</p>'
    : '') +
  (kayitlar.length ? satirlar : '<p style="color:#64748b">Henüz kayıt yok.</p>') +
  '</body></html>';

return [{ json: { html } }];
`;

const kod = (ad, id, x, y, js) => ({
  parameters: { jsCode: js },
  id, name: ad, type: 'n8n-nodes-base.code', typeVersion: 2, position: [x, y]
});

const workflow = [{
  id: 'lcarlieWhats001',
  name: 'WHATSAPP KANALI - Meta Cloud API',
  active: false,
  nodes: [
    // --- Dogrulama kolu (GET) ---
    {
      parameters: { httpMethod: 'GET', path: 'whatsapp', responseMode: 'responseNode', options: {} },
      id: 'cccccccc-0000-4000-8000-000000000001',
      name: 'Meta dogrulama (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, -220],
      webhookId: 'cccccccc-0000-4000-8000-0000000000a1'
    },
    kod('Dogrulama kontrolu', 'cccccccc-0000-4000-8000-000000000002', 240, -220, kodDogrula),
    {
      parameters: { respondWith: 'text', responseBody: '={{ $json.cevap }}', options: {} },
      id: 'cccccccc-0000-4000-8000-000000000003',
      name: 'Challenge dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [480, -220]
    },

    // --- Mesaj kolu (POST) ---
    {
      // onReceived: Meta'ya HEMEN 200 doner, islem arkada surer.
      // Meta gec cevapta webhook'u devre disi birakabiliyor.
      parameters: { httpMethod: 'POST', path: 'whatsapp', responseMode: 'onReceived', options: {} },
      id: 'cccccccc-0000-4000-8000-000000000004',
      name: 'Gelen mesaj (POST)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 60],
      webhookId: 'cccccccc-0000-4000-8000-0000000000a2'
    },
    kod('Mesajlari ayikla', 'cccccccc-0000-4000-8000-000000000005', 240, 60, kodAyikla),
    {
      // Metin olmayan mesajlar (gorsel, ses, konum) ajana gitmez
      parameters: {
        conditions: {
          options: { caseSensitive: true, leftValue: '', version: 2 },
          conditions: [{
            id: 'f1', operator: { type: 'boolean', operation: 'true', singleValue: true },
            leftValue: '={{ $json.metinMi }}', rightValue: ''
          }],
          combinator: 'and'
        },
        options: {}
      },
      id: 'cccccccc-0000-4000-8000-000000000006',
      name: 'Metin mi?',
      type: 'n8n-nodes-base.if', typeVersion: 2, position: [480, 60]
    },
    {
      parameters: {
        workflowId: { __rl: true, value: 'lcarlieAkis0001', mode: 'id' },
        // 🔴 'each' SART: Meta tek cagride birden cok mesaj gonderebiliyor ve
        // ajan "bir calistirma = bir mesaj" varsayiyor. 'once' birakilirsa
        // ajan sadece ILK mesaji isler, digerleri sessizce duser.
        mode: 'each',
        options: { waitForSubWorkflow: true }
      },
      id: 'cccccccc-0000-4000-8000-000000000007',
      name: 'Satis ajanina sor',
      type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2, position: [720, -40],
      // 🔴 HATA YOLU (CR-002 madde 2).
      // Onceki halinde ajan bir istisna firlattiginda calisma burada
      // kopuyordu: pilot kaydi yazilmiyor, eskalasyon olusmuyor, sayac
      // artmiyordu. Mesaj HICBIR IZ birakmadan kayboluyordu.
      // Ayni duzeltme 15.09'da yalnizca web sohbetine uygulanmisti ve o
      // workflow ayni gun devre disi birakildi (CR-001 bulgusu).
      //
      // 🔴 RETRY MUSTERIYE IKI MESAJ GONDERMEZ:
      //    (a) lcarlieAkis0001 statik veri yazmaz - saf karar fonksiyonu.
      //    (b) 'WhatsApp yaniti gonder' dugumu zaten disabled; gonderim yok.
      //    (c) Gonderim ileride acilirsa bile tekrar korumasi 'Mesajlari
      //        ayikla' icindeki sd.islenenMesajlar (son 2000 wamid) ile
      //        WEBHOOK SEVIYESINDE calisir - bu retry o katmanin altinda
      //        kaldigi icin ayni wamid ikinci kez islenmez.
      onError: 'continueRegularOutput',
      retryOnFail: true, maxTries: 2, waitBetweenTries: 1000
    },
    kod('Yaniti hazirla', 'cccccccc-0000-4000-8000-000000000008', 960, -40, kodYanit),
    {
      // Ajan gonderilmesin dediyse (insana aktarilan durumlar) gonderme
      parameters: {
        conditions: {
          options: { caseSensitive: true, leftValue: '', version: 2 },
          conditions: [{
            id: 'g1', operator: { type: 'boolean', operation: 'true', singleValue: true },
            leftValue: '={{ $json.gonderilecek }}', rightValue: ''
          }],
          combinator: 'and'
        },
        options: {}
      },
      id: 'cccccccc-0000-4000-8000-00000000000a',
      name: 'Gonderilecek mi?',
      type: 'n8n-nodes-base.if', typeVersion: 2, position: [1200, -40]
    },
    {
      // 🔴 KIMLIK BILGISI: n8n arayuzunden "WhatsApp API" credential'i olusturulup
      // buraya baglanmali. Meta access token BURAYA YAZILMAZ, credential'da durur.
      parameters: {
        method: 'POST',
        url: '=https://graph.facebook.com/v21.0/{{ $json.telefonNoId }}/messages',
        authentication: 'predefinedCredentialType',
        nodeCredentialType: 'whatsAppApi',
        sendBody: true,
        specifyBody: 'json',
        jsonBody: '={{ JSON.stringify($json.govde) }}',
        options: {}
      },
      id: 'cccccccc-0000-4000-8000-00000000000b',
      name: 'WhatsApp yaniti gonder',
      type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: [1440, -140],
      // 🔴 BILEREK KAPALI (pilot mod).
      // 1) Kimlik bilgisi olmadan n8n workflow'u yayinlatmiyor; kapali dugum
      //    engel olmuyor, boylece webhook calisir ve Meta dogrulamasi yapilabilir.
      // 2) Pilot asamasinda zaten otomatik gonderim istemiyoruz: mesajlar gelir,
      //    ajan karar uretir, hicbir sey gonderilmez. Kararlar execution
      //    gecmisinde gorulur.
      // ACMAK ICIN: credential baglandiktan sonra dugume sag tiklayip "Enable".
      disabled: true
    },
    kod('Gonderilmedi -> insana', 'cccccccc-0000-4000-8000-00000000000c', 1440, 60,
      `return [{ json: {
  gonderilmedi: true,
  insanaAktar: true,
  sebep: $json.sebep || 'Ajan otomatik cevap vermedi',
  musteriId: $json.musteriId,
  kayit: $json.kayit
} }];`),
    kod('Pilot kaydi', 'cccccccc-0000-4000-8000-00000000000d', 1200, -260, kodPilotKayit),
    // --- Pilot paneli (GET) ---
    {
      parameters: { httpMethod: 'GET', path: 'pilot', responseMode: 'responseNode', options: {} },
      id: 'cccccccc-0000-4000-8000-00000000000e',
      name: 'Pilot paneli (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 420],
      webhookId: 'cccccccc-0000-4000-8000-0000000000a3'
    },
    kod('Paneli olustur', 'cccccccc-0000-4000-8000-00000000000f', 240, 420, kodPilotPanel),
    {
      parameters: {
        respondWith: 'text',
        responseBody: '={{ $json.html }}',
        options: { responseHeaders: { entries: [
          { name: 'Content-Type', value: 'text/html; charset=utf-8' }
        ] } }
      },
      id: 'cccccccc-0000-4000-8000-000000000010',
      name: 'Paneli dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [480, 420]
    },
    kod('Metin disi -> insana', 'cccccccc-0000-4000-8000-000000000009', 720, 180,
      `return [{ json: {
  gonderilecek: false,
  insanaAktar: true,
  sebep: 'Metin olmayan mesaj (' + ($json.mesajTipi || 'bilinmiyor') + ') - insan bakmali',
  musteriId: $json.musteriId, mesajId: $json.mesajId
} }];`)
  ],
  connections: {
    'Meta dogrulama (GET)': { main: [[{ node: 'Dogrulama kontrolu', type: 'main', index: 0 }]] },
    'Dogrulama kontrolu':   { main: [[{ node: 'Challenge dondur',   type: 'main', index: 0 }]] },
    'Gelen mesaj (POST)':   { main: [[{ node: 'Mesajlari ayikla',   type: 'main', index: 0 }]] },
    'Mesajlari ayikla':     { main: [[{ node: 'Metin mi?',          type: 'main', index: 0 }]] },
    'Metin mi?': {
      main: [
        [{ node: 'Satis ajanina sor',   type: 'main', index: 0 }],   // true
        [{ node: 'Metin disi -> insana', type: 'main', index: 0 }]   // false
      ]
    },
    'Satis ajanina sor':    { main: [[{ node: 'Yaniti hazirla',     type: 'main', index: 0 }]] },
    'Yaniti hazirla':       { main: [[{ node: 'Pilot kaydi',        type: 'main', index: 0 }]] },
    'Pilot kaydi':          { main: [[{ node: 'Gonderilecek mi?',   type: 'main', index: 0 }]] },
    'Pilot paneli (GET)':   { main: [[{ node: 'Paneli olustur',     type: 'main', index: 0 }]] },
    'Paneli olustur':       { main: [[{ node: 'Paneli dondur',      type: 'main', index: 0 }]] },
    'Gonderilecek mi?': {
      main: [
        [{ node: 'WhatsApp yaniti gonder',  type: 'main', index: 0 }],  // true
        [{ node: 'Gonderilmedi -> insana',  type: 'main', index: 0 }]   // false
      ]
    }
  },
  settings: { executionOrder: 'v1' }
}];

fs.writeFileSync('/tmp/whatsapp-workflow.json', JSON.stringify(workflow, null, 2));
console.log('Yazildi. Node sayisi: ' + workflow[0].nodes.length);
