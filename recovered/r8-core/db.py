from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import DB_PATH, DATA_ROOT

_LOCK = threading.RLock()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kind TEXT NOT NULL DEFAULT 'user',
    archived INTEGER NOT NULL DEFAULT 0,
    hidden_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '',
    settings_json TEXT NOT NULL DEFAULT '{}',
    last_test_status TEXT NOT NULL DEFAULT '',
    last_test_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_requests (
    request_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS project_loop_settings (
    project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    workspace TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL DEFAULT '',
    test_command TEXT NOT NULL DEFAULT '',
    max_steps INTEGER NOT NULL DEFAULT 4,
    auto_model INTEGER NOT NULL DEFAULT 1,
    model TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_loop_runs (
    run_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    goal TEXT NOT NULL,
    workspace TEXT NOT NULL,
    test_command TEXT NOT NULL,
    model TEXT NOT NULL,
    auto_model INTEGER NOT NULL DEFAULT 1,
    max_steps INTEGER NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_loop_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES project_loop_runs(run_id) ON DELETE CASCADE,
    step_no INTEGER NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS autodev_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    goal TEXT NOT NULL,
    test_command TEXT NOT NULL DEFAULT '',
    max_steps INTEGER NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'pending',
    run_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS terminal_jobs (
    job_id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL,
    exit_code INTEGER,
    stdout TEXT NOT NULL DEFAULT '',
    stderr TEXT NOT NULL DEFAULT '',
    risk TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_project_id ON messages(project_id,id);
CREATE INDEX IF NOT EXISTS idx_chat_requests_project_id ON chat_requests(project_id,created_at);
CREATE INDEX IF NOT EXISTS idx_terminal_jobs_created_at ON terminal_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_project_loop_runs_project_id ON project_loop_runs(project_id,created_at);
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_open_fingerprint ON issues(project_id,fingerprint) WHERE status='open';
CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id,status,id);
CREATE INDEX IF NOT EXISTS idx_project_loop_steps_run_id ON project_loop_steps(run_id,id);

CREATE TABLE IF NOT EXISTS autodev_sessions (
    session_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    workspace TEXT NOT NULL,
    goal TEXT NOT NULL,
    test_command TEXT NOT NULL,
    max_steps INTEGER NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'prepared',
    current_task TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '',
    snapshot_sha256 TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL DEFAULT 'coding',
    success INTEGER NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    failure_category TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES autodev_sessions(session_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL DEFAULT '',
    entry_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_autodev_sessions_project ON autodev_sessions(project_id,created_at);
CREATE INDEX IF NOT EXISTS idx_model_outcomes_model ON model_outcomes(model,task_type,id);
CREATE INDEX IF NOT EXISTS idx_run_ledger_session ON run_ledger(session_id,id);
CREATE TABLE IF NOT EXISTS test_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    failure_hash TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_test_observations_project_test ON test_observations(project_id,test_name,id);
CREATE TABLE IF NOT EXISTS supervisor_runs (
    supervisor_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    workspace TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',
    cycle_no INTEGER NOT NULL DEFAULT 0,
    max_cycles INTEGER NOT NULL DEFAULT 2,
    confidence REAL NOT NULL DEFAULT 0,
    plan_json TEXT NOT NULL DEFAULT '{}',
    checkpoint_ref TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_supervisor_runs_project ON supervisor_runs(project_id,created_at);
CREATE TABLE IF NOT EXISTS deferred_work (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    goal TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_deferred_work_project ON deferred_work(project_id,status,id);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL DEFAULT '',
    entry_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_events_id ON audit_events(id);
CREATE TABLE IF NOT EXISTS alpha_release_runs (
    run_id TEXT PRIMARY KEY,
    build TEXT NOT NULL,
    status TEXT NOT NULL,
    proof_sha256 TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_alpha_release_runs_created ON alpha_release_runs(created_at);
"""


def connect(read_only: bool = False) -> sqlite3.Connection:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    if read_only:
        uri = "file:" + str(DB_PATH).replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        conn=connect()
        try:
            conn.executescript(SCHEMA)
            connection_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(connections)").fetchall()}
            if "last_test_status" not in connection_cols:
                conn.execute("ALTER TABLE connections ADD COLUMN last_test_status TEXT NOT NULL DEFAULT ''")
            if "last_test_detail" not in connection_cols:
                conn.execute("ALTER TABLE connections ADD COLUMN last_test_detail TEXT NOT NULL DEFAULT ''")
            project_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
            if "kind" not in project_cols:
                conn.execute("ALTER TABLE projects ADD COLUMN kind TEXT NOT NULL DEFAULT 'user'")
            if "archived" not in project_cols:
                conn.execute("ALTER TABLE projects ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            if "hidden_reason" not in project_cols:
                conn.execute("ALTER TABLE projects ADD COLUMN hidden_reason TEXT NOT NULL DEFAULT ''")
            _classify_existing_projects_conn(conn)
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','9')")
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('legacy_imported','false')")
            conn.commit()
        finally:
            conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def rows(sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn=connect(read_only=True)
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def row(sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    conn=connect(read_only=True)
    try:
        r = conn.execute(sql, args).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def execute(sql: str, args: tuple[Any, ...] = ()) -> int:
    with transaction() as conn:
        cur = conn.execute(sql, args)
        return int(cur.lastrowid or 0)


PROJECT_KINDS = {"user", "autodev", "template", "test", "system"}

def _classification_for_name(name: str) -> tuple[str, int, str]:
    n=(name or '').strip(); u=n.upper()
    if u in {'TEMPLATE 1 - SYSTEM STRESS TEST','TEMPLATE 2 - SNAKE GAME'}: return ('template',1,'template_workflow')
    if u == 'TEST': return ('test',1,'temporary_test_project')
    if u.startswith('AGAPE AUTODEV GAUNTLET'): return ('system',1,'gauntlet_test_project')
    if u.startswith('AGAPE NEXT') or u.startswith('NEXT20 RUNTIME') or u.startswith('RUNTIME GATE') or u.startswith('V16 ACCEPTANCE') or u.startswith('V17 ACCEPTANCE'):
        return ('autodev',1,'autodev_internal_project')
    return ('user',0,'')

def _classify_existing_projects_conn(conn: sqlite3.Connection) -> dict[str,int]:
    changed=0
    for r in conn.execute("SELECT id,name,kind,archived,hidden_reason FROM projects").fetchall():
        kind,archived,reason=_classification_for_name(str(r['name']))
        current_kind=str(r['kind'] or 'user'); current_arch=int(r['archived'] or 0)
        # Only auto-hide known system-generated names. Never auto-unarchive or relabel unknown user projects.
        if kind != 'user' and (current_kind!=kind or current_arch!=archived or str(r['hidden_reason'] or '')!=reason):
            conn.execute("UPDATE projects SET kind=?,archived=?,hidden_reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(kind,archived,reason,int(r['id']))); changed+=1
    return {'changed':changed}

def classify_existing_projects() -> dict[str,Any]:
    with transaction() as conn: result=_classify_existing_projects_conn(conn)
    result.update(project_catalog_status()); result['ok']=True; return result

def create_project(name: str, kind: str='user', archived: bool=False) -> dict[str, Any]:
    name=(name or '').strip(); kind=str(kind or 'user').strip().lower()
    if not name: raise ValueError('PROJECT_NAME_REQUIRED')
    if len(name)>120: raise ValueError('PROJECT_NAME_TOO_LONG')
    if kind not in PROJECT_KINDS: raise ValueError('PROJECT_KIND_INVALID')
    project_id=execute("INSERT INTO projects(name,kind,archived) VALUES(?,?,?)",(name,kind,1 if archived else 0))
    return row("SELECT * FROM projects WHERE id=?",(project_id,)) or {}

def set_project_classification(project_id: int, kind: str, archived: bool, reason: str='') -> dict[str,Any]:
    kind=str(kind or '').strip().lower()
    if kind not in PROJECT_KINDS: raise ValueError('PROJECT_KIND_INVALID')
    with transaction() as conn:
        cur=conn.execute("UPDATE projects SET kind=?,archived=?,hidden_reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(kind,1 if archived else 0,str(reason or ''),int(project_id)))
        if cur.rowcount!=1: raise ValueError('PROJECT_NOT_FOUND')
    return project(project_id) or {}

def delete_project(project_id: int) -> None:
    with transaction() as conn:
        cur=conn.execute("DELETE FROM projects WHERE id=?",(project_id,))
        if cur.rowcount != 1: raise ValueError("PROJECT_NOT_FOUND")

def list_projects(scope: str='user') -> list[dict[str, Any]]:
    scope=str(scope or 'user').strip().lower()
    if scope=='all': return rows("SELECT * FROM projects ORDER BY updated_at DESC,id DESC")
    if scope=='hidden': return rows("SELECT * FROM projects WHERE archived=1 ORDER BY updated_at DESC,id DESC")
    if scope=='active': return rows("SELECT * FROM projects WHERE archived=0 ORDER BY updated_at DESC,id DESC")
    if scope!='user': raise ValueError('PROJECT_SCOPE_INVALID')
    return rows("SELECT * FROM projects WHERE archived=0 AND kind='user' ORDER BY updated_at DESC,id DESC")

def project_catalog_status() -> dict[str,Any]:
    all_rows=rows("SELECT kind,archived,COUNT(*) AS count FROM projects GROUP BY kind,archived ORDER BY kind,archived")
    return {'ok':True,'visible_user_projects':sum(int(x['count']) for x in all_rows if x['kind']=='user' and int(x['archived'])==0),'hidden_projects':sum(int(x['count']) for x in all_rows if int(x['archived'])==1),'groups':all_rows}

def project(project_id: int) -> dict[str, Any] | None:
    return row("SELECT * FROM projects WHERE id=?",(project_id,))


def add_message(project_id: int, role: str, content: str, provider: str = "", model: str = "") -> int:
    return execute(
        "INSERT INTO messages(project_id,role,provider,model,content) VALUES(?,?,?,?,?)",
        (project_id, role, provider, model, content),
    )


def list_messages(project_id: int, limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    return rows(
        "SELECT * FROM (SELECT * FROM messages WHERE project_id=? ORDER BY id DESC LIMIT ?) x ORDER BY id ASC",
        (project_id, limit),
    )


def start_request(request_id: str, project_id: int, provider: str, model: str) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO chat_requests(request_id,project_id,status,stage,provider,model) VALUES(?,?,?,?,?,?)",
            (request_id, project_id, "running", "QUEUED", provider, model),
        )


def update_request(request_id: str, stage: str, status: str = "running", error: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE chat_requests SET status=?,stage=?,error=?,updated_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP WHERE request_id=?",
            (status, stage, error, request_id),
        )


def finish_request(request_id: str, status: str, stage: str, error: str = "") -> None:
    update_request(request_id, stage=stage, status=status, error=error)



def recover_incomplete_requests() -> int:
    """Mark requests left running by a prior process as interrupted on startup."""
    with transaction() as conn:
        cur = conn.execute(
            "UPDATE chat_requests SET status='interrupted',stage='INTERRUPTED_RESTART',"
            "error='PROCESS_RESTARTED',updated_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP "
            "WHERE status='running'"
        )
        return int(cur.rowcount or 0)

def terminal_job_create(job_id: str, project_id: int | None, command: str, risk: str) -> None:
    execute(
        "INSERT INTO terminal_jobs(job_id,project_id,command,status,risk) VALUES(?,?,?,?,?)",
        (job_id, project_id, command, "running", risk),
    )


def terminal_job_finish(job_id: str, exit_code: int, stdout: str, stderr: str) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE terminal_jobs SET status=?,exit_code=?,stdout=?,stderr=?,finished_at=CURRENT_TIMESTAMP WHERE job_id=?",
            ("completed" if exit_code == 0 else "failed", int(exit_code), stdout, stderr, job_id),
        )


def terminal_history(limit: int = 100) -> list[dict[str, Any]]:
    return rows(
        "SELECT job_id,project_id,command,status,exit_code,stdout,stderr,risk,created_at,finished_at FROM terminal_jobs ORDER BY rowid DESC LIMIT ?",
        (max(1, min(int(limit), 500)),),
    )


def status() -> dict[str, Any]:
    conn=connect(read_only=True)
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        counts = {}
        for table in ("projects", "messages", "connections", "chat_requests", "terminal_jobs", "project_loop_settings", "project_loop_runs", "project_loop_steps", "autodev_sessions", "model_outcomes", "run_ledger", "test_observations", "supervisor_runs", "deferred_work", "audit_events", "alpha_release_runs"):
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return {
            "ok": str(quick).lower() == "ok",
            "quick_check": str(quick),
            "database": str(DB_PATH),
            "counts": counts,
        }
    finally:
        conn.close()

def save_project_loop_settings(project_id: int, workspace: str, goal: str, test_command: str, max_steps: int, auto_model: bool, model: str = "") -> None:
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE id=?", (int(project_id),)).fetchone():
            raise ValueError("PROJECT_NOT_FOUND")
        conn.execute(
            "INSERT INTO project_loop_settings(project_id,workspace,goal,test_command,max_steps,auto_model,model,updated_at) "
            "VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(project_id) DO UPDATE SET workspace=excluded.workspace,goal=excluded.goal,test_command=excluded.test_command,"
            "max_steps=excluded.max_steps,auto_model=excluded.auto_model,model=excluded.model,updated_at=CURRENT_TIMESTAMP",
            (int(project_id), str(workspace), str(goal), str(test_command), int(max_steps), 1 if auto_model else 0, str(model)),
        )
        conn.execute("UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(project_id),))


def project_loop_settings(project_id: int) -> dict[str, Any] | None:
    return row("SELECT * FROM project_loop_settings WHERE project_id=?", (int(project_id),))


def project_loop_run_start(run_id: str, project_id: int, goal: str, workspace: str, test_command: str, model: str, max_steps: int, auto_model: bool) -> None:
    with transaction() as conn:
        active = conn.execute("SELECT run_id FROM project_loop_runs WHERE project_id=? AND status='running' LIMIT 1", (int(project_id),)).fetchone()
        if active:
            raise ValueError("PROJECT_LOOP_ALREADY_RUNNING=" + str(active[0]))
        conn.execute(
            "INSERT INTO project_loop_runs(run_id,project_id,status,stage,goal,workspace,test_command,model,auto_model,max_steps,current_step) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            (str(run_id), int(project_id), "running", "STARTING", str(goal), str(workspace), str(test_command), str(model), 1 if auto_model else 0, int(max_steps)),
        )


def project_loop_run_update(run_id: str, status: str, stage: str, current_step: int, summary: str = "", error: str = "") -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE project_loop_runs SET status=?,stage=?,current_step=?,summary=?,error=?,updated_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP WHERE run_id=?",
            (str(status), str(stage), int(current_step), str(summary), str(error), str(run_id)),
        )


def project_loop_run_finish(run_id: str, status: str, stage: str, current_step: int, summary: str = "", error: str = "") -> None:
    project_loop_run_update(run_id, status, stage, current_step, summary, error)


def project_loop_step_add(run_id: str, step_no: int, phase: str, status: str, detail: dict[str, Any] | None = None) -> int:
    return execute(
        "INSERT INTO project_loop_steps(run_id,step_no,phase,status,detail_json) VALUES(?,?,?,?,?)",
        (str(run_id), int(step_no), str(phase), str(status), json.dumps(detail or {}, ensure_ascii=False)),
    )


def project_loop_runs(project_id: int, limit: int = 30) -> list[dict[str, Any]]:
    return rows(
        "SELECT * FROM project_loop_runs WHERE project_id=? ORDER BY created_at DESC,run_id DESC LIMIT ?",
        (int(project_id), max(1, min(int(limit), 100))),
    )


def project_loop_run(run_id: str) -> dict[str, Any] | None:
    item = row("SELECT * FROM project_loop_runs WHERE run_id=?", (str(run_id),))
    if not item:
        return None
    steps = rows("SELECT * FROM project_loop_steps WHERE run_id=? ORDER BY id ASC", (str(run_id),))
    for step in steps:
        try:
            step["detail"] = json.loads(str(step.pop("detail_json", "{}") or "{}"))
        except Exception:
            step["detail"] = {}
    item["steps"] = steps
    return item


def recover_incomplete_loops() -> int:
    with transaction() as conn:
        cur = conn.execute(
            "UPDATE project_loop_runs SET status='interrupted',stage='INTERRUPTED_RESTART',"
            "error='PROCESS_RESTARTED',updated_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP WHERE status='running'"
        )
        return int(cur.rowcount or 0)


# --- DMT Core V1.5 management extensions ---
def save_connection(provider: str, enabled: bool, model: str = "", settings: dict[str, Any] | None = None, last_test_status: str = "", last_test_detail: str = "") -> dict[str, Any]:
    provider = str(provider or "").strip().lower()
    if not provider:
        raise ValueError("CONNECTION_PROVIDER_REQUIRED")
    payload = json.dumps(settings or {}, ensure_ascii=False, separators=(",", ":"))
    with transaction() as conn:
        conn.execute(
            "INSERT INTO connections(provider,enabled,model,settings_json,last_test_status,last_test_detail,updated_at) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(provider) DO UPDATE SET enabled=excluded.enabled,model=excluded.model,settings_json=excluded.settings_json,last_test_status=excluded.last_test_status,last_test_detail=excluded.last_test_detail,updated_at=CURRENT_TIMESTAMP",
            (provider, 1 if enabled else 0, str(model or ""), payload, str(last_test_status or ""), str(last_test_detail or "")),
        )
    return connection(provider) or {}


def _connection_record(item: dict[str, Any]) -> dict[str, Any]:
    value = dict(item)
    value["enabled"] = bool(value.get("enabled"))
    try:
        value["settings"] = json.loads(str(value.get("settings_json") or "{}"))
    except Exception:
        value["settings"] = {}
    return value


def list_connections() -> list[dict[str, Any]]:
    return [_connection_record(x) for x in rows("SELECT * FROM connections ORDER BY provider ASC")]


def connection(provider: str) -> dict[str, Any] | None:
    item = row("SELECT * FROM connections WHERE provider=?", (str(provider or "").strip().lower(),))
    return _connection_record(item) if item else None


def database_tables() -> list[str]:
    return [str(x["name"]) for x in rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def database_table_rows(name: str, limit: int = 100) -> list[dict[str, Any]]:
    table = str(name or "").strip()
    if not table or not table.replace("_", "").isalnum() or table not in database_tables():
        raise ValueError("DATABASE_TABLE_NOT_ALLOWED")
    n = max(1, min(int(limit), 1000))
    return rows(f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT ?', (n,))


def backup_database(destination_dir: str) -> str:
    dest_dir = Path(str(destination_dir or "")).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / ("dmt-core-backup-" + time.strftime("%Y%m%d-%H%M%S") + ".sqlite3")
    with _LOCK:
        src = connect(read_only=False)
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close(); src.close()
    return str(dest)


def add_issue(project_id: int, fingerprint: str, title: str, detail: str='', severity: str='medium') -> dict[str,Any]:
    if not project(int(project_id)): raise ValueError('PROJECT_NOT_FOUND')
    fp=str(fingerprint or '').strip(); title=str(title or '').strip(); sev=str(severity or 'medium').lower()
    if not fp or not title: raise ValueError('ISSUE_FIELDS_REQUIRED')
    if sev not in {'critical','high','medium','low'}: sev='medium'
    with transaction() as conn:
        existing=conn.execute("SELECT * FROM issues WHERE project_id=? AND fingerprint=? AND status='open'",(int(project_id),fp)).fetchone()
        if existing:
            conn.execute("UPDATE issues SET title=?,detail=?,severity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(title,str(detail or ''),sev,int(existing['id'])))
            issue_id=int(existing['id'])
        else:
            cur=conn.execute("INSERT INTO issues(project_id,fingerprint,title,detail,severity,status) VALUES(?,?,?,?,?,'open')",(int(project_id),fp,title,str(detail or ''),sev)); issue_id=int(cur.lastrowid)
    return row("SELECT * FROM issues WHERE id=?",(issue_id,)) or {}

def list_issues(project_id: int, status: str|None=None) -> list[dict[str,Any]]:
    if status is None: return rows("SELECT * FROM issues WHERE project_id=? ORDER BY id DESC",(int(project_id),))
    state=str(status).strip().lower()
    if state not in {'open','resolved'}: raise ValueError('ISSUE_STATUS_INVALID')
    return rows("SELECT * FROM issues WHERE project_id=? AND status=? ORDER BY id DESC",(int(project_id),state))

def resolve_issue(issue_id: int) -> dict[str,Any]:
    with transaction() as conn:
        cur=conn.execute("UPDATE issues SET status='resolved',resolved_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(int(issue_id),))
        if cur.rowcount!=1: raise ValueError('ISSUE_NOT_FOUND')
    return row("SELECT * FROM issues WHERE id=?",(int(issue_id),)) or {}

def enqueue_autodev_task(project_id: int, goal: str, test_command: str = "", max_steps: int = 4) -> dict[str, Any]:
    if not project(int(project_id)):
        raise ValueError("PROJECT_NOT_FOUND")
    steps = max(1, min(int(max_steps), 8))
    item_id = execute("INSERT INTO autodev_queue(project_id,goal,test_command,max_steps,status) VALUES(?,?,?,?,?)", (int(project_id), str(goal or ""), str(test_command or ""), steps, "pending"))
    return row("SELECT * FROM autodev_queue WHERE id=?", (item_id,)) or {}


def list_autodev_queue(project_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    n=max(1,min(int(limit),500))
    if project_id is None:
        return rows("SELECT * FROM autodev_queue ORDER BY id DESC LIMIT ?", (n,))
    return rows("SELECT * FROM autodev_queue WHERE project_id=? ORDER BY id DESC LIMIT ?", (int(project_id),n))


def update_autodev_queue(item_id: int, status: str, run_id: str = "") -> dict[str, Any]:
    allowed={"pending","running","completed","failed","cancelled"}
    state=str(status or "").strip().lower()
    if state not in allowed:
        raise ValueError("AUTODEV_QUEUE_STATUS_INVALID")
    with transaction() as conn:
        cur=conn.execute("UPDATE autodev_queue SET status=?,run_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (state,str(run_id or ""),int(item_id)))
        if cur.rowcount != 1:
            raise ValueError("AUTODEV_QUEUE_ITEM_NOT_FOUND")
    return row("SELECT * FROM autodev_queue WHERE id=?", (int(item_id),)) or {}

AUTODEV_SESSION_STATES = {'prepared','running','paused','repairing','completed','failed','rolled_back'}

def create_autodev_session(session_id: str, project_id: int, workspace: str, goal: str, test_command: str, max_steps: int, model: str='', snapshot_sha256: str='') -> dict[str,Any]:
    sid=str(session_id or '').strip()
    if not sid: raise ValueError('AUTODEV_SESSION_ID_REQUIRED')
    if not project(int(project_id)): raise ValueError('PROJECT_NOT_FOUND')
    steps=max(1,min(int(max_steps or 4),8))
    with transaction() as conn:
        conn.execute("INSERT INTO autodev_sessions(session_id,project_id,workspace,goal,test_command,max_steps,status,model,snapshot_sha256) VALUES(?,?,?,?,?,?,'prepared',?,?)",(sid,int(project_id),str(workspace),str(goal),str(test_command),steps,str(model or ''),str(snapshot_sha256 or '')))
    return row('SELECT * FROM autodev_sessions WHERE session_id=?',(sid,)) or {}

def autodev_session(session_id: str) -> dict[str,Any] | None:
    return row('SELECT * FROM autodev_sessions WHERE session_id=?',(str(session_id or ''),))

def list_autodev_sessions(project_id: int | None=None, limit: int=100) -> list[dict[str,Any]]:
    n=max(1,min(int(limit),500))
    if project_id is None: return rows('SELECT * FROM autodev_sessions ORDER BY rowid DESC LIMIT ?',(n,))
    return rows('SELECT * FROM autodev_sessions WHERE project_id=? ORDER BY rowid DESC LIMIT ?',(int(project_id),n))

def update_autodev_session(session_id: str, status: str | None=None, current_task: str | None=None, attempt: int | None=None, model: str | None=None, run_id: str | None=None, summary: str | None=None, error: str | None=None) -> dict[str,Any]:
    sid=str(session_id or '')
    existing=autodev_session(sid)
    if not existing: raise ValueError('AUTODEV_SESSION_NOT_FOUND')
    state=str(status if status is not None else existing['status']).lower()
    if state not in AUTODEV_SESSION_STATES: raise ValueError('AUTODEV_SESSION_STATUS_INVALID')
    values=(state,str(current_task if current_task is not None else existing['current_task']),int(attempt if attempt is not None else existing['attempt']),str(model if model is not None else existing['model']),str(run_id if run_id is not None else existing['run_id']),str(summary if summary is not None else existing['summary']),str(error if error is not None else existing['error']),sid)
    with transaction() as conn:
        conn.execute('UPDATE autodev_sessions SET status=?,current_task=?,attempt=?,model=?,run_id=?,summary=?,error=?,updated_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP WHERE session_id=?',values)
    return autodev_session(sid) or {}

def record_model_outcome(model: str, task_type: str, success: bool, duration_seconds: float=0.0, failure_category: str='', session_id: str='') -> dict[str,Any]:
    name=str(model or '').strip()
    if not name: raise ValueError('MODEL_OUTCOME_MODEL_REQUIRED')
    ident=execute('INSERT INTO model_outcomes(model,task_type,success,duration_seconds,failure_category,session_id) VALUES(?,?,?,?,?,?)',(name,str(task_type or 'coding'),1 if success else 0,max(0.0,float(duration_seconds or 0.0)),str(failure_category or ''),str(session_id or '')))
    return row('SELECT * FROM model_outcomes WHERE id=?',(ident,)) or {}

def model_outcome_stats(task_type: str='') -> list[dict[str,Any]]:
    tt=str(task_type or '').strip()
    where=' WHERE task_type=?' if tt else ''
    args=(tt,) if tt else ()
    sql='SELECT model,COUNT(*) AS total,SUM(success) AS successes,AVG(duration_seconds) AS avg_duration_seconds FROM model_outcomes'+where+' GROUP BY model ORDER BY model'
    return rows(sql,args)

def append_run_ledger(session_id: str, stage: str, status: str, payload: dict[str,Any]) -> dict[str,Any]:
    import hashlib
    sid=str(session_id or '').strip(); stage=str(stage or '').strip(); state=str(status or '').strip().upper()
    if not autodev_session(sid): raise ValueError('AUTODEV_SESSION_NOT_FOUND')
    if not stage or not state: raise ValueError('RUN_LEDGER_FIELDS_REQUIRED')
    payload_json=json.dumps(dict(payload or {}),sort_keys=True,separators=(',',':'),ensure_ascii=False)
    with transaction() as conn:
        prev=conn.execute('SELECT entry_hash FROM run_ledger WHERE session_id=? ORDER BY id DESC LIMIT 1',(sid,)).fetchone()
        prev_hash=str(prev[0]) if prev else ''
        digest=hashlib.sha256((prev_hash+'|'+sid+'|'+stage+'|'+state+'|'+payload_json).encode('utf-8')).hexdigest().upper()
        cur=conn.execute('INSERT INTO run_ledger(session_id,stage,status,payload_json,prev_hash,entry_hash) VALUES(?,?,?,?,?,?)',(sid,stage,state,payload_json,prev_hash,digest))
        ident=int(cur.lastrowid)
    item=row('SELECT * FROM run_ledger WHERE id=?',(ident,)) or {}
    try: item['payload']=json.loads(str(item.get('payload_json') or '{}'))
    except Exception: item['payload']={}
    return item

def list_run_ledger(session_id: str) -> list[dict[str,Any]]:
    result=rows('SELECT * FROM run_ledger WHERE session_id=? ORDER BY id ASC',(str(session_id or ''),))
    for item in result:
        try: item['payload']=json.loads(str(item.get('payload_json') or '{}'))
        except Exception: item['payload']={}
    return result

def verify_run_ledger(session_id: str) -> dict[str,Any]:
    import hashlib
    entries=list_run_ledger(session_id); prev=''; bad=[]
    for item in entries:
        payload_json=json.dumps(dict(item.get('payload') or {}),sort_keys=True,separators=(',',':'),ensure_ascii=False)
        expected=hashlib.sha256((prev+'|'+str(item['session_id'])+'|'+str(item['stage'])+'|'+str(item['status'])+'|'+payload_json).encode('utf-8')).hexdigest().upper()
        if str(item.get('prev_hash') or '')!=prev or str(item.get('entry_hash') or '').upper()!=expected: bad.append(int(item['id']))
        prev=str(item.get('entry_hash') or '')
    return {'ok':not bad,'entries':len(entries),'bad_entry_ids':bad,'head_hash':prev}

def record_test_observation(project_id: int, test_name: str, status: str, duration_seconds: float=0.0, failure_hash: str='', session_id: str='') -> dict[str,Any]:
    name=str(test_name or '').strip(); state=str(status or '').upper().strip()
    if not project(int(project_id)): raise ValueError('PROJECT_NOT_FOUND')
    if not name: raise ValueError('TEST_OBSERVATION_NAME_REQUIRED')
    if state not in {'PASS','FAIL'}: raise ValueError('TEST_OBSERVATION_STATUS_INVALID')
    ident=execute('INSERT INTO test_observations(project_id,test_name,status,duration_seconds,failure_hash,session_id) VALUES(?,?,?,?,?,?)',(int(project_id),name,state,max(0.0,float(duration_seconds or 0.0)),str(failure_hash or ''),str(session_id or '')))
    return row('SELECT * FROM test_observations WHERE id=?',(ident,)) or {}

def list_test_observations(project_id: int, test_name: str='', limit: int=100) -> list[dict[str,Any]]:
    n=max(1,min(int(limit or 100),500)); name=str(test_name or '').strip()
    if name: return rows('SELECT * FROM test_observations WHERE project_id=? AND test_name=? ORDER BY id DESC LIMIT ?',(int(project_id),name,n))
    return rows('SELECT * FROM test_observations WHERE project_id=? ORDER BY id DESC LIMIT ?',(int(project_id),n))

SUPERVISOR_STATES={'prepared','running','paused','completed','failed','rolled_back'}

def _supervisor_record(item: dict[str,Any] | None) -> dict[str,Any] | None:
    if not item: return None
    value=dict(item)
    try: value['plan']=json.loads(str(value.get('plan_json') or '{}'))
    except Exception: value['plan']={}
    return value

def create_supervisor_run(supervisor_id: str, project_id: int, workspace: str, goal: str, plan: dict[str,Any], max_cycles: int=2) -> dict[str,Any]:
    sid=str(supervisor_id or '').strip(); cycles=max(1,min(int(max_cycles or 2),4))
    if not sid: raise ValueError('SUPERVISOR_ID_REQUIRED')
    if not project(int(project_id)): raise ValueError('PROJECT_NOT_FOUND')
    payload=json.dumps(dict(plan or {}),sort_keys=True,separators=(',',':'),ensure_ascii=False)
    with transaction() as conn:
        conn.execute("INSERT INTO supervisor_runs(supervisor_id,project_id,workspace,goal,status,max_cycles,plan_json) VALUES(?,?,?,?,'prepared',?,?)",(sid,int(project_id),str(workspace),str(goal),cycles,payload))
    return supervisor_run(sid) or {}

def supervisor_run(supervisor_id: str) -> dict[str,Any] | None:
    return _supervisor_record(row('SELECT * FROM supervisor_runs WHERE supervisor_id=?',(str(supervisor_id or ''),)))

def list_supervisor_runs(project_id: int | None=None, limit: int=100) -> list[dict[str,Any]]:
    n=max(1,min(int(limit or 100),500))
    values=rows('SELECT * FROM supervisor_runs ORDER BY rowid DESC LIMIT ?',(n,)) if project_id is None else rows('SELECT * FROM supervisor_runs WHERE project_id=? ORDER BY rowid DESC LIMIT ?',(int(project_id),n))
    return [_supervisor_record(x) or {} for x in values]

def update_supervisor_run(supervisor_id: str, status: str | None=None, cycle_no: int | None=None, confidence: float | None=None, checkpoint_ref: str | None=None, summary: str | None=None, last_error: str | None=None) -> dict[str,Any]:
    existing=supervisor_run(supervisor_id)
    if not existing: raise ValueError('SUPERVISOR_NOT_FOUND')
    state=str(status if status is not None else existing['status']).lower()
    if state not in SUPERVISOR_STATES: raise ValueError('SUPERVISOR_STATUS_INVALID')
    values=(state,int(cycle_no if cycle_no is not None else existing['cycle_no']),max(0.0,min(float(confidence if confidence is not None else existing['confidence']),1.0)),str(checkpoint_ref if checkpoint_ref is not None else existing['checkpoint_ref']),str(summary if summary is not None else existing['summary']),str(last_error if last_error is not None else existing['last_error']),str(supervisor_id))
    with transaction() as conn:
        conn.execute('UPDATE supervisor_runs SET status=?,cycle_no=?,confidence=?,checkpoint_ref=?,summary=?,last_error=?,updated_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP WHERE supervisor_id=?',values)
    return supervisor_run(supervisor_id) or {}



DEFERRED_STATES={'pending','ready','running','completed','failed','cancelled'}
def enqueue_deferred_work(project_id: int, goal: str, reason: str='', provider: str='') -> dict[str,Any]:
    if not project(int(project_id)): raise ValueError('PROJECT_NOT_FOUND')
    text=str(goal or '').strip()
    if not text: raise ValueError('DEFERRED_GOAL_REQUIRED')
    ident=execute('INSERT INTO deferred_work(project_id,goal,reason,provider,status) VALUES(?,?,?,?,\'pending\')',(int(project_id),text,str(reason or ''),str(provider or '')))
    return row('SELECT * FROM deferred_work WHERE id=?',(ident,)) or {}
def list_deferred_work(project_id: int | None=None, status: str='') -> list[dict[str,Any]]:
    state=str(status or '').strip().lower(); clauses=[]; args=[]
    if project_id is not None: clauses.append('project_id=?'); args.append(int(project_id))
    if state: clauses.append('status=?'); args.append(state)
    where=(' WHERE '+' AND '.join(clauses)) if clauses else ''
    return rows('SELECT * FROM deferred_work'+where+' ORDER BY id DESC',tuple(args))
def update_deferred_work(item_id: int, status: str) -> dict[str,Any]:
    state=str(status or '').lower().strip()
    if state not in DEFERRED_STATES: raise ValueError('DEFERRED_STATUS_INVALID')
    with transaction() as conn:
        cur=conn.execute('UPDATE deferred_work SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(state,int(item_id)))
        if int(cur.rowcount or 0)!=1: raise ValueError('DEFERRED_ITEM_NOT_FOUND')
    return row('SELECT * FROM deferred_work WHERE id=?',(int(item_id),)) or {}

def append_audit_event(category: str, action: str, status: str, payload: dict[str,Any], project_id: int | None=None) -> dict[str,Any]:
    import hashlib
    cat=str(category or '').strip(); act=str(action or '').strip(); state=str(status or '').strip().upper()
    if not cat or not act or not state: raise ValueError('AUDIT_FIELDS_REQUIRED')
    if project_id is not None and not project(int(project_id)): raise ValueError('PROJECT_NOT_FOUND')
    payload_json=json.dumps(dict(payload or {}),sort_keys=True,separators=(',',':'),ensure_ascii=False)
    with transaction() as conn:
        prev=conn.execute('SELECT entry_hash FROM audit_events ORDER BY id DESC LIMIT 1').fetchone(); prev_hash=str(prev[0]) if prev else ''
        digest=hashlib.sha256((prev_hash+'|'+cat+'|'+act+'|'+state+'|'+payload_json).encode('utf-8')).hexdigest().upper()
        cur=conn.execute('INSERT INTO audit_events(project_id,category,action,status,payload_json,prev_hash,entry_hash) VALUES(?,?,?,?,?,?,?)',(int(project_id) if project_id is not None else None,cat,act,state,payload_json,prev_hash,digest)); ident=int(cur.lastrowid)
    return row('SELECT * FROM audit_events WHERE id=?',(ident,)) or {}
def list_audit_events(limit: int=100) -> list[dict[str,Any]]:
    return rows('SELECT * FROM audit_events ORDER BY id DESC LIMIT ?',(max(1,min(int(limit or 100),500)),))
def verify_audit_events() -> dict[str,Any]:
    import hashlib
    items=rows('SELECT * FROM audit_events ORDER BY id ASC'); prev=''; bad=[]
    for item in items:
        payload=str(item.get('payload_json') or '{}'); expected=hashlib.sha256((prev+'|'+str(item['category'])+'|'+str(item['action'])+'|'+str(item['status'])+'|'+payload).encode('utf-8')).hexdigest().upper()
        if str(item.get('prev_hash') or '')!=prev or str(item.get('entry_hash') or '').upper()!=expected: bad.append(int(item['id']))
        prev=str(item.get('entry_hash') or '')
    return {'ok':not bad,'entries':len(items),'bad_entry_ids':bad,'head_hash':prev}
def record_alpha_release_run(run_id: str, build: str, status: str, proof_sha256: str='', detail: dict[str,Any] | None=None) -> dict[str,Any]:
    rid=str(run_id or '').strip(); state=str(status or '').upper().strip()
    if not rid or state not in {'PASS','FAIL'}: raise ValueError('ALPHA_RELEASE_FIELDS_INVALID')
    execute('INSERT INTO alpha_release_runs(run_id,build,status,proof_sha256,detail_json) VALUES(?,?,?,?,?)',(rid,str(build or ''),state,str(proof_sha256 or ''),json.dumps(dict(detail or {}),sort_keys=True,separators=(',',':'),ensure_ascii=False)))
    return row('SELECT * FROM alpha_release_runs WHERE run_id=?',(rid,)) or {}
def list_alpha_release_runs(limit: int=50) -> list[dict[str,Any]]:
    return rows('SELECT * FROM alpha_release_runs ORDER BY created_at DESC,run_id DESC LIMIT ?',(max(1,min(int(limit or 50),200)),))
