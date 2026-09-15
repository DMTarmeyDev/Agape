from __future__ import annotations
import json, sqlite3, threading, time, uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = r'''
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 50,
  lane TEXT NOT NULL DEFAULT 'STANDARD',
  resources_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  available_at REAL NOT NULL,
  retries INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 2,
  worker_id TEXT,
  lease_until REAL,
  current_stage TEXT,
  checkpoint_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_state_avail ON jobs(state, available_at, priority, created_at);
CREATE TABLE IF NOT EXISTS job_stages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  name TEXT NOT NULL,
  state TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 1,
  started_at REAL,
  finished_at REAL,
  checkpoint_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT,
  error TEXT,
  UNIQUE(job_id,name,attempt)
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  job_id TEXT,
  component TEXT NOT NULL,
  stage TEXT,
  level TEXT NOT NULL,
  event TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id,id);
CREATE TABLE IF NOT EXISTS schedules(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  schedule_type TEXT NOT NULL,
  schedule_value TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 20,
  enabled INTEGER NOT NULL DEFAULT 1,
  next_run_at REAL,
  last_run_at REAL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_health(
  provider TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL,
  failure_class TEXT,
  fail_count INTEGER NOT NULL DEFAULT 0,
  retry_at REAL,
  max_request_chars INTEGER,
  last_status TEXT,
  updated_at REAL NOT NULL,
  PRIMARY KEY(provider,model)
);
CREATE TABLE IF NOT EXISTS plugins(
  plugin_id TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  installed INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'COLD',
  entrypoint TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  manifest_json TEXT NOT NULL DEFAULT '{}',
  last_used_at REAL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS services(
  name TEXT PRIMARY KEY,
  host TEXT NOT NULL,
  port INTEGER NOT NULL,
  expected_state TEXT NOT NULL,
  start_cmd_json TEXT,
  last_state TEXT,
  last_checked_at REAL,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS uploads(
  upload_id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  total_size INTEGER NOT NULL,
  chunk_size INTEGER NOT NULL,
  total_sha256 TEXT,
  state TEXT NOT NULL,
  object_path TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS upload_chunks(
  upload_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  state TEXT NOT NULL,
  path TEXT NOT NULL,
  updated_at REAL NOT NULL,
  PRIMARY KEY(upload_id,chunk_index)
);
CREATE TABLE IF NOT EXISTS code_files(
  path TEXT PRIMARY KEY,
  size INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  language TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS code_symbols(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  line INTEGER NOT NULL,
  end_line INTEGER,
  signature TEXT
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON code_symbols(name);
CREATE TABLE IF NOT EXISTS code_chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON code_chunks(path);
CREATE TABLE IF NOT EXISTS optimizer_runs(
  run_id TEXT NOT NULL,
  trial INTEGER NOT NULL,
  params_json TEXT NOT NULL,
  score REAL,
  quality REAL,
  elapsed_ms REAL,
  state TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY(run_id,trial)
);
'''

class EngineDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=30000')
        try:
            yield c
        finally:
            c.close()

    def event(self, component, event, *, job_id=None, stage=None, level='INFO', data=None):
        with self.connect() as c:
            c.execute('INSERT INTO events(ts,job_id,component,stage,level,event,data_json) VALUES(?,?,?,?,?,?,?)',
                      (time.time(), job_id, component, stage, level, event, json.dumps(data or {}, ensure_ascii=False)))

    def create_job(self, kind, payload=None, priority=50, lane='STANDARD', resources=None, max_retries=2, available_at=None):
        now = time.time(); jid = uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute('INSERT INTO jobs(id,kind,payload_json,state,priority,lane,resources_json,created_at,updated_at,available_at,max_retries) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (jid, kind, json.dumps(payload or {}, ensure_ascii=False), 'QUEUED', int(priority), lane, json.dumps(resources or {}, ensure_ascii=False), now, now, float(available_at or now), int(max_retries)))
        self.event('work', 'JOB_CREATED', job_id=jid, data={'kind':kind,'priority':priority,'lane':lane})
        return jid

    def get_job(self, job_id):
        with self.connect() as c:
            r = c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        return dict(r) if r else None

    def list_jobs(self, limit=200):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?', (int(limit),)).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            for k in ('payload_json','resources_json','checkpoint_json','result_json'):
                try:d[k[:-5] if k.endswith('_json') else k]=json.loads(d[k]) if d.get(k) else None
                except Exception:pass
            out.append(d)
        return out

    def update_job(self, job_id, **fields):
        allowed={'state','priority','available_at','retries','worker_id','lease_until','current_stage','checkpoint_json','result_json','error','lane'}
        clean={k:v for k,v in fields.items() if k in allowed}
        if not clean:return
        clean['updated_at']=time.time()
        cols=', '.join(f'{k}=?' for k in clean)
        vals=list(clean.values())+[job_id]
        with self.connect() as c:c.execute(f'UPDATE jobs SET {cols} WHERE id=?', vals)

    def acquire_job(self, worker_id, lease_seconds=30):
        now=time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("UPDATE jobs SET state='QUEUED', worker_id=NULL, lease_until=NULL, updated_at=? WHERE state='RUNNING' AND lease_until IS NOT NULL AND lease_until < ?",(now,now))
            row=c.execute("SELECT * FROM jobs WHERE state='QUEUED' AND available_at<=? ORDER BY priority DESC, created_at ASC LIMIT 1",(now,)).fetchone()
            if not row:
                c.execute('COMMIT'); return None
            c.execute("UPDATE jobs SET state='RUNNING',worker_id=?,lease_until=?,updated_at=? WHERE id=? AND state='QUEUED'",(worker_id,now+lease_seconds,now,row['id']))
            changed=c.execute('SELECT changes()').fetchone()[0]
            c.execute('COMMIT')
            if not changed:return None
        return self.get_job(row['id'])

    def heartbeat(self, job_id, worker_id, lease_seconds=30):
        with self.connect() as c:
            c.execute("UPDATE jobs SET lease_until=?,updated_at=? WHERE id=? AND worker_id=? AND state='RUNNING'",(time.time()+lease_seconds,time.time(),job_id,worker_id))

    def stage_start(self, job_id, name, attempt=1, checkpoint=None):
        now=time.time()
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO job_stages(job_id,name,state,attempt,started_at,checkpoint_json) VALUES(?,?,?,?,?,?)',
                      (job_id,name,'RUNNING',int(attempt),now,json.dumps(checkpoint or {},ensure_ascii=False)))
        self.update_job(job_id,current_stage=name)
        self.event('work','STAGE_START',job_id=job_id,stage=name)

    def stage_finish(self, job_id, name, attempt=1, result=None, checkpoint=None):
        with self.connect() as c:
            c.execute("UPDATE job_stages SET state='PASS',finished_at=?,result_json=?,checkpoint_json=? WHERE job_id=? AND name=? AND attempt=?",
                      (time.time(),json.dumps(result or {},ensure_ascii=False),json.dumps(checkpoint or {},ensure_ascii=False),job_id,name,int(attempt)))
        self.update_job(job_id,checkpoint_json=json.dumps(checkpoint or {},ensure_ascii=False))
        self.event('work','STAGE_PASS',job_id=job_id,stage=name,data=result or {})

    def stage_fail(self, job_id, name, attempt=1, error=''):
        with self.connect() as c:
            c.execute("UPDATE job_stages SET state='FAIL',finished_at=?,error=? WHERE job_id=? AND name=? AND attempt=?",(time.time(),str(error)[:4000],job_id,name,int(attempt)))
        self.event('work','STAGE_FAIL',job_id=job_id,stage=name,level='ERROR',data={'error':str(error)[:2000]})
