'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { parseAndValidate, responseHash } = require('../deploy/question-worker-phase2b');

const good = { soru: 'Neyi bilmiyoruz?', neden_onemli: 'Karar icin', kaynak_plani: 'Iki kaynak', oncelik: 'P1', beklenen_bilgi_degeri: 'YUKSEK' };

test('accepts exact schema', () => assert.deepEqual(parseAndValidate(JSON.stringify(good)), good));
test('rejects prose wrapped JSON', () => assert.throws(() => parseAndValidate(`result: ${JSON.stringify(good)}`), /INVALID_JSON/));
test('rejects truncated JSON', () => assert.throws(() => parseAndValidate('{"soru":'), /INVALID_JSON/));
test('rejects empty output', () => assert.throws(() => parseAndValidate(''), /INVALID_JSON/));
test('rejects extra fields and approval injection', () => assert.throws(() => parseAndValidate(JSON.stringify({ ...good, approved: true })), /INVALID_SCHEMA/));
test('hashes without logging response content', () => assert.match(responseHash('secret response'), /^[a-f0-9]{64}$/));
