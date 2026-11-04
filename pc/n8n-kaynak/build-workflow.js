// Mevzuat filtresi JS'ini okuyup n8n workflow JSON'una gomer.
// Elle escape etmeye gerek kalmaz.
const fs = require('fs');

let kod = fs.readFileSync('/tmp/mevzuat-filtresi.js', 'utf8');
// module.exports satirini cikar (n8n Code node'unda gereksiz)
kod = kod.replace(/module\.exports[\s\S]*$/m, '').trimEnd();

const nodeKodu = kod + `

// ===================== n8n GIRIS / CIKIS =====================
// Girdi:  { metin: "...", kaynak: "whatsapp|instagram|site", musteriId: "..." }
// Cikti:  { sonuc, etiket, insanaAktar, mesaj, bulgular[], kayit{} }
return $input.all().map(item => {
  const g = item.json || {};
  const metin = g.metin ?? g.text ?? g.mesaj ?? '';
  return {
    json: mevzuatFiltresi(metin, {
      kaynak: g.kaynak || 'bilinmiyor',
      musteriId: g.musteriId || null
    })
  };
});
`;

const workflow = [{
  id: 'lcarlieMevzuat01',
  name: 'MEVZUAT FILTRESI - her mesaj once buradan gecer',
  active: false,
  nodes: [
    {
      parameters: { inputSource: 'passthrough' },
      id: 'aaaaaaaa-0000-4000-8000-000000000001',
      name: 'Cagrildiginda',
      type: 'n8n-nodes-base.executeWorkflowTrigger',
      typeVersion: 1.1,
      position: [0, 0]
    },
    {
      parameters: { jsCode: nodeKodu },
      id: 'aaaaaaaa-0000-4000-8000-000000000002',
      name: 'Mevzuat Filtresi',
      type: 'n8n-nodes-base.code',
      typeVersion: 2,
      position: [240, 0]
    }
  ],
  connections: {
    'Cagrildiginda': { main: [[{ node: 'Mevzuat Filtresi', type: 'main', index: 0 }]] }
  },
  settings: { executionOrder: 'v1' }
}];

fs.writeFileSync('/tmp/mevzuat-workflow.json', JSON.stringify(workflow, null, 2));
console.log('Workflow JSON yazildi. Kod uzunlugu: ' + nodeKodu.length + ' karakter');
