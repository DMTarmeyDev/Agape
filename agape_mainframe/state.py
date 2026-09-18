from __future__ import annotations
import json, os, shutil, sqlite3, threading, time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from .platform_paths import user_data_root

BUILD = "AGAPE-MAINFRAME-V5.5-UX-DOWNLOAD-QA"
ROOT = Path(__file__).resolve().parent.parent
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", str(ROOT)))
PREVIOUS_DATA_ROOTS = [
    LOCALAPPDATA / "Agape-Mainframe-V2" / "data",
    LOCALAPPDATA / "Agape-Mainframe-V1" / "data",
]
DATA_ROOT = user_data_root()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_ROOT / "settings.json"
DB_FILE = DATA_ROOT / "mainframe.sqlite3"
PREPARE_ROOT = DATA_ROOT / "intake-prepare"
PREPARE_ROOT.mkdir(parents=True, exist_ok=True)

# One-time, non-destructive migration. Prefer the newest earlier data and
# leave every previous installation untouched.
if not os.environ.get("AGAPE_MAINFRAME_DATA"):
    for name in ("settings.json", "mainframe.sqlite3"):
        dst = DATA_ROOT / name
        if dst.exists():
            continue
        for previous_root in PREVIOUS_DATA_ROOTS:
            src = previous_root / name
            if src.exists():
                try:
                    shutil.copy2(src, dst)
                    break
                except Exception:
                    pass
LOCK = threading.RLock()

DEFAULT_SETTINGS = {
    "setup_complete": False,
    "experience": "basic",
    "theme": "forest",
    "quality": "standard",
    "auto_install_support": False,
    "show_technical_details": False,
    "router": "agape",
    "coding_model_mode": "auto-coding",
    "coding_agent": "auto",
    "code_manager": "agape",
    "enabled_capabilities": ["ai-routing", "projects", "documents", "research"],
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _atomic(path: Path, value: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_settings() -> dict[str, Any]:
    with LOCK:
        out = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    out.update({k: raw[k] for k in out if k in raw})
            except Exception:
                pass
        if out.get("experience") not in {"basic", "standard", "advanced"}:
            out["experience"] = "basic"
        if not isinstance(out.get("enabled_capabilities"), list):
            out["enabled_capabilities"] = list(DEFAULT_SETTINGS["enabled_capabilities"])
        return out


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with LOCK:
        cur = load_settings()
        for key in DEFAULT_SETTINGS:
            if key in patch:
                cur[key] = patch[key]
        if cur.get("experience") not in {"basic", "standard", "advanced"}:
            raise ValueError("EXPERIENCE_MUST_BE_BASIC_STANDARD_OR_ADVANCED")
        if str(cur.get("router") or "agape") not in {"agape", "litellm"}:
            raise ValueError("ROUTER_MUST_BE_AGAPE_OR_LITELLM")
        if str(cur.get("quality") or "gold") not in {"gold", "standard"}:
            raise ValueError("QUALITY_MUST_BE_GOLD_OR_STANDARD")
        if str(cur.get("coding_model_mode") or "auto-coding") not in {"auto-coding","local-first","cloud-first","manual"}:
            raise ValueError("INVALID_CODING_MODEL_MODE")
        if str(cur.get("coding_agent") or "auto") not in {"auto","agape-native","aider","openhands","open-interpreter","compare"}:
            raise ValueError("INVALID_CODING_AGENT")
        if str(cur.get("code_manager") or "agape") not in {"agape","theia-lite","theia-full","vscode"}:
            raise ValueError("INVALID_CODE_MANAGER")
        cur["setup_complete"] = bool(cur.get("setup_complete"))
        cur["show_technical_details"] = bool(cur.get("show_technical_details"))
        cur["auto_install_support"] = bool(cur.get("auto_install_support"))
        caps = cur.get("enabled_capabilities") or []
        cur["enabled_capabilities"] = list(dict.fromkeys(str(x) for x in caps if str(x).strip()))
        _atomic(SETTINGS_FILE, cur)
        return cur


@contextmanager
def db():
    """Open one Mainframe SQLite transaction and always release its file handle.

    sqlite3.Connection's own context-manager commits/rolls back but does not
    close the connection.  That leaks a file handle until garbage collection
    and prevents TemporaryDirectory cleanup on Windows.
    """
    con = sqlite3.connect(DB_FILE, timeout=20)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                run_id TEXT,
                capability TEXT,
                stage TEXT,
                status TEXT,
                message TEXT,
                detail TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS recent_work(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                title TEXT,
                task TEXT,
                route TEXT,
                external_job_id TEXT,
                status TEXT,
                result_json TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS intake_prepare_jobs(
                job_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                message TEXT,
                result_json TEXT,
                error TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                worker_instance TEXT NOT NULL DEFAULT '',
                heartbeat_epoch REAL NOT NULL DEFAULT 0
            )
        """)
        cols={str(r[1]) for r in con.execute("PRAGMA table_info(intake_prepare_jobs)").fetchall()}
        if "attempts" not in cols:
            con.execute("ALTER TABLE intake_prepare_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
        if "worker_instance" not in cols:
            con.execute("ALTER TABLE intake_prepare_jobs ADD COLUMN worker_instance TEXT NOT NULL DEFAULT ''")
        if "heartbeat_epoch" not in cols:
            con.execute("ALTER TABLE intake_prepare_jobs ADD COLUMN heartbeat_epoch REAL NOT NULL DEFAULT 0")
        yield con
        con.commit()
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def record_event(run_id: str, capability: str, stage: str, status: str, message: str, detail: str = "") -> None:
    with db() as con:
        con.execute(
            "INSERT INTO events(created_at,run_id,capability,stage,status,message,detail) VALUES(?,?,?,?,?,?,?)",
            (now_iso(), run_id, capability, stage, status, message, detail[:8000]),
        )
        con.commit()


def events(limit: int = 150) -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (max(1, min(1000, int(limit))),)).fetchall()
    return [dict(r) for r in rows]


def remember_work(title: str, task: str, route: str, external_job_id: str, status: str, result: Any = None) -> int:
    raw = json.dumps(result, ensure_ascii=False, default=str) if result is not None else ""
    with db() as con:
        cur = con.execute(
            "INSERT INTO recent_work(created_at,title,task,route,external_job_id,status,result_json) VALUES(?,?,?,?,?,?,?)",
            (now_iso(), title[:300], task[:4000], route, external_job_id, status, raw[:200000]),
        )
        con.commit()
        return int(cur.lastrowid)


def recent_work(limit: int = 50) -> list[dict[str, Any]]:
    with db() as con:
        rows = con.execute("SELECT * FROM recent_work ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        if d.get("result_json"):
            try:d["result"]=json.loads(d.pop("result_json"))
            except Exception:d.pop("result_json",None)
        else:d.pop("result_json",None)
        out.append(d)
    return out




def sync_external_work_status(external_job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Mirror a delegated bridge job back into Mainframe history/events exactly once.

    Browser polling is the natural place to observe terminal bridge state.  This
    function updates recent_work on every poll and emits one matching terminal
    event for the original MAIN-* run so Activity never ends at START.
    """
    status=str(payload.get("status") or payload.get("state") or "").upper().strip() or "UNKNOWN"
    terminal=status in {"PASS","FAIL","BLOCKED","FAILED","COMPLETE","COMPLETED"}
    mapped="PASS" if status in {"PASS","COMPLETE","COMPLETED"} else ("BLOCKED" if status=="BLOCKED" else ("FAIL" if status in {"FAIL","FAILED"} else status))
    raw=json.dumps(payload,ensure_ascii=False,default=str)[:200000]
    with db() as con:
        row=con.execute("SELECT * FROM recent_work WHERE external_job_id=? ORDER BY id DESC LIMIT 1",(str(external_job_id),)).fetchone()
        if not row:
            return {"ok":False,"reason":"WORK_HISTORY_NOT_FOUND"}
        previous=str(row["status"] or "").upper()
        meta={}
        try:
            meta=json.loads(row["result_json"] or "{}") if row["result_json"] else {}
        except Exception:
            meta={}
        run_id=str(meta.get("run_id") or meta.get("_mainframe_run_id") or "")
        stored=dict(payload)
        if run_id:stored["_mainframe_run_id"]=run_id
        raw=json.dumps(stored,ensure_ascii=False,default=str)[:200000]
        con.execute("UPDATE recent_work SET status=?,result_json=? WHERE id=?",(mapped,raw,int(row["id"])))
        emitted=False
        if terminal and previous not in {"PASS","FAIL","BLOCKED","FAILED","COMPLETE","COMPLETED"} and run_id:
            message="Work completed" if mapped=="PASS" else ("Action required" if mapped=="BLOCKED" else "Work failed")
            detail=str(payload.get("error") or payload.get("message") or "")[:8000]
            con.execute("INSERT INTO events(created_at,run_id,capability,stage,status,message,detail) VALUES(?,?,?,?,?,?,?)",
                        (now_iso(),run_id,"workflow-bridge","complete" if mapped=="PASS" else "execute",mapped,message,detail))
            emitted=True
        con.commit()
    return {"ok":True,"status":mapped,"event_emitted":emitted,"run_id":run_id}

def _prepare_request_file(job_id: str) -> Path:
    safe="".join(ch for ch in str(job_id) if ch.isalnum() or ch in "-_")[:96]
    return PREPARE_ROOT / f"{safe}.request.json"


def save_intake_prepare_request(job_id: str, payload: dict[str, Any]) -> None:
    path=_prepare_request_file(job_id)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,default=str),encoding="utf-8")
    os.replace(tmp,path)


def load_intake_prepare_request(job_id: str) -> dict[str, Any] | None:
    path=_prepare_request_file(job_id)
    if not path.is_file():
        return None
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj,dict) else None
    except Exception:
        return None


def delete_intake_prepare_request(job_id: str) -> None:
    try:
        _prepare_request_file(job_id).unlink(missing_ok=True)
    except Exception:
        pass


def create_intake_prepare_job(job_id: str, message: str = "Queued", request: dict[str, Any] | None = None) -> dict[str, Any]:
    now = now_iso()
    if isinstance(request,dict):
        save_intake_prepare_request(job_id,request)
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO intake_prepare_jobs(job_id,created_at,updated_at,status,progress,message,result_json,error,attempts,worker_instance,heartbeat_epoch) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, now, now, "QUEUED", 1.0, message[:1000], "", "", 0, "", 0.0),
        )
    return get_intake_prepare_job(job_id) or {"job_id": job_id, "status": "QUEUED", "progress": 1.0, "message": message}


def claim_intake_prepare_job(job_id: str, worker_instance: str, message: str) -> dict[str, Any]:
    with db() as con:
        con.execute(
            "UPDATE intake_prepare_jobs SET updated_at=?,status='RUNNING',message=?,attempts=COALESCE(attempts,0)+1,worker_instance=?,heartbeat_epoch=? WHERE job_id=?",
            (now_iso(),str(message)[:1000],str(worker_instance)[:120],time.time(),job_id),
        )
    return get_intake_prepare_job(job_id) or {}


def update_intake_prepare_job(job_id: str, *, status: str | None = None, progress: float | None = None, message: str | None = None, result: Any = None, error: str | None = None, worker_instance: str | None = None) -> dict[str, Any]:
    current = get_intake_prepare_job(job_id) or {"progress": 0.0, "status": "QUEUED", "message": "Queued"}
    next_progress = float(current.get("progress") or 0.0)
    if progress is not None:
        next_progress = max(next_progress, max(0.0, min(100.0, float(progress))))
    next_status = str(status or current.get("status") or "QUEUED")
    next_message = str(message if message is not None else current.get("message") or "")
    result_json = json.dumps(result, ensure_ascii=False, default=str) if result is not None else None
    next_error = str(error) if error is not None else None
    owner=str(worker_instance if worker_instance is not None else current.get("worker_instance") or "")
    heartbeat=time.time() if next_status.upper()=="RUNNING" else float(current.get("heartbeat_epoch") or 0.0)
    with db() as con:
        if result_json is None and next_error is None:
            con.execute(
                "UPDATE intake_prepare_jobs SET updated_at=?,status=?,progress=?,message=?,worker_instance=?,heartbeat_epoch=? WHERE job_id=?",
                (now_iso(), next_status, next_progress, next_message[:1000],owner[:120],heartbeat, job_id),
            )
        elif result_json is not None:
            con.execute(
                "UPDATE intake_prepare_jobs SET updated_at=?,status=?,progress=?,message=?,result_json=?,error='',worker_instance=?,heartbeat_epoch=? WHERE job_id=?",
                (now_iso(), next_status, next_progress, next_message[:1000], result_json[:1000000],owner[:120],heartbeat, job_id),
            )
        else:
            con.execute(
                "UPDATE intake_prepare_jobs SET updated_at=?,status=?,progress=?,message=?,error=?,worker_instance=?,heartbeat_epoch=? WHERE job_id=?",
                (now_iso(), next_status, next_progress, next_message[:1000], (next_error or '')[:8000],owner[:120],heartbeat, job_id),
            )
    return get_intake_prepare_job(job_id) or {}


def get_intake_prepare_job(job_id: str) -> dict[str, Any] | None:
    with db() as con:
        row = con.execute("SELECT * FROM intake_prepare_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    raw = out.pop("result_json", "") or ""
    if raw:
        try:
            out["result"] = json.loads(raw)
        except Exception:
            out["result"] = {"raw": raw}
    out["ok"] = out.get("status") not in {"FAILED", "ERROR"}
    return out

