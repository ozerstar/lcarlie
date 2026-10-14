import unittest
from jarvis.data_completion import ga4_replace_sql,conversation_sql


class RefreshTests(unittest.TestCase):
    def funnel(self,n='1'):
        return [{'date':'20261014','eventName':'page_view','eventCount':n}]

    def test_replaces_actual_granularity_not_nonexistent_state(self):
        sql,count=ga4_replace_sql(self.funnel(),[],'2026-10-14','2026-10-14')
        self.assertIn("granulerlik='GUNLUK_TOPLAM'",sql)
        self.assertNotIn('GA4_AGGREGATE',sql)
        self.assertTrue(sql.startswith('BEGIN;'))
        self.assertTrue(sql.endswith('COMMIT;'))
        self.assertEqual(count,1)

    def test_changed_daily_count_is_present(self):
        sql,_=ga4_replace_sql(self.funnel('35'),[],'2026-10-14','2026-10-14')
        self.assertIn('35',sql)
        self.assertLess(sql.index('DELETE FROM'),sql.index('INSERT INTO raw.ga4_event'))

    def test_empty_report_cannot_delete(self):
        with self.assertRaises(ValueError):ga4_replace_sql([],[],'2026-10-14','2026-10-14')

    def test_invalid_date_cannot_delete(self):
        with self.assertRaises(ValueError):ga4_replace_sql([{'date':'bad','eventName':'x','eventCount':'1'}],[],'2026-10-14','2026-10-14')

    def test_outside_interval_rejected(self):
        with self.assertRaises(ValueError):ga4_replace_sql(self.funnel(),[],'2026-10-01','2026-10-13')

    def test_nonfinite_purchase_rejected(self):
        with self.assertRaises(ValueError):ga4_replace_sql(self.funnel(),[{'date':'20261014','transactionId':'x','purchaseRevenue':'NaN'}],'2026-10-14','2026-10-14')

    def test_unidentified_purchase_is_not_invented_transaction(self):
        _,count=ga4_replace_sql(self.funnel(),[{'date':'20261014','transactionId':'(not set)','purchaseRevenue':'40'}],'2026-10-14','2026-10-14')
        self.assertEqual(count,1)

    def conv(self):
        return {'id':'conv-1','participants':{'data':[{'id':'brand'},{'id':'customer'}]}}

    def msg(self,sender='customer',body="Hello ' quoted"):
        return {'id':'m1','created_time':'2026-10-14T10:00:00+00:00','from':{'id':sender},'message':body}

    def test_direction_is_from_verified_sender(self):
        incoming=conversation_sql('instagram',self.conv(),[self.msg()],{'brand'},True)
        outgoing=conversation_sql('instagram',self.conv(),[self.msg('brand')],{'brand'},True)
        self.assertIn("'gelen'",incoming);self.assertIn("'giden'",outgoing)
        self.assertIn('ON CONFLICT(konusma_id,harici_id)',incoming)

    def test_unknown_sender_rejected(self):
        with self.assertRaises(ValueError):conversation_sql('instagram',self.conv(),[self.msg('unknown')],{'brand'},True)

    def test_ambiguous_customer_rejected(self):
        r=self.conv();r['participants']['data'].append({'id':'other'})
        with self.assertRaises(ValueError):conversation_sql('instagram',r,[self.msg()],{'brand'},True)

    def test_sql_text_is_escaped_and_no_outbound_api(self):
        sql=conversation_sql('messenger',self.conv(),[self.msg(body="a'; DROP TABLE x; --")],{'brand'},False)
        self.assertIn("a''; DROP TABLE",sql)
        self.assertNotIn('https://',sql)
        self.assertIn('history_complete',sql)

    def test_manual_outcome_not_overwritten(self):
        sql=conversation_sql('messenger',self.conv(),[self.msg()],{'brand'},True)
        self.assertNotIn('sonuc=',sql);self.assertNotIn('siparis_no=',sql)
