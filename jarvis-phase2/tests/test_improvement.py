import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from jarvis.improvement import Store, cycle, CASES, evaluate_model


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Store(Path(self.tmp.name)/'ledger.db')
        self.before = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        self.at = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        self.after = datetime.now(timezone.utc).isoformat()
        self.i = self.s.work(source_key='test',domain='operations',objective='Reduce errors',owner='operations',
                             metric='errors',unit='errors',target=0,source='test-report')

    def applied(self):
        self.s.apply(work_id=self.i,at=self.at,evidence='commit:verified',actor='tester')

    def measured(self, **changes):
        vals=dict(work_id=self.i,baseline=1,result=0,sample=1204,before_at=self.before,after_at=self.after,
                  before_source='failed.log',after_source='passed.log',note='Technical result; not sales',actor='tester')
        vals.update(changes)
        self.s.measure(**vals)

    def test_approval_does_not_close_work(self):
        for state in ['APPROVED','EXECUTED','PROPOSED']:
            with self.s.db() as db:
                db.execute('UPDATE work SET approval_state=? WHERE id=?',(state,self.i))
            self.assertEqual(self.s.snapshot()['works'][0]['status'],'WAITING_APPLICATION_EVIDENCE')

    def test_application_without_measurement_waits(self):
        self.applied()
        self.assertEqual(self.s.snapshot()['works'][0]['status'],'WAITING_MEASUREMENT')

    def test_measurement_needs_real_application(self):
        with self.assertRaises(ValueError):self.measured()
        self.assertEqual(self.s.snapshot()['outcome_lessons'],[])

    def test_target_reached_and_no_causal_claim(self):
        self.applied();self.measured()
        snap=self.s.snapshot()
        self.assertEqual(snap['works'][0]['status'],'TARGET_REACHED')
        self.assertEqual(snap['outcome_lessons'][0]['causality'],'NOT_ESTABLISHED')

    def test_missed_target_is_follow_up(self):
        self.applied();self.measured(result=2)
        self.assertEqual(self.s.snapshot()['works'][0]['status'],'MEASURED_FOLLOW_UP')

    def test_higher_direction(self):
        self.s.plan(work_id=self.i,owner='operations',metric='score',unit='points',direction='higher',target=3,
                    due=self.after,actor='tester')
        self.applied();self.measured(result=4)
        self.assertEqual(self.s.snapshot()['works'][0]['status'],'TARGET_REACHED')

    def test_nonfinite_and_boolean_rejected(self):
        self.applied()
        for value in [float('nan'),float('inf'),True]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.measured(result=value)

    def test_bad_sample(self):
        self.applied()
        for n in [0,-1,1.5,True]:
            with self.subTest(n=n),self.assertRaises(ValueError):self.measured(sample=n)

    def test_bad_time_order(self):
        self.applied()
        with self.assertRaises(ValueError):self.measured(before_at=self.after,after_at=self.before)

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):self.s.apply(work_id=self.i,at='2026-01-01T00:00:00',evidence='x',actor='tester')

    def test_application_outside_window_rejected(self):
        self.applied()
        with self.assertRaises(ValueError):self.measured(before_at=self.after)

    def test_no_unknown_work(self):
        with self.assertRaises(ValueError):self.s.apply(work_id=999,at=self.at,evidence='x',actor='tester')

    def test_dedup_preserves_measurement(self):
        self.applied();self.applied();self.measured();self.measured()
        snap=self.s.snapshot()['works'][0]
        self.assertEqual(len(snap['applications']),1)
        self.assertEqual(len(snap['measurements']),1)

    def test_cannot_redefine_measured_target(self):
        self.applied();self.measured()
        with self.assertRaises(ValueError):
            self.s.plan(work_id=self.i,owner='a',metric='b',unit='c',direction='higher',target=4,due=self.after,actor='tester')

    def test_rejected_proposal_is_cancelled(self):
        with self.s.db() as db:db.execute("UPDATE work SET approval_state='REJECTED' WHERE id=?",(self.i,))
        self.assertEqual(self.s.snapshot()['works'][0]['status'],'CANCELLED')

    def test_correction_persisted_and_retrieved_only_relevant(self):
        self.s.correct(domain='coding',wrong='tests false',right='Hunspell needs UTF8 locale',reason='measured failure',evidence='test.log',actor='operator')
        other=Store(self.s.path)
        self.assertIn('Hunspell',other.context('Hunspell coding'))
        self.assertEqual(other.context('lipstick branding'),'')
        self.assertIn('yetki değildir',other.context('Hunspell'))

    def test_actor_cannot_be_spoofed_in_api(self):
        with self.assertRaises(ValueError):self.s.operation({'operation':'correction','actor':'admin'},'tester')

    def test_unknown_operation(self):
        with self.assertRaises(ValueError):self.s.operation({'operation':'execute'},'tester')

    def test_concurrent_work_creation_is_idempotent(self):
        def work(_):return self.s.work(source_key='parallel',domain='ops',objective='x',owner='ops',metric='x',unit='x',source='x')
        with ThreadPoolExecutor(max_workers=4) as pool: ids=list(pool.map(work,range(12)))
        self.assertEqual(len(set(ids)),1)

    def test_cycle_unavailable_does_not_pass(self):
        class Memory:
            def _fetch(self,key):raise RuntimeError('not available')
        snap=cycle(Memory(),self.s)
        self.assertEqual(len(snap['evaluation']['cases']),20)
        self.assertTrue(all(r['status']=='ERROR' for r in snap['evaluation']['cases']))
        self.assertEqual(snap['evaluation']['cost'],None)

    def test_cycle_empty_needs_data_and_no_duplicate_work(self):
        class Memory:
            def _fetch(self,key):return SimpleNamespace(records=[],source='postgres:'+key,authority='CANONICAL_COMPANY_MEMORY')
        a=cycle(Memory(),self.s);b=cycle(Memory(),self.s)
        self.assertEqual(len(a['works']),len(b['works']))
        self.assertTrue(all(r['status']=='NEEDS_DATA' for r in b['evaluation']['cases']))

    def test_proposal_sync_never_creates_application(self):
        class Memory:
            def _fetch(self,key):
                rows=[{'entity_id':1,'state':'EXECUTED','action_type':'PRICE_CHANGE'}] if key=='own_proposals' else []
                return SimpleNamespace(records=rows,source='postgres:'+key,authority='CANONICAL_COMPANY_MEMORY')
        snap=cycle(Memory(),self.s)
        proposal=next(w for w in snap['works'] if w['source_key']=='proposal:1')
        self.assertEqual(proposal['status'],'WAITING_APPLICATION_EVIDENCE')
        self.assertEqual(proposal['applications'],[])

    def test_evidence_gap_and_funnel_are_owned(self):
        class Memory:
            def _fetch(self,key):
                rows=([{'entity_id':'behavior','current_connection':'BLOCKED','freshness':'unknown'}] if key=='provenance' else
                      [{'entity_id':'CART','oran_durumu':'NOT_MEASURABLE','oran_yuzde':None}] if key=='ecommerce_funnel' else [])
                return SimpleNamespace(records=rows,source='postgres:'+key,authority='CANONICAL_COMPANY_MEMORY')
        snap=cycle(Memory(),self.s)
        self.assertTrue(any(w['source_key']=='connection:behavior' and w['owner']=='operations' for w in snap['works']))
        self.assertTrue(any(w['source_key']=='funnel:CART' for w in snap['works']))

    def test_wrong_schema_is_not_passed(self):
        class Memory:
            def _fetch(self,key):return SimpleNamespace(records=[{'wrong':'shape'}],source='postgres:'+key,authority='CANONICAL_COMPANY_MEMORY')
        snap=cycle(Memory(),self.s)
        self.assertTrue(all(r['status']=='CONTRACT_ERROR' for r in snap['evaluation']['cases']))

    def test_model_eval_failures_do_not_pass(self):
        class Memory:
            def _fetch(self,key):raise RuntimeError('not available')
        report=evaluate_model(Memory(),None,self.s)
        self.assertTrue(all(r['status']=='ERROR' for r in report['cases']))
        self.assertTrue(all(r['model_calls'] is None for r in report['cases']))

    def test_model_eval_scores_answers_and_refs(self):
        class Memory:
            def _fetch(self,key):
                rows={'own_proposals':[{'state':'EXECUTED'}], 'ecommerce_funnel':[{'oran_durumu':'NOT_MEASURABLE'}],
                      'evidence_readiness':[{'veri_kalitesi':[{'durum':'TAHMIN'}]}],
                      'provenance':[{'entity_id':'inventory','current_connection':'PARTIAL'}],
                      'advertising_performance':[{'meta_conversion_signal':'CLAIM'}]}
                return SimpleNamespace(records=rows[key],source='postgres:'+key)
        class Router:
            def synthesize(self,question,evidence,max_tokens):
                import re
                field=re.search(r'JSON döndür: \{"([^"]+)"',question)[1]
                return SimpleNamespace(answer='{"'+field+'": false}',evidence_refs=[evidence[0]['ref']],
                                       model='test',tier='TEST',model_calls=1,prompt_tokens=10,completion_tokens=4)
        report=evaluate_model(Memory(),Router(),self.s)
        self.assertTrue(all(r['status']=='PASS' for r in report['cases']),report)
        self.assertIsNotNone(self.s.snapshot()['model_evaluation'])

    def test_contract_suite_is_twenty_distinct_queries(self):
        self.assertEqual(len(set(x[1] for x in CASES)),20)


if __name__=='__main__':unittest.main()
