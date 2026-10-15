const assert = require('node:assert/strict');
require('../static/display-text.js');

const m = globalThis.JarvisMetin;
const cases = [
  ['extreme macro of matte sage green mineral surface with fine water film, cool eucalyptus tones, soft even light, continuous uninterrupted surface, editorial text', 'Adaçayı tonlarında mineral yüzey görseli'],
  ['extreme macro of soft cotton muslin weave, milk white fibres, pale cool blue light, gentle shallow focus, continuous fabric surface, calm, editorial texture pho', 'Beyaz pamuklu kumaş görseli'],
  ['extreme macro of folded matte silk textile, soft deep rose and muted plum shadow, gentle fabric curve, very soft diffused light, no pattern, continuous surface', 'Gül ve erik tonlarında ipek kumaş görseli'],
  ['extreme macro of dry cracked terracotta clay surface, fine fissures, warm sand and burnt ochre tones, soft directional light grazing the cracks, continuous surf', 'Toprak tonlarında çatlak kil görseli'],
];
for (const [istem, expected] of cases) assert.equal(m.jobTitle({istem}), expected);
assert.equal(m.jobTitle({istem:'Müşteriye taslak hazırla'}), 'Müşteriye taslak hazırla');
assert.equal(m.jobTitle({id:'ktb-yuz', isteyen:'katalog/bolum-acilisi', istem:cases[0][0]}), 'Katalog görseli: Yüz');
assert.equal(m.source({isteyen:'mobil-operator'}), 'Telefondan istendi');
assert.equal(m.safeTitle('internal_data_analysis: SUCCEEDED', 'Planlı çalışma'), 'Planlı çalışma');
assert.equal(m.errorText('HTTP 500 Internal Server Error', 'İşlem yapılamadı.'), 'İşlem yapılamadı.');
assert.equal(m.errorText('Gerekli alan eksik.', 'İşlem yapılamadı.'), 'Gerekli alan eksik.');
console.log('Görünen metin kontrolleri geçti.');
