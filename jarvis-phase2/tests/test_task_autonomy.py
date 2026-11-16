import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jarvis.improvement import Store
from jarvis.is_uretici import Agac
from jarvis.task_autonomy import recover_pruned_work


class TaskAutonomyTests(unittest.TestCase):
    def test_pruned_work_returns_once_without_being_marked_done(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = Store(root / 'improvement' / 'ledger.sqlite3')
            work_id = store.work(source_key='isuretici:2026-11-02-SEO-h1',
                                 domain='SEO · Search', objective='Check pages — Teslim: report',
                                 owner='seo_agent', metric='Kabul: 3 pages', unit='teslim',
                                 source='iş-üretici/haftalik', due='2026-11-09T00:00:00+00:00')
            tree_dir = root / 'is-uretici'
            now = datetime.now(timezone.utc)
            self.assertEqual(recover_pruned_work(store, tree_dir, now), 1)
            self.assertEqual(recover_pruned_work(store, tree_dir, now), 0)
            task = Agac(tree_dir).oku()['departmanlar']['SEO']['gorevler'][0]
            self.assertEqual((task['work_id'], task['durum']), (work_id, 'YENIDEN_PLANLA'))
            self.assertEqual(store.snapshot()['works'][0]['status'], 'NEEDS_REPLAN')

    def test_applied_or_cancelled_work_is_not_reopened(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = Store(root / 'improvement' / 'ledger.sqlite3')
            now = datetime.now(timezone.utc)
            for state in ('APPLIED', 'REJECTED', 'EXPIRED'):
                work_id = store.work(source_key='isuretici:' + state,
                    domain='SEO', objective='Check pages', owner='seo',
                    metric='pages', unit='teslim', source='test')
                if state == 'APPLIED':
                    store.apply(work_id=work_id, at=now.isoformat(), evidence='verified delivery', actor='seo')
                else:
                    with store.db() as db:
                        db.execute('UPDATE work SET approval_state=? WHERE id=?', (state, work_id))
            self.assertEqual(recover_pruned_work(store, root / 'is-uretici', now), 0)
            self.assertEqual(Agac(root / 'is-uretici').oku()['departmanlar'], {})
            with store.db() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM work').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM application').fetchone()[0], 1)
