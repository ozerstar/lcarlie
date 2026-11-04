import unittest
from types import SimpleNamespace
from jarvis import holding,roster

class HoldingTests(unittest.TestCase):
 def test_unknown_entities_do_not_invent_company_assignments(self):
  s=holding.structure([{'kod':'GOOGLE_ADS'},{'kod':'HR'}],holding.DEFAULT_STRUCTURE)
  self.assertEqual(s['unassigned'],1)
  self.assertEqual(len(s['groups']),2)
 def test_cycles_and_missing_parents_rejected(self):
  for parent in ['a','missing']:
   with self.assertRaises(ValueError):holding.structure([],{'entities':[{'id':'a','name':'A','parent_id':parent}]})
 def test_complete_estimated_cost_is_not_verified_profit(self):
  rows=holding.portfolio([{'urun_adi':'A','ciro_net':100,'brut_marj':50,'kapsama_yuzde':100}],[{'urun_adi':'A','maliyet_kaynagi':'tahmini maliyet'}])
  self.assertEqual(rows[0]['reliability'],'Tahmini maliyet')
  self.assertFalse(rows[0]['confirmed_profit'])
 def test_duplicate_names_and_nonfinite_values_are_not_silently_matched(self):
  rows=holding.portfolio([{'urun_adi':'A','ciro_net':'NaN'}],[{'urun_adi':'A'},{'urun_adi':'A'}])
  self.assertIsNone(rows[0]['revenue'])
  self.assertEqual(rows[0]['cost_source'],'Kaynak eşleşmesi yok')
 def test_source_failure_stays_visible(self):
  class Memory:
   def _fetch(self,q):
    if q=='agenda':raise RuntimeError('secret')
    return SimpleNamespace(records=[],source='test',retrieved_at=None)
  result=holding.snapshot(Memory())
  self.assertEqual(next(s for s in result['sources'] if s['query']=='agenda')['status'],'unavailable')
  self.assertTrue(result['read_only'])
 def test_retention_uses_actual_order_field_and_unknown_denominator(self):
  text=roster._say_tekrar_satin_alma({'crm_customers':[{'siparis_tum_zaman':2},{'siparis_tum_zaman':1},{}]})
  self.assertIn('%50',text)
  self.assertIn('1 müşteride sipariş sayısı bilinmiyor',text)
 def test_cro_has_real_source_and_cannot_claim_data_when_empty(self):
  member=next(m for m in roster.ROSTER if m.key=='CRO_SPECIALIST')
  self.assertIn('ecommerce_funnel',member.reads)

if __name__=='__main__':unittest.main()
