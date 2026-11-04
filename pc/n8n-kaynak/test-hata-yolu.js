// =====================================================================
// L'CARLIE - HATA YOLU TESTI   (CR-002 madde 2 / 11-C / 11-L)
//
// Neden ayri bir test?
//   CR-001'de aktif Instagram ve WhatsApp workflow'larinda HICBIR hata
//   yolu olmadigi bulundu: ajan bir istisna firlattiginda musteri HTTP 500
//   aliyor, kayit/eskalasyon/sayac hic olusmuyor, mesaj IZSIZ kayboluyordu.
//   Ayni koruma 15.09'da YALNIZCA web sohbetine eklenmis, o workflow da
//   ayni gun devre disi birakilmisti - yani koruma kullanilmayan tek yerde
//   duruyordu ve hicbir test bunu fark etmiyordu.
//
// 🔴 Bu test URETILEN workflow JSON'undan kodu cikarip GERCEKTEN calistirir.
//    Kaynakta ne yazdigina degil, YAYINLANACAK dosyada ne oldugna bakar.
//
// Olculen davranis:
//   1. Iki kanalda da 'Satis ajanina sor' dugumunde onError + retry var
//   2. Ajan cokunce musteri BOSLUGA BAKMIYOR (notr cevap doner)
//   3. Ajan cokunce konusma HER ZAMAN insana aktariliyor
//   4. Ajan cokunce musteri kimligi KAYBOLMUYOR (onceki dugumden alinir)
//   5. Hata kaydi 8 zorunlu alanin HEPSINI iceriyor
//   6. 🔴 Hata kaydinda PII YOK (mesaj metni, telefon, e-posta)
//   7. Normal akis DEGISMIYOR (coken yokken davranis eskisiyle ayni)
//   8. PII temizleyicisi gercekten calisiyor
// =====================================================================
const fs = require('fs');
const path = require('path');

const KLASOR = __dirname;
let basarili = 0, basarisiz = 0;
const kontrol = (ad, kosul, detay) => {
  if (kosul) { basarili++; console.log('  ok   ' + ad); }
  else { basarisiz++; console.log('  HATA ' + ad + (detay ? '  -> ' + detay : '')); }
};

// --- Workflow'lari uret ----------------------------------------------
// 🔴 SAHTE DOGRULAMA ANAHTARLARI - BILEREK.
//    Ureticiler, Meta dogrulama anahtari verilmezse process.exit(1) ile
//    PATLAR (26.09.2026: canli workflow'da placeholder'in sessizce kalmis
//    oldugu olculdu; sessiz varsayilan bir daha birakilmadi). Bu testler
//    ureticiyi require() ile AYNI SURECTE calistirdigi icin o exit testi
//    de oldurur. Testlerin dogrulama dugumuyle isi yok -- sahte anahtar
//    yeterli. Gercek anahtar yalniz yayin hattinda .env'den gecirilir.
if (!process.env.WHATSAPP_VERIFY_TOKEN) process.env.WHATSAPP_VERIFY_TOKEN = 'test-sahte-anahtar';
if (!process.env.MESSENGER_VERIFY_TOKEN) process.env.MESSENGER_VERIFY_TOKEN = 'test-sahte-anahtar';

require(path.join(KLASOR, 'build-instagram-workflow.js'));
require(path.join(KLASOR, 'build-whatsapp-workflow.js'));

const ig = JSON.parse(fs.readFileSync('/tmp/instagram-workflow.json', 'utf8'))[0];
const wa = JSON.parse(fs.readFileSync('/tmp/whatsapp-workflow.json', 'utf8'))[0];

const dugum = (wf, ad) => wf.nodes.find(n => n.name === ad);
const kodOf = (wf, ad) => {
  const d = dugum(wf, ad);
  if (!d || !d.parameters || !d.parameters.jsCode) {
    console.error('HATA: "' + ad + '" dugumu veya kodu bulunamadi (' + wf.id + ').');
    process.exit(1);
  }
  return d.parameters.jsCode;
};

// =====================================================================
console.log('\n--- 1) Dugum yapilandirmasi ---');
// =====================================================================
for (const [ad, wf] of [['instagram', ig], ['whatsapp', wa]]) {
  const d = dugum(wf, 'Satis ajanina sor');
  kontrol(ad + ': onError=continueRegularOutput',
    d && d.onError === 'continueRegularOutput', d && String(d.onError));
  kontrol(ad + ': retryOnFail acik', d && d.retryOnFail === true);
  kontrol(ad + ': maxTries >= 2', d && d.maxTries >= 2, d && String(d.maxTries));
  // 🔴 'each' kaybolmamali - retry eklenirken yanlislikla silinebilir
  kontrol(ad + ": mode hala 'each'", d && d.parameters && d.parameters.mode === 'each');
}

// =====================================================================
console.log('\n--- 2) PII temizleyici ---');
// =====================================================================
{
  const kod = kodOf(ig, 'Cevabi hazirla');
  const fn = new Function(kod.replace(/\n\/\/ ===== n8n[\s\S]*$/, '\nreturn { piiTemizle, hataSinifi, korelasyonUret };'));
  const yrd = fn();
  const t = yrd.piiTemizle;
  kontrol('telefon maskeleniyor', !/905551112233/.test(t('musteri 905551112233 yazdi')), t('musteri 905551112233 yazdi'));
  kontrol('e-posta maskeleniyor', !/@/.test(t('kisi ali@ornek.com yazdi')), t('kisi ali@ornek.com yazdi'));
  kontrol('wamid maskeleniyor', !/wamid\.HBg/.test(t('id wamid.HBgMOTA1NTUx')), t('id wamid.HBgMOTA1NTUx'));
  kontrol('uzun deger maskeleniyor', !/ABCDEFGHIJKLMNOPQRSTUVWXYZ012345/.test(t('tok ABCDEFGHIJKLMNOPQRSTUVWXYZ012345')));
  kontrol('kisa metin bozulmuyor', t('alt akis bulunamadi') === 'alt akis bulunamadi', t('alt akis bulunamadi'));
  kontrol('200 karakterle sinirli', t('x'.repeat(500)).length <= 200);
  kontrol('korelasyon PII icermiyor',
    /^ig-[a-z0-9]+-[a-z0-9]{4}$/.test(yrd.korelasyonUret('ig')), yrd.korelasyonUret('ig'));
  kontrol('hata sinifi tutarli',
    yrd.hataSinifi({ name: 'NodeOperationError' }) === 'NODEOPERATIONERROR',
    yrd.hataSinifi({ name: 'NodeOperationError' }));
}

// =====================================================================
console.log('\n--- 3) INSTAGRAM: ajan cokerse ---');
// =====================================================================
{
  const kod = kodOf(ig, 'Cevabi hazirla');
  const statik = {};
  // Ajan coktu: 'continueRegularOutput' yalnizca error alani olan bir oge verir.
  const ajanCiktisi = [{ json: { error: { name: 'NodeOperationError',
    message: 'Could not find workflow lcarlieAkis0001' } } }];
  // Onceki dugum (Gecerli mi?) kimligi ve korelasyonu hala tasiyor.
  const oncekiler = [{ json: { gecerli: true, mesaj: 'vireon fiyati nedir',
    musteriId: '905551112233', korelasyon: 'ig-abc123-9f2a', kanal: 'instagram' } }];

  const fn = new Function('$getWorkflowStaticData', '$input', '$', '$workflow', '$execution', kod);
  const sonuc = fn(
    () => statik,
    { all: () => ajanCiktisi },
    (ad) => ({ all: () => (ad === 'Gecerli mi?' ? oncekiler : []) }),
    { id: 'lcarlieInsta01' },
    { id: '9999' }
  );

  kontrol('musteri bosluga bakmiyor (cevap var)',
    sonuc.length === 1 && typeof sonuc[0].json.cevap === 'string' && sonuc[0].json.cevap.length > 20);
  kontrol('cevapta insanaAktar=true', sonuc[0].json.insanaAktar === true, JSON.stringify(sonuc[0].json.insanaAktar));
  kontrol('otomatik=false', sonuc[0].json.otomatik === false);

  const kayit = (statik.kayitlar || [])[0];
  kontrol('konusma kaydi yazildi', !!kayit);
  kontrol('kayitta sinif AJAN-HATASI', kayit && kayit.sinif === 'AJAN-HATASI', kayit && kayit.sinif);
  // 🔴 Kimlik kaybolmamali - yoksa musteriye donus yapilamaz
  kontrol('musteri kimligi korundu', kayit && kayit.musteri === '905551112233', kayit && kayit.musteri);
  kontrol('gelen mesaj korundu', kayit && kayit.gelen === 'vireon fiyati nedir', kayit && kayit.gelen);

  const esk = (statik.eskalasyonlar || [])[0];
  kontrol('eskalasyon olusturuldu', !!esk);
  kontrol('eskalasyon acik', esk && esk.kapatildi === false);
  kontrol('eskalasyon sayaci artti', statik.eskalasyonToplam === 1, String(statik.eskalasyonToplam));

  const h = (statik.hatalar || [])[0];
  kontrol('hata kaydi yazildi', !!h);
  const zorunlu = ['ts', 'workflow_id', 'execution_id', 'channel', 'stage', 'error_class', 'error_summary', 'correlation_id'];
  const eksik = h ? zorunlu.filter(a => !(a in h)) : zorunlu;
  kontrol('8 zorunlu alan tam', eksik.length === 0, 'eksik: ' + eksik.join(','));
  kontrol('workflow_id dogru', h && h.workflow_id === 'lcarlieInsta01', h && h.workflow_id);
  kontrol('execution_id dogru', h && h.execution_id === '9999', h && h.execution_id);
  kontrol('channel dogru', h && h.channel === 'instagram', h && h.channel);
  kontrol('stage dogru', h && h.stage === 'ajan', h && h.stage);
  kontrol('error_class dolu', h && h.error_class && h.error_class !== 'BILINMEYEN', h && h.error_class);
  kontrol('correlation_id tasindi', h && h.correlation_id === 'ig-abc123-9f2a', h && h.correlation_id);

  // 🔴 EN ONEMLI KONTROL: hata kaydinda PII OLMAMALI
  const metin = JSON.stringify(h || {});
  kontrol('hata kaydinda telefon YOK', !/905551112233/.test(metin), metin);
  kontrol('hata kaydinda musteri mesaji YOK', !/vireon fiyati nedir/.test(metin), metin);
}

// =====================================================================
console.log('\n--- 4) INSTAGRAM: normal akis degismedi ---');
// =====================================================================
{
  const kod = kodOf(ig, 'Cevabi hazirla');
  const statik = {};
  const ajanCiktisi = [{ json: { gonder: true, cevap: 'VIREON 1.200 TL.', sinif: 'FIYAT',
    insanaAktar: false, musteriId: '905551112233', gelenMesaj: 'vireon fiyati' } }];
  const oncekiler = [{ json: { gecerli: true, mesaj: 'vireon fiyati', musteriId: '905551112233',
    korelasyon: 'ig-xyz-1111' } }];
  const fn = new Function('$getWorkflowStaticData', '$input', '$', '$workflow', '$execution', kod);
  const sonuc = fn(() => statik, { all: () => ajanCiktisi },
    (ad) => ({ all: () => (ad === 'Gecerli mi?' ? oncekiler : []) }),
    { id: 'lcarlieInsta01' }, { id: '1' });

  kontrol('ajan cevabi aynen gidiyor', sonuc[0].json.cevap === 'VIREON 1.200 TL.', sonuc[0].json.cevap);
  kontrol('otomatik=true', sonuc[0].json.otomatik === true);
  kontrol('insanaAktar=false', sonuc[0].json.insanaAktar === false);
  kontrol('gereksiz eskalasyon yok', !(statik.eskalasyonlar || []).length);
  // 🔴 Saglikli akista hata kaydi OLUSMAMALI - yoksa durum sayfasi bos yere kizarir
  kontrol('hata kaydi olusmadi', !(statik.hatalar || []).length, JSON.stringify(statik.hatalar));
}

// =====================================================================
console.log('\n--- 5) WHATSAPP: ajan cokerse ---');
// =====================================================================
{
  const kodYanit = kodOf(wa, 'Yaniti hazirla');
  const kodPilot = kodOf(wa, 'Pilot kaydi');

  const ajanCiktisi = [{ json: { error: 'Active version not found for workflow lcarlieAkis0001' } }];
  const ayiklanan = [{ json: { mesaj: 'kargom nerede', musteriId: '905551112233',
    korelasyon: 'wa-def456-3c7b', telefonNoId: '1234567890', mesajId: 'wamid.HBgMOTA1' } }];

  const fnY = new Function('$input', '$', kodYanit);
  const yanit = fnY({ all: () => ajanCiktisi },
    (ad) => ({
      all: () => (ad === 'Metin mi?' ? ayiklanan : ayiklanan),
      first: () => ayiklanan[0]
    }));

  kontrol('gonderilecek=false (musteriye mesaj GITMEZ)', yanit[0].json.gonderilecek === false);
  kontrol('ajanCokti isaretlendi', yanit[0].json.ajanCokti === true);
  kontrol('insanaAktar=true', yanit[0].json.insanaAktar === true);
  kontrol('musteri kimligi korundu', yanit[0].json.musteriId === '905551112233', yanit[0].json.musteriId);
  kontrol('korelasyon korundu', yanit[0].json.korelasyon === 'wa-def456-3c7b', yanit[0].json.korelasyon);

  const statik = {};
  const fnP = new Function('$getWorkflowStaticData', '$input', '$workflow', '$execution', kodPilot);
  fnP(() => statik, { all: () => yanit }, { id: 'lcarlieWhats001' }, { id: '8888' });

  const p = (statik.pilot || [])[0];
  kontrol('pilot kaydi yazildi', !!p);
  kontrol('pilot sinif AJAN-HATASI', p && p.sinif === 'AJAN-HATASI', p && p.sinif);
  kontrol('pilot insanaAktar=true', p && p.insanaAktar === true);
  kontrol('pilot gonderildi=false', p && p.gonderildi === false);

  const esk = (statik.eskalasyonlar || [])[0];
  kontrol('eskalasyon olusturuldu', !!esk);
  kontrol('eskalasyon sayaci artti', statik.eskalasyonToplam === 1, String(statik.eskalasyonToplam));

  const h = (statik.hatalar || [])[0];
  kontrol('hata kaydi yazildi', !!h);
  kontrol('channel=whatsapp', h && h.channel === 'whatsapp', h && h.channel);
  kontrol('workflow_id dogru', h && h.workflow_id === 'lcarlieWhats001', h && h.workflow_id);
  kontrol('execution_id dogru', h && h.execution_id === '8888', h && h.execution_id);
  kontrol('correlation_id tasindi', h && h.correlation_id === 'wa-def456-3c7b', h && h.correlation_id);

  const metin = JSON.stringify(h || {});
  kontrol('hata kaydinda telefon YOK', !/905551112233/.test(metin), metin);
  kontrol('hata kaydinda mesaj metni YOK', !/kargom nerede/.test(metin), metin);
  kontrol('hata kaydinda wamid YOK', !/wamid\.HBgMOTA1/.test(metin), metin);
}

// =====================================================================
console.log('\n--- 6) WHATSAPP: normal akis degismedi ---');
// =====================================================================
{
  const kodYanit = kodOf(wa, 'Yaniti hazirla');
  const ajanCiktisi = [{ json: { gonder: true, cevap: 'Merhaba!', sinif: 'SELAMLAMA',
    insanaAktar: false, musteriId: '905551112233', kayit: { zaman: 'z', musteriId: '905551112233' } } }];
  const ayiklanan = [{ json: { musteriId: '905551112233', korelasyon: 'wa-1', telefonNoId: '111' } }];
  const fnY = new Function('$input', '$', kodYanit);
  const yanit = fnY({ all: () => ajanCiktisi },
    (ad) => ({ all: () => ayiklanan, first: () => ayiklanan[0] }));

  kontrol('gonderilecek=true', yanit[0].json.gonderilecek === true);
  kontrol('ajanCokti isaretlenmedi', !yanit[0].json.ajanCokti);
  kontrol('Meta govdesi uretildi', yanit[0].json.govde && yanit[0].json.govde.text.body === 'Merhaba!');
  kontrol('telefonNoId tasindi', yanit[0].json.telefonNoId === '111', yanit[0].json.telefonNoId);

  // 🔴 TEK MESAJ = TEK GONDERIM. Coklu oge gelirse coklu cikti olmali,
  //    ama ayni oge IKI KEZ uretilmemeli (duplicate gonderim korumasi).
  const ikiKarar = [ajanCiktisi[0], JSON.parse(JSON.stringify(ajanCiktisi[0]))];
  const ikiOnceki = [ayiklanan[0], { json: { musteriId: '905550000000', korelasyon: 'wa-2', telefonNoId: '111' } }];
  const yanit2 = fnY({ all: () => ikiKarar },
    (ad) => ({ all: () => ikiOnceki, first: () => ikiOnceki[0] }));
  kontrol('2 giris -> 2 cikis (ne eksik ne fazla)', yanit2.length === 2, String(yanit2.length));
}

// --- Ozet ------------------------------------------------------------
console.log('\n----------------------------------------');
console.log('Basarili: ' + basarili);
console.log('Basarisiz: ' + basarisiz);
console.log('----------------------------------------\n');
process.exit(basarisiz > 0 ? 1 : 0);
