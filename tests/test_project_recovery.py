import os
import pathlib
import sqlite3
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from agape_mainframe.project_recovery import recover_past_projects

SCHEMA='''
CREATE TABLE projects(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,created_at TEXT,updated_at TEXT,kind TEXT DEFAULT 'user',archived INTEGER DEFAULT 0,hidden_reason TEXT DEFAULT '');
CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL,role TEXT NOT NULL,provider TEXT DEFAULT '',model TEXT DEFAULT '',content TEXT NOT NULL,created_at TEXT);
CREATE TABLE project_loop_settings(project_id INTEGER PRIMARY KEY,workspace TEXT DEFAULT '',goal TEXT DEFAULT '',test_command TEXT DEFAULT '',max_steps INTEGER DEFAULT 4,auto_model INTEGER DEFAULT 1,model TEXT DEFAULT '',updated_at TEXT);
'''

def make_db(path, projects):
    path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path)
    con.executescript(SCHEMA)
    for p in projects:
        cur=con.execute('INSERT INTO projects(name,created_at,updated_at,kind,archived,hidden_reason) VALUES(?,?,?,?,?,?)',(
            p['name'],p.get('created','2026-09-01'),p.get('updated','2026-09-01'),p.get('kind','user'),p.get('archived',0),p.get('hidden','')))
        pid=cur.lastrowid
        for i,m in enumerate(p.get('messages',[]),1):
            con.execute('INSERT INTO messages(project_id,role,provider,model,content,created_at) VALUES(?,?,?,?,?,?)',(pid,m.get('role','user'),'', '',m['content'],m.get('created',f'2026-09-01 10:00:{i:02d}')))
        if p.get('goal'):
            con.execute('INSERT INTO project_loop_settings(project_id,workspace,goal,test_command,max_steps,auto_model,model,updated_at) VALUES(?,?,?,?,?,?,?,?)',(pid,'C:/work',p['goal'],'',4,1,'','2026-09-01'))
    con.commit();con.close()

class RecoveryTests(unittest.TestCase):
    def test_explicit_recovery_root_inside_os_temp_is_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            target=root/'live'/'dmt_core.sqlite3'
            source=root/'backups'/'old1'/'dmt_memory.sqlite3'
            make_db(target,[{'name':'Current Project'}])
            make_db(source,[{'name':'Recovered From Temp','messages':[{'content':'historic'}]}])
            old={k:os.environ.get(k) for k in ('AGAPE_CORE_DB','AGAPE_RECOVERY_ROOTS','AGAPE_RECOVERY_BACKUP_ROOT','AGAPE_RECOVERY_REPORT_ROOT')}
            os.environ['AGAPE_CORE_DB']=str(target)
            os.environ['AGAPE_RECOVERY_ROOTS']=str(root/'backups')
            os.environ['AGAPE_RECOVERY_BACKUP_ROOT']=str(root/'safety')
            os.environ['AGAPE_RECOVERY_REPORT_ROOT']=str(root/'reports')
            try:
                result=recover_past_projects()
                self.assertTrue(result['ok'])
                self.assertEqual(result['projects_added'],1)
                self.assertIn('Recovered From Temp',result['recovered_projects'])
            finally:
                for k,v in old.items():
                    if v is None: os.environ.pop(k,None)
                    else: os.environ[k]=v

    def test_recovers_missing_legacy_projects_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            target=root/'live'/'dmt_core.sqlite3'
            make_db(target,[{'name':'Daz','messages':[{'content':'Current Daz message','created':'2026-09-10'}]}])
            backups=root/'backups'
            make_db(backups/'old1'/'dmt_memory.sqlite3',[
                {'name':'DMT AI Studio','messages':[{'content':'Old studio message'}],'goal':'Restore app development'},
                {'name':'Daz','messages':[{'content':'Historic Daz message','created':'2026-09-02'}]},
                {'name':'Old Archived Project','archived':1,'messages':[{'content':'Archived but recoverable'}]},
                {'name':'Template 1 - System Stress Test','kind':'template'},
                {'name':'Crash Recovery Mock Project','messages':[{'content':'Do not recover'}]},
            ])
            make_db(backups/'isolated-data'/'dmt_core.sqlite3',[{'name':'Should Not Restore'}])
            old={k:os.environ.get(k) for k in ('AGAPE_CORE_DB','AGAPE_RECOVERY_ROOTS','AGAPE_RECOVERY_BACKUP_ROOT','AGAPE_RECOVERY_REPORT_ROOT')}
            os.environ['AGAPE_CORE_DB']=str(target)
            os.environ['AGAPE_RECOVERY_ROOTS']=str(backups)
            os.environ['AGAPE_RECOVERY_BACKUP_ROOT']=str(root/'safety')
            os.environ['AGAPE_RECOVERY_REPORT_ROOT']=str(root/'reports')
            try:
                result=recover_past_projects()
                self.assertTrue(result['ok'])
                self.assertEqual(result['projects_added'],2)
                self.assertGreaterEqual(result['messages_added'],3)
                self.assertTrue(pathlib.Path(result['backup']).is_file())
                con=sqlite3.connect(target)
                names={r[0] for r in con.execute('SELECT name FROM projects')}
                self.assertIn('DMT AI Studio',names)
                self.assertIn('Old Archived Project',names)
                self.assertIn('Daz',names)
                self.assertNotIn('Template 1 - System Stress Test',names)
                self.assertNotIn('Crash Recovery Mock Project',names)
                self.assertNotIn('Should Not Restore',names)
                daz_id=con.execute("SELECT id FROM projects WHERE name='Daz'").fetchone()[0]
                daz_messages={r[0] for r in con.execute('SELECT content FROM messages WHERE project_id=?',(daz_id,))}
                self.assertIn('Current Daz message',daz_messages)
                self.assertIn('Historic Daz message',daz_messages)
                archived=con.execute("SELECT archived FROM projects WHERE name='Old Archived Project'").fetchone()[0]
                self.assertEqual(archived,0)
                con.close()

                again=recover_past_projects()
                self.assertTrue(again['ok'])
                self.assertEqual(again['projects_added'],0)
                self.assertEqual(again['messages_added'],0)
            finally:
                for k,v in old.items():
                    if v is None: os.environ.pop(k,None)
                    else: os.environ[k]=v

if __name__=='__main__': unittest.main(verbosity=2)
