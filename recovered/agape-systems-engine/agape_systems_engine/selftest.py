from __future__ import annotations
import hashlib, json, socket, tempfile, threading, time
from pathlib import Path
from .db import EngineDB
from .telemetry import Telemetry
from .work_engine import WorkEngine
from .code_intel import index_root, search, context_pack
from .provider_circuit import ProviderCircuit, classify, prompt_budget
from .lanes import choose_lane
from .scheduler import Scheduler
from .plugins import PluginManager
from .uploads import UploadManager
from .supervisor import Supervisor
from .optimizer import SweetSpotOptimizer


def run():
    td=Path(tempfile.mkdtemp(prefix='agape-engine-test-'));db=EngineDB(td/'engine.sqlite3');results=[]
    def ok(name,fn):
        try:r=fn();results.append({'name':name,'status':'PASS','detail':r})
        except Exception as e:results.append({'name':name,'status':'FAIL','error':repr(e)})
    def t_db():
        with db.connect() as c:mode=c.execute('PRAGMA journal_mode').fetchone()[0]
        assert str(mode).lower()=='wal';return {'journal_mode':mode}
    ok('01_SQLITE_WAL',t_db)
    def t_work():
        eng=WorkEngine(db,td);jid=db.create_job('sleep_test',{'seconds':0.02,'steps':2});r=eng.run_one('test');assert r['state']=='PASS';j=db.get_job(jid);assert j['state']=='PASS';return r
    ok('02_DURABLE_WORK_ENGINE',t_work)
    def t_code():
        root=td/'code';root.mkdir();(root/'a.py').write_text('def hello(name):\n    return name\n\nclass Thing:\n    pass\n',encoding='utf-8');(root/'b.py').write_text('from a import hello\nprint(hello("x"))\n',encoding='utf-8');r=index_root(db,root);hits=search(db,'hello');ctx=context_pack(db,'hello function');assert r['changed']==2 and hits and 'hello' in ctx['text'];return {'index':r,'hits':len(hits),'context_chars':ctx['chars']}
    ok('03_CODE_INTELLIGENCE_CONTEXT_PACK',t_code)
    def t_provider():
        pc=ProviderCircuit(db);assert classify(413,'TPM limit')=='request_too_large';r=pc.record_failure('groq','x',413,'TPM limit',18000);assert pc.allowed('groq','x',2000)['allowed'];assert not pc.allowed('groq','x',17000)['allowed'];pc.record_success('groq','x');assert not pc.allowed('groq','x',17000)['allowed'];return {'classification':r,'rows':pc.rows()}
    ok('04_PROVIDER_CIRCUIT',t_provider)
    def t_lane():
        a=choose_lane('Quotation',False,False,1000,'');b=choose_lane('Business Proposal',True,False,1000,'deep research');assert a['lane']=='FAST' and b['lane']=='DEEP';return {'quote':a,'proposal':b,'quote_budget':prompt_budget('Quotation','FAST')}
    ok('05_EXECUTION_LANES',t_lane)
    def t_opt():
        op=SweetSpotOptimizer(db);r=op.run({'context':[4000,8000,16000],'repairs':[0,1]},lambda p:{'quality':1.0 if p['context']>=8000 else .8,'elapsed_ms':p['context']/10+p['repairs']*100},max_trials=10);assert r['best'] and r['best']['params']['context']==8000 and r['best']['params']['repairs']==0;return r
    ok('06_SWEET_SPOT_OPTIMIZER',t_opt)
    def t_telemetry():
        tel=Telemetry(db)
        with tel.span('test','unit'):time.sleep(.005)
        with db.connect() as c:n=c.execute("SELECT COUNT(*) FROM events WHERE component='test'").fetchone()[0]
        assert n>=2;return {'events':n}
    ok('07_FLIGHT_RECORDER',t_telemetry)
    def t_schedule():
        s=Scheduler(db);sid=s.add('fast','sleep_test',{'seconds':0.01},'interval','1');withdb=None
        with db.connect() as c:c.execute('UPDATE schedules SET next_run_at=? WHERE id=?',(time.time()-1,sid))
        jobs=s.enqueue_due();assert jobs;return {'schedule_id':sid,'jobs':jobs}
    ok('08_SCHEDULER_CRON_FOUNDATION',t_schedule)
    def t_plugin():
        pr=td/'plug';pr.mkdir();(pr/'demo_plugin.py').write_text('VALUE=42\ndef run(): return VALUE\n',encoding='utf-8');pm=PluginManager(db,td/'plugins');pm.register({'id':'demo','version':'1','enabled':True,'entrypoint':'demo_plugin:run','python_path':str(pr),'capabilities':['demo']});fn=pm.load('demo');assert fn()==42;pm.hibernate('demo');return {'plugins':pm.list()}
    ok('09_PLUGIN_LAZY_LOAD',t_plugin)
    def t_supervisor():
        s=socket.socket();s.bind(('127.0.0.1',0));s.listen(1);port=s.getsockname()[1];sup=Supervisor(db);sup.register('test','127.0.0.1',port,'ACTIVE');r=sup.check('test');s.close();assert r['healthy'];return r
    ok('10_SERVICE_SUPERVISOR',t_supervisor)
    def t_upload():
        um=UploadManager(db,td/'uploads');data=(b'abc123'*100000)+b'end';full=hashlib.sha256(data).hexdigest();st=um.start('big.bin',len(data),chunk_size=100000,total_sha256=full);uid=st['upload_id'];chunks=[data[i:i+100000] for i in range(0,len(data),100000)]
        for i,b in enumerate(chunks[:3]):um.put_chunk(uid,i,b,hashlib.sha256(b).hexdigest())
        before=um.status(uid);assert before['received_bytes']<len(data)
        for i,b in enumerate(chunks[3:],3):um.put_chunk(uid,i,b,hashlib.sha256(b).hexdigest())
        r=um.finalize(uid);assert r['sha256']==full and Path(r['file_path']).exists();return {'resume_bytes':before['received_bytes'],'final':r}
    ok('11_RESUMABLE_CHUNK_UPLOAD',t_upload)
    passed=sum(1 for x in results if x['status']=='PASS');return {'ok':passed==len(results),'passed':passed,'total':len(results),'results':results,'temp':str(td)}

def main():
    r=run();print(json.dumps(r,indent=2,ensure_ascii=False,default=str));raise SystemExit(0 if r['ok'] else 9)
if __name__=='__main__':main()
