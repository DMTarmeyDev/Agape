import json, pathlib, sqlite3, tempfile, unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0,str(ROOT))
from agape_mainframe import state

class ActivityTerminalSyncTests(unittest.TestCase):
    def test_delegated_job_emits_one_terminal_event_and_keeps_run_id(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(state,'DB_FILE',pathlib.Path(td)/'mainframe.sqlite3'):
            state.remember_work('Doc','task','document','J-1','QUEUED',{'run_id':'MAIN-TEST-1'})
            r1=state.sync_external_work_status('J-1',{'id':'J-1','status':'RUNNING','progress':50})
            self.assertFalse(r1['event_emitted'])
            r2=state.sync_external_work_status('J-1',{'id':'J-1','status':'FAIL','error':'provider failed'})
            self.assertTrue(r2['event_emitted'])
            r3=state.sync_external_work_status('J-1',{'id':'J-1','status':'FAIL','error':'provider failed'})
            self.assertFalse(r3['event_emitted'])
            ev=state.events(10)
            terminal=[e for e in ev if e['run_id']=='MAIN-TEST-1' and e['status']=='FAIL']
            self.assertEqual(len(terminal),1)
            self.assertIn('provider failed',terminal[0]['detail'])

    def test_mainframe_db_context_closes_connection_for_windows_cleanup(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(state,'DB_FILE',pathlib.Path(td)/'mainframe.sqlite3'):
            with state.db() as con:
                con.execute("SELECT 1").fetchone()
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute("SELECT 1")

if __name__=='__main__': unittest.main(verbosity=2)
