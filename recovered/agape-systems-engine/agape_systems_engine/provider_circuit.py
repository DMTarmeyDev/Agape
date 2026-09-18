from __future__ import annotations
import json, re, time

TTL={'auth':86400,'credits':21600,'daily_quota':3600,'rate_limit':60,'transient':120,'validation':30}

def classify(http_status=None,error=''):
    s=(error or '').lower();code=int(http_status) if str(http_status or '').isdigit() else None
    if code in (401,403) or any(x in s for x in ('invalid api key','unauthorized','not logged in','bad credentials')):return 'auth'
    if code==402 or 'payment required' in s or 'out of credits' in s or 'no team credits' in s:return 'credits'
    if code==413 or 'request too large' in s or 'token limit' in s or 'tpm limit' in s:return 'request_too_large'
    if code==429:
        if any(x in s for x in ('daily','free allocation','quota exhausted')):return 'daily_quota'
        return 'rate_limit'
    if code in (408,500,502,503,504) or any(x in s for x in ('timeout','timed out','connection refused','temporarily')):return 'transient'
    if any(x in s for x in ('validation','empty response','malformed')):return 'validation'
    return 'unknown'

class ProviderCircuit:
    def __init__(self,db):self.db=db
    def record_success(self,provider,model='',status='PASS'):
        with self.db.connect() as c:
            old=c.execute('SELECT max_request_chars FROM provider_health WHERE provider=? AND model=?',(provider,model)).fetchone()
            max_chars=int(old['max_request_chars']) if old and old['max_request_chars'] else None
            c.execute("INSERT OR REPLACE INTO provider_health(provider,model,state,failure_class,fail_count,retry_at,max_request_chars,last_status,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(provider,model,'HEALTHY',None,0,None,max_chars,status,time.time()))
    def record_failure(self,provider,model='',http_status=None,error='',request_chars=None):
        fc=classify(http_status,error);now=time.time()
        with self.db.connect() as c:
            old=c.execute('SELECT * FROM provider_health WHERE provider=? AND model=?',(provider,model)).fetchone();fails=(int(old['fail_count']) if old else 0)+1
            retry=None;state='DEGRADED';max_chars=(int(old['max_request_chars']) if old and old['max_request_chars'] else None)
            if fc=='request_too_large':
                if request_chars:max_chars=max(1000,int(request_chars*0.80))
                state='HEALTHY'
            elif fc in TTL:
                retry=now+TTL[fc];state='OPEN'
            c.execute("INSERT OR REPLACE INTO provider_health(provider,model,state,failure_class,fail_count,retry_at,max_request_chars,last_status,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(provider,model,state,fc,fails,retry,max_chars,(str(http_status or '')+' '+error)[:1000],now))
        return {'failure_class':fc,'state':state,'retry_at':retry,'max_request_chars':max_chars}
    def allowed(self,provider,model='',request_chars=None):
        with self.db.connect() as c:r=c.execute('SELECT * FROM provider_health WHERE provider=? AND model=?',(provider,model)).fetchone()
        if not r:return {'allowed':True,'reason':'UNKNOWN_HEALTH'}
        d=dict(r);now=time.time()
        if d.get('max_request_chars') and request_chars and request_chars>int(d['max_request_chars']):return {'allowed':False,'reason':'REQUEST_TOO_LARGE_FOR_PROVIDER','max_request_chars':d['max_request_chars']}
        if d['state']=='OPEN' and d.get('retry_at') and float(d['retry_at'])>now:return {'allowed':False,'reason':d.get('failure_class') or 'CIRCUIT_OPEN','retry_at':d['retry_at']}
        return {'allowed':True,'reason':'HEALTHY_OR_RETRY_DUE'}
    def rows(self):
        with self.db.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM provider_health ORDER BY provider,model').fetchall()]

PROMPT_BUDGETS={
 'Quotation':6000,'Business Letter':4500,'Meeting Minutes':6000,'Project Plan':9000,
 'Business Report':12000,'Technical Report':14000,'Business Proposal':14000,'DEEP':30000
}
def prompt_budget(doc_type,lane='STANDARD'):
    if lane=='DEEP':return PROMPT_BUDGETS['DEEP']
    base=PROMPT_BUDGETS.get(doc_type,10000)
    if lane=='FAST':return max(3500,int(base*0.7))
    return base
