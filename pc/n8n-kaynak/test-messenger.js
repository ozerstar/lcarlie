// =============================================================================
// MESSENGER KANALI - GIRIS KAPISI TESTI
//
// Neyi sinar: uretilmis workflow'un "Mesajlari ayikla" dugumunu GERCEK Meta
// zarfiyla calistirir. Kaynak dosyayi degil, URETILMIS JSON'u okur -- yani
// "kod dogru ama uretilen workflow'a girmemis" durumunu da yakalar.
//
// 🔴 EN KRITIK VAKA: is_echo. Messenger kendi gonderdigimiz mesaji bize geri
//    bildirir. Elenmezse cevap -> echo -> cevap dongusu olusur, Meta bunu
//    spam sayar ve sayfayi kisitlar. Bu testin var olma sebebi odur.
// =============================================================================
'use strict';
const fs = require('fs');
const vm = require('vm');

const YOL = '/tmp/messenger-workflow.json';

// 🔴 TEST, URETIMDEN ONCE KOSAR. n8n-yayinla.sh sirasi: kaynak kopyala (2/7)
//    -> TESTLER (3/7) -> workflow uret (4/7). Yani test calistiginda JSON
//    HENUZ YOKTUR ve dosyayi dogrudan okumak ENOENT verir. Bu projede
//    "eksik test = basarisiz test" kurali oldugu icin bu, saglam bir
//    yayini kilitlerdi. Cozum: yoksa ureticiyi burada calistir.
if (!fs.existsSync(YOL)) {
  const URETICI = '/tmp/build-messenger-workflow.js';
  if (!fs.existsSync(URETICI)) {
    console.log('HATA: ne ' + YOL + ' ne de ' + URETICI + ' var');
    process.exit(1);
  }
  // 🔴 SAHTE DOGRULAMA ANAHTARI - BILEREK.
  //    Uretici, anahtar verilmezse PATLAR (canli WhatsApp'ta placeholder'in
  //    sessizce kalmis olmasi yuzunden oyle yapildi). Bu test dogrulama
  //    dugumune HIC dokunmuyor, yalniz "Mesajlari ayikla"yi sinar; o yuzden
  //    burada sahte bir anahtar yeterli. Gercek anahtar yayin hattinin
  //    uretim adiminda .env'den gecirilir ve bu dosyayi EZER.
  require('child_process').execFileSync(process.execPath, [URETICI], {
    stdio: 'ignore',
    env: Object.assign({}, process.env, { MESSENGER_VERIFY_TOKEN: 'test-sahte-anahtar', MESSENGER_PANEL_TOKEN: 'test-sahte-panel' })
  });
}
const SAYFA = '1222783064240254';
const MUSTERI = '9876543210';
const SAAT = 60 * 60 * 1000;

let basarili = 0, basarisiz = 0;
function kontrol(ad, kosul, ek) {
  if (kosul) { basarili++; console.log('  GECTI   ' + ad); }
  else { basarisiz++; console.log('  HATA    ' + ad + (ek ? '  -> ' + ek : '')); }
}

const wf = JSON.parse(fs.readFileSync(YOL, 'utf8'))[0];
const dugum = wf.nodes.find(n => n.name === 'Mesajlari ayikla');
if (!dugum) { console.log('HATA: "Mesajlari ayikla" dugumu yok'); process.exit(1); }

// --- n8n ortami taklidi -----------------------------------------------------
function calistir(govdeler, statik) {
  const sd = statik || {};
  const items = govdeler.map(b => ({ json: { body: b } }));
  const sandbox = {
    $input: { all: () => items, first: () => items[0] },
    $getWorkflowStaticData: () => sd,
    console,
    module: {}, require,
    korelasyonUret: p => p + '-sahte',
    trafikSinifi: id => (String(id).indexOf('test-') === 0 ? 'test' : 'production')
  };
  const kod = '(function(){' + dugum.parameters.jsCode + '})()';
  const sonuc = vm.runInNewContext(kod, sandbox, { timeout: 5000 });
  return { sonuc, sd };
}

// Kaynak dosya kimlik.js/hata-kaydi.js yardimcilarini GOMUYOR; testte onlari
// sandbox'tan veriyoruz. Gomulu tanimlari kaldir ki cakismasin.
dugum.parameters.jsCode = dugum.parameters.jsCode
  .replace(/^[\s\S]*?\/\/ ===== n8n: Meta Messenger payload'ini ayikla =====/, '');

const msj = (opts) => ({
  entry: [{
    id: SAYFA,
    messaging: [Object.assign({
      sender: { id: MUSTERI },
      recipient: { id: SAYFA },
      timestamp: Date.now(),
      message: { mid: 'm-' + Math.random().toString(36).slice(2), text: 'merhaba' }
    }, opts)]
  }]
});

console.log('MESSENGER GIRIS KAPISI');
console.log('');

// 1) Normal metin mesaji gecer
{
  const { sonuc } = calistir([msj({})]);
  const g = sonuc.filter(x => x.json.metinMi);
  kontrol('normal metin mesaji gecer', g.length === 1, 'cikan=' + sonuc.length);
  kontrol('kanal messenger yazilir', g[0] && g[0].json.kanal === 'messenger');
  kontrol('24 saat penceresi ACIK isaretlenir', g[0] && g[0].pencereIcinde !== false && g[0].json.pencereIcinde === true);
}

// 2) 🔴 ECHO ELENIR - bu testin ana sebebi
{
  const { sonuc } = calistir([msj({
    sender: { id: SAYFA }, recipient: { id: MUSTERI },
    message: { mid: 'e1', text: 'bizim cevabimiz', is_echo: true }
  })]);
  const gecen = sonuc.filter(x => x.json.metinMi);
  kontrol('is_echo mesaji ELENIR (sonsuz dongu korumasi)', gecen.length === 0,
          'gecen=' + gecen.length);
}

// 3) Gonderen sayfanin kendisi ise elenir (is_echo gelmese bile)
{
  const { sonuc } = calistir([msj({
    sender: { id: SAYFA },
    message: { mid: 'e2', text: 'sayfadan' }
  })]);
  kontrol('gonderen = sayfa ise ELENIR', sonuc.filter(x => x.json.metinMi).length === 0);
}

// 4) Mesaj olmayan olaylar elenir
{
  const olaylar = {
    entry: [{ id: SAYFA, messaging: [
      { sender: { id: MUSTERI }, recipient: { id: SAYFA }, delivery: { mids: ['x'] } },
      { sender: { id: MUSTERI }, recipient: { id: SAYFA }, read: { watermark: 1 } },
      { sender: { id: MUSTERI }, recipient: { id: SAYFA }, reaction: { emoji: '👍' } }
    ] }]
  };
  const { sonuc } = calistir([olaylar]);
  kontrol('delivery/read/reaction ajana GITMEZ', sonuc.filter(x => x.json.metinMi).length === 0);
}

// 5) Ayni mid iki kez gelirse ikincisi elenir (Meta tekrar gonderimi)
{
  const sd = {};
  const govde = msj({ message: { mid: 'tekrar-1', text: 'ayni mesaj' } });
  const a = calistir([govde], sd);
  const b = calistir([govde], sd);
  kontrol('ilk gelisinde islenir', a.sonuc.filter(x => x.json.metinMi).length === 1);
  kontrol('ayni mid ikinci kez ELENIR', b.sonuc.filter(x => x.json.metinMi).length === 0,
          'gecen=' + b.sonuc.filter(x => x.json.metinMi).length);
}

// 6) 24 saatten eski mesaj pencere DISI isaretlenir
{
  const { sonuc } = calistir([msj({ timestamp: Date.now() - 30 * SAAT })]);
  const g = sonuc.filter(x => x.json.metinMi)[0];
  kontrol('30 saat once gelen mesaj pencere DISI', g && g.json.pencereIcinde === false);
}

// 7) Zaman damgasi okunamazsa pencere ACIK SAYILMAZ
{
  const { sonuc } = calistir([msj({ timestamp: 'bozuk' })]);
  const g = sonuc.filter(x => x.json.metinMi)[0];
  kontrol('okunamayan damga -> pencere KAPALI sayilir (tahmin uretmez)',
          g && g.json.pencereIcinde === false && g.json.damgaGecerli === false);
}

// 8) Metin olmayan mesaj isaretlenir (insana gider)
{
  const { sonuc } = calistir([msj({
    message: { mid: 'a1', attachments: [{ type: 'image', payload: {} }] }
  })]);
  const g = sonuc[0];
  kontrol('gorsel mesaj metinMi=false', g && g.json.metinMi === false);
  kontrol('gorsel mesaj tipi yazilir', g && g.json.mesajTipi === 'image');
}

// 9) Tek cagride birden cok mesaj -> hepsi ayri item
{
  const cok = { entry: [{ id: SAYFA, messaging: [
    { sender: { id: '111' }, recipient: { id: SAYFA }, timestamp: Date.now(), message: { mid: 'c1', text: 'bir' } },
    { sender: { id: '222' }, recipient: { id: SAYFA }, timestamp: Date.now(), message: { mid: 'c2', text: 'iki' } },
    { sender: { id: '333' }, recipient: { id: SAYFA }, timestamp: Date.now(), message: { mid: 'c3', text: 'uc' } }
  ] }] };
  const { sonuc } = calistir([cok]);
  kontrol('tek cagrideki 3 mesajin 3u de cikar',
          sonuc.filter(x => x.json.metinMi).length === 3,
          'cikan=' + sonuc.filter(x => x.json.metinMi).length);
}

// 10) PII sizmaz: mid korelasyon kimligine girmez
{
  const { sonuc } = calistir([msj({ message: { mid: 'GIZLI-MID-123', text: 'selam' } })]);
  const g = sonuc.filter(x => x.json.metinMi)[0];
  kontrol('korelasyon kimligi mid tasimaz',
          g && String(g.json.korelasyon).indexOf('GIZLI-MID-123') === -1);
}

// 11) Kisi basi hiz siniri calisir
{
  const sd = {};
  let gecen = 0;
  for (let i = 0; i < 25; i++) {
    const r = calistir([msj({ message: { mid: 'h' + i, text: 'spam ' + i } })], sd);
    gecen += r.sonuc.filter(x => x.json.metinMi).length;
  }
  kontrol('kisi basi hiz siniri 20de durur', gecen === 20, 'gecen=' + gecen);
}

console.log('');
console.log('Basarili: ' + basarili);
console.log('Basarisiz: ' + basarisiz);
process.exit(basarisiz > 0 ? 1 : 0);
