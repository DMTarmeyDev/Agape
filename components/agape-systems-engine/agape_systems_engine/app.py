from __future__ import annotations
# AGAPE_R1_3_SCHEDULE_DECOUPLE_FIX
import argparse, base64, hashlib, json, os, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from .db import EngineDB
from .telemetry import Telemetry
from .work_engine import WorkEngine
from .scheduler import Scheduler
from .provider_circuit import ProviderCircuit, prompt_budget
from .plugins import PluginManager
from .uploads import UploadManager
from .supervisor import Supervisor
from .optimizer import SweetSpotOptimizer
from . import code_intel
from .lanes import choose_lane
from .resources import snapshot

HTML=r'''<!doctype html><html><head><meta charset="utf-8"><title>Agape Work Engine</title><style>
body{font-family:Segoe UI,Arial;margin:0;background:#f5f7f8;color:#18252f}header{background:#132d3a;color:#fff;padding:18px 24px}main{max-width:1250px;margin:auto;padding:18px}.tabs button,.btn{padding:8px 12px;margin:3px;border:0;border-radius:7px;background:#dce6eb}.btn{background:#1f6f8b;color:#fff}.panel{display:none}.panel.active{display:block}.card{background:#fff;border:1px solid #dce5ea;border-radius:10px;padding:14px;margin:12px 0}table{border-collapse:collapse;width:100%}th,td{padding:7px;border-bottom:1px solid #e5eaed;text-align:left;font-size:13px}input,textarea,select{padding:8px;border:1px solid #bbcbd3;border-radius:7px;width:100%;box-sizing:border-box}pre{white-space:pre-wrap;background:#0e1c23;color:#d9edf6;padding:12px;border-radius:8px;max-height:420px;overflow:auto}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.ok{color:#08783d}.bad{color:#b11}</style></head><body>
<header><h1>Agape Work Engine R1.3</h1><div>Durable queue, schedules, code intelligence, provider circuits, plugins, services, resumable uploads and telemetry.</div></header><main>
<div class=tabs><button onclick="tab('work')">Work Queue</button><button onclick="tab('schedule')">Schedules</button><button onclick="tab('code')">Code Intelligence</button><button onclick="tab('providers')">Providers</button><button onclick="tab('plugins')">Plugins</button><button onclick="tab('services')">Services</button><button onclick="tab('events')">Flight Recorder</button></div>
<div id=work class="panel active"><div class=card><h2>Add work</h2><div class=grid><div><label>Kind</label><select id=jobKind><option>code_index</option><option>service_health</option><option>sleep_test</option><option>file_hash</option></select></div><div><label>Priority</label><input id=jobPriority value=50></div></div><label>Payload JSON</label><textarea id=jobPayload>{"seconds":1,"steps":4}</textarea><button class=btn onclick="addJob()">Add to queue</button><button onclick="refresh()">Refresh</button></div><div class=card><table><thead><tr><th>ID</th><th>Kind</th><th>State</th><th>Stage</th><th>Retries</th><th>Actions</th></tr></thead><tbody id=jobs></tbody></table></div></div>
<div id=schedule class=panel><div class=card><h2>Schedules</h2><p>Interval schedules are in seconds. Daily schedules use HH:MM.</p><button class=btn onclick="addSchedule()">Add 15-minute service-health job</button><table><tbody id=schedules></tbody></table></div></div>
<div id=code class=panel><div class=card><h2>Code Intelligence</h2><label>Root</label><input id=codeRoot><label>Search / task</label><input id=codeQuery value="provider failover"><button class=btn onclick="indexCode()">Index changed files</button><button onclick="searchCode()">Search</button><button onclick="contextPack()">Build Context Pack</button><pre id=codeOut></pre></div></div>
<div id=providers class=panel><div class=card><h2>Provider circuits</h2><p>Records auth, credits, rate limits, request-too-large and transient failures separately.</p><pre id=providerOut></pre></div></div>
<div id=plugins class=panel><div class=card><h2>Plugins</h2><pre id=pluginOut></pre></div></div>
<div id=services class=panel><div class=card><h2>Service Supervisor</h2><button class=btn onclick="checkServices(false)">Check expected services</button><button onclick="checkServices(true)">Recover required services</button><pre id=serviceOut></pre></div></div>
<div id=events class=panel><div class=card><h2>Flight Recorder</h2><pre id=eventOut></pre></div></div>
</main><script>
const $=x=>document.getElementById(x);async function api(p,o){let r=await fetch(p,o);let t=await r.text();let j;try{j=JSON.parse(t)}catch{j={text:t}}if(!r.ok)throw new Error(j.error||t);return j}function tab(id){document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));$(id).classList.add('active');if(id==='schedule')refreshSchedules();else refresh()}
async function addJob(){let payload={};try{payload=JSON.parse($('jobPayload').value)}catch(e){alert(e);return}await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:$('jobKind').value,payload,priority:Number($('jobPriority').value||50)})});refresh()}
async function act(id,a){await api('/api/jobs/'+id+'/'+a,{method:'POST'});refresh()}
async function refreshSchedules(){let s=await api('/api/schedules');let rows=(s&&s.schedules)||[];$('schedules').innerHTML=rows.map(x=>`<tr data-schedule-id="${x.id}"><td>${x.name}</td><td>${x.schedule_type}:${x.schedule_value}</td><td>${new Date((x.next_run_at||0)*1000).toLocaleString()}</td></tr>`).join('');return rows}
async function addSchedule(){let created=await api('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Service health every 15 minutes',kind:'service_health',payload:{recover:true},schedule_type:'interval',schedule_value:'900'})});let sid=created.schedule_id||'';for(let i=0;i<40;i++){let rows=await refreshSchedules();if(rows.some(x=>x.id===sid))return created;await new Promise(r=>setTimeout(r,100))}throw new Error('SCHEDULE_NOT_VISIBLE_AFTER_CREATE='+sid)}
async function indexCode(){let r=await api('/api/code/index',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({root:$('codeRoot').value})});$('codeOut').textContent=JSON.stringify(r,null,2)}
async function searchCode(){let r=await api('/api/code/search?q='+encodeURIComponent($('codeQuery').value));$('codeOut').textContent=JSON.stringify(r,null,2)}
async function contextPack(){let r=await api('/api/code/context?q='+encodeURIComponent($('codeQuery').value));$('codeOut').textContent=JSON.stringify(r,null,2)}
async function checkServices(recover){let r=await api('/api/services/check?recover='+(recover?'1':'0'));$('serviceOut').textContent=JSON.stringify(r,null,2)}
async function refresh(){let s=await api('/api/status');$('jobs').innerHTML=s.jobs.map(j=>`<tr><td>${j.id}</td><td>${j.kind}</td><td>${j.state}</td><td>${j.current_stage||''}</td><td>${j.retries}</td><td><button onclick="act('${j.id}','pause')">Pause</button><button onclick="act('${j.id}','resume')">Resume</button><button onclick="act('${j.id}','retry')">Retry</button><button onclick="act('${j.id}','cancel')">Cancel</button></td></tr>`).join('');$('schedules').innerHTML=s.schedules.map(x=>`<tr><td>${x.name}</td><td>${x.schedule_type}:${x.schedule_value}</td><td>${new Date((x.next_run_at||0)*1000).toLocaleString()}</td></tr>`).join('');$('providerOut').textContent=JSON.stringify(s.providers,null,2);$('pluginOut').textContent=JSON.stringify(s.plugins,null,2);$('serviceOut').textContent=JSON.stringify(s.services,null,2);$('eventOut').textContent=JSON.stringify(s.events,null,2);if(!$('codeRoot').value)$('codeRoot').value=s.core_root||''}
refresh();setInterval(refresh,4000)</script></body></html>'''

class Runtime:
    def __init__(self,data_root,core_root):
        self.data_root=Path(data_root);self.data_root.mkdir(parents=True,exist_ok=True);self.core_root=Path(core_root).resolve() if core_root else Path.cwd()
        self.db=EngineDB(self.data_root/'agape-work-engine.sqlite3');self.telemetry=Telemetry(self.db);self.engine=WorkEngine(self.db,self.data_root,self.telemetry);self.scheduler=Scheduler(self.db);self.providers=ProviderCircuit(self.db);self.plugins=PluginManager(self.db,self.data_root/'plugins');self.uploads=UploadManager(self.db,self.data_root/'uploads');self.supervisor=Supervisor(self.db);self.optimizer=SweetSpotOptimizer(self.db);self.engine.set_supervisor(self.supervisor)
        core_data=self.data_root.parent
        workflow=core_data/'workflow-output';workflow.mkdir(parents=True,exist_ok=True)
        service_logs=self.data_root/'service-logs';service_logs.mkdir(parents=True,exist_ok=True)
        core_start=None
        for name in ('START-DMT-SECOND-BRAIN.ps1','START-AGAPE.ps1','START-AGAPE-CORE.ps1','OPEN-AGAPE.ps1','START-DMT-CORE.ps1'):
            q=self.core_root/name
            if q.exists():
                core_start={'cmd':['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(q)],'cwd':str(self.core_root),'stdout_path':str(service_logs/'core-start.log'),'stderr_path':str(service_logs/'core-start.err.log')};break
        if core_start is None and (self.core_root/'app.py').exists():
            core_start={'cmd':[sys.executable,'-u',str(self.core_root/'app.py'),'--port','8797'],'cwd':str(self.core_root),'env':{'DMT_DATA_ROOT':str(core_data),'DMT_WORKFLOW_ROOT':str(workflow)},'stdout_path':str(service_logs/'core-start.log'),'stderr_path':str(service_logs/'core-start.err.log')}
        ds=self.core_root/'OPEN-AGAPE-DOCUMENT-STUDIO.ps1';ds_start=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ds)] if ds.exists() else None
        self.supervisor.register('Core','127.0.0.1',8797,'ACTIVE',core_start)
        self.supervisor.register('DocumentStudio','127.0.0.1',8800,'COLD',ds_start)
        self.supervisor.register('Ollama','127.0.0.1',11434,'COLD')
        self.worker=threading.Thread(target=self.engine.worker_loop,daemon=True);self.worker.start();self.sched_stop=threading.Event();self.sched=threading.Thread(target=self._schedule_loop,daemon=True);self.sched.start()
    def _schedule_loop(self):
        while not self.sched_stop.is_set():
            try:self.scheduler.enqueue_due()
            except Exception as e:self.db.event('scheduler','ERROR',level='ERROR',data={'error':str(e)})
            self.sched_stop.wait(2)
    def status(self):
        with self.db.connect() as c:events=[dict(x) for x in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 80').fetchall()]
        return {'version':'R1.3','core_root':str(self.core_root),'jobs':self.db.list_jobs(100),'schedules':self.scheduler.list(),'providers':self.providers.rows(),'plugins':self.plugins.list(),'services':self.supervisor.check_all(False),'events':events,'resources':snapshot(self.data_root)}

RUNTIME=None

def jsend(h,status,obj):
    b=json.dumps(obj,ensure_ascii=False,default=str).encode('utf-8');h.send_response(status);h.send_header('Content-Type','application/json; charset=utf-8');h.send_header('Content-Length',str(len(b)));h.end_headers();h.wfile.write(b)

def body_json(h):
    n=int(h.headers.get('Content-Length','0') or 0);raw=h.rfile.read(n) if n else b'{}';return json.loads(raw.decode('utf-8','replace') or '{}')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):return
    def do_GET(self):
        u=urllib.parse.urlparse(self.path);q=urllib.parse.parse_qs(u.query)
        try:
            if u.path=='/':
                b=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
            if u.path=='/api/health':return jsend(self,200,{'ok':True,'version':'R1.3'})
            if u.path=='/api/status':return jsend(self,200,RUNTIME.status())
            if u.path=='/api/schedules':return jsend(self,200,{'schedules':RUNTIME.scheduler.list()})
            if u.path=='/api/code/search':return jsend(self,200,{'results':code_intel.search(RUNTIME.db,q.get('q',[''])[0])})
            if u.path=='/api/code/context':return jsend(self,200,code_intel.context_pack(RUNTIME.db,q.get('q',[''])[0],int(q.get('max_chars',['12000'])[0])))
            if u.path=='/api/services/check':return jsend(self,200,RUNTIME.supervisor.summary(q.get('recover',['0'])[0]=='1'))
            if u.path.startswith('/api/uploads/') and u.path.endswith('/status'):
                uid=u.path.split('/')[3];return jsend(self,200,RUNTIME.uploads.status(uid))
            return jsend(self,404,{'error':'NOT_FOUND'})
        except Exception as e:return jsend(self,500,{'error':str(e)})
    def do_PUT(self):
        u=urllib.parse.urlparse(self.path);q=urllib.parse.parse_qs(u.query)
        try:
            parts=u.path.strip('/').split('/')
            if len(parts)==5 and parts[:2]==['api','uploads'] and parts[3]=='chunk':
                uid=parts[2];idx=int(parts[4]);n=int(self.headers.get('Content-Length','0'));data=self.rfile.read(n);return jsend(self,200,RUNTIME.uploads.put_chunk(uid,idx,data,q.get('sha256',[None])[0]))
            return jsend(self,404,{'error':'NOT_FOUND'})
        except Exception as e:return jsend(self,500,{'error':str(e)})
    def do_POST(self):
        u=urllib.parse.urlparse(self.path)
        try:
            if u.path=='/api/jobs':
                d=body_json(self);jid=RUNTIME.db.create_job(d['kind'],d.get('payload'),d.get('priority',50),d.get('lane','STANDARD'),d.get('resources'),d.get('max_retries',2));return jsend(self,202,{'job_id':jid})
            if u.path.startswith('/api/jobs/'):
                parts=u.path.strip('/').split('/')
                if len(parts)!=4:return jsend(self,404,{'error':'BAD_JOB_ACTION_PATH'})
                _,_,jid,action=parts;job=RUNTIME.db.get_job(jid)
                if not job:return jsend(self,404,{'error':'JOB_NOT_FOUND'})
                if action=='pause':RUNTIME.db.update_job(jid,state='PAUSED',worker_id=None,lease_until=None)
                elif action=='resume':RUNTIME.db.update_job(jid,state='QUEUED',available_at=time.time(),worker_id=None,lease_until=None)
                elif action=='retry':RUNTIME.db.update_job(jid,state='QUEUED',available_at=time.time(),worker_id=None,lease_until=None,error=None)
                elif action=='cancel':RUNTIME.db.update_job(jid,state='CANCELLED',worker_id=None,lease_until=None)
                return jsend(self,200,{'ok':True,'action':action})
            if u.path=='/api/schedules':
                d=body_json(self);sid=RUNTIME.scheduler.add(d['name'],d['kind'],d.get('payload',{}),d['schedule_type'],d['schedule_value'],d.get('priority',20),d.get('enabled',True));return jsend(self,201,{'schedule_id':sid})
            if u.path=='/api/code/index':
                d=body_json(self);return jsend(self,200,code_intel.index_root(RUNTIME.db,d.get('root') or RUNTIME.core_root,int(d.get('max_files',5000))))
            if u.path=='/api/providers/record':
                d=body_json(self);r=RUNTIME.providers.record_failure(d['provider'],d.get('model',''),d.get('http_status'),d.get('error',''),d.get('request_chars'));return jsend(self,200,r)
            if u.path=='/api/lanes/choose':
                d=body_json(self);r=choose_lane(d.get('doc_type',''),d.get('research',False),d.get('rag',False),d.get('source_chars',0),d.get('instructions',''));r['prompt_budget']=prompt_budget(d.get('doc_type',''),r['lane']);return jsend(self,200,r)
            if u.path=='/api/uploads/start':
                d=body_json(self);return jsend(self,201,RUNTIME.uploads.start(d['filename'],d['total_size'],d.get('chunk_size',4*1024*1024),d.get('total_sha256')))
            if u.path.startswith('/api/uploads/') and u.path.endswith('/finalize'):
                uid=u.path.split('/')[3];return jsend(self,200,RUNTIME.uploads.finalize(uid))
            return jsend(self,404,{'error':'NOT_FOUND'})
        except Exception as e:return jsend(self,500,{'error':str(e)})

def serve(port,data_root,core_root,no_browser=False):
    global RUNTIME;RUNTIME=Runtime(data_root,core_root);srv=ThreadingHTTPServer(('127.0.0.1',int(port)),Handler)
    if not no_browser:threading.Timer(0.8,lambda:webbrowser.open(f'http://127.0.0.1:{port}/')).start()
    try:srv.serve_forever()
    finally:RUNTIME.engine.stop_event.set();RUNTIME.sched_stop.set();srv.server_close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8820);ap.add_argument('--data-root',required=True);ap.add_argument('--core-root',required=True);ap.add_argument('--no-browser',action='store_true');a=ap.parse_args();serve(a.port,a.data_root,a.core_root,a.no_browser)
if __name__=='__main__':main()
