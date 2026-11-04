import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cari
import cari_channels as channels


def observation(source='wix', **changes):
    return dict({'source':source,'store_id':'store-a','store_name':'Test store',
        'object_id':'order-123','event_key':'event-123','currency':'TRY',
        'source_updated_at':'2026-01-10T12:00:00+03:00','customer_name':'Test customer',
        'status':'processing' if source in channels.ORDER_SOURCES else 'pending',
        'gross_amount':'120.00'}, **changes)


def row(body, identifier='test-event'):
    return {'event_id':identifier,'created_at':'2026-01-10T10:00:00+00:00',
            'payload':channels.normalize(body)}


class ChannelProjectionTests(unittest.TestCase):
    def test_malformed_enum_types_are_validation_errors(self):
        invalid=[dict(observation(),source=[]), observation(status=[]), observation(payment_status={}),
                 observation(invoice={'status':[]}), observation(invoice={'platform_status':[]}),
                 observation(evidence_kind=[]), observation('qnb_pos',order_link={'source':[]})]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(cari.CariError):
                channels.normalize(body)

    def test_all_named_sources_exist_without_claiming_live_connection(self):
        board = channels.project([])
        self.assertEqual([c['name'] for c in board['channels']],
            ['Trendyol','n11','Amazon','Hepsiburada','Wix','BasitKargo','QNB POS'])
        self.assertTrue(all(not c['live_connection_verified'] for c in board['channels']))

    def test_unknown_invoice_is_not_silently_classified_as_missing(self):
        board = channels.project([row(observation())])
        self.assertEqual(board['orders'][0]['invoice']['status'], 'unknown')
        self.assertIn('doğrulanmadı', board['orders'][0]['invoice_checks'][0])

    def test_issued_invoice_does_not_imply_platform_upload(self):
        board=channels.project([row(observation(invoice={'status':'issued','number':'TEST'}))])
        self.assertEqual(board['orders'][0]['invoice']['platform_status'],'unknown')
        board=channels.project([row(observation(invoice={'status':'issued','number':'TEST',
                                                          'platform_status':'rejected'}))])
        self.assertEqual(board['invoice_check_count'],1)

    def test_issued_invoice_needs_number_and_amount_mismatch_is_visible(self):
        with self.assertRaises(cari.CariError):
            channels.normalize(observation(invoice={'status':'issued'}))
        board = channels.project([row(observation(invoice={'status':'issued','number':'TEST123',
                                                         'gross_amount':'100.00'}))])
        self.assertEqual(len(board['orders'][0]['invoice_checks']), 1)

    def test_cancelled_order_does_not_infer_missing_invoice_but_flags_issued_one(self):
        self.assertEqual(channels.project([row(observation(status='cancelled'))])['invoice_check_count'], 0)
        board = channels.project([row(observation(status='cancelled',invoice={'status':'issued','number':'TEST'}))])
        self.assertEqual(board['invoice_check_count'], 1)

    def test_cargo_and_pos_join_order_without_creating_additional_sales(self):
        link={'source':'wix','store_id':'store-a','object_id':'order-123'}
        records=[row(observation()),
            row(observation('basitkargo',object_id='shipment-1',order_link=link)),
            row(observation('qnb_pos',object_id='terminal-tx-1',order_link=link,status='approved'))]
        board = channels.project(records)
        self.assertEqual(board['order_count'], 1)
        self.assertEqual(len(board['orders'][0]['related']), 2)
        self.assertEqual(board['orders'][0]['payment_status'], 'unknown')
        self.assertEqual(board['orders'][0]['invoice']['status'], 'unknown')

    def test_name_and_amount_match_never_link_sources(self):
        board = channels.project([row(observation()),row(observation('basitkargo'))])
        self.assertEqual(board['orders'][0]['related'], [])
        self.assertFalse(board['other_records'][0]['order_matched'])

    def test_store_and_channel_identifiers_are_part_of_the_order_identity(self):
        link={'source':'wix','store_id':'different-store','object_id':'order-123'}
        board=channels.project([row(observation()),row(observation('qnb_pos',order_link=link))])
        self.assertFalse(board['other_records'][0]['order_matched'])

    def test_cargo_and_pos_cannot_claim_to_have_a_customer_invoice(self):
        for source in ('basitkargo','qnb_pos'):
            with self.subTest(source=source), self.assertRaises(cari.CariError):
                channels.normalize(observation(source,invoice={'status':'issued','number':'X'}))

    def test_source_update_time_requires_timezone_and_unknown_money_stays_unknown(self):
        with self.assertRaises(cari.CariError):
            channels.normalize(observation(source_updated_at='2026-01-10T12:00:00'))
        p=channels.normalize(observation(gross_amount=None))
        self.assertIsNone(p['gross_cents'])

    def test_currencies_stay_separate_and_raw_sensitive_fields_are_not_stored(self):
        data=observation(currency='USD',card_number='do-not-store',api_key='do-not-store')
        normalized=channels.normalize(data)
        self.assertEqual(normalized['currency'],'USD')
        self.assertNotIn('card_number',normalized)
        self.assertNotIn('api_key',normalized)
        self.assertNotIn('total_sales',channels.project([row(data)]))


@unittest.skipUnless(os.environ.get('CARI_TEST_DSN'),'isolated PostgreSQL not configured')
class ChannelPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg=psycopg
        self.dsn=os.environ['CARI_TEST_DSN']
        with psycopg.connect(self.dsn) as conn:
            conn.execute('RESET ROLE')
            if conn.execute('SELECT current_database()').fetchone()[0]!='jarvis_cari_test':
                raise RuntimeError('Disposable test database required')
            conn.execute('TRUNCATE core.jarvis_cari_source_event,core.jarvis_cari_entry,core.jarvis_cari_account')
        def connect():
            conn=psycopg.connect(self.dsn,row_factory=dict_row)
            conn.execute('SET ROLE jarvis_web')
            return conn
        p=patch.object(channels,'_connect',connect);p.start();self.addCleanup(p.stop)

    def test_ingest_is_idempotent_and_changed_retry_is_rejected(self):
        first=channels.observe('alice',observation())
        second=channels.observe('alice',observation())
        self.assertEqual(first['id'],second['id'])
        self.assertTrue(second['reused'])
        with self.assertRaises(cari.CariConflict):
            channels.observe('alice',observation(gross_amount='130'))
        self.assertEqual(channels.board('alice')['order_count'],1)

    def test_stale_observation_does_not_overwrite_newer_source_state(self):
        channels.observe('alice',observation(source_updated_at='2026-01-11T12:00:00Z',
            event_key='newer',invoice={'status':'issued','number':'TEST1'}))
        channels.observe('alice',observation(source_updated_at='2026-01-09T12:00:00Z',event_key='older'))
        self.assertEqual(channels.board('alice')['orders'][0]['invoice']['number'],'TEST1')

    def test_owner_boundary_and_explicit_cari_mapping(self):
        with self.assertRaises(cari.CariNotFound):
            channels.observe('alice',observation(account_id='a'*32))
        channels.observe('alice',observation())
        self.assertEqual(channels.board('bob')['orders'],[])

    def test_source_event_does_not_post_financial_entry_and_history_is_immutable(self):
        channels.observe('alice',observation())
        with channels._connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM core.jarvis_cari_entry').fetchone()['count'],0)
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            with channels._connect() as conn:
                conn.execute('DELETE FROM core.jarvis_cari_source_event')


if __name__=='__main__':
    unittest.main()
