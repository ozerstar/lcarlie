import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from jarvis import office_operations as ops
from jarvis.office_answer_guard import percent, metrics, prepare, validate, answer

class OfficeOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ops.Store(self.tmp.name)
        self.items = [dict(id='one', title='Stok kaydını kontrol et', source='Stok', fingerprint='a', department='WEB', status='open', version=0)]
        self.members = {'WEB': (SimpleNamespace(key='web', name='Web sorumlusu'),)}
        self.body = dict(id='one', department='WEB', owner='web', due='2026-11-01', status='progress', note='Kaynak bekleniyor', version=0)

    def test_assignment_persists_and_stale_editor_cannot_overwrite(self):
        item = self.store.save(self.body, 'operator', self.items, self.members)
        self.assertEqual(item['version'], 1)
        self.assertEqual(ops.Store(self.tmp.name).all()['one']['owner'], 'web')
        with self.assertRaises(ops.Conflict):
            self.store.save(self.body, 'operator', self.items, self.members)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audits').fetchone()[0], 1)

    def test_owner_date_status_and_resolution_validated(self):
        for values in [dict(owner='other'),dict(due='yesterday'),dict(status='resolved',note=''),dict(department='FAKE')]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.store.save(dict(self.body, **values), 'operator', self.items, self.members)

    def test_acknowledgement_is_per_operator_and_content(self):
        self.store.acknowledge('a','one','digest')
        self.assertEqual(self.store.acknowledged('a'), {'one':'digest'})
        self.assertEqual(self.store.acknowledged('b'), {})
        self.assertNotEqual(self.store.acknowledged('a')['one'], 'new-content')

    def test_same_cycle_refresh_is_not_repeated_failure(self):
        report = {'generated_at':'2026-10-26T01:00:00Z','activity':{'web':{'status':'ERROR'}}}
        self.assertEqual(self.store.observe(report), {})
        self.assertEqual(self.store.observe(report), {})
        report['generated_at']='2026-10-26T02:00:00Z'
        self.assertEqual(self.store.observe(report), {'web':2})
        report['generated_at']='2026-10-26T03:00:00Z'
        report['activity']['web']['status']='WORKED'
        self.assertEqual(self.store.observe(report), {})

    def test_product_join_exact_id_and_unique_sku_only(self):
        rows={'urun_karti':[{'urun_id':'p1','urun_adi':'Sabun','sku':'s1','wix_gorsel':5}, {'urun_id':'p2','urun_adi':'Sabun','sku':'s2'}],
              'ecommerce_profitability':[{'entity_id':'p2','ciro_net':20}]}
        catalog={'urunler':[{'sku':'s1','gorseller':['../secret.jpg','soap.webp']} ]}
        out=ops.products(rows,catalog)
        self.assertIsNone(out[0]['net_revenue'])
        self.assertEqual(out[1]['net_revenue'],20)
        self.assertEqual(out[0]['image'],'/katalog-gorsel/soap.webp')
        self.assertIsNone(out[1]['image'])
        catalog['urunler'].append({'sku':'s1','gorseller':['other.webp']})
        self.assertIsNone(ops.products(rows,catalog)[0]['image'])

    def test_snapshot_preserves_unseen_work_and_unknown_due(self):
        self.store.save(self.body,'operator',self.items,self.members)
        rows={q:[] for q in ops.QUERIES}
        rows['open_work']=[{'tur':'stock','anahtar':'p1','detay':'Stok kontrolü','zaman':'2000-01-01'}]
        reads={q:{'ok':True,'at':'2026-10-26'} for q in ops.QUERIES}
        with patch.object(ops,'read_snapshot',return_value=(rows,reads)):
            result=ops.snapshot(None,self.tmp.name)
        previous=next(i for i in result['items'] if i['id']=='one')
        self.assertFalse(previous['observed'])
        self.assertEqual(previous['status'],'progress')
        new=next(i for i in result['items'] if i['id']!='one')
        self.assertFalse(new['overdue'])
        self.assertEqual(new['due'],'')

class AnswerGuardTests(unittest.TestCase):
    def test_percentage_direction_and_missing_denominator(self):
        self.assertEqual(percent(20,36),'55,6')
        self.assertEqual(percent(16,36),'44,4')
        self.assertIsNone(percent(0,0))
        data={'urun_karti':{'source':'Ürünler','at':'today','records':[{'urun_id':str(i)} for i in range(36)]},'ecommerce_profitability':{'source':'Kârlılık','at':'today','records':[{'entity_id':str(i)} for i in range(20)]}}
        text=' '.join(i['summary'] for i in metrics(data))
        self.assertIn('Eşleşen oran %55,6',text)
        self.assertIn('eşleşmeyen oran %44,4',text)
        self.assertIn('sorgusu sınırlıdır',text)

    def test_wrong_quote_and_invented_source_rejected(self):
        prepared=prepare([{'ref':'Stok','summary':'Kaynakta 20 ürün bulunuyor.','at':'today'}],{})
        for row in [{'kaynak':'K1','alinti':'Kaynakta 30 ürün bulunuyor.'},{'kaynak':'K99','alinti':'Kaynakta 20 ürün bulunuyor.'}]:
            self.assertIsNone(validate(json.dumps({'bulgular':[row]}),prepared))
        valid=validate(json.dumps({'bulgular':[{'kaynak':'K1','alinti':'Kaynakta 20 ürün bulunuyor.'}],'oneriler':['30 gün bekleyin','Kaynağı yeniden kontrol etmeyi değerlendirin.']}),prepared)
        self.assertEqual(len(valid['oneriler']),1)

    def test_unavailable_model_returns_evidence_not_fake_completion(self):
        router=SimpleNamespace(synthesize=lambda *a,**k:SimpleNamespace(answer='Invalid answer'))
        result=answer('Ne yaptın?',[{'ref':'Ekip kaydı','summary':'Son ekip döngüsü girdi bekliyor.'}],{},router,lambda call:call())
        self.assertFalse(result['model_kullanildi'])
        self.assertIn('Müdür yorumu doğrulanamadı',result['cevap'])
        self.assertIn('Son ekip döngüsü girdi bekliyor.',result['cevap'])

if __name__=='__main__':
    unittest.main()
