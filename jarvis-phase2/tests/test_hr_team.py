import unittest
from types import SimpleNamespace
from jarvis import hr_team, roster


class HRTests(unittest.TestCase):
    def test_source_disconnected_does_not_erase_successful_internal_read(self):
        d = dict(kod='RND', birim_durumu='YOK', uyeler=[dict(
            key='yeni_urun_on_arastirma', ad='Araştırmacı', durum='KONUŞTU')])
        report = hr_team.review([d])
        self.assertEqual(report['source_missing'], 1)
        self.assertFalse(any(f['kind'].startswith('member_') for f in report['findings']))

    def test_partial_reads_remain_visible_and_do_not_deduplicate_departments(self):
        d = dict(kod='META_MEDIA', birim_durumu='CALISIYOR', uyeler=[dict(
            key='meta_performance', ad='Analist', durum='KONUŞTU', eksik=['advertising_spend'])])
        report = hr_team.review([d])
        self.assertTrue(any('advertising_spend' in f['detail'] for f in report['findings']))
        self.assertEqual(report['source_missing'], 0)

    def test_unknown_connection_is_not_healthy(self):
        report = hr_team.review([dict(kod='NEW', uyeler=[])])
        self.assertIn('source_unknown', [f['kind'] for f in report['findings']])

    def test_roster_is_growing_and_hr_is_real_read_only_team(self):
        team = roster.departman_uyeleri()['HR']
        self.assertEqual(len(team), 4)
        self.assertIn(roster.departman_sorumlusu('HR'), team)
        self.assertEqual(roster.eslenmeyen_uyeler(), ())
        class EmptyMemory:
            def _fetch(self, q): return SimpleNamespace(records=[])
        opinions=roster.opinions(EmptyMemory(), only=tuple(m.key for m in team))
        self.assertTrue(all(o['status'] == roster.NO_DATA for o in opinions))
        self.assertTrue(all(o['model_calls'] == 0 for o in opinions))

    def test_organisation_manager_assignments_match_their_departments(self):
        result = hr_team.organisation({'departments':[{'kod':'BIZDEV'}]})
        self.assertIn('Geçerli ekip sorumlusu eksik: yok', result)
        self.assertEqual(roster.DEPARTMAN_SORUMLUSU['BIZDEV'], 'firsat_takibi')
        for code in ('BIZDEV','MARKETPLACE'):
            self.assertIn(roster.departman_sorumlusu(code), roster.departman_uyeleri()[code])

if __name__ == '__main__': unittest.main()
