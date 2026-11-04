import test from 'node:test';
import assert from 'node:assert/strict';
import {displayText,errorText} from './src/turkish.js';
test('Turkish labels, errors, names and identities',()=>{
 assert.equal(displayText('GOOGLE_ADS'),'Google arama reklamları');
 assert.equal(displayText('ecommerce_profitability'),'Ürün kârlılığı');
 assert.equal(displayText('Müşteri kaydı (DATA_BI)'),'Müşteri kaydı — Veri ve iş zekâsı —');
 assert.match(errorText('no model provider could answer'),/Yanıt hizmeti/);
 assert.match(displayText('Failed to fetch'),/İşlem tamamlanamadı/);
 assert.equal(displayText('moy_test@example.com'),'moy_test@example.com');
 assert.equal(displayText('https://example.com/test_page'),'https://example.com/test_page');
 assert.equal(displayText('İş Birliği ve Influencer Sorumlusu'),'İş Birliği ve İçerik Üreticisi Sorumlusu');
 assert(!displayText('The provider cannot answer your request.').includes('provider'));
});
