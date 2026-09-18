from __future__ import annotations
import base64, json, os, re, sqlite3, subprocess, threading, time, urllib.parse
from pathlib import Path
from typing import Any
from .project_recovery import find_live_core_db
from .http_client import request_json
from .state import record_event, remember_work, recent_work, sync_external_work_status
from .service_runtime import (
    runtime_log_dir,
    service_command,
    service_environment,
    service_source_path,
    service_working_directory,
)

R24="http://127.0.0.1:8852"
CORE="http://127.0.0.1:8797"
DOC="http://127.0.0.1:8851"
R24_BUNDLED=service_source_path("workflow-bridge")
DOC_BUNDLED=service_source_path("document-studio")
EXPECTED_DOC_VERSION="R31.16"
EXPECTED_R24_BUILD="AGAPE-UNIFIED-R4.7-TARGETED-VALIDATION-REPAIR"


_STATUS_SYNC_LOCK = threading.Lock()
_STATUS_SYNC_LAST = 0.0
_STATUS_SYNC_TTL = 2.0
_TERMINAL_WORK = {"PASS","FAIL","BLOCKED","FAILED","COMPLETE","COMPLETED","SUCCESS","DONE","ERROR","ACTION_REQUIRED"}

def _display_work_status(value: Any) -> str:
    raw=str(value or "").strip().upper().replace("-","_").replace(" ","_")
    if raw in {"PASS","COMPLETE","COMPLETED","SUCCESS","DONE"}: return "Complete"
    if raw in {"BLOCKED","ACTION_REQUIRED","NEEDS_ATTENTION"}: return "Needs attention"
    if raw in {"FAIL","FAILED","ERROR"}: return "Failed"
    if raw in {"QUEUED","PENDING"}: return "Queued"
    if raw in {"RUNNING","WORKING","IN_PROGRESS","START","STARTED","UNKNOWN"}: return "Working"
    return str(value or "Saved").strip() or "Saved"

def _result_project_id(item: dict[str,Any]) -> int:
    root=item.get("result") if isinstance(item.get("result"),dict) else {}
    candidates=[root,root.get("job") if isinstance(root.get("job"),dict) else {},root.get("result") if isinstance(root.get("result"),dict) else {}]
    if isinstance(root.get("job"),dict) and isinstance(root["job"].get("result"),dict): candidates.append(root["job"]["result"])
    for value in candidates:
        if not isinstance(value,dict): continue
        try:
            pid=int(value.get("project_id") or value.get("source_project_id") or 0)
            if pid>0:return pid
        except Exception: pass
    return 0

def recent_work_with_live_status(limit: int = 50) -> list[dict[str,Any]]:
    """Return Mainframe history after refreshing unfinished bridge jobs.

    This is the canonical status feed for every UI page/device.  Refreshing here
    prevents Results, Projects and Workspace from disagreeing simply because one
    browser happened to poll the job more recently than another.
    """
    global _STATUS_SYNC_LAST
    rows=recent_work(limit)
    now=time.monotonic()
    should_refresh=(now-_STATUS_SYNC_LAST)>=_STATUS_SYNC_TTL
    if should_refresh and _STATUS_SYNC_LOCK.acquire(blocking=False):
        try:
            _STATUS_SYNC_LAST=now
            active=[x for x in rows if x.get("external_job_id") and str(x.get("status") or "").upper() not in _TERMINAL_WORK][:20]
            if active:
                # Do not start the bridge just to paint a status badge. If it is
                # already running, local status checks are fast and authoritative.
                if r24_ready():
                    for item in active:
                        jid=str(item.get("external_job_id") or "")
                        if not jid: continue
                        status,payload=request_json("GET",R24+"/api/jobs/"+urllib.parse.quote(jid),timeout=3)
                        if status==200 and isinstance(payload,dict):
                            try: sync_external_work_status(jid,payload)
                            except Exception: pass
                rows=recent_work(limit)
        finally:
            _STATUS_SYNC_LOCK.release()
    for item in rows:
        item["status_label"]=_display_work_status(item.get("status"))
        item["terminal"]=str(item.get("status") or "").upper() in _TERMINAL_WORK
        pid=_result_project_id(item)
        if pid:item["project_id"]=pid
    return rows

def projects_with_live_status() -> list[dict[str,Any]]:
    """Return projects decorated with the latest canonical work status."""
    rows=projects()
    history=recent_work_with_live_status(100)
    by_project: dict[int,dict[str,Any]]={}
    by_name: dict[str,dict[str,Any]]={}
    for work in history:
        pid=int(work.get("project_id") or 0)
        if pid>0 and pid not in by_project: by_project[pid]=work
        title=str(work.get("title") or "").strip().casefold()
        if title and title not in by_name: by_name[title]=work
    out=[]
    for project in rows:
        row=dict(project)
        try: pid=int(row.get("id") or 0)
        except Exception: pid=0
        work=by_project.get(pid)
        if not work:
            work=by_name.get(str(row.get("name") or "").strip().casefold())
        if work:
            raw=str(work.get("status") or "")
            row["saved_status"]=row.get("status")
            row["status"]=raw
            row["status_label"]=_display_work_status(raw)
            row["latest_job_id"]=str(work.get("external_job_id") or "")
            row["latest_work_at"]=str(work.get("created_at") or "")
        else:
            row["status_label"]=_display_work_status(row.get("status") or "Saved")
        out.append(row)
    return out



def _existing_core_root() -> Path | None:
    lad=Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
    if not lad:return None
    p=lad/"DMT-Core-V3.1"/"SecondBrain"/"dmt-second-brain"
    return p if p.exists() else None

def _launch_ps1(path: Path) -> None:
    if os.name!="nt" or not path.exists():return
    flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
    subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(path)],cwd=str(path.parent),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)

def _launch_service(name: str, *args: str, log_name: str = "service", extra_env: dict[str,str] | None = None) -> bool:
    source=service_source_path(name)
    if not source.exists():
        return False
    runtime=runtime_log_dir()
    flags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0
    env=service_environment(name)
    if extra_env:
        env.update({str(k):str(v) for k,v in extra_env.items()})
    command=service_command(name,*args)
    with open(runtime/(log_name+".out.log"),"ab",buffering=0) as so, open(runtime/(log_name+".err.log"),"ab",buffering=0) as se:
        subprocess.Popen(command,cwd=str(service_working_directory(name)),stdout=so,stderr=se,creationflags=flags,env=env)
    return True


def _wait(url: str, seconds: int=30) -> bool:
    end=time.time()+seconds
    while time.time()<end:
        s,p=request_json("GET",url,timeout=2)
        if s==200 and isinstance(p,dict) and p.get("ok",True) is not False:return True
        time.sleep(.5)
    return False

def ensure_existing_services(plan: dict[str,Any], project_id: int=0) -> dict[str,Any]:
    """Adopt the verified installed stack when present. Never installs or mutates it."""
    root=_existing_core_root();route=str(plan.get("route") or "")
    result={"core":False,"documents":False,"work":False,"adopted_root":str(root) if root else ""}
    need_core=bool(project_id) or route=="development"
    need_docs=route in {"document","research"}
    need_work=route=="development"
    if need_core:
        s,p=request_json("GET",CORE+"/api/version",timeout=2);result["core"]=s==200
        if not result["core"] and root:
            _launch_ps1(root/"START-DMT-SECOND-BRAIN.ps1");result["core"]=_wait(CORE+"/api/version",35)
    if need_docs:
        s,p=request_json("GET",DOC+"/api/health",timeout=2)
        result["documents"]=bool(s==200 and isinstance(p,dict) and str(p.get("version") or "")==EXPECTED_DOC_VERSION)
        # V3.4 uses a private Document Studio port so an older installed R31.10
        # process on the legacy 8800 port can never be adopted accidentally.
        if not result["documents"] and DOC_BUNDLED.exists():
            _launch_service("document-studio","--port","8851","--no-browser",log_name="document-studio-v41")
            end=time.time()+45
            while time.time()<end:
                ds,dp=request_json("GET",DOC+"/api/health",timeout=2)
                if ds==200 and isinstance(dp,dict) and str(dp.get("version") or "")==EXPECTED_DOC_VERSION:
                    result["documents"]=True;break
                time.sleep(.5)
        if not result["documents"]:
            raise RuntimeError("DOCUMENT_STUDIO_INCOMPATIBLE_OR_NOT_READY: V4.7 requires bundled "+EXPECTED_DOC_VERSION+" on private port 8851.")
    if need_work:
        s,p=request_json("GET","http://127.0.0.1:8820/api/health",timeout=2);result["work"]=s==200 and isinstance(p,dict) and p.get("ok",True) is not False
        if not result["work"] and root:
            _launch_ps1(root/"OPEN-AGAPE-WORK-ENGINE.ps1");result["work"]=_wait("http://127.0.0.1:8820/api/health",40)
    if need_core and not result["core"]:raise RuntimeError("AGAPE_CORE_NOT_READY: Open Settings > Capabilities to repair or reinstall the Projects capability.")
    if need_docs and not result["documents"]:raise RuntimeError("DOCUMENT_STUDIO_NOT_READY: The Documents capability is installed separately and could not be started.")
    return result

def r24_ready() -> bool:
    s,p=request_json("GET",R24+"/api/health",timeout=2)
    return bool(s==200 and isinstance(p,dict) and p.get("ok") is not False and str(p.get("build") or "")==EXPECTED_R24_BUILD)


def ensure_r24() -> dict[str, Any]:
    if r24_ready():return {"ok":True,"already_running":True}
    if not R24_BUNDLED.exists():return {"ok":False,"error":"BUNDLED_WORKFLOW_BRIDGE_MISSING"}
    started=_launch_service("workflow-bridge","--port","8852",log_name="workflow-bridge",extra_env={"AGAPE_DOC_URL":DOC})
    if not started:return {"ok":False,"error":"WORKFLOW_BRIDGE_START_FAILED"}
    for _ in range(40):
        time.sleep(.25)
        if r24_ready():return {"ok":True,"already_running":False}
    return {"ok":False,"error":"WORKFLOW_BRIDGE_START_FAILED"}


def _core_db_candidates() -> list[Path]:
    """Return likely Core databases in priority order without starting Core."""
    out: list[Path] = []
    override = str(os.environ.get("AGAPE_CORE_DB") or "").strip()
    if override:
        # An explicit override is authoritative. This is important for tests,
        # diagnostics and recovery tooling: never fall through to the user's
        # live Core database when a caller deliberately supplied another path.
        return [Path(override).expanduser()]
    data_override = str(os.environ.get("DMT_DATA_ROOT") or "").strip()
    if data_override:
        out.append(Path(data_override).expanduser() / "dmt_core.sqlite3")
    home = Path.home()
    out.append(home / "Documents" / "DMT-CORE-V3.1" / "second-brain-data" / "dmt_core.sqlite3")
    one_drive = str(os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or "").strip()
    if one_drive:
        out.append(Path(one_drive) / "Documents" / "DMT-CORE-V3.1" / "second-brain-data" / "dmt_core.sqlite3")
    # Some Windows profiles redirect Documents into OneDrive even when the environment variable is absent.
    out.append(home / "OneDrive" / "Documents" / "DMT-CORE-V3.1" / "second-brain-data" / "dmt_core.sqlite3")
    seen: set[str] = set(); unique: list[Path] = []
    for item in out:
        try:
            key = str(item.expanduser().resolve()).lower()
        except Exception:
            key = str(item).lower()
        if key not in seen:
            seen.add(key); unique.append(item)
    return unique


def _find_core_db() -> Path | None:
    # Use the newest healthy canonical Core database. Historic installs can leave
    # multiple valid copies behind; first-path-wins can therefore hide newer projects.
    selected = find_live_core_db()
    if selected:
        return selected
    for candidate in _core_db_candidates():
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        except Exception:
            continue
    return None


def _core_db_read_project_bundle(project_id: int) -> dict[str, Any] | None:
    """Read a saved project directly from Core's SQLite database, read-only.

    This is deliberately a fallback for human document workflows. It never writes the
    Core database and means saved-project source preparation does not depend on port 8797.
    """
    path = _find_core_db()
    if project_id <= 0 or not path:
        return None
    try:
        uri = "file:" + str(path).replace("\\", "/") + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=8)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT * FROM projects WHERE id=?", (int(project_id),)).fetchone()
            if not row:
                return None
            project = dict(row)
            messages = [dict(x) for x in con.execute(
                "SELECT id,project_id,role,provider,model,content,created_at FROM messages WHERE project_id=? ORDER BY id",
                (int(project_id),),
            ).fetchall()]
            loop_row = con.execute("SELECT * FROM project_loop_settings WHERE project_id=?", (int(project_id),)).fetchone()
            loop_settings = dict(loop_row) if loop_row else {}
            return {
                "ok": True,
                "project": project,
                "messages": {"ok": True, "messages": messages},
                "template": {"ok": False, "offline": True, "detail": "Template status requires Core; saved project facts were loaded directly from SQLite."},
                "loop_settings": {"ok": True, **loop_settings} if loop_settings else {"ok": True},
                "source_database": str(path),
                "source_access": "read-only-sqlite-fallback",
            }
        finally:
            con.close()
    except Exception:
        return None


def _project_name_is_internal_test(name: str) -> bool:
    low=str(name or "").strip().casefold()
    return any(x in low for x in ("crash recovery mock", "rollback mock project", "loop mock project")) or low.startswith("r4 integration ")


def projects() -> list[dict[str, Any]]:
    # Project discovery is a local-data operation. Prefer the read-only SQLite
    # source so the Create page remains fast even when Core is stopped.
    db_path=_find_core_db()
    if db_path:
        try:
            uri="file:"+str(db_path).replace("\\","/")+"?mode=ro"
            con=sqlite3.connect(uri,uri=True,timeout=8);con.row_factory=sqlite3.Row
            try:
                try:
                    rows=[dict(r) for r in con.execute("SELECT * FROM projects WHERE COALESCE(archived,0)=0 AND COALESCE(kind,'user')='user' ORDER BY updated_at DESC,id DESC").fetchall()]
                except sqlite3.OperationalError:
                    rows=[dict(r) for r in con.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()]
                rows=[r for r in rows if not _project_name_is_internal_test(str(r.get("name") or ""))]
                if rows:return rows
            finally:con.close()
        except Exception:
            pass
    s,p=request_json("GET",R24+"/api/projects",timeout=4)
    if s==200 and isinstance(p,dict):
        rows=p.get("projects") or []
        if isinstance(rows,list):return rows
    s,p=request_json("GET",CORE+"/api/projects?scope=all",timeout=4)
    if s==200 and isinstance(p,dict):
        rows=p.get("projects") or []
        if isinstance(rows,list):return rows
    return []


def _saved_project_bundle(project_id: int) -> dict[str, Any]:
    if project_id <= 0:
        raise RuntimeError("PROJECT_SOURCE_LOAD_FAILED: invalid project id")
    # A saved project is already local data. Read it directly first so no local
    # HTTP service is a prerequisite for the human workflow.
    direct = _core_db_read_project_bundle(project_id)
    if direct and isinstance(direct.get("project"), dict):
        return direct
    status, payload = request_json("GET", R24 + "/api/project?project_id=" + urllib.parse.quote(str(project_id)), timeout=5)
    if status == 200 and isinstance(payload, dict) and isinstance(payload.get("project"), dict):
        return payload
    raise RuntimeError("PROJECT_SOURCE_LOAD_FAILED: no readable local project database was found and the Core service is unavailable. Bridge detail: " + json.dumps(payload, ensure_ascii=False)[:900])


def _saved_project_source(project_id: int, payload: dict[str, Any] | None = None) -> str:
    """Build a human-first source snapshot from an existing Agape project.

    Do not serialise the whole database/API bundle into the writing source. JSON
    metadata, IDs, provider names and assistant boilerplate are useful for the
    software but are poor document evidence and create false spelling/grammar
    suggestions. Prefer project facts plus user-authored project notes.
    """
    if project_id <= 0:
        return ""
    payload = payload if isinstance(payload,dict) else _saved_project_bundle(project_id)
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    messages_obj = payload.get("messages") if isinstance(payload.get("messages"), dict) else {}
    messages = messages_obj.get("messages") if isinstance(messages_obj.get("messages"), list) else []
    loop_obj = payload.get("loop_settings") if isinstance(payload.get("loop_settings"), dict) else {}

    rows=["Saved Agape project selected as the source for AI brief filling."]
    name=str(project.get("name") or "").strip()
    if name:
        rows += ["", "Project name: " + name]

    # Preserve meaningful human project fields while excluding storage/runtime metadata.
    excluded={"id","project_id","created_at","updated_at","kind","archived","hidden_reason","provider","model","pid"}
    preferred=("goal","description","summary","objective","purpose","notes","instructions","brief")
    used=set()
    for key in preferred:
        value=project.get(key)
        if isinstance(value,str) and value.strip():
            rows.append(key.replace("_"," ").title()+": "+value.strip())
            used.add(key)
    for key,value in project.items():
        if key in excluded or key in used or key=="name":
            continue
        if isinstance(value,str) and value.strip() and len(value.strip()) <= 12000:
            rows.append(key.replace("_"," ").title()+": "+value.strip())

    goal=str(loop_obj.get("goal") or "").strip()
    if goal and goal not in "\n".join(rows):
        rows += ["", "Project goal: " + goal]

    # User-authored messages are authoritative evidence. Keep them all (within the
    # source-size cap). Assistant messages are secondary context: retain only
    # substantive project summaries and discard generic questions, acknowledgements,
    # code/terminal chatter and other boilerplate. This recovers useful context that
    # earlier releases accidentally threw away without reintroducing raw JSON noise.
    user_notes=[]
    assistant_context=[]
    project_terms={x.casefold() for x in re.findall(r"[A-Za-z][A-Za-z0-9'-]{3,}", name)
                   if x.casefold() not in {"business","plan","project","commercial","interiors"}}
    project_terms.update({"budget","market","customer","competitor","timeline","goal","constraint","pricing","business plan","commercial interiors"})
    boilerplate_starts=(
        "would you like", "please let me know", "if you have any", "if you need",
        "let me know if", "how can i assist", "execution completed", "press enter",
        "available on the internet", "i can help", "sure!", "certainly!",
    )
    for msg in messages:
        if not isinstance(msg,dict):
            continue
        role=str(msg.get("role") or "").strip().lower()
        content=str(msg.get("content") or "").strip()
        if not content:
            continue
        if role in {"user","owner","human"}:
            user_notes.append(content)
            continue
        if role not in {"assistant","ai"}:
            continue
        low=content.casefold().strip()
        if len(content) < 100 or low.startswith(boilerplate_starts):
            continue
        if any(x in low for x in ("traceback (most recent call last)", "dmt_execution=", "powershell.exe", "127.0.0.1:", "```powershell", "```python")):
            continue
        if not any(term in low for term in project_terms):
            continue
        cleaned=re.sub(r"```.*?```", " ", content, flags=re.S)
        cleaned=re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) >= 100:
            assistant_context.append(cleaned[:3500])
    if user_notes:
        rows += ["", "User-provided project notes:"]
        for idx,content in enumerate(user_notes[-80:],1):
            rows.append(f"{idx}. {content}")
    if assistant_context:
        rows += ["", "Secondary assistant project summaries (use as supporting context; user notes and explicit project facts take priority):"]
        for idx,content in enumerate(assistant_context[-20:],1):
            rows.append(f"Summary {idx}: {content}")

    rows += ["", "Source note: storage metadata, raw JSON and generic assistant boilerplate were excluded from this writing source."]
    return "\n".join(rows)[:120000]



def _ensure_project_database() -> Path:
    """Return a writable Core-compatible project DB, creating a minimal one if needed."""
    existing=_find_core_db()
    if existing:
        return existing
    local=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData"/"Local")))
    path=local/"DMT-Core-V3.1"/"second-brain-data"/"dmt_core.sqlite3"
    path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(str(path),timeout=20)
    try:
        con.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS projects(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          kind TEXT NOT NULL DEFAULT 'user',
          archived INTEGER NOT NULL DEFAULT 0,
          hidden_reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          role TEXT NOT NULL,
          provider TEXT NOT NULL DEFAULT '',
          model TEXT NOT NULL DEFAULT '',
          content TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS project_loop_settings(
          project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
          workspace TEXT NOT NULL DEFAULT '', goal TEXT NOT NULL DEFAULT '',
          test_command TEXT NOT NULL DEFAULT '', max_steps INTEGER NOT NULL DEFAULT 4,
          auto_model INTEGER NOT NULL DEFAULT 1, model TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        con.commit()
    finally:
        con.close()
    return path


def _project_name_from_intake(intake: dict[str,Any], body: dict[str,Any], file_name: str) -> str:
    ai=intake.get("ai_fill") if isinstance(intake.get("ai_fill"),dict) else {}
    candidates=[ai.get("project_name"),ai.get("title"),intake.get("project_name"),body.get("title"),body.get("instruction")]
    if file_name and file_name not in {"pasted-source.txt","prepared-intake.txt"}:
        candidates.append(Path(file_name).stem)
    for value in candidates:
        name=re.sub(r"\\s+"," ",str(value or "")).strip(" .-_")
        if len(name)>=3:
            return name[:110]
    return "Agape Project "+time.strftime("%Y-%m-%d %H%M")


def _save_new_source_as_project(intake: dict[str,Any], body: dict[str,Any], source_text: str, file_name: str) -> dict[str,Any]:
    """Create a user project for new pasted/uploaded work and attach source context."""
    db_path=_ensure_project_database()
    name=_project_name_from_intake(intake,body,file_name)
    con=sqlite3.connect(str(db_path),timeout=30)
    con.row_factory=sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout=30000")
        base=name
        suffix=1
        while con.execute("SELECT 1 FROM projects WHERE name=?",(name,)).fetchone():
            suffix+=1
            name=(base[:96]+f" ({suffix})")[:120]
        cur=con.execute("INSERT INTO projects(name,kind,archived,hidden_reason) VALUES(?,?,0,'')",(name,"user"))
        pid=int(cur.lastrowid)
        instruction=str(body.get("instruction") or "").strip()
        upload=intake.get("upload") if isinstance(intake.get("upload"),dict) else {}
        extracted=str(upload.get("text") or upload.get("preview") or "").strip()
        source=(source_text or extracted).strip()
        note_parts=["Agape automatically saved this new work as a reusable project."]
        if instruction: note_parts += ["", "Requested result:", instruction]
        if source: note_parts += ["", "Source information:", source[:80000]]
        con.execute("INSERT INTO messages(project_id,role,provider,model,content) VALUES(?,?,?,?,?)",(pid,"user","","","\\n".join(note_parts)))
        con.commit()
        return {"id":pid,"name":name,"kind":"user","archived":0,"source_database":str(db_path)}
    finally:
        con.close()

def run_work(body: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    task=str(body.get("task") or "").strip(); project_id=int(body.get("project_id") or 0); quality=str(body.get("quality") or "gold").lower()
    adopted=ensure_existing_services(plan,project_id)
    if quality not in {"standard","gold"}:quality="gold"
    reviewer_count=max(2,min(10,int(body.get("reviewer_count") or 10)))
    file_name=str(body.get("file_name") or "").strip(); file_b64=str(body.get("file_data_base64") or "").strip()
    run_id="MAIN-"+time.strftime("%Y%m%d-%H%M%S")
    record_event(run_id,"mainframe","plan","PASS",plan.get("title") or "Work planned")
    intake_id=str(body.get("intake_id") or "").strip()
    if not intake_id and file_name and file_b64:
        bridge=ensure_r24()
        if not bridge.get("ok"):
            raise RuntimeError(str(bridge.get("error")))
        record_event(run_id,"documents","intake","START","Preparing uploaded source")
        s,p=request_json("POST",R24+"/api/document/intake",{
            "name":Path(file_name).name,"data_base64":file_b64,"project_id":project_id,"instruction":task,
            "format":str(body.get("format") or "docx"),"also_pdf":bool(body.get("also_pdf",True)),
        },timeout=600)
        if s!=200 or not isinstance(p,dict) or not isinstance(p.get("intake"),dict):
            raise RuntimeError("DOCUMENT_INTAKE_FAILED: "+json.dumps(p,ensure_ascii=False)[:1200])
        intake_id=str(p["intake"].get("id") or "")
        record_event(run_id,"documents","intake","PASS","Source prepared")
    job_body={
        "project_id":project_id,"intake_id":intake_id,"instruction":task,"quality_mode":quality,
        "reviewer_count":reviewer_count,"router":str(body.get("router") or "agape"),
        "format":str(body.get("format") or "docx"),"also_pdf":bool(body.get("also_pdf",True)),
    }
    if not project_id and not intake_id:
        # Simple text-only document/research requests can go directly to Document Studio.
        if plan.get("route") in {"document","research"}:
            s,p=request_json("POST",DOC+"/api/create",{
                "title":str(body.get("title") or "Agape Result"),"app":"writer","doc_type":"Business Report" if plan.get("route")=="research" else "Proposal",
                "theme":"Executive Navy","format":str(body.get("format") or "docx"),"content":task,
            },timeout=1200)
            if s==200 and isinstance(p,dict) and p.get("ok"):
                remember_work(str(body.get("title") or plan.get("title")),task,str(plan.get("route")),"", "PASS",p)
                record_event(run_id,"documents","complete","PASS","Finished output created")
                return {"ok":True,"mode":"direct-document","result":p,"run_id":run_id}
        raise RuntimeError("PROJECT_OR_SOURCE_DOCUMENT_REQUIRED")
    bridge=ensure_r24()
    if not bridge.get("ok"):
        raise RuntimeError(str(bridge.get("error")))
    record_event(run_id,"workflow-bridge","execute","START","Work accepted")
    s,p=request_json("POST",R24+"/api/jobs",job_body,timeout=30)
    if s not in {200,201,202} or not isinstance(p,dict) or not p.get("job_id"):
        raise RuntimeError("WORK_SUBMIT_FAILED: "+json.dumps(p,ensure_ascii=False)[:1200])
    jid=str(p["job_id"])
    remember_work(str(body.get("title") or plan.get("title")),task,str(plan.get("route")),jid,"QUEUED",{
        "run_id":run_id,"project_id":project_id,"intake_id":intake_id
    })
    return {"ok":True,"mode":"delegated","job_id":jid,"run_id":run_id,"status_url":"/api/work/"+urllib.parse.quote(jid)}


def prepare_intake(body: dict[str, Any], progress=None) -> dict[str, Any]:
    """Prepare exactly one user-selected source for the document workflow.

    Older clients can omit source_mode; the mode is then inferred for
    compatibility. New clients send an explicit mode so irrelevant source
    branches are ignored after the user makes a choice.
    """
    plan={"route":"document"}
    if progress:
        progress(5, "Reading the selected source")
    source_mode=str(body.get("source_mode") or "").strip().lower()
    project_id=int(body.get("project_id") or 0)
    file_name=str(body.get("file_name") or "").strip()
    file_b64=str(body.get("file_data_base64") or "").strip()
    source_text=str(body.get("source_text") or "").strip()
    source_project_id=0
    project_name=""

    if source_mode not in {"paste","upload","project"}:
        if source_text:
            source_mode="paste"
        elif file_name and file_b64:
            source_mode="upload"
        elif project_id>0:
            source_mode="project"
        else:
            raise ValueError("CHOOSE_SOURCE_TEXT_FILE_OR_SAVED_PROJECT")

    # Once a mode is selected, discard the other source branches. This keeps
    # both the logic and the AI context unambiguous.
    if source_mode=="paste":
        if not source_text:
            raise ValueError("PASTED_SOURCE_TEXT_REQUIRED")
        project_id=0; file_name="pasted-source.txt"
        file_b64=base64.b64encode(source_text.encode("utf-8")).decode("ascii")
    elif source_mode=="upload":
        if not file_name or not file_b64:
            raise ValueError("UPLOADED_SOURCE_DOCUMENT_REQUIRED")
        project_id=0; source_text=""
    else:
        if project_id<=0:
            raise ValueError("SAVED_PROJECT_REQUIRED")
        source_project_id=project_id
        bundle=_saved_project_bundle(project_id)
        project=bundle.get("project") if isinstance(bundle.get("project"),dict) else {}
        source_text=_saved_project_source(project_id,bundle)
        project_name=str(project.get("name") or f"Saved Project {project_id}").strip()
        safe_name="".join(ch if ch.isalnum() or ch in " -_." else "-" for ch in project_name).strip(" .")[:100] or f"saved-project-{project_id}"
        file_name=safe_name+".txt"
        file_b64=base64.b64encode(source_text.encode("utf-8")).decode("ascii")
        # The project has now been snapshotted into the source text. From here on,
        # document preparation must not depend on Core remaining online.
        project_id=0

    if progress:
        progress(18, "Source selected and validated")
    ensure_existing_services(plan,0)
    if progress:
        progress(32, "Document tools are ready")
    bridge=ensure_r24()
    if not bridge.get("ok"):
        raise RuntimeError(str(bridge.get("error")))
    if progress:
        progress(45, "Checking spelling and grammar, then filling the brief with AI")

    request_body={
        "prepare_request_id":str(body.get("prepare_request_id") or ""),
        "name":Path(file_name).name,"data_base64":file_b64,"project_id":project_id,
        "source_mode":source_mode,"instruction":str(body.get("instruction") or ""),
        "format":str(body.get("format") or "docx"),"also_pdf":bool(body.get("also_pdf",True)),
    }
    if source_mode=="project":
        request_body["source_project_id"]=int(source_project_id or 0)
        request_body["project_name"]=str(project_name or "Saved Agape Project")
        request_body["project_info"]=source_text
    s,p=request_json("POST",R24+"/api/document/intake",request_body,timeout=900)
    if s!=200 or not isinstance(p,dict):
        raise RuntimeError("DOCUMENT_INTAKE_FAILED: "+json.dumps(p,ensure_ascii=False)[:1600])
    if progress:
        progress(96, "AI brief prepared; finalising the review screen")
    row=p.get("intake") if isinstance(p.get("intake"),dict) else p
    if isinstance(row,dict):
        row["source_mode"]=source_mode
        if source_mode in {"paste","upload"} and int(row.get("project_id") or 0)<=0:
            saved=_save_new_source_as_project(row,body,source_text,file_name)
            row["project_id"]=int(saved["id"])
            row["project_name"]=str(saved["name"])
            row["auto_saved_project"]=saved
            intake_id=str(row.get("id") or "")
            if intake_id:
                request_json("POST",R24+"/api/intakes/"+urllib.parse.quote(intake_id)+"/project",{
                    "project_id":int(saved["id"]),"project_name":str(saved["name"])
                },timeout=30)
        if "intake" in p and isinstance(p.get("intake"),dict):
            p["intake"]=row
    return p


def intake(intake_id: str) -> tuple[int, Any]:
    ensure_r24()
    return request_json("GET",R24+"/api/intakes/"+urllib.parse.quote(intake_id),timeout=20)

def improve_intake(intake_id: str) -> tuple[int, Any]:
    ensure_r24()
    return request_json("POST",R24+"/api/intakes/"+urllib.parse.quote(intake_id)+"/improve",{},timeout=900)

def revise_intake(intake_id: str, instruction: str) -> tuple[int, Any]:
    ensure_r24()
    return request_json("POST",R24+"/api/intakes/"+urllib.parse.quote(intake_id)+"/revise",{"instruction":instruction},timeout=900)

def answer_intake(intake_id: str, answers: dict[str,Any]) -> tuple[int, Any]:
    ensure_r24()
    return request_json("POST",R24+"/api/intakes/"+urllib.parse.quote(intake_id)+"/answers",{"answers":answers},timeout=120)

def revise_work(job_id: str, instruction: str, quality_mode: str="") -> tuple[int, Any]:
    ensure_r24()
    return request_json("POST",R24+"/api/jobs/"+urllib.parse.quote(job_id)+"/revise",{"instruction":instruction,"quality_mode":quality_mode},timeout=30)

def open_result_folder(job_id: str, index: int = 0) -> tuple[int, Any]:
    ensure_r24()
    return request_json("POST",R24+"/api/open-result-folder",{"job_id":job_id,"index":int(index)},timeout=15)


def job(job_id: str) -> tuple[int, Any]:
    status, payload = request_json("GET",R24+"/api/jobs/"+urllib.parse.quote(job_id),timeout=10)
    if status == 200 and isinstance(payload, dict):
        try:
            sync_external_work_status(job_id, payload)
        except Exception:
            # Activity synchronisation is telemetry and must never break job polling.
            pass
    return status, payload
