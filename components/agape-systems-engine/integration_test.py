from __future__ import annotations
import argparse, hashlib, json, time, urllib.request, urllib.parse

def req(base,path,method='GET',obj=None,data=None,headers=None,timeout=20):
    if obj is not None:
        data=json.dumps(obj).encode('utf-8');headers={'Content-Type':'application/json'}
    r=urllib.request.Request(base+path,data=data,method=method,headers=headers or {})
    with urllib.request.urlopen(r,timeout=timeout) as x:
        raw=x.read().decode('utf-8','replace');return json.loads(raw)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--core-root',required=True);ap.add_argument('--require-core',action='store_true');a=ap.parse_args();b=a.base.rstrip('/');checks=[]
    def check(name,fn):
        try:r=fn();checks.append({'name':name,'status':'PASS','detail':r})
        except Exception as e:checks.append({'name':name,'status':'FAIL','error':repr(e)})
    check('HTTP_HEALTH',lambda:(lambda r:(r if r.get('ok') else (_ for _ in ()).throw(AssertionError(r))))(req(b,'/api/health')))
    check('CODE_INDEX',lambda:(lambda r:(r if r.get('ok') else (_ for _ in ()).throw(AssertionError(r))))(req(b,'/api/code/index','POST',{'root':a.core_root,'max_files':700})))
    check('CONTEXT_PACK',lambda:(lambda r:(r if r.get('hits',0)>=1 else (_ for _ in ()).throw(AssertionError(r))))(req(b,'/api/code/context?q=def')))
    check('FAST_LANE',lambda:(lambda r:(r if r.get('lane')=='FAST' and r.get('prompt_budget',99999)<=6000 else (_ for _ in ()).throw(AssertionError(r))))(req(b,'/api/lanes/choose','POST',{'doc_type':'Quotation','source_chars':1200})))
    def queue():
        j=req(b,'/api/jobs','POST',{'kind':'sleep_test','payload':{'seconds':0.25,'steps':5},'priority':99})['job_id'];time.sleep(.06);req(b,f'/api/jobs/{j}/pause','POST');time.sleep(.35);s=req(b,'/api/status');row=next(x for x in s['jobs'] if x['id']==j);assert row['state']=='PAUSED',row;req(b,f'/api/jobs/{j}/resume','POST');deadline=time.time()+5
        while time.time()<deadline:
            s=req(b,'/api/status');row=next(x for x in s['jobs'] if x['id']==j)
            if row['state'] in ('PASS','FAIL'):break
            time.sleep(.1)
        assert row['state']=='PASS',row;return {'job_id':j,'final_state':row['state']}
    check('QUEUE_PAUSE_RESUME',queue)
    def upload():
        blob=(b'AGAPE-CHUNK-'*50000)+b'END';full=hashlib.sha256(blob).hexdigest();chunk=131072;u=req(b,'/api/uploads/start','POST',{'filename':'integration-resume.bin','total_size':len(blob),'chunk_size':chunk,'total_sha256':full})['upload_id'];parts=[blob[i:i+chunk] for i in range(0,len(blob),chunk)]
        for i,x in enumerate(parts[:2]):req(b,f'/api/uploads/{u}/chunk/{i}?sha256={hashlib.sha256(x).hexdigest()}','PUT',data=x,headers={'Content-Type':'application/octet-stream'})
        mid=req(b,f'/api/uploads/{u}/status');assert 0<mid['received_bytes']<len(blob)
        for i,x in enumerate(parts[2:],2):req(b,f'/api/uploads/{u}/chunk/{i}?sha256={hashlib.sha256(x).hexdigest()}','PUT',data=x,headers={'Content-Type':'application/octet-stream'})
        r=req(b,f'/api/uploads/{u}/finalize','POST');assert r['sha256']==full;return {'upload_id':u,'resumed_from_bytes':mid['received_bytes'],'sha256':full}
    check('RESUMABLE_UPLOAD',upload)
    def service_check():
        r=req(b,'/api/services/check?recover=1' if a.require_core else '/api/services/check',timeout=60)
        if a.require_core and not r.get('ok'):
            raise AssertionError(r)
        return r
    check('SERVICE_SUPERVISOR',service_check)
    result={'ok':all(x['status']=='PASS' for x in checks),'passed':sum(x['status']=='PASS' for x in checks),'total':len(checks),'checks':checks}
    print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['ok'] else 9)
if __name__=='__main__':main()
