// =============================================================================
// MESSENGER KANALI - Meta Page Messaging
//
// Uretildi: 25.09.2026
// Workflow ID: lcarlieMsgr001
//
// 🔴 NEDEN VAR. 25.09.2026'da olculdu: gercek musteri trafiginin TAMAMI
//    Messenger'dan geliyor (569 gelen / 1.124 giden mesaj), ama n8n'de
//    yalniz WhatsApp, Instagram ve web sohbet kanallari vardi. Yani hat
//    kurulu kanallarda bos duruyor, trafigin oldugu kanalda hat yok.
//    Cevapsiz 11 konusmanin 11'i de messenger.
//
// Satis ajani (lcarlieAkis0001) KANAL BAGIMSIZ - bu dosya sadece giris kapisi.
// Mevzuat filtresi ve urun bilgi tabani ajan tarafinda, burada TEKRARLANMAZ.
//
//   GET  /webhook/messenger   (Meta dogrulamasi, hub.challenge)
//   POST /webhook/messenger   (gelen mesajlar)
//
// =============================================================================
// 🔴🔴 BAN RISKI - BU DOSYANIN TASARIM OMURGASI
//
// Meta, sayfa mesajlasmasinda politika ihlalini otomatik cezalandirir;
// ceza sayfa duzeyindedir ve reklam hesabina da yansiyabilir. Bu yuzden
// "once calistiralim, sonra duzeltiriz" YAPILMADI. Bes ayri kapi var ve
// dordu gonderim acilsa bile yerinde kalir:
//
//   1. GONDERIM DUGUMU KAPALI (pilot kip). Mesaj gelir, ajan karar uretir,
//      DISARIYA HICBIR SEY CIKMAZ. Bu haliyle ban riski sifirdir, cunku
//      Meta'ya tek bir gonderim istegi bile gitmez.
//
//   2. is_echo FILTRESI. 🔴 MESSENGER'A OZGU EN BUYUK TUZAK BU.
//      WhatsApp Cloud API kendi gonderdigin mesaji sana geri bildirmez;
//      Messenger BILDIRIR (message.is_echo = true). Filtrelenmezse:
//      cevap gonder -> echo webhook'u gelir -> ajan onu musteri mesaji
//      sanip cevap uretir -> sonsuz dongu. Meta bunu spam sayar ve
//      sayfayi kisitlar. Bu dosyada echo hem is_echo hem de
//      "gonderen = sayfa kimligi" olmak uzere IKI kez elenir.
//
//   3. 24 SAAT PENCERESI. Messenger'da musterinin son mesajindan sonraki
//      24 saat disinda serbest mesaj gonderilemez; onayli bir etiket
//      gerekir. Pencere BURADA hesaplanir ve her karara islenir. Gonderim
//      ileride acilsa bile pencere disindaki mesaj gonderime girmez,
//      insana aktarilir.
//
//   4. TEKRAR KORUMASI (mid). Meta 200 alamazsa ayni mesaji yeniden
//      gonderir. Tekrar elenmezse musteri ayni cevabi iki kez alir; bu da
//      spam sinyalidir.
//
//   5. HIZ SINIRI. Kisi basi ve toplam tavan - WhatsApp kanaliyla ayni.
//
// 🔴 AYRICA: yalniz `message` olaylari islenir. `delivery`, `read`,
//    `reaction`, `message_edit`, `postback` gibi olaylar mesaj DEGILDIR;
//    ajana verilirse anlamsiz cevap uretilir.
// =============================================================================
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
//    Neden boyle: n8n'de `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` -- Code
//    dugumu ortam degiskeni OKUYAMAZ, yani anahtar calisma aninda
//    alinamaz. Tek secenek uretim aninda gommek.
//
//    🔴 OLCULEN HATA (26.09.2026): canli WhatsApp workflow'unda bu deger
//    HALA 'BURAYA_META_DOGRULAMA_ANAHTARI' placeholder'iydi. Yani o
//    kanalin Meta dogrulamasi hicbir zaman tamamlanamazdi ve kanal
//    "aktif" gorunurken ise yaramaz durumdaydi. Placeholder'i sessizce
//    birakmak, kanali kurmus gibi gorunup kurmamak demek.
//
//    Bu yuzden burada varsayilan YOK: anahtar verilmezse uretici
//    PATLAR. Sessizce bozuk bir workflow uretmekten iyidir.
const DOGRULAMA = process.env.MESSENGER_VERIFY_TOKEN || '';
if (!DOGRULAMA) {
  console.error('HATA: MESSENGER_VERIFY_TOKEN verilmedi.');
  console.error('Okumak icin: grep MESSENGER_VERIFY_TOKEN /opt/lcarlie/n8n/.env');
  console.error('Uretim icin:  docker exec -e MESSENGER_VERIFY_TOKEN=... lcarlie-n8n node /tmp/build-messenger-workflow.js');
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

// ===== n8n: Meta Messenger payload'ini ayikla =====

// 🔴 HIZ SINIRI
//
// ⚠️ IP SINIRI YOK - BILEREK. Tum istekler Meta'nin birkac IP'sinden
//    gelir; IP'ye sinir koymak reklam donen bir gunde GERCEK musterileri
//    bogar. Kimlik, Meta'nin verdigi gonderen kimligidir (PSID).
const KISI_LIMIT = 20, KISI_PENCERE = 10 * 60 * 1000;
const TOPLAM_LIMIT = 1000, TOPLAM_PENCERE = 60 * 60 * 1000;

// 🔴 24 SAAT PENCERESI (Messenger standart mesajlasma penceresi).
const PENCERE_MS = 24 * 60 * 60 * 1000;

const sd = $getWorkflowStaticData('global');
if (!Array.isArray(sd.islenenMesajlar)) sd.islenenMesajlar = [];
sd.hiz = sd.hiz || {};
sd.toplam = Array.isArray(sd.toplam) ? sd.toplam : [];

const simdi = Date.now();
sd.toplam = sd.toplam.filter(t => simdi - t < TOPLAM_PENCERE);
for (const k of Object.keys(sd.hiz)) {
  sd.hiz[k] = sd.hiz[k].filter(t => simdi - t < KISI_PENCERE);
  if (!sd.hiz[k].length) delete sd.hiz[k];
}

const cikti = [];
let elenen = { echo: 0, tekrar: 0, olayDegil: 0, hiz: 0 };

// 🔴 all() - first() DEGIL. first() kullanilirsa diger musterilerin
//    mesajlari HATA VERMEDEN duser. Bu projede uc kez yasandi.
for (const item of $input.all()) {
  const govde = item.json.body ?? item.json;

  // Messenger zarfi: entry[].messaging[]  (WhatsApp'taki changes[] DEGIL)
  for (const giris of (govde.entry ?? [])) {
    const sayfaId = String(giris.id ?? '');

    for (const olay of (giris.messaging ?? [])) {
      const m = olay.message;

      // 🔴 YALNIZ MESAJ OLAYLARI. delivery/read/reaction/postback/
      //    message_edit mesaj DEGILDIR; ajana verilirse anlamsiz cevap
      //    uretir ve pilot kaydini kirletir.
      if (!m) { elenen.olayDegil++; continue; }

      const gonderen = String(olay.sender?.id ?? '');
      const alici    = String(olay.recipient?.id ?? '');

      // 🔴 ECHO KAPISI - IKI KAT.
      //    (a) Meta kendi gonderdigimiz mesaji is_echo=true ile geri bildirir.
      //    (b) Ayrica gonderen sayfanin kendisi olabilir.
      //    Elenmezse: cevap -> echo -> cevap -> ... sonsuz dongu. Meta bunu
      //    spam sayar. Bu dosyada ban riskinin en somut kaynagi budur.
      if (m.is_echo === true || (sayfaId && gonderen === sayfaId) || gonderen === alici) {
        elenen.echo++;
        continue;
      }

      // Tekrar gonderim korumasi (idempotency): Meta 200 alamazsa ayni
      // mesaji yeniden gonderir; musteri ayni cevabi iki kez almamali.
      const mid = m.mid ? String(m.mid) : '';
      if (mid && sd.islenenMesajlar.indexOf(mid) !== -1) { elenen.tekrar++; continue; }
      if (mid) {
        sd.islenenMesajlar.unshift(mid);
        if (sd.islenenMesajlar.length > 2000) sd.islenenMesajlar.length = 2000;
      }

      if (sd.hiz[gonderen] && sd.hiz[gonderen].length >= KISI_LIMIT) { elenen.hiz++; continue; }
      if (sd.toplam.length >= TOPLAM_LIMIT) { elenen.hiz++; continue; }
      sd.hiz[gonderen] = sd.hiz[gonderen] || [];
      sd.hiz[gonderen].push(simdi);
      sd.toplam.push(simdi);

      // Sadece metin mesajlarini isle. Gorsel/ses/konum/dosya insana gider.
      const metin = (typeof m.text === 'string' && m.text.trim())
        ? m.text.trim()
        : (m.quick_reply?.payload ? String(m.quick_reply.payload) : null);

      const ekTipi = Array.isArray(m.attachments) && m.attachments.length
        ? String(m.attachments[0].type || 'ek')
        : null;

      // 🔴 24 SAAT PENCERESI. olay.timestamp musterinin mesaj anidir;
      //    pencere ONDAN baslar. Damga okunamazsa pencere ACIK SAYILMAZ --
      //    bilinmeyeni "gonderilebilir" kabul etmek tam olarak ban uretir.
      const damga = Number(olay.timestamp);
      const damgaGecerli = Number.isFinite(damga) && damga > 0;
      const pencereIcinde = damgaGecerli ? (simdi - damga) < PENCERE_MS : false;

      cikti.push({
        json: {
          mesaj: metin ?? '',
          musteriId: gonderen,
          musteriAdi: null,          // PSID'den ad cozulmez; ayri API cagrisi ister
          kanal: 'messenger',
          // 🔴 KORELASYON KIMLIGI (CR-002 madde 2).
          // Ajan cokerse 'continueRegularOutput' giris ogesini gecirmez;
          // hata kaydinin hangi istege ait oldugunu bu kimlik soyler.
          // 🔴 mid KULLANILMAZ - PII tasiyicisi sayilir, hata kaydina girmez.
          korelasyon: korelasyonUret('ms'),
          // 🔴 TRAFIK SINIFI GIRISTE BELIRLENIR (CR-002.5 madde A).
          trafik: trafikSinifi(gonderen),
          mesajId: mid || null,
          mesajTipi: metin ? 'text' : (ekTipi || 'bilinmiyor'),
          metinMi: Boolean(metin),
          sayfaId: sayfaId || null,
          pencereIcinde,
          damgaGecerli,
          zaman: damgaGecerli ? damga : null
        }
      });
    }
  }
}

// Elenenler SAYILIR ve kayda gecer: "hic mesaj gelmedi" ile "geldi ama
// elendi" ayri seylerdir. Bu ayrim olmadan echo dongusu sessizce buyur.
if (cikti.length === 0) {
  return [{ json: { gecerli: false, bosGecti: true, elenen } }];
}
cikti[0].json.elenen = elenen;
return cikti;
`;

// ---------------------------------------------------------------------
// 3) AJAN KARARINI GONDERIM GOVDESINE CEVIR
// ---------------------------------------------------------------------
const kodYanit = ORTAK + `

// ===== n8n: yaniti hazirla =====
return $input.all().map(item => {
  const karar = item.json || {};
  const onceki = $('Mesajlari ayikla').all()
    .map(x => x.json)
    .find(x => x.musteriId === karar.musteriId) || {};

  const ortak = {
    musteriId: karar.musteriId || onceki.musteriId,
    korelasyon: onceki.korelasyon || '-',
    trafik: onceki.trafik || trafikSinifi(onceki.musteriId),
    // Gonderim adresi sayfa kimliginden kurulur; sabit yazilmaz.
    sayfaId: onceki.sayfaId || null,
    pencereIcinde: onceki.pencereIcinde === true,
    // 🔴 URUN VE SINIF PILOT KAYDI ICIN TASINIR.
    //    (Yorumda ters tirnak KULLANILMAZ: bu blok bir template literal
    //     icinde gomulu, ters tirnak diziyi keser ve uretici patlar.)
    //    Olculdu 26.09.2026: ilk surumde pilot kaydi kayit.urun ve
    //    kayit.niyet okuyordu; ajan o adlari HIC kullanmiyor (urun ust
    //    seviyede, sinif kayit.sinif icinde). Sonuc: kayit "gonderilecek: true"
    //    diyordu ama NEYI gonderecegini soylemiyordu -- yani "ajan dogru
    //    mu dedi" sorusu cevaplanamiyordu, ki kaydin tek amaci odur.
    urun: karar.urun || (karar.kayit && karar.kayit.urun) || null,
    sinif: (karar.kayit && karar.kayit.sinif) || karar.sinif || null,
    kayit: karar.kayit
  };

  if (!karar.cevap || karar.insanaAktar) {
    return { json: { gonderilecek: false, insanaAktar: true, ...ortak } };
  }

  // 🔴 24 SAAT KAPISI. Pencere disindaki mesaj gonderime GIRMEZ.
  //    Messenger'da pencere disi serbest mesaj, onayli etiket olmadan
  //    politika ihlalidir. Gonderim dugumu ileride acilsa bile bu kapi
  //    yerinde kalir; karar 'insana aktar' olur, sessizce dusmez.
  if (onceki.pencereIcinde !== true) {
    return {
      json: {
        gonderilecek: false,
        insanaAktar: true,
        sebep: onceki.damgaGecerli === false
          ? '24 saat penceresi HESAPLANAMADI (zaman damgasi okunamadi) - insan bakmali'
          : '24 saat penceresi kapali - otomatik gonderim politikaya aykiri',
        ...ortak
      }
    };
  }

  return {
    json: {
      gonderilecek: true,
      ...ortak,
      // Meta Graph API govdesi (Send API)
      govde: {
        messaging_type: 'RESPONSE',   // 🔴 yalniz yanit; MESSAGE_TAG KULLANILMAZ
        recipient: { id: karar.musteriId },
        message: { text: karar.cevap }
      },
      insanaAktar: karar.insanaAktar
    }
  };
});
`;

// ---------------------------------------------------------------------
// 4) PILOT KAYDI - her karar kalici olarak saklanir (son 60 adet)
// ---------------------------------------------------------------------
const kodPilotKayit = ORTAK + `

// ===== n8n: pilot kaydi =====
const sd = $getWorkflowStaticData('global');
if (!Array.isArray(sd.pilot)) sd.pilot = [];

for (const item of $input.all()) {
  const j = item.json;
  const k = j.kayit || {};

  // 🔴 PII YAZILMAZ -- ama KENDI CEVABIMIZ PII DEGILDIR.
  //
  //    Ilk surum yalnizca "gonderilecek: true/false" yaziyordu ve urun/
  //    niyet alanlarini ajanin HIC kullanmadigi adlardan okudugu icin
  //    ikisi de null cikiyordu. Yani kayit "bir sey gonderecektim" diyor,
  //    NE gonderecegini soylemiyordu. Boyle bir kayitla "ajan dogru mu
  //    dedi" sorusu cevaplanamaz -- ki pilot kipinin tek amaci odur.
  //
  //    Yazilanlar: kendi cevap metnimiz, urun, sinif, mevzuat filtresinin
  //    iki sonucu ve gerekceler.
  //    YAZILMAYANLAR: musteri kimligi (k.musteriId) ve musterinin mesaji
  //    (k.gelenMesaj). Ikisi de PII; korelasyon kimligi izleme icin yeter.
  const cevap = k.gonderilenCevap || null;
  sd.pilot.unshift({
    ts: new Date().toISOString(),
    korelasyon: j.korelasyon || '-',
    trafik: j.trafik || 'unknown',
    gonderilecek: Boolean(j.gonderilecek),
    insanaAktar: Boolean(j.insanaAktar),
    sebep: j.sebep || null,
    urun: j.urun || null,
    sinif: j.sinif || null,
    pencereIcinde: j.pencereIcinde === true,
    // Cevap 400 karakterle sinirli: kayit 60 kaydi tasiyor ve statik veri
    // her calistirmada yaziliyor; sinirsiz metin onu sisirir.
    cevap: cevap ? String(cevap).slice(0, 400) : null,
    filtre: {
      gelen: k.gelenFiltreSonucu || null,
      taslak: k.taslakFiltreSonucu || null
    },
    gerekceler: Array.isArray(k.gerekceler) ? k.gerekceler.slice(0, 4) : null
  });
}
if (sd.pilot.length > 60) sd.pilot.length = 60;
return $input.all();
`;

// ---------------------------------------------------------------------
// 5) PILOT PANELI (GET) - sahip kararlari kendi gozuyle gorsun
//
// 🔴 NEDEN AYRI BIR SAYFA. Pilot kipin butun anlami "ajan ne diyecekti"
//    sorusunu cevaplamak. O cevap n8n'in execution ekraninda duruyordu;
//    oraya bakmak icin n8n hesabi ve JSON okumak gerekiyor. Karar verecek
//    kisi icin bu, kaydin hic olmamasiyla neredeyse ayni sey.
//
// 🔴 PANEL DE PII GOSTERMEZ. Kayit zaten musteri kimligini ve musterinin
//    mesajini tutmuyor; panel de uyduramaz. Gosterilen: bizim cevabimiz,
//    urun, sinif, mevzuat filtresi ve gerekceler.
// ---------------------------------------------------------------------
const PANEL_ANAHTARI = process.env.MESSENGER_PANEL_TOKEN || '';
if (!PANEL_ANAHTARI) {
  console.error('HATA: MESSENGER_PANEL_TOKEN verilmedi.');
  console.error('Okumak icin: grep MESSENGER_PANEL_TOKEN /opt/lcarlie/n8n/.env');
  process.exit(1);
}

const kodPanel = `
const ANAHTAR = ${JSON.stringify(PANEL_ANAHTARI)};
const q = $input.first().json.query || {};
if (q.k !== ANAHTAR) {
  return [{ json: { html: '<!doctype html><meta charset="utf-8">' +
    '<body style="font-family:system-ui;padding:2rem">Erisim anahtari gecersiz.</body>' } }];
}

const sd = $getWorkflowStaticData('global');
const kayitlar = Array.isArray(sd.pilot) ? sd.pilot : [];

const kacis = (s) => String(s ?? '')
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const saat = (iso) => {
  try { return new Date(iso).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul' }); }
  catch (e) { return String(iso); }
};

// --- ozet -------------------------------------------------------------
const uretim = kayitlar.filter(r => r.trafik === 'production');
const say = (dizi, f) => dizi.filter(f).length;
const ozetKutu = (baslik, deger, renk, alt) =>
  '<div style="flex:1;min-width:130px;border:1px solid #e2e8f0;border-radius:10px;padding:.8rem;background:#fff">' +
  '<div style="font-size:.7rem;letter-spacing:.06em;color:#64748b;text-transform:uppercase">' + baslik + '</div>' +
  '<div style="font-size:1.6rem;font-weight:700;color:' + renk + ';line-height:1.2">' + deger + '</div>' +
  '<div style="font-size:.72rem;color:#64748b">' + alt + '</div></div>';

const ozet =
  ozetKutu('Toplam karar', kayitlar.length, '#0f172a', uretim.length + ' gercek musteri') +
  ozetKutu('Gonderilecekti', say(kayitlar, r => r.gonderilecek), '#16a34a', 'ajan cevap uretti') +
  ozetKutu('Insana aktarilan', say(kayitlar, r => r.insanaAktar), '#d97706', 'otomatik cevaplanmadi') +
  ozetKutu('Pencere disi', say(kayitlar, r => r.pencereIcinde === false), '#dc2626', '24 saat gecmis') +
  ozetKutu('Mevzuat blogu', say(kayitlar, r => (r.filtre && (r.filtre.gelen === 'BLOKLU' || r.filtre.taslak === 'BLOKLU'))), '#7c3aed', 'filtre devreye girdi');

// --- kartlar ----------------------------------------------------------
const rozet = (metin, renk, zemin) =>
  '<span style="display:inline-block;font-size:.7rem;font-weight:600;color:' + renk +
  ';background:' + zemin + ';border-radius:999px;padding:.15rem .55rem;margin-right:.35rem">' + metin + '</span>';

const kartlar = kayitlar.map(function (r) {
  const durum = r.gonderilecek
    ? rozet('GONDERILECEKTI', '#166534', '#dcfce7')
    : rozet('GONDERILMEZ', '#991b1b', '#fee2e2');
  const insan = r.insanaAktar ? rozet('INSANA AKTARILDI', '#92400e', '#fef3c7') : '';
  const test = r.trafik !== 'production' ? rozet(String(r.trafik || 'unknown').toUpperCase(), '#475569', '#e2e8f0') : '';
  const pencere = r.pencereIcinde === false ? rozet('24 SAAT DISI', '#991b1b', '#fee2e2') : '';
  const f = r.filtre || {};
  const filtre = (f.gelen || f.taslak)
    ? rozet('FILTRE ' + kacis(f.gelen || '-') + ' / ' + kacis(f.taslak || '-'),
            (f.gelen === 'BLOKLU' || f.taslak === 'BLOKLU') ? '#5b21b6' : '#334155',
            (f.gelen === 'BLOKLU' || f.taslak === 'BLOKLU') ? '#ede9fe' : '#f1f5f9')
    : '';
  const cevap = r.cevap
    ? '<div style="background:#f8fafc;border-left:3px solid #94a3b8;padding:.6rem .8rem;border-radius:0 6px 6px 0;margin-top:.6rem;white-space:pre-wrap;font-size:.9rem">' + kacis(r.cevap) + '</div>'
    : '<div style="color:#64748b;margin-top:.6rem;font-size:.85rem">(cevap uretilmedi)</div>';
  const ger = Array.isArray(r.gerekceler) && r.gerekceler.length
    ? '<ul style="margin:.6rem 0 0;padding-left:1.1rem;color:#475569;font-size:.78rem">' +
      r.gerekceler.map(g => '<li>' + kacis(g) + '</li>').join('') + '</ul>'
    : '';
  const sebep = r.sebep
    ? '<div style="font-size:.78rem;color:#b45309;margin-top:.5rem">' + kacis(r.sebep) + '</div>' : '';
  const baslik = [r.urun, r.sinif].filter(Boolean).map(kacis).join(' · ') || 'siniflandirilmadi';
  return '<div style="border:1px solid #e2e8f0;border-radius:12px;padding:1rem;margin-bottom:.9rem;background:#fff">' +
    '<div style="display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap">' +
      '<div style="font-weight:700">' + baslik + '</div>' +
      '<div style="font-size:.75rem;color:#64748b">' + kacis(saat(r.ts)) + ' · ' + kacis(r.korelasyon || '-') + '</div>' +
    '</div>' +
    '<div style="margin-top:.55rem">' + durum + insan + pencere + filtre + test + '</div>' +
    cevap + sebep + ger +
    '</div>';
}).join('');

const bos = '<div style="border:1px dashed #cbd5e1;border-radius:12px;padding:2rem;text-align:center;color:#64748b;background:#fff">' +
  'Henuz karar kaydi yok.<br><span style="font-size:.85rem">Messenger\\'dan ilk mesaj geldiginde burada gorunecek.</span></div>';

const html = '<!doctype html><html lang="tr"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>L\\'CARLIE · Messenger Pilot</title></head>' +
  '<body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f1f5f9;margin:0;padding:1rem;color:#0f172a">' +
  '<div style="max-width:880px;margin:0 auto">' +
  '<h1 style="font-size:1.15rem;margin:.3rem 0 .2rem">L\\'CARLIE · Messenger Pilot Paneli</h1>' +
  '<div style="font-size:.82rem;color:#64748b;margin-bottom:.9rem">Ajanin ne diyecegi. Gonderim KAPALI.</div>' +
  '<div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:.7rem .9rem;font-size:.82rem;margin-bottom:1rem">' +
  '<b>Pilot kip.</b> Mesajlar geliyor, ajan karar uretiyor, <b>disariya hicbir sey gonderilmiyor</b>. ' +
  'Bu sayfadaki cevaplar musteriye ULASMADI. Ayrica: kayit yalniz son 60 karari tutar ve <b>her n8n yayininda sifirlanir</b>.' +
  '</div>' +
  '<div style="display:flex;gap:.7rem;flex-wrap:wrap;margin-bottom:1.2rem">' + ozet + '</div>' +
  (kayitlar.length ? kartlar : bos) +
  '<div style="font-size:.72rem;color:#94a3b8;margin:1.2rem 0 2rem">' +
  'Gizlilik: bu sayfa musteri kimligi veya musterinin mesajini GOSTERMEZ - kayitta tutulmuyorlar. ' +
  'Gosterilen metin bizim uretecegimiz cevaptir.</div>' +
  '</div></body></html>';

return [{ json: { html } }];
`;

const kod = (ad, id, x, y, js) => ({
  parameters: { jsCode: js },
  id, name: ad, type: 'n8n-nodes-base.code', typeVersion: 2, position: [x, y]
});

const workflow = [{
  id: 'lcarlieMsgr001',
  name: 'MESSENGER KANALI - Meta Page Messaging',
  active: false,
  nodes: [
    // --- Dogrulama kolu (GET) ---
    {
      parameters: { httpMethod: 'GET', path: 'messenger', responseMode: 'responseNode', options: {} },
      id: 'dddddddd-0000-4000-8000-000000000001',
      name: 'Meta dogrulama (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, -220],
      webhookId: 'dddddddd-0000-4000-8000-0000000000a1'
    },
    kod('Dogrulama kontrolu', 'dddddddd-0000-4000-8000-000000000002', 240, -220, kodDogrula),
    {
      parameters: { respondWith: 'text', responseBody: '={{ $json.cevap }}', options: {} },
      id: 'dddddddd-0000-4000-8000-000000000003',
      name: 'Challenge dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [480, -220]
    },

    // --- Mesaj kolu (POST) ---
    {
      // onReceived: Meta'ya HEMEN 200 doner, islem arkada surer.
      // 🔴 Meta gec cevapta webhook'u DEVRE DISI BIRAKIR - bu kanalin
      //    sessizce olmesinin en bilinen sebebi budur.
      parameters: { httpMethod: 'POST', path: 'messenger', responseMode: 'onReceived', options: {} },
      id: 'dddddddd-0000-4000-8000-000000000004',
      name: 'Gelen mesaj (POST)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 60],
      webhookId: 'dddddddd-0000-4000-8000-0000000000a2'
    },
    kod('Mesajlari ayikla', 'dddddddd-0000-4000-8000-000000000005', 240, 60, kodAyikla),
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
      id: 'dddddddd-0000-4000-8000-000000000006',
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
      id: 'dddddddd-0000-4000-8000-000000000007',
      name: 'Satis ajanina sor',
      type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2, position: [720, -40],
      // 🔴 HATA YOLU (CR-002 madde 2). Ajan istisna firlatirsa calisma
      //    burada kopmamali: pilot kaydi yazilmali, mesaj iz birakmali.
      //
      // 🔴 RETRY MUSTERIYE IKI MESAJ GONDERMEZ:
      //    (a) lcarlieAkis0001 statik veri yazmaz - saf karar fonksiyonu.
      //    (b) 'Messenger yaniti gonder' dugumu zaten disabled.
      //    (c) Gonderim acilirsa bile tekrar korumasi 'Mesajlari ayikla'
      //        icindeki sd.islenenMesajlar (son 2000 mid) ile WEBHOOK
      //        SEVIYESINDE calisir; retry o katmanin altinda kalir.
      onError: 'continueRegularOutput',
      retryOnFail: true, maxTries: 2, waitBetweenTries: 1000
    },
    kod('Yaniti hazirla', 'dddddddd-0000-4000-8000-000000000008', 960, -40, kodYanit),
    kod('Pilot kaydi', 'dddddddd-0000-4000-8000-000000000009', 1200, -140, kodPilotKayit),
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
      id: 'dddddddd-0000-4000-8000-00000000000a',
      name: 'Gonderilecek mi?',
      type: 'n8n-nodes-base.if', typeVersion: 2, position: [1440, -140]
    },
    {
      // 🔴 KIMLIK BILGISI: sayfa jetonu BURAYA YAZILMAZ, n8n credential'inda durur.
      parameters: {
        method: 'POST',
        // Send API: /{sayfa-kimligi}/messages. Sayfa kimligi gelen olaydan
        // gelir (entry[].id); sabit yazilmaz. Okunamazsa jetonun sahibi
        // sayfaya karsilik gelen /me kullanilir.
        url: '=https://graph.facebook.com/v21.0/{{ $json.sayfaId || "me" }}/messages',
        authentication: 'predefinedCredentialType',
        nodeCredentialType: 'facebookGraphApi',
        sendBody: true,
        specifyBody: 'json',
        jsonBody: '={{ JSON.stringify($json.govde) }}',
        options: {}
      },
      // 🔴 SAYFA JETONU BURADA DEGIL, n8n credential'inda durur ve orada
      //    sifreli saklanir (26.09.2026'da olculdu: credentials_entity.data
      //    sifreli). Workflow JSON'u `n8n-wf-yedek.sh` ile git'e gidiyor;
      //    jeton koda yazilsa surum gecmisine sizardi.
      credentials: {
        facebookGraphApi: { id: 'lcarlieSayfaJet', name: 'LCARLIE Sayfa Jetonu (Messenger)' }
      },
      id: 'dddddddd-0000-4000-8000-00000000000b',
      name: 'Messenger yaniti gonder',
      type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position: [1680, -240],
      // 🔴🔴 BILEREK KAPALI - PILOT KIP. BU DOSYANIN EN ONEMLI SATIRI.
      //
      // Kapali oldugu surece Meta'ya TEK BIR gonderim istegi gitmez;
      // yani bu kanalin ban riski SIFIRDIR. Mesajlar gelir, ajan karar
      // uretir, kararlar pilot kaydinda ve execution gecmisinde gorulur.
      //
      // ACMADAN ONCE SIRASIYLA:
      //   1. Sayfa jetonu icin n8n credential'i olustur (Facebook Graph API).
      //   2. Pilot kaydinda en az birkac gunluk gercek karar incele --
      //      ajan ne diyecekti, dogru muydu?
      //   3. 24 saat penceresi kapisinin calistigini dogrula.
      //   4. ANCAK ONDAN SONRA bu dugume sag tiklayip "Enable".
      // Bu sira atlanirsa musteriye denetlenmemis metin gider.
      disabled: true
    },
    kod('Gonderilmedi -> insana', 'dddddddd-0000-4000-8000-00000000000c', 1680, -40,
      `return [{ json: {
  gonderilmedi: true,
  insanaAktar: true,
  sebep: $json.sebep || 'ajan insana aktarilmasini istedi',
  korelasyon: $json.korelasyon || '-'
} }];`),
    // --- Pilot paneli kolu (GET) ---
    {
      parameters: { httpMethod: 'GET', path: 'messenger-panel', responseMode: 'responseNode', options: {} },
      id: 'dddddddd-0000-4000-8000-00000000000e',
      name: 'Pilot paneli (GET)',
      type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [0, 420],
      webhookId: 'dddddddd-0000-4000-8000-0000000000a3'
    },
    kod('Paneli olustur', 'dddddddd-0000-4000-8000-00000000000f', 240, 420, kodPanel),
    {
      parameters: {
        respondWith: 'text',
        responseBody: '={{ $json.html }}',
        options: { responseHeaders: { entries: [
          { name: 'Content-Type', value: 'text/html; charset=utf-8' }
        ] } }
      },
      id: 'dddddddd-0000-4000-8000-000000000010',
      name: 'Paneli dondur',
      type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1, position: [480, 420]
    },
    kod('Metin disi -> insana', 'dddddddd-0000-4000-8000-00000000000d', 720, 180,
      `return [{ json: {
  gonderilecek: false,
  insanaAktar: true,
  sebep: 'Metin olmayan mesaj (' + ($json.mesajTipi || 'bilinmiyor') + ') - insan bakmali',
  musteriId: $json.musteriId, mesajId: $json.mesajId, korelasyon: $json.korelasyon || '-'
} }];`)
  ],
  connections: {
    'Meta dogrulama (GET)': { main: [[{ node: 'Dogrulama kontrolu', type: 'main', index: 0 }]] },
    'Dogrulama kontrolu':   { main: [[{ node: 'Challenge dondur',   type: 'main', index: 0 }]] },
    'Gelen mesaj (POST)':   { main: [[{ node: 'Mesajlari ayikla',   type: 'main', index: 0 }]] },
    'Mesajlari ayikla':     { main: [[{ node: 'Metin mi?',          type: 'main', index: 0 }]] },
    'Metin mi?': {
      main: [
        [{ node: 'Satis ajanina sor',    type: 'main', index: 0 }],   // true
        [{ node: 'Metin disi -> insana', type: 'main', index: 0 }]    // false
      ]
    },
    'Satis ajanina sor':    { main: [[{ node: 'Yaniti hazirla',   type: 'main', index: 0 }]] },
    'Yaniti hazirla':       { main: [[{ node: 'Pilot kaydi',      type: 'main', index: 0 }]] },
    'Pilot kaydi':          { main: [[{ node: 'Gonderilecek mi?', type: 'main', index: 0 }]] },
    'Gonderilecek mi?': {
      main: [
        [{ node: 'Messenger yaniti gonder', type: 'main', index: 0 }],  // true
        [{ node: 'Gonderilmedi -> insana',  type: 'main', index: 0 }]   // false
      ]
    },
    'Pilot paneli (GET)': { main: [[{ node: 'Paneli olustur', type: 'main', index: 0 }]] },
    'Paneli olustur':     { main: [[{ node: 'Paneli dondur',  type: 'main', index: 0 }]] }
  },
  settings: { executionOrder: 'v1' }
}];

fs.writeFileSync('/tmp/messenger-workflow.json', JSON.stringify(workflow, null, 2));
console.log('Yazildi. Node sayisi: ' + workflow[0].nodes.length);
