from __future__ import annotations
import datetime as dt, json, time, uuid

def next_time(schedule_type,value,now=None):
    now=float(now or time.time())
    if schedule_type=='interval':return now+max(1,int(value))
    if schedule_type=='daily':
        hh,mm=[int(x) for x in str(value).split(':',1)];d=dt.datetime.fromtimestamp(now);cand=d.replace(hour=hh,minute=mm,second=0,microsecond=0)
        if cand.timestamp()<=now:cand+=dt.timedelta(days=1)
        return cand.timestamp()
    raise ValueError('UNSUPPORTED_SCHEDULE')

class Scheduler:
    def __init__(self,db):self.db=db
    def add(self,name,kind,payload,schedule_type,value,priority=20,enabled=True):
        sid=uuid.uuid4().hex[:12];now=time.time();nxt=next_time(schedule_type,value,now)
        with self.db.connect() as c:c.execute('INSERT INTO schedules(id,name,kind,payload_json,schedule_type,schedule_value,priority,enabled,next_run_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,name,kind,json.dumps(payload or {}),schedule_type,str(value),int(priority),int(bool(enabled)),nxt,now))
        return sid
    def due(self,now=None):
        now=float(now or time.time())
        with self.db.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM schedules WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at',(now,)).fetchall()]
    def enqueue_due(self):
        now=time.time();rows=self.due(now);created=[]
        for r in rows:
            jid=self.db.create_job(r['kind'],json.loads(r['payload_json']),priority=r['priority']);created.append(jid)
            nxt=next_time(r['schedule_type'],r['schedule_value'],now)
            with self.db.connect() as c:c.execute('UPDATE schedules SET last_run_at=?,next_run_at=? WHERE id=?',(now,nxt,r['id']))
        return created
    def list(self):
        with self.db.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM schedules ORDER BY name').fetchall()]
