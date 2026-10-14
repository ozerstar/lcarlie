import subprocess
import unittest
from unittest.mock import patch
from jarvis.memory import CompanyMemory, MemoryError
from jarvis.roster import ROSTER
from jarvis import loop

class RepairTests(unittest.TestCase):
    def test_every_roster_read_has_a_real_query(self):
        missing={q for m in ROSTER for q in m.reads}-CompanyMemory.QUERIES.keys()
        self.assertEqual(set(),missing)

    def test_local_sql_errors_stop_before_rollback_hides_them(self):
        result=subprocess.CompletedProcess([],1,'','ERROR: relation missing')
        with patch('jarvis.memory.subprocess.run',return_value=result) as run:
            with self.assertRaises(MemoryError):
                CompanyMemory(host=None)._fetch('system')
        self.assertIn('ON_ERROR_STOP=1',run.call_args.args[0])

    def test_remote_sql_errors_also_stop(self):
        result=subprocess.CompletedProcess([],0,'{}','')
        with patch('jarvis.memory.subprocess.run',return_value=result) as run:
            CompanyMemory(host='lcarlie')._fetch('system')
        self.assertIn('ON_ERROR_STOP=1',run.call_args.args[0][-1])

    def test_claim_filters_at_database_before_leasing(self):
        with patch.object(loop,'_psql',return_value=[]) as psql:
            self.assertIsNone(loop._claim_task(None))
        self.assertIn("'PROPOSE_ACTION'",psql.call_args.args[0])

if __name__=='__main__': unittest.main()
