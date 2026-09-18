from __future__ import annotations
import hashlib, json, os, threading, time, traceback, uuid
from pathlib import Path
from .resources import snapshot, allowed
from . import code_intel

class PauseRequested(Exception): pass
class CancelRequested(Exception): pass

class WorkEngine:
    def __init__(self,db,data_root,telemetry=None):
        self.db=db;self.data_root=Path(data_root);self.telemetry=telemetry;self.stop_event=threading.Event();self.handlers={}
        self.register('sleep_test',self._sleep_test);self.register('file_hash',self._file_hash);self.register('code_index',self._code_index);self.register('service_health',self._service_health)
        self.supervisor=None
    def register(self,kind,fn):self.handlers[kind]=fn
    def set_supervisor(self,s):self.supervisor=s
    def _sleep_test(self,ctx,payload):
        total=float(payload.get('seconds',0.1));steps=max(1,int(payload.get('steps',2)))
        for i in range(steps):ctx.stage(f'sleep-{i+1}',lambda:time.sleep(total/steps),checkpoint={'step':i+1})
        return {'slept':total,'steps':steps}
    def _file_hash(self,ctx,payload):
        p=Path(payload['path'])
        def run():
            h=hashlib.sha256()
            with open(p,'rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
            return {'sha256':h.hexdigest(),'size':p.stat().st_size}
        return ctx.stage('hash',run)
    def _code_index(self,ctx,payload):return ctx.stage('index',lambda:code_intel.index_root(self.db,payload['root'],int(payload.get('max_files',5000))))
    def _service_health(self,ctx,payload):
        if not self.supervisor:raise RuntimeError('SUPERVISOR_NOT_SET')
        def run():
            result=self.supervisor.summary(bool(payload.get('recover',False)))
            if not result['ok']:
                raise RuntimeError('REQUIRED_SERVICES_UNHEALTHY='+','.join(result['required_unhealthy']))
            return result
        return ctx.stage('services',run)
    def run_one(self,worker_id=None):
        wid=worker_id or ('worker-'+uuid.uuid4().hex[:8]);job=self.db.acquire_job(wid)
        if not job:return None
        resources=json.loads(job.get('resources_json') or '{}');limits=resources.get('limits') or {}
        if limits:
            res=allowed(snapshot(self.data_root),limits)
            if not res['allowed']:
                self.db.update_job(job['id'],state='QUEUED',available_at=time.time()+15,worker_id=None,lease_until=None,error='WAITING_RESOURCES:'+','.join(res['reasons']))
                return {'job_id':job['id'],'state':'WAITING_RESOURCES','resource':res}
        fn=self.handlers.get(job['kind'])
        if not fn:
            self.db.update_job(job['id'],state='FAIL',error='UNKNOWN_JOB_KIND',worker_id=None,lease_until=None);return {'job_id':job['id'],'state':'FAIL'}
        ctx=JobContext(self.db,job['id'],wid)
        try:
            payload=json.loads(job['payload_json'] or '{}');result=fn(ctx,payload)
            ctl=self.db.get_job(job['id'])
            if ctl and ctl['state']=='PAUSED':
                self.db.update_job(job['id'],worker_id=None,lease_until=None,current_stage=None)
                return {'job_id':job['id'],'state':'PAUSED'}
            if ctl and ctl['state']=='CANCELLED':
                self.db.update_job(job['id'],worker_id=None,lease_until=None,current_stage=None)
                return {'job_id':job['id'],'state':'CANCELLED'}
            self.db.update_job(job['id'],state='PASS',result_json=json.dumps(result or {},ensure_ascii=False),worker_id=None,lease_until=None,current_stage=None,error=None)
            self.db.event('work','JOB_PASS',job_id=job['id'],data=result or {})
            return {'job_id':job['id'],'state':'PASS','result':result}
        except PauseRequested:
            self.db.update_job(job['id'],state='PAUSED',worker_id=None,lease_until=None,current_stage=None)
            return {'job_id':job['id'],'state':'PAUSED'}
        except CancelRequested:
            self.db.update_job(job['id'],state='CANCELLED',worker_id=None,lease_until=None,current_stage=None)
            return {'job_id':job['id'],'state':'CANCELLED'}
        except Exception as e:
            j=self.db.get_job(job['id']);retry=int(j['retries'])+1
            if retry<=int(j['max_retries']):
                self.db.update_job(job['id'],state='QUEUED',retries=retry,available_at=time.time()+min(60,2**retry),worker_id=None,lease_until=None,error=str(e)[:2000])
                state='RETRY_QUEUED'
            else:
                self.db.update_job(job['id'],state='FAIL',retries=retry,worker_id=None,lease_until=None,error=str(e)[:2000]);state='FAIL'
            self.db.event('work','JOB_ERROR',job_id=job['id'],level='ERROR',data={'error':str(e)[:2000],'trace':traceback.format_exc()[-4000:]})
            return {'job_id':job['id'],'state':state,'error':str(e)}
    def worker_loop(self,interval=0.5):
        wid='worker-'+uuid.uuid4().hex[:8]
        while not self.stop_event.is_set():
            r=self.run_one(wid)
            if not r:self.stop_event.wait(interval)

class JobContext:
    def __init__(self,db,job_id,worker_id):self.db=db;self.job_id=job_id;self.worker_id=worker_id;self.attempts={}
    def _check_control(self):
        j=self.db.get_job(self.job_id)
        if j and j['state']=='PAUSED':raise PauseRequested()
        if j and j['state']=='CANCELLED':raise CancelRequested()
    def stage(self,name,fn,checkpoint=None):
        self._check_control()
        att=self.attempts.get(name,0)+1;self.attempts[name]=att;self.db.stage_start(self.job_id,name,att,checkpoint)
        self.db.heartbeat(self.job_id,self.worker_id)
        try:r=fn()
        except Exception as e:self.db.stage_fail(self.job_id,name,att,str(e));raise
        self.db.stage_finish(self.job_id,name,att,r if isinstance(r,dict) else {'value':r},checkpoint);self.db.heartbeat(self.job_id,self.worker_id);self._check_control();return r
