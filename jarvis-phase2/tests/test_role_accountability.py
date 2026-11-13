"""Role activity must describe actual, attributable work, not status labels."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis import agency, department_activation, roster


class RoleAccountabilityTests(unittest.TestCase):
    def test_research_status_is_never_a_research_deliverable(self):
        for state in ('RESEARCH_REQUIRED', 'NOT_REQUIRED', 'COMPLETE', ''):
            with self.subTest(state=state):
                result = agency.role_contributions(
                    (agency.COMPETITOR_CREATIVE,), {'research_state': state})[0]
                self.assertEqual(result['produced'], 0)
                self.assertEqual(result['status'], 'NO_OUTPUT')

    def test_actual_creative_outputs_still_count(self):
        result = agency.role_contributions(
            (agency.COPYWRITER,), {'creative_concepts': [{'title': 'draft'}]})[0]
        self.assertEqual(result['produced'], 1)
        self.assertEqual(result['status'], 'PRODUCED')

    def test_untrusted_or_unattributed_rows_never_reach_speaker(self):
        for source, authority in (('external:unchecked', 'UNTRUSTED'),
                                  ('postgres:crm', 'UNTRUSTED'),
                                  ('external:unchecked', 'CANONICAL_COMPANY_MEMORY'),
                                  ('', '')):
            with self.subTest(source=source, authority=authority):
                memory = Mock()
                memory._fetch.return_value = SimpleNamespace(
                    records=[{'bekleme_saat': 999}], source=source, authority=authority)
                speaker = Mock(return_value='must not be called')
                with patch.dict(roster.SPEAKERS, {'musteri_hizmetleri': speaker}):
                    result = roster.opinions(memory, only=('musteri_hizmetleri',))[0]
                speaker.assert_not_called()
                self.assertEqual(result['status'], roster.NO_DATA)
                self.assertTrue(result['untrusted_sources'])
                self.assertEqual(result['evidence_refs'], [])
                self.assertNotIn('999', result['statement'])

    def test_only_canonical_rows_enter_shared_cache(self):
        memory = Mock()
        def fetch(query):
            return SimpleNamespace(records=[{'verified': True}],
                                   source=f'postgres:{query}',
                                   authority='CANONICAL_COMPANY_MEMORY')
        memory._fetch.side_effect = fetch
        speaker = Mock(return_value='verified data')
        with patch.dict(roster.SPEAKERS, {'ecommerce_sales': speaker, 'field_b2b_sales': speaker}):
            results = roster.opinions(memory, only=('ecommerce_sales', 'field_b2b_sales'))
        self.assertTrue(all(r['status'] == roster.SPEAKS for r in results))
        queries = [c.args[0] for c in memory._fetch.call_args_list]
        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all(r['evidence_refs'] for r in results))

    def test_revision_request_is_not_completed_revision(self):
        result = department_activation._ig_direktor({'ig_gunluk_paket': [{
            'gun': '2026-11-12', 'uzman_karari': 'DUZELT', 'denetim': 'TEMIZ',
            'durum': 'ONERI', 'urun_slug': 'hydravie'}]})
        self.assertIn('1 tanesinde düzeltme talebi var', result)
        self.assertIn('tamamlandığı doğrulanmadı', result)
        self.assertNotIn('düzelttirdim', result)
        self.assertIn('1 içerik sahip kararını bekliyor', result)


if __name__ == '__main__':
    unittest.main()
