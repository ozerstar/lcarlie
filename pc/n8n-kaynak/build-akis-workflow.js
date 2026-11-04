const fs = require('fs');

// Urun bilgi tabani ONCE gelir - fonksiyonlari motor tarafindan kullanilir.
let urunler = fs.readFileSync('/tmp/urunler.js', 'utf8');
urunler = urunler.replace(/if \(typeof module[\s\S]*$/m, '').trimEnd();

let motorHam = fs.readFileSync('/tmp/akis-motoru.js', 'utf8');
motorHam = motorHam.replace(/module\.exports[\s\S]*$/m, '').trimEnd();
// n8n'de require yok; urunler zaten yukarida gomulu, require shim'i cikar.
motorHam = motorHam.replace(
  /if \(typeof urunTani === 'undefined'\) \{[\s\S]*?\n\}/m,
  '// (urun bilgi tabani yukarida gomulu)'
);

const motor = urunler + '\n\n' + motorHam;

const kod1 = motor + `

// ===== n8n: gelen mesaji sinifla ve taslak cevap uret =====

// 🔴 BU WORKFLOW TEK MESAJ ISLER - COKLU GELIRSE SESSIZ KAYIP OLUR.
//
// Asagidaki dugumler ('2a', '3a', '4. Karar') $json ve .first() kullanarak
// tek ogeye iniyor. Yani birden fazla mesaj gelirse ILKI DISINDAKILER
// HATA VERMEDEN DUSER - ustelik 4. dugum, hayatta kalan mesaj icin
// ILK mesajin filtre sonucunu okur. Bu, projede uc kez yasanan hatanin
// ta kendisi.
//
// Bugun guvenli: cagiran dort kanal da 'mode: each' kullaniyor, yani her
// mesaj icin bu workflow ayri calisiyor. Ama biri n8n arayuzunden elle
// 'once' yaparsa ya da yeni bir kanal 'yeni-kanal.js' kullanmadan
// baglanirsa, mesajlar sessizce kaybolmaya baslar.
//
// Coklu ogeye tam destek, calisan satis ajaninin cekirdegini yeniden
// yazmayi gerektiriyor (filtre alt workflow cagrilari dahil). Gizli bir
// riski kovalarken gercek risk uretmemek icin bunun yerine SESSIZ KAYIP
// GURULTULU HATAYA cevrildi: artik cagiran tarafta hata yolu var
// (onError: continueRegularOutput), yani musteri yine notr cevap alir ve
// konusma insana aktarilir - kaybolmaz.
const gelenler = $input.all();
if (gelenler.length > 1) {
  throw new Error(
    'AKIS AJANI TEK MESAJ ISLER ama ' + gelenler.length + ' mesaj geldi. ' +
    'Cagiran dugumde "mode: each" olmali (su an muhtemelen "once"). ' +
    'Bu haliyle ilk mesaj disindakiler sessizce duserdi.'
  );
}

return gelenler.map(item => ({ json: akisMotoru(item.json || {}) }));
`;

const kod4 = motor + `

// ===== n8n: iki filtre sonucunu birlestirip karar ver =====
const motorCiktisi = $('1. Motor - sinifla ve taslak uret').first().json;
const gelenFiltre  = $('2b. Filtre - GELEN mesaj').first().json;
const taslakFiltre = $('3b. Filtre - TASLAK cevap').first().json;

const karar = kararVer(motorCiktisi, gelenFiltre, taslakFiltre);

// Ispat kulfeti / satis takibi kaydi
karar.kayit = {
  zaman: karar.zaman,
  kanal: karar.kanal,
  musteriId: karar.musteriId,
  gelenMesaj: karar.mesaj,
  sinif: karar.sinif,
  gonderildi: karar.gonder,
  gonderilenCevap: karar.gonder ? karar.cevap : null,
  insanaAktarildi: karar.insanaAktar,
  satisKaybi: karar.satisKaybi,
  optOut: karar.optOutKaydi,
  gelenFiltreSonucu: gelenFiltre?.sonuc || null,
  taslakFiltreSonucu: taslakFiltre?.sonuc || null,
  gerekceler: karar.gerekceler
};

return [{ json: karar }];
`;

const altWf = (ad, id, x) => ({
  parameters: {
    workflowId: { __rl: true, value: 'lcarlieMevzuat01', mode: 'id' },
    options: {}
  },
  id, name: ad, type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2,
  position: [x, 0]
});

const kodNode = (ad, id, x, js) => ({
  parameters: { jsCode: js },
  id, name: ad, type: 'n8n-nodes-base.code', typeVersion: 2,
  position: [x, 0]
});

const workflow = [{
  id: 'lcarlieAkis0001',
  name: 'SATIS AJANI - konusma akisi (kanal bagimsiz)',
  active: false,
  nodes: [
    {
      parameters: { inputSource: 'passthrough' },
      id: 'bbbbbbbb-0000-4000-8000-000000000001',
      name: 'Cagrildiginda',
      type: 'n8n-nodes-base.executeWorkflowTrigger',
      typeVersion: 1.1,
      position: [0, 0]
    },
    kodNode('1. Motor - sinifla ve taslak uret', 'bbbbbbbb-0000-4000-8000-000000000002', 220, kod1),
    kodNode('2a. Gelen mesaji hazirla', 'bbbbbbbb-0000-4000-8000-000000000003', 440,
      `return [{ json: { metin: $json.mesaj || '', kaynak: 'gelen', musteriId: $json.musteriId } }];`),
    altWf('2b. Filtre - GELEN mesaj', 'bbbbbbbb-0000-4000-8000-000000000004', 660),
    kodNode('3a. Taslagi hazirla', 'bbbbbbbb-0000-4000-8000-000000000005', 880,
      `const m = $('1. Motor - sinifla ve taslak uret').first().json;
return [{ json: { metin: m.taslakCevap || '', kaynak: 'taslak', musteriId: m.musteriId } }];`),
    altWf('3b. Filtre - TASLAK cevap', 'bbbbbbbb-0000-4000-8000-000000000006', 1100),
    kodNode('4. Karar', 'bbbbbbbb-0000-4000-8000-000000000007', 1320, kod4)
  ],
  connections: {
    'Cagrildiginda':                      { main: [[{ node: '1. Motor - sinifla ve taslak uret', type: 'main', index: 0 }]] },
    '1. Motor - sinifla ve taslak uret':  { main: [[{ node: '2a. Gelen mesaji hazirla',          type: 'main', index: 0 }]] },
    '2a. Gelen mesaji hazirla':           { main: [[{ node: '2b. Filtre - GELEN mesaj',          type: 'main', index: 0 }]] },
    '2b. Filtre - GELEN mesaj':           { main: [[{ node: '3a. Taslagi hazirla',               type: 'main', index: 0 }]] },
    '3a. Taslagi hazirla':                { main: [[{ node: '3b. Filtre - TASLAK cevap',         type: 'main', index: 0 }]] },
    '3b. Filtre - TASLAK cevap':          { main: [[{ node: '4. Karar',                          type: 'main', index: 0 }]] }
  },
  settings: { executionOrder: 'v1' }
}];

fs.writeFileSync('/tmp/akis-workflow.json', JSON.stringify(workflow, null, 2));
console.log('Yazildi. Node sayisi: ' + workflow[0].nodes.length);
