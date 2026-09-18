from __future__ import annotations
import argparse, base64, json, mimetypes, os, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from . import __version__
from .bridge import R24, answer_intake, ensure_r24, improve_intake, intake as bridge_intake, job as bridge_job, open_result_folder, prepare_intake, projects_with_live_status as bridge_projects, recent_work_with_live_status, revise_intake, revise_work, run_work
from .capabilities import apply_profile, capability_status, install_support, profile_plan, service_status
from .planner import plan as make_plan
from .state import BUILD, ROOT, claim_intake_prepare_job, create_intake_prepare_job, delete_intake_prepare_request, events, get_intake_prepare_job, load_intake_prepare_request, load_settings, recent_work, save_settings, update_intake_prepare_job
from .system_probe import probe
from .security import approved_installers, revoke_approval
from .project_recovery import recover_past_projects
from .coding_tools import tool_status as coding_tool_status, action as coding_tool_action
from .browser_qa import status as browser_qa_status, run as browser_qa_run, install_chromium as browser_qa_install_chromium
from .desktop_qa import status as desktop_qa_status, probe as desktop_qa_probe
from .testing_tools import status as testing_tool_status, install as testing_tool_install
from .api_keys import status as api_key_status, set_key as api_key_set, remove_key as api_key_remove, import_key_file as api_key_import, bootstrap as api_key_bootstrap

WEB=ROOT/"web"

# Load private saved API keys into environment variables before any provider is used.
# If API-KEYS.local.json is present, missing keys are imported once without overwriting existing values.
try:
    api_key_bootstrap()
except Exception:
    pass


INSTANCE_ID = "MAIN-" + uuid.uuid4().hex[:12].upper()
STARTED_AT = time.strftime("%Y-%m-%dT%H:%M:%S")
_PREP_LOCK = threading.RLock()
_PREP_THREADS: dict[str, threading.Thread] = {}
_PREP_TERMINAL = {"COMPLETE","COMPLETED","PASS","SUCCESS","DONE","FAILED","FAIL","ERROR","BLOCKED"}


def _active_prepare_job_ids() -> list[str]:
    with _PREP_LOCK:
        return sorted(jid for jid,t in _PREP_THREADS.items() if t.is_alive())


def _launch_intake_prepare_worker(job_id: str, payload: dict[str, Any], *, resumed: bool = False) -> dict[str, Any]:
    with _PREP_LOCK:
        current_thread=_PREP_THREADS.get(job_id)
        if current_thread and current_thread.is_alive():
            return get_intake_prepare_job(job_id) or {"job_id":job_id,"status":"RUNNING"}
        row=get_intake_prepare_job(job_id) or {}
        status=str(row.get("status") or "QUEUED").upper()
        if status in _PREP_TERMINAL:
            return row
        attempts=int(row.get("attempts") or 0)
        if attempts >= 3:
            failed=update_intake_prepare_job(
                job_id,status="FAILED",progress=100,message="Source preparation stopped after repeated Mainframe interruptions",
                error="SOURCE_PREPARATION_INTERRUPTED_REPEATEDLY: Restart Agape and press Prepare with AI again.",worker_instance=INSTANCE_ID,
            )
            delete_intake_prepare_request(job_id)
            return failed
        claim_intake_prepare_job(job_id,INSTANCE_ID,"Resuming source preparation after Mainframe restart" if resumed else "Starting source preparation")

        def worker():
            try:
                def report(percent: float, message: str):
                    update_intake_prepare_job(job_id,status="RUNNING",progress=percent,message=message,worker_instance=INSTANCE_ID)
                report(float((get_intake_prepare_job(job_id) or {}).get("progress") or 3), "Resuming source preparation" if resumed else "Starting source preparation")
                result=prepare_intake(payload,progress=report)
                update_intake_prepare_job(job_id,status="COMPLETE",progress=100,message="Source prepared",result=result,worker_instance=INSTANCE_ID)
                delete_intake_prepare_request(job_id)
            except Exception as exc:
                update_intake_prepare_job(job_id,status="FAILED",progress=100,message="Source preparation failed",error=str(exc),worker_instance=INSTANCE_ID)
                delete_intake_prepare_request(job_id)
            finally:
                with _PREP_LOCK:
                    _PREP_THREADS.pop(job_id,None)

        thread=threading.Thread(target=worker,daemon=True,name=f"AgapeIntakePrepare-{job_id}")
        _PREP_THREADS[job_id]=thread
        thread.start()
        return get_intake_prepare_job(job_id) or {"job_id":job_id,"status":"RUNNING"}


def _ensure_intake_prepare_worker(job_id: str) -> dict[str, Any] | None:
    row=get_intake_prepare_job(job_id)
    if not row:
        return None
    status=str(row.get("status") or "").upper()
    if status in _PREP_TERMINAL:
        return row
    with _PREP_LOCK:
        active=bool(_PREP_THREADS.get(job_id) and _PREP_THREADS[job_id].is_alive())
    if active:
        return row
    payload=load_intake_prepare_request(job_id)
    if not payload:
        return update_intake_prepare_job(
            job_id,status="FAILED",progress=100,message="Source preparation cannot be resumed",
            error="SOURCE_PREPARATION_REQUEST_NOT_AVAILABLE: Press Prepare with AI again.",worker_instance=INSTANCE_ID,
        )
    return _launch_intake_prepare_worker(job_id,payload,resumed=bool(row.get("attempts")))


def _start_intake_prepare(payload: dict[str, Any]) -> dict[str, Any]:
    request_id=str(payload.get("prepare_request_id") or "").strip()
    job_id="PREP-"+(uuid.uuid5(uuid.NAMESPACE_URL,request_id).hex[:16].upper() if request_id else uuid.uuid4().hex[:16].upper())
    existing=get_intake_prepare_job(job_id)
    if existing:
        row=_ensure_intake_prepare_worker(job_id) or existing
        return {"ok":True,"prepare_job_id":job_id,"status":row.get("status") or "QUEUED","status_url":"/api/intake-prepare/"+urllib.parse.quote(job_id),"reused":True}
    create_intake_prepare_job(job_id,"Source accepted; preparation queued",request=payload)
    row=_launch_intake_prepare_worker(job_id,payload,resumed=False)
    return {"ok":True,"prepare_job_id":job_id,"status":row.get("status") or "QUEUED","status_url":"/api/intake-prepare/"+urllib.parse.quote(job_id)}


def send_json(h:BaseHTTPRequestHandler,status:int,payload:Any):
    raw=json.dumps(payload,ensure_ascii=False,default=str).encode("utf-8")
    h.send_response(status);h.send_header("Content-Type","application/json; charset=utf-8");h.send_header("Cache-Control","no-store");h.send_header("X-Content-Type-Options","nosniff");h.send_header("Content-Length",str(len(raw)));h.end_headers();h.wfile.write(raw)


def proxy_r24_bytes(h:BaseHTTPRequestHandler, path:str):
    url=R24+path
    try:
        with urllib.request.urlopen(url,timeout=60) as r:
            raw=r.read();status=getattr(r,"status",200);ctype=r.headers.get("Content-Type") or "application/octet-stream";cd=r.headers.get("Content-Disposition")
        h.send_response(status);h.send_header("Content-Type",ctype);h.send_header("Cache-Control","no-store")
        if cd:h.send_header("Content-Disposition",cd)
        h.send_header("Content-Length",str(len(raw)));h.end_headers();h.wfile.write(raw)
    except urllib.error.HTTPError as e:
        raw=e.read() or b"";ctype=e.headers.get("Content-Type") or "application/json; charset=utf-8"
        h.send_response(int(e.code));h.send_header("Content-Type",ctype);h.send_header("Cache-Control","no-store");h.send_header("Content-Length",str(len(raw)));h.end_headers();h.wfile.write(raw)
    except Exception as e:send_json(h,502,{"error":"DOWNLOAD_PROXY_FAILED: "+str(e),"upstream":R24})

def body(h:BaseHTTPRequestHandler)->dict[str,Any]:
    n=int(h.headers.get("Content-Length","0") or 0)
    if n>55*1024*1024:raise ValueError("REQUEST_TOO_LARGE")
    raw=h.rfile.read(n) if n else b"{}";obj=json.loads(raw.decode("utf-8",errors="replace") or "{}")
    if not isinstance(obj,dict):raise ValueError("JSON_OBJECT_REQUIRED")
    return obj

class Handler(BaseHTTPRequestHandler):
    server_version="AgapeMainframe/1"
    def log_message(self,*a):return
    def static(self,path:str):
        name=path.lstrip("/") or "index.html";target=(WEB/name).resolve()
        if WEB not in target.parents and target!=WEB:return self.send_error(403)
        if not target.exists():return self.send_error(404)
        raw=target.read_bytes();mime=mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200);self.send_header("Content-Type",mime+("; charset=utf-8" if mime.startswith("text/") or mime in {"application/javascript","application/json"} else ""));self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path);q=urllib.parse.parse_qs(u.query)
        try:
            if u.path=="/api/health":return send_json(self,200,{"ok":True,"build":BUILD,"version":__version__,"pid":os.getpid(),"instance_id":INSTANCE_ID,"started_at":STARTED_AT,"active_source_jobs":_active_prepare_job_ids(),"settings":load_settings(),"services_endpoint":"/api/services"})
            if u.path=="/api/setup/status":
                system=probe();s=load_settings();return send_json(self,200,{"ok":True,"settings":s,"system":system,"plan":profile_plan(str(s.get("experience") or "basic"),system),"services":service_status()})
            if u.path=="/api/setup/plan":
                exp=str((q.get("experience") or ["basic"])[0]);system=probe();return send_json(self,200,{"ok":True,"system":system,"plan":profile_plan(exp,system)})
            if u.path=="/api/system":return send_json(self,200,probe())
            if u.path=="/api/capabilities":return send_json(self,200,{"ok":True,"capabilities":capability_status(probe())})
            if u.path=="/api/services":return send_json(self,200,{"ok":True,"services":service_status()})
            if u.path=="/api/projects":return send_json(self,200,{"ok":True,"projects":bridge_projects()})
            if u.path=="/api/events":return send_json(self,200,{"ok":True,"events":events(int((q.get("limit") or [150])[0]))})
            if u.path=="/api/recent":return send_json(self,200,{"ok":True,"items":recent_work_with_live_status(int((q.get("limit") or [50])[0]))})
            if u.path=="/api/security/approved-installers":return send_json(self,200,{"ok":True,"approved":approved_installers()})
            if u.path=="/api/coding/tools":return send_json(self,200,coding_tool_status())
            if u.path=="/api/qa/browser":return send_json(self,200,browser_qa_status())
            if u.path=="/api/qa/desktop":return send_json(self,200,desktop_qa_status())
            if u.path=="/api/testing/tools":return send_json(self,200,testing_tool_status())
            if u.path=="/api/keys/status":return send_json(self,200,api_key_status())
            if u.path.startswith("/api/intake-prepare/"):
                jid=u.path.split("/",3)[3];row=_ensure_intake_prepare_worker(jid)
                if not row:return send_json(self,404,{"error":"INTAKE_PREPARE_JOB_NOT_FOUND"})
                return send_json(self,200,row)
            if u.path.startswith("/api/intake/"):
                iid=u.path.split("/",3)[3];st,p=bridge_intake(iid);return send_json(self,200 if st==200 else 502,p)
            if u.path.startswith("/api/work/") and u.path.endswith("/download"):
                parts=u.path.split("/");jid=parts[3];idx=int((q.get("index") or [0])[0]);return proxy_r24_bytes(self,"/api/jobs/"+urllib.parse.quote(jid)+"/download?index="+str(idx))
            if u.path.startswith("/api/work/"):
                jid=u.path.split("/",3)[3];s,p=bridge_job(jid);return send_json(self,200 if s==200 else 502,p)
            if u.path=="/":return self.static("/index.html")
            if u.path in {"/app.js","/styles.css"}:return self.static(u.path)
            return send_json(self,404,{"error":"NOT_FOUND"})
        except Exception as e:return send_json(self,500,{"error":str(e),"type":type(e).__name__})
    def do_POST(self):
        u=urllib.parse.urlparse(self.path)
        try:
            if u.path=="/api/setup/apply":
                b=body(self);return send_json(self,200,{"ok":True,"settings":apply_profile(str(b.get("experience") or "basic"),b.get("selected_capabilities") if isinstance(b.get("selected_capabilities"),list) else None),"bridge":{"lazy":True}})
            if u.path=="/api/settings":return send_json(self,200,{"ok":True,"settings":save_settings(body(self))})
            if u.path=="/api/security/approved-installers/revoke":
                b=body(self);return send_json(self,200,revoke_approval(str(b.get("id") or "")))
            if u.path=="/api/projects/recover":
                result=recover_past_projects();return send_json(self,200 if result.get("ok") else 500,result)
            if u.path=="/api/support/install":
                b=body(self);return send_json(self,200,install_support(str(b.get("kind") or ""),str(b.get("package") or "")))
            if u.path=="/api/coding/tools/action":
                b=body(self);return send_json(self,200,coding_tool_action(str(b.get("tool") or ""),str(b.get("action") or ""),str(b.get("workspace") or "")))
            if u.path=="/api/qa/browser/run":
                b=body(self);result=browser_qa_run(str(b.get("base_url") or ("http://127.0.0.1:"+str(self.server.server_port))),str(b.get("mode") or "safe"));return send_json(self,200 if result.get("ok") else 500,result)
            if u.path=="/api/qa/browser/install-chromium":
                return send_json(self,200,browser_qa_install_chromium())
            if u.path=="/api/qa/desktop/probe":
                b=body(self);return send_json(self,200,desktop_qa_probe(str(b.get("manager") or ""),str(b.get("workspace") or "")))
            if u.path=="/api/testing/tools/install":
                b=body(self);result=testing_tool_install(str(b.get("tool") or ""));return send_json(self,200 if result.get("ok") else 500,result)
            if u.path=="/api/keys/set":
                b=body(self);return send_json(self,200,api_key_set(str(b.get("provider") or ""),str(b.get("value") or "")))
            if u.path=="/api/keys/remove":
                b=body(self);return send_json(self,200,api_key_remove(str(b.get("provider") or "")))
            if u.path=="/api/keys/import":
                b=body(self);result=api_key_import(str(b.get("path") or "") or None,overwrite=bool(b.get("overwrite")));return send_json(self,200 if result.get("ok") else 404,result)
            if u.path=="/api/intake/start":
                return send_json(self,202,_start_intake_prepare(body(self)))
            if u.path=="/api/intake":
                # Compatibility endpoint for older clients. New UI uses the
                # background preparation job so long AI work never depends on
                # one browser fetch staying open.
                return send_json(self,200,prepare_intake(body(self)))
            if u.path.startswith("/api/intake/") and u.path.endswith("/improve"):
                iid=u.path.strip("/").split("/")[2];st,p=improve_intake(iid);return send_json(self,200 if st==200 else 502,p)
            if u.path.startswith("/api/intake/") and u.path.endswith("/revise"):
                iid=u.path.strip("/").split("/")[2];b=body(self);st,p=revise_intake(iid,str(b.get("instruction") or ""));return send_json(self,200 if st==200 else 502,p)
            if u.path.startswith("/api/intake/") and u.path.endswith("/answers"):
                iid=u.path.strip("/").split("/")[2];b=body(self);st,p=answer_intake(iid,b.get("answers") if isinstance(b.get("answers"),dict) else {});return send_json(self,200 if st==200 else 502,p)
            if u.path.startswith("/api/work/") and u.path.endswith("/revise"):
                jid=u.path.strip("/").split("/")[2];b=body(self);st,p=revise_work(jid,str(b.get("instruction") or ""),str(b.get("quality_mode") or ""));return send_json(self,202 if st in {200,201,202} else 502,p)
            if u.path.startswith("/api/work/") and u.path.endswith("/open-folder"):
                jid=u.path.strip("/").split("/")[2];q=urllib.parse.parse_qs(u.query);idx=int((q.get("index") or [0])[0]);st,p=open_result_folder(jid,idx);return send_json(self,200 if st==200 else 502,p)
            if u.path=="/api/plan":
                b=body(self);p=make_plan(str(b.get("task") or ""),has_file=bool(b.get("file_name")),project_id=int(b.get("project_id") or 0),quality=str(b.get("quality") or load_settings().get("quality") or "gold"));return send_json(self,200,p)
            if u.path=="/api/run":
                b=body(self);settings=load_settings()
                if not isinstance(b.get("coding"),dict):b["coding"]={}
                b["coding"].setdefault("model_mode",settings.get("coding_model_mode","auto-coding"))
                b["coding"].setdefault("agent",settings.get("coding_agent","auto"))
                b["coding"].setdefault("manager",settings.get("code_manager","agape"))
                p=make_plan(str(b.get("task") or ""),has_file=bool(b.get("file_name")),project_id=int(b.get("project_id") or 0),quality=str(b.get("quality") or settings.get("quality") or "gold"));p["coding"]=dict(b["coding"]);return send_json(self,202,run_work(b,p))
            return send_json(self,404,{"error":"NOT_FOUND"})
        except ValueError as e:return send_json(self,400,{"error":str(e)})
        except Exception as e:return send_json(self,500,{"error":str(e),"type":type(e).__name__})

def serve(port:int=8850):
    srv=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(f"AGAPE_MAINFRAME_READY=http://127.0.0.1:{port}",flush=True);print(f"BUILD={BUILD}",flush=True)
    try:srv.serve_forever()
    finally:srv.server_close()

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--port",type=int,default=8850);a=ap.parse_args();serve(a.port);return 0


if __name__=="__main__":
    raise SystemExit(main())
