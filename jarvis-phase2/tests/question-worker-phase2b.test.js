'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { parseAndValidate, responseHash, runDeterministicProviderChain } = require('../deploy/question-worker-phase2b');

const good = { soru: 'Neyi bilmiyoruz?', neden_onemli: 'Karar icin', kaynak_plani: 'Iki kaynak', oncelik: 'P1', beklenen_bilgi_degeri: 'YUKSEK' };

test('accepts exact schema', () => assert.deepEqual(parseAndValidate(JSON.stringify(good)), good));
test('rejects prose wrapped JSON', () => assert.throws(() => parseAndValidate(`result: ${JSON.stringify(good)}`), /INVALID_JSON/));
test('rejects markdown wrapped JSON', () => assert.throws(() => parseAndValidate('```json\n' + JSON.stringify(good) + '\n```'), /INVALID_JSON/));
test('rejects truncated JSON', () => assert.throws(() => parseAndValidate('{"soru":'), /INVALID_JSON/));
test('rejects empty output', () => assert.throws(() => parseAndValidate(''), /INVALID_JSON/));
test('rejects extra fields and approval injection', () => assert.throws(() => parseAndValidate(JSON.stringify({ ...good, approved: true })), /INVALID_SCHEMA/));
test('hashes without logging response content', () => assert.match(responseHash('secret response'), /^[a-f0-9]{64}$/));
test('falls back deterministically without a partial write', async () => {
  const result = await runDeterministicProviderChain([
    { name: 'provider-a', call: async () => 'not json' },
    { name: 'provider-b', call: async () => JSON.stringify(good) },
  ]);
  assert.equal(result.provider, 'provider-b');
  assert.deepEqual(result.payload, good);
});
test('fails safe when every provider fails', async () => {
  await assert.rejects(
    runDeterministicProviderChain([{ name: 'provider-a', call: async () => '' }]),
    /ALL_PROVIDERS_FAILED/,
  );
});
