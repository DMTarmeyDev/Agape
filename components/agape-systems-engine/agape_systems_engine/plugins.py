from __future__ import annotations
import importlib, json, sys, time
from pathlib import Path

class PluginManager:
    def __init__(self,db,plugin_root):
        self.db=db;self.plugin_root=Path(plugin_root);self.plugin_root.mkdir(parents=True,exist_ok=True);self.loaded={}
    def register(self,manifest):
        pid=manifest['id'];now=time.time()
        with self.db.connect() as c:c.execute("INSERT OR REPLACE INTO plugins(plugin_id,version,installed,enabled,state,entrypoint,capabilities_json,manifest_json,last_used_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(pid,str(manifest.get('version','1')),1,int(bool(manifest.get('enabled',False))),'COLD',manifest.get('entrypoint'),json.dumps(manifest.get('capabilities',[])),json.dumps(manifest),None,now))
        return pid
    def list(self):
        with self.db.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM plugins ORDER BY plugin_id').fetchall()]
    def set_enabled(self,pid,enabled):
        with self.db.connect() as c:c.execute('UPDATE plugins SET enabled=?,state=?,updated_at=? WHERE plugin_id=?',(int(bool(enabled)),'COLD' if enabled else 'DISABLED',time.time(),pid))
    def load(self,pid):
        with self.db.connect() as c:r=c.execute('SELECT * FROM plugins WHERE plugin_id=?',(pid,)).fetchone()
        if not r:raise KeyError(pid)
        if not r['enabled']:raise RuntimeError('PLUGIN_DISABLED')
        if pid in self.loaded:return self.loaded[pid]
        manifest=json.loads(r['manifest_json'] or '{}');ep=r['entrypoint']
        if not ep:raise RuntimeError('PLUGIN_ENTRYPOINT_MISSING')
        extra=manifest.get('python_path')
        if extra and extra not in sys.path:sys.path.insert(0,extra)
        mod_name,_,attr=ep.partition(':');mod=importlib.import_module(mod_name);obj=getattr(mod,attr) if attr else mod
        self.loaded[pid]=obj
        with self.db.connect() as c:c.execute("UPDATE plugins SET state='ACTIVE',last_used_at=?,updated_at=? WHERE plugin_id=?",(time.time(),time.time(),pid))
        return obj
    def hibernate(self,pid):
        self.loaded.pop(pid,None)
        with self.db.connect() as c:c.execute("UPDATE plugins SET state='COLD',updated_at=? WHERE plugin_id=? AND enabled=1",(time.time(),pid))
