import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from jarvis import role_activity,roster
from test_roster import SahteMemory

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/name)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
plan=load('departman-arastirma.py')
site=load('site-nobeti.py')
bridge=load('bulgu-gorev.py')

class ResearchPlanTests(unittest.TestCase):
    def test_limit_refuses_unbounded_or_injected_values(self):
        for value in (0,-1,33,'1;DROP'):
            with self.assertRaises(ValueError): plan.plandan_konular(value)

    def test_queries_use_json_not_pipe_splitting(self):
        row={'plan_id':1,'konu':'a|b\nnew line','hedef':'dept'}
        result=subprocess.CompletedProcess([],0,json.dumps(row)+'\n','')
        with patch.object(plan.subprocess,'run',return_value=result) as run:
            self.assertEqual([row],plan.plandan_konular(8))
        query=run.call_args.args[0][-1]
        self.assertIn('SET SESSION AUTHORIZATION ai_reader',query)
        self.assertIn('WHERE vakti_geldi',query)
        self.assertIn('LIMIT 8',query)

    def test_empty_due_queue_does_not_run_fallback_topics(self):
        with patch.object(plan,'plandan_konular',return_value=[]),patch.object(plan,'_plan_sql',return_value=[12]),patch('sys.argv',['plan']),patch.object(plan.knowledge,'research_topic') as research:
            self.assertEqual(0,plan.main())
        research.assert_not_called()

    def test_completion_requires_existing_row(self):
        with patch.object(plan,'_plan_sql',return_value=[]):
            with self.assertRaises(RuntimeError): plan.plani_tamamla(3,0)

class FindingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.row={'signature':'site_erisim:https://www.lcarlie.shop/category/a', 'signal_code':'site_erisim','reason':'/category/a HTTP 404 donuyor.','evidence':{'url':'https://www.lcarlie.shop/category/a'},'severity':'CRITICAL'}

    def test_only_successfully_remeasured_error_is_closed(self):
        url=self.row['evidence']['url']
        with patch.object(site,'_son_bulgular',return_value={self.row['signature']:self.row}):
            self.assertEqual([],site._kapanan_http_bulgulari({},[]))
            self.assertEqual([],site._kapanan_http_bulgulari({url:{'durum':404}},[]))
            out=site._kapanan_http_bulgulari({url:{'durum':200}},[])
        self.assertEqual('RESOLVED',out[0]['status'])

    def test_current_problem_is_not_closed_even_with_http_200(self):
        url=self.row['evidence']['url']
        flags=[(url,'WARNING','site_erisim','TLS expiry',{})]
        with patch.object(site,'_son_bulgular',return_value={self.row['signature']:self.row}):
            self.assertEqual([],site._kapanan_http_bulgulari({url:{'durum':200}},flags))

    def test_resolution_removes_old_finding_from_task_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'findings.jsonl'
            path.write_text(json.dumps(self.row)+'\n'+json.dumps({**self.row,'status':'RESOLVED','severity':'INFO'})+'\n')
            with patch.object(bridge,'BULGU_DOSYA',path):
                self.assertEqual([],bridge._bulgular())

    def test_old_urls_are_restricted_to_our_site(self):
        evil={**self.row,'evidence':{'url':'https://attacker.example/category/a'}}
        with patch.object(site,'_son_bulgular',return_value={'x':evil}):
            self.assertEqual([],site._acik_http_adresleri())

class RoleActivityTests(unittest.TestCase):
    def test_empty_research_is_not_reported_as_completed(self):
        self.assertEqual({},role_activity.research_outputs([],datetime.now(timezone.utc)))

    def test_old_or_injected_sources_are_not_used(self):
        now=datetime.now(timezone.utc)
        base={'url':'https://example.org','konu':'rakip kampanya','zaman':now.isoformat()}
        rows=[{**base,'enjeksiyon':True},{**base,'zaman':(now-timedelta(days=15)).isoformat()}]
        self.assertEqual({},role_activity.research_outputs(rows,now))

    def test_research_outputs_retain_real_source_urls(self):
        now=datetime.now(timezone.utc)
        out=role_activity.research_outputs([{'url':'https://example.org','konu':'pazar rakip reklam','zaman':now.isoformat(),'baslik':'A'}],now)
        self.assertEqual(4,len(out))
        self.assertEqual(['https://example.org'],out['research']['evidence_refs'])

    def test_roster_requires_both_output_and_evidence(self):
        recorded={'research':{'status':'PRODUCED','statement':'work','evidence_refs':[]}}
        out=roster.opinions(SahteMemory(),only=('research',),activity=recorded)
        self.assertEqual(roster.NEEDS_RESEARCH,out[0]['status'])
        recorded['research']['evidence_refs']=['https://example.org']
        out=roster.opinions(SahteMemory(),only=('research',),activity=recorded)
        self.assertEqual(roster.SPEAKS,out[0]['status'])

    def test_stale_snapshot_is_not_current_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'team-cycle').mkdir()
            (root/'team-cycle/latest.json').write_text(json.dumps({'generated_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),'roles':{'research':{'status':'PRODUCED'}}}))
            with patch.object(role_activity,'state_dir',return_value=root): self.assertEqual({},role_activity.latest())

if __name__=='__main__': unittest.main()
