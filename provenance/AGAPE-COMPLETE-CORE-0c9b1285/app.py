from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import db
import intent_router
import desktop_tools
import startup
import model_router
import release_manager
import alpha_readiness
import project_summary
import autodev_controller
import codebase_index
import test_planner
import code_review
import escalation_router
import changeset
import project_health
import dependency_map
import impact_analysis
import test_selector
import failure_cluster
import resource_budget
import task_priority
import approval_gate
import changelog_builder
import release_compare
import goal_spec
import workspace_snapshot
import context_pack
import work_breakdown
import patch_plan
import patch_transaction
import test_matrix
import repair_cycle
import evidence_bundle
import autodev_pipeline
import autodev_session
import task_graph
import scope_lock
import failure_triage
import model_scorecard
import adaptive_router
import resume_planner
import acceptance_gate
import run_ledger
import autodev_cycle
import requirements_spec
import change_budget
import context_freshness
import retry_policy
import repair_verifier
import dependency_executor
import completion_evidence
import regression_planner
import release_confidence
import self_heal_controller
import baseline_attestation
import failure_evidence
import root_cause
import reproduction_planner
import repair_candidate
import flake_detector
import checkpoint_selector
import execution_budget
import autonomy_policy
import autodev_governor
import work_plan
import interruption_recovery
import dependency_state
import confidence_tracker
import stale_failure
import parallelism_advisor
import checkpoint_cadence
import regression_memory
import completion_proof
import development_supervisor
import provider_catalog
import connection_spec
import external_provider
import provider_failover
import request_budget
import offline_queue
import backup_restore
import project_portability
import diagnostic_bundle
import instance_guard
import schema_guard
import startup_recovery
import audit_trail
import provider_resilience
import alpha_user_readiness
import safety_matrix
import retention_policy
import resource_envelope
import mission_proof
import alpha_release
from config import BROWSER_NAMESPACE, BUILD, DATA_ROOT, DEFAULT_PORT, HOST, SESSION_TOKEN_FILE
from orchestrator import run_chat
from system_test import run_system_test
from providers import ProviderError, ollama_models
from security import ensure_session_token, session_ok
from tools import analyze_command
from workflows import list_templates, run_template
from project_loop import configure_project_loop, recover_interrupted_edits, run_project_loop

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
FIRST_RUN = ROOT / "first-run.html"
STARTED = time.time()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "DMTCoreV1/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def send_json(self, value: Any, status: int = 200) -> None:
        data = json_bytes(value)
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def send_text(self, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        data = text.encode("utf-8")
        self._headers(status, content_type, len(data))
        self.wfile.write(data)

    def read_json(self, limit: int = 1_000_000) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > limit:
            raise ValueError("INVALID_CONTENT_LENGTH")
        raw = self.rfile.read(length)
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("JSON_OBJECT_REQUIRED")
        return obj

    def require_session(self) -> bool:
        if session_ok(self.headers.get("X-DMT-Session")):
            return True
        self.send_json({"ok": False, "error": "SESSION_REQUIRED"}, 403)
        return False

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                self.send_text(INDEX.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")
                return
            if path in ("/first-run", "/first-run.html"):
                self.send_text(FIRST_RUN.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")
                return
            if path == "/api/version":
                self.send_json({
                    "ok": True,
                    "build": BUILD,
                    "pid": os.getpid(),
                    "project_path": str(ROOT),
                    "data_path": str(DATA_ROOT),
                    "database": str(db.DB_PATH),
                    "browser_namespace": BROWSER_NAMESPACE,
                    "uptime_seconds": round(time.time() - STARTED, 3),
                    "architecture": "modular-core-v1",
                })
                return
            if path == "/api/security/bootstrap.js":
                token = ensure_session_token()
                script = (
                    "(()=>{const t=" + json.dumps(token) + ";const f=window.fetch.bind(window);"
                    "window.fetch=(u,o={})=>{o.headers=new Headers(o.headers||{});o.headers.set('X-DMT-Session',t);return f(u,o);};"
                    "window.DMT_SESSION_READY=true;})();"
                )
                self.send_text(script, content_type="application/javascript; charset=utf-8")
                return
            if path == "/api/projects":
                scope = str((query.get("scope") or ["user"])[0])
                self.send_json({"ok": True, "projects": db.list_projects(scope), "catalog": db.project_catalog_status()})
                return
            if path == "/api/projects/catalog":
                self.send_json(db.project_catalog_status())
                return
            if path == "/api/project/summary":
                project_id=int((query.get("project_id") or ["0"])[0]); item=db.project(project_id)
                if not item: raise ValueError("PROJECT_NOT_FOUND")
                self.send_json(project_summary.summarize_project(item, db.project_loop_runs(project_id), db.list_issues(project_id)))
                return
            if path == "/api/issues":
                project_id=int((query.get("project_id") or ["0"])[0]); status=(query.get("status") or [None])[0]
                self.send_json({"ok":True,"issues":db.list_issues(project_id,status)})
                return
            if path == "/api/models/escalate":
                failures=int((query.get("failures") or ["0"])[0]); complexity=str((query.get("complexity") or ["low"])[0])
                try: installed=ollama_models()
                except Exception: installed=[{"name":"qwen2.5-coder:1.5b-instruct"},{"name":"qwen2.5-coder:7b"}]
                self.send_json(escalation_router.choose_escalation(installed,failures,complexity))
                return
            if path == "/api/autodev/supervisor/runs":
                raw=(query.get("project_id") or [""])[0]; project_id=int(raw) if str(raw).strip() else None; limit=int((query.get("limit") or ["100"])[0])
                self.send_json({"ok":True,"runs":db.list_supervisor_runs(project_id,limit)})
                return
            if path == "/api/tests/observations":
                project_id=int((query.get("project_id") or ["0"])[0]); test_name=str((query.get("test_name") or [""])[0]); limit=int((query.get("limit") or ["100"])[0])
                self.send_json({"ok":True,"observations":db.list_test_observations(project_id,test_name,limit)})
                return
            if path == "/api/providers/catalog":
                self.send_json(provider_catalog.provider_catalog())
                return
            if path == "/api/deferred":
                raw=(query.get("project_id") or [""])[0]; project_id=int(raw) if str(raw).strip() else None; status=str((query.get("status") or [""])[0])
                self.send_json(offline_queue.list_items(project_id,status))
                return
            if path == "/api/audit":
                self.send_json(audit_trail.list_events(int((query.get("limit") or ["100"])[0])))
                return
            if path == "/api/alpha/release/runs":
                self.send_json({"ok":True,"runs":db.list_alpha_release_runs(int((query.get("limit") or ["50"])[0]))})
                return
            if path == "/api/messages":
                project_id = int((query.get("project_id") or ["0"])[0])
                self.send_json({"ok": True, "messages": db.list_messages(project_id)})
                return
            if path == "/api/db/status":
                self.send_json(db.status())
                return
            if path == "/api/system-test":
                self.send_json(run_system_test())
                return
            if path == "/api/ollama/models":
                try:
                    models = ollama_models()
                    self.send_json({"ok": True, "models": models})
                except Exception as exc:
                    self.send_json({"ok": False, "models": [], "error": str(exc)}, 503)
                return
            if path == "/api/terminal/history":
                self.send_json({"ok": True, "history": db.terminal_history()})
                return
            if path == "/api/templates":
                self.send_json({"ok": True, "templates": list_templates()})
                return
            if path == "/api/chat/status":
                self.send_json({"ok": True, "requests": db.rows("SELECT * FROM chat_requests ORDER BY rowid DESC LIMIT 100")})
                return
            if path == "/api/project-loop/settings":
                project_id = int((query.get("project_id") or ["0"])[0])
                self.send_json({"ok": True, "settings": db.project_loop_settings(project_id)})
                return
            if path == "/api/project-loop/runs":
                project_id = int((query.get("project_id") or ["0"])[0])
                self.send_json({"ok": True, "runs": db.project_loop_runs(project_id)})
                return
            if path == "/api/project-loop/run":
                run_id = str((query.get("run_id") or [""])[0]).strip()
                if not run_id:
                    raise ValueError("RUN_ID_REQUIRED")
                item = db.project_loop_run(run_id)
                if not item:
                    raise ValueError("PROJECT_LOOP_RUN_NOT_FOUND")
                self.send_json({"ok": True, "run": item})
                return
            if path == "/api/connections":
                self.send_json({"ok": True, "connections": db.list_connections()})
                return
            if path == "/api/autodev/sessions":
                pid=int(query.get("project_id",["0"])[0] or 0)
                self.send_json(autodev_session.list_sessions(pid if pid else None,int(query.get("limit",["100"])[0] or 100)))
                return
            if path == "/api/models/scorecard":
                models=ollama_models()
                self.send_json(model_scorecard.build_scorecard(models,str(query.get("task_type",["coding"])[0] or "coding")))
                return
            if path == "/api/run-ledger":
                self.send_json(run_ledger.ledger_status(str(query.get("session_id",[""])[0] or "")))
                return
            if path == "/api/db/tables":
                self.send_json({"ok": True, "tables": db.database_tables()})
                return
            if path == "/api/db/table":
                name = str((query.get("name") or [""])[0])
                limit = int((query.get("limit") or ["100"])[0])
                self.send_json({"ok": True, "name": name, "rows": db.database_table_rows(name, limit)})
                return
            if path == "/api/startup/status":
                self.send_json(startup.startup_status(DEFAULT_PORT))
                return
            if path == "/api/models/recommend":
                task = str((query.get("task") or [""])[0])
                try:
                    installed = ollama_models()
                except Exception:
                    installed = [{"name":"qwen2.5-coder:1.5b-instruct"},{"name":"qwen2.5-coder:7b"}]
                self.send_json(model_router.choose_model(installed, task))
                return
            if path == "/api/autodev/queue":
                raw = str((query.get("project_id") or [""])[0]).strip()
                project_id = int(raw) if raw else None
                self.send_json({"ok": True, "queue": db.list_autodev_queue(project_id)})
                return
            if path == "/api/releases/checkpoints":
                checkpoint_root = DATA_ROOT / "release-checkpoints"
                self.send_json({"ok": True, "checkpoints": release_manager.list_checkpoints(str(checkpoint_root))})
                return
            if path == "/api/alpha/readiness":
                signals = {
                    "core_system_test": callable(run_system_test),
                    "session_security": SESSION_TOKEN_FILE.is_file(),
                    "project_loop": True,
                    "connection_manager": hasattr(db, "save_connection"),
                    "database_manager": hasattr(db, "database_tables"),
                    "model_router": True,
                    "autodev_queue": hasattr(db, "enqueue_autodev_task"),
                    "release_checkpoints": True,
                    "fixed_startup": startup.startup_status(DEFAULT_PORT).get("fixed_port") == DEFAULT_PORT,
                    "terminal_history": hasattr(db, "terminal_history"),
                }
                self.send_json(alpha_readiness.evaluate_readiness(signals))
                return
            self.send_json({"ok": False, "error": "NOT_FOUND"}, 404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if not self.require_session():
            return
        try:
            data = self.read_json()
            # AGAPE_INTENT_ROUTE_STABLE
            if path == "/api/intent/route":
                message = str(data.get("message") or "")
                self.send_json({"ok": True, "intent": intent_router.classify_intent(message)})
                return
            if path == "/api/projects/classify":
                self.send_json(db.classify_existing_projects())
                return
            if path == "/api/projects/archive":
                item=db.project(int(data.get("project_id") or 0))
                if not item: raise ValueError("PROJECT_NOT_FOUND")
                archived=bool(data.get("archived",True)); kind=str(data.get("kind") or item.get("kind") or "user")
                self.send_json({"ok":True,"project":db.set_project_classification(int(item["id"]),kind,archived,str(data.get("reason") or ("manual_archive" if archived else "")))})
                return
            if path == "/api/autodev/policy":
                self.send_json(autodev_controller.decide_next(bool(data.get("test_passed")),int(data.get("step") or 0),int(data.get("max_steps") or 4),int(data.get("consecutive_failures") or 0),bool(data.get("changed",True))))
                return
            if path == "/api/codebase/index":
                self.send_json(codebase_index.build_index(str(data.get("workspace") or ""),int(data.get("max_files") or 500)))
                return
            if path == "/api/tests/plan":
                self.send_json(test_planner.plan_tests(str(data.get("workspace") or "")))
                return
            if path == "/api/review/run":
                self.send_json(code_review.review_python(str(data.get("path") or "")))
                return
            if path == "/api/issues/add":
                self.send_json({"ok":True,"issue":db.add_issue(int(data.get("project_id") or 0),str(data.get("fingerprint") or ""),str(data.get("title") or ""),str(data.get("detail") or ""),str(data.get("severity") or "medium"))})
                return
            if path == "/api/issues/resolve":
                self.send_json({"ok":True,"issue":db.resolve_issue(int(data.get("issue_id") or 0))})
                return
            if path == "/api/changeset/preview":
                self.send_json(changeset.preview_changes(str(data.get("before_root") or ""),str(data.get("after_root") or ""),list(data.get("protected_names") or [])))
                return
            if path == "/api/project/health":
                self.send_json(project_health.score_health(data))
                return
            if path == "/api/dependencies/map":
                self.send_json(dependency_map.build_dependency_map(str(data.get("workspace") or ""),int(data.get("max_files") or 500)))
                return
            if path == "/api/impact/analyze":
                self.send_json(impact_analysis.analyze_impact(dict(data.get("graph") or {}),list(data.get("changed_files") or [])))
                return
            if path == "/api/tests/select":
                self.send_json(test_selector.select_tests(list(data.get("changed_files") or []),list(data.get("test_files") or [])))
                return
            if path == "/api/failures/cluster":
                self.send_json(failure_cluster.cluster_failures(list(data.get("failures") or [])))
                return
            if path == "/api/resources/budget":
                self.send_json(resource_budget.evaluate_budget(dict(data.get("signals") or {}),dict(data.get("limits") or {})))
                return
            if path == "/api/tasks/prioritize":
                self.send_json(task_priority.prioritize_tasks(list(data.get("tasks") or [])))
                return
            if path == "/api/approval/evaluate":
                self.send_json(approval_gate.evaluate_change(dict(data.get("change") or data)))
                return
            if path == "/api/changelog/build":
                self.send_json(changelog_builder.build_changelog(list(data.get("entries") or [])))
                return
            if path == "/api/releases/compare":
                self.send_json(release_compare.compare_manifests(dict(data.get("old_manifest") or {}),dict(data.get("new_manifest") or {})))
                return
            if path == "/api/goal/normalize":
                self.send_json(goal_spec.normalize_goal(str(data.get("goal") or ""), list(data.get("constraints") or [])))
                return
            if path == "/api/workspace/snapshot":
                self.send_json(workspace_snapshot.create_snapshot(str(data.get("workspace") or ""), int(data.get("max_files") or 1000)))
                return
            if path == "/api/context/pack":
                self.send_json(context_pack.build_context_pack(str(data.get("workspace") or ""), str(data.get("goal") or ""), dict(data.get("snapshot") or {}), int(data.get("max_files") or 12), int(data.get("max_chars") or 24000)))
                return
            if path == "/api/work/plan":
                self.send_json(work_breakdown.build_work_plan(dict(data.get("goal_spec") or {}), dict(data.get("context_pack") or {}), int(data.get("max_tasks") or 6)))
                return
            if path == "/api/patch/validate":
                self.send_json(patch_plan.validate_patch_plan(str(data.get("workspace") or ""), list(data.get("changes") or []), list(data.get("protected_names") or [])))
                return
            if path == "/api/patch/apply":
                workspace=str(data.get("workspace") or "")
                plan=patch_plan.validate_patch_plan(workspace, list(data.get("changes") or []), list(data.get("protected_names") or []))
                self.send_json(patch_transaction.apply_transaction(workspace, plan, bool(data.get("dry_run", True))))
                return
            if path == "/api/tests/matrix":
                self.send_json(test_matrix.build_test_matrix(dict(data.get("planned") or {}), list(data.get("selected_tests") or []), str(data.get("full_command") or "")))
                return
            if path == "/api/repair/decide":
                self.send_json(repair_cycle.decide_repair(bool(data.get("test_passed")), int(data.get("attempt") or 1), int(data.get("max_attempts") or 3), list(data.get("failures") or []), bool(data.get("changed", True))))
                return
            if path == "/api/evidence/build":
                output_root=str(DATA_ROOT / "evidence")
                self.send_json(evidence_bundle.build_evidence_bundle(output_root, str(data.get("label") or "run"), dict(data.get("evidence") or {})))
                return
            if path == "/api/autodev/pipeline/plan":
                self.send_json(autodev_pipeline.prepare_pipeline(str(data.get("workspace") or ""), str(data.get("goal") or ""), list(data.get("constraints") or []), int(data.get("max_steps") or 4)))
                return
            if path == "/api/autodev/session/create":
                self.send_json(autodev_session.create_session(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),str(data.get("test_command") or ""),int(data.get("max_steps") or 4),str(data.get("model") or "")))
                return
            if path == "/api/tasks/graph":
                self.send_json(task_graph.build_task_graph(list(data.get("tasks") or []),list(data.get("completed") or []),list(data.get("failed") or [])))
                return
            if path == "/api/scope/lock":
                self.send_json(scope_lock.create_scope_lock(str(data.get("workspace") or ""),list(data.get("allowed_paths") or []),int(data.get("max_files") or 1000)))
                return
            if path == "/api/scope/check":
                self.send_json(scope_lock.check_scope_lock(dict(data.get("lock") or {}),str(data.get("workspace") or ""),int(data.get("max_files") or 1000)))
                return
            if path == "/api/failures/triage":
                self.send_json(failure_triage.triage_failure(str(data.get("stdout") or ""),str(data.get("stderr") or ""),int(data["exit_code"]) if data.get("exit_code") is not None else None))
                return
            if path == "/api/models/outcome":
                item=db.record_model_outcome(str(data.get("model") or ""),str(data.get("task_type") or "coding"),bool(data.get("success")),float(data.get("duration_seconds") or 0),str(data.get("failure_category") or ""),str(data.get("session_id") or ""))
                self.send_json({"ok":True,"outcome":item})
                return
            if path == "/api/models/adaptive":
                models=list(data.get("models") or []) or ollama_models()
                self.send_json(adaptive_router.choose_adaptive_model(models,str(data.get("task") or ""),int(data.get("attempt") or 1),str(data.get("failure_category") or "")))
                return
            if path == "/api/autodev/resume":
                session=db.autodev_session(str(data.get("session_id") or ""))
                if not session: raise ValueError("AUTODEV_SESSION_NOT_FOUND")
                self.send_json(resume_planner.decide_resume(session,dict(data.get("scope_status") or {}),bool(data.get("ledger_ok",True))))
                return
            if path == "/api/acceptance/evaluate":
                self.send_json(acceptance_gate.evaluate_acceptance(dict(data.get("checks") or {}),list(data.get("required") or [])))
                return
            if path == "/api/ledger/append":
                self.send_json(run_ledger.append_entry(str(data.get("session_id") or ""),str(data.get("stage") or ""),str(data.get("status") or ""),dict(data.get("payload") or {})))
                return
            if path == "/api/autodev/cycle/prepare":
                models=list(data.get("models") or []) or ollama_models()
                self.send_json(autodev_cycle.prepare_cycle(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),list(data.get("constraints") or []),int(data.get("max_steps") or 4),models))
                return
            if path == "/api/autodev/cycle/run":
                models=list(data.get("models") or []) or ollama_models()
                result=autodev_cycle.execute_bounded_cycle(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),list(data.get("constraints") or []),int(data.get("max_steps") or 4),models)
                self.send_json(result,200 if result.get("ok") else 422)
                return
            if path == "/api/requirements/build":
                self.send_json(requirements_spec.build_requirements(str(data.get("goal") or ""),list(data.get("requirements") or []),list(data.get("acceptance_criteria") or []),list(data.get("constraints") or [])))
                return
            if path == "/api/changes/budget":
                self.send_json(change_budget.evaluate_change_budget(list(data.get("changes") or []),dict(data.get("limits") or {})))
                return
            if path == "/api/context/freshness":
                self.send_json(context_freshness.check_context_freshness(str(data.get("workspace") or ""),dict(data.get("captured_snapshot") or {}),list(data.get("allowed_changed_paths") or []),int(data.get("max_files") or 1000)))
                return
            if path == "/api/retry/decide":
                self.send_json(retry_policy.decide_retry(int(data.get("attempt") or 1),str(data.get("failure_category") or "unknown"),int(data.get("max_attempts") or 3),int(data.get("consecutive_failures") or 1)))
                return
            if path == "/api/repair/verify":
                self.send_json(repair_verifier.verify_repair(dict(data.get("before_failure") or {}),dict(data.get("after_test") or {}),list(data.get("regressions") or []),dict(data.get("budget") or {}) if data.get("budget") is not None else None,dict(data.get("context") or {}) if data.get("context") is not None else None))
                return
            if path == "/api/tasks/next":
                self.send_json(dependency_executor.plan_next_tasks(list(data.get("tasks") or []),dict(data.get("states") or {}),int(data.get("max_parallel") or 1)))
                return
            if path == "/api/completion/evaluate":
                self.send_json(completion_evidence.evaluate_completion(dict(data.get("requirements") or {}),dict(data.get("evidence") or {}),dict(data.get("ledger") or {}) if data.get("ledger") is not None else None))
                return
            if path == "/api/regressions/plan":
                self.send_json(regression_planner.plan_regressions(str(data.get("workspace") or ""),list(data.get("changed_files") or []),list(data.get("historical_failures") or [])))
                return
            if path == "/api/releases/confidence":
                self.send_json(release_confidence.score_release_confidence(dict(data.get("signals") or {}),list(data.get("required") or []) or None))
                return
            if path == "/api/autodev/self-heal/prepare":
                models=list(data.get("models") or []) or ollama_models()
                self.send_json(self_heal_controller.prepare_self_heal(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),list(data.get("requirements") or []),list(data.get("acceptance_criteria") or []),list(data.get("constraints") or []),int(data.get("max_steps") or 4),models))
                return
            if path == "/api/autodev/self-heal/run":
                models=list(data.get("models") or []) or ollama_models()
                result=self_heal_controller.execute_passing_self_heal(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),list(data.get("constraints") or []),int(data.get("max_steps") or 2),models)
                self.send_json(result,200 if result.get("ok") else 422)
                return
            if path == "/api/work-plan/build":
                self.send_json(work_plan.build_work_plan(str(data.get("goal") or ""),list(data.get("tasks") or []),list(data.get("requirements") or []),int(data.get("max_tasks") or 12)))
                return
            if path == "/api/recovery/interruption":
                self.send_json(interruption_recovery.decide_interruption_recovery(dict(data.get("session") or {}),dict(data.get("ledger") or {}),dict(data.get("scope") or {}),str(data.get("current_snapshot_sha256") or ""),dict(data.get("checkpoint") or {}) if data.get("checkpoint") else None))
                return
            if path == "/api/dependencies/state":
                self.send_json(dependency_state.evaluate_dependency_state(list(data.get("tasks") or [])))
                return
            if path == "/api/confidence/track":
                self.send_json(confidence_tracker.track_confidence(dict(data.get("signals") or {}),list(data.get("critical") or []) or None,float(data.get("threshold") or 0.95)))
                return
            if path == "/api/failures/stale":
                self.send_json(stale_failure.classify_failure_freshness(dict(data.get("failure") or {}),str(data.get("current_snapshot_sha256") or ""),list(data.get("observations") or [])))
                return
            if path == "/api/parallelism/advise":
                self.send_json(parallelism_advisor.advise_parallelism(list(data.get("tasks") or []),int(data.get("max_parallel") or 2)))
                return
            if path == "/api/checkpoints/cadence":
                self.send_json(checkpoint_cadence.checkpoint_decision(int(data.get("cycles_since") or 0),int(data.get("accepted_changes") or 0),float(data.get("minutes_since") or 0),bool(data.get("tests_passed",False)),bool(data.get("final_acceptance",False)),int(data.get("max_cycles") or 2),int(data.get("max_changes") or 3),float(data.get("max_minutes") or 30)))
                return
            if path == "/api/regressions/memory":
                if data.get("project_id") is not None: self.send_json(regression_memory.project_regression_memory(int(data.get("project_id") or 0),int(data.get("limit") or 200)))
                else: self.send_json(regression_memory.summarize_regression_memory(list(data.get("observations") or [])))
                return
            if path == "/api/completion/proof":
                self.send_json(completion_proof.build_completion_proof(dict(data.get("requirements") or {}),dict(data.get("confidence") or {}),dict(data.get("ledger") or {}),dict(data.get("database") or {}),bool(data.get("history_preserved",True)),bool(data.get("acceptance",True)),int(data.get("unresolved_critical") or 0)))
                return
            if path == "/api/autodev/supervisor/prepare":
                runtime=dict(data.get("runtime") or {"ok":True,"build":BUILD}); database=dict(data.get("database") or db.status())
                self.send_json(development_supervisor.prepare_supervisor_run(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),runtime,database,str(data.get("expected_build") or BUILD),str(data.get("manifest_build") or BUILD),int(data.get("max_cycles") or 2),list(data.get("tasks") or []),bool(data.get("persist",True))))
                return
            if path == "/api/autodev/supervisor/run":
                models=list(data.get("models") or []) or ollama_models(); runtime=dict(data.get("runtime") or {"ok":True,"build":BUILD}); database=dict(data.get("database") or db.status())
                result=development_supervisor.execute_passing_supervisor_run(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),runtime,database,str(data.get("expected_build") or BUILD),str(data.get("manifest_build") or BUILD),models,int(data.get("max_cycles") or 2),int(data.get("max_steps") or 2))
                self.send_json(result,200 if result.get("ok") else 422)
                return
            if path == "/api/baseline/attest":
                self.send_json(baseline_attestation.attest_baseline(dict(data.get("runtime") or {}),dict(data.get("database") or {}),str(data.get("expected_build") or ""),str(data.get("manifest_build") or ""),bool(data.get("source_manifest_ok",True)),bool(data.get("history_preserved",True))))
                return
            if path == "/api/failures/evidence":
                self.send_json(failure_evidence.build_failure_evidence(data.get("stdout",""),data.get("stderr",""),data.get("error",""),data.get("exit_code"),list(data.get("failed_tests") or []),list(data.get("changed_files") or [])))
                return
            if path == "/api/root-cause/rank":
                self.send_json(root_cause.rank_root_causes(dict(data.get("evidence") or {}),dict(data.get("dependency_graph") or {}),list(data.get("candidate_files") or []),int(data.get("limit") or 5)))
                return
            if path == "/api/reproduction/plan":
                self.send_json(reproduction_planner.plan_reproduction(str(data.get("workspace") or ""),dict(data.get("evidence") or {}),list(data.get("changed_files") or [])))
                return
            if path == "/api/repairs/score":
                self.send_json(repair_candidate.score_candidates(list(data.get("candidates") or [])))
                return
            if path == "/api/tests/observation":
                self.send_json(flake_detector.record_and_classify(int(data.get("project_id") or 0),str(data.get("test_name") or ""),str(data.get("status") or ""),float(data.get("duration_seconds") or 0.0),str(data.get("failure_text") or ""),str(data.get("session_id") or ""),int(data.get("limit") or 20)))
                return
            if path == "/api/tests/flake":
                self.send_json(flake_detector.classify_observations(list(data.get("observations") or []),int(data.get("min_runs") or 3)))
                return
            if path == "/api/checkpoints/select":
                self.send_json(checkpoint_selector.select_checkpoint(list(data.get("checkpoints") or []),str(data.get("expected_build") or ""),bool(data.get("require_verified",True))))
                return
            if path == "/api/execution/budget":
                self.send_json(execution_budget.evaluate_execution_budget(dict(data.get("consumed") or {}),dict(data.get("limits") or {})))
                return
            if path == "/api/autonomy/decide":
                self.send_json(autonomy_policy.decide_autonomy(dict(data.get("change") or {}),str(data.get("mode") or "safe")))
                return
            if path == "/api/autodev/governor/prepare":
                self.send_json(autodev_governor.prepare_governed_run(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),dict(data.get("runtime") or {}),dict(data.get("database") or {}),str(data.get("expected_build") or BUILD),str(data.get("manifest_build") or BUILD),bool(data.get("source_manifest_ok",True)),bool(data.get("history_preserved",True)),dict(data.get("failure") or {}) if data.get("failure") is not None else None,list(data.get("changed_files") or []),list(data.get("checkpoints") or []),dict(data.get("consumed") or {}),dict(data.get("limits") or {}),dict(data.get("change") or {})))
                return
            if path == "/api/autodev/governor/run":
                models=list(data.get("models") or []) or ollama_models()
                runtime=dict(data.get("runtime") or {"ok":True,"build":BUILD}); database=dict(data.get("database") or db.status())
                result=autodev_governor.execute_passing_governed_run(int(data.get("project_id") or 0),str(data.get("workspace") or ""),str(data.get("goal") or ""),runtime,database,str(data.get("expected_build") or BUILD),str(data.get("manifest_build") or BUILD),models,int(data.get("max_steps") or 2))
                self.send_json(result,200 if result.get("ok") else 422)
                return
            if path == "/api/providers/connection-spec":
                self.send_json(connection_spec.normalize_connection(str(data.get("provider") or ""),str(data.get("model") or ""),dict(data.get("settings") or {})))
                return
            if path == "/api/providers/failover":
                self.send_json(provider_failover.choose_provider(list(data.get("candidates") or []),str(data.get("task") or ""),bool(data.get("offline_first",True)),bool(data.get("require_online",False))))
                return
            if path == "/api/providers/budget":
                self.send_json(request_budget.evaluate_request_budget(dict(data.get("consumed") or {}),dict(data.get("limits") or {})))
                return
            if path == "/api/deferred/add":
                self.send_json(offline_queue.enqueue(int(data.get("project_id") or 0),str(data.get("goal") or ""),str(data.get("reason") or "provider_unavailable"),str(data.get("provider") or "")))
                return
            if path == "/api/deferred/update":
                self.send_json(offline_queue.update(int(data.get("id") or 0),str(data.get("status") or "")))
                return
            if path == "/api/db/backup/verify":
                self.send_json(backup_restore.verify_sqlite_backup(str(data.get("path") or "")))
                return
            if path == "/api/db/restore/plan":
                self.send_json(backup_restore.plan_restore(dict(data.get("backup") or {}),str(data.get("target") or "")))
                return
            if path == "/api/projects/export":
                project_id=int(data.get("project_id") or 0); p=db.project(project_id)
                if not p: raise ValueError("PROJECT_NOT_FOUND")
                self.send_json(project_portability.export_project(p,db.list_messages(project_id,10000),db.list_issues(project_id)))
                return
            if path == "/api/projects/import/validate":
                self.send_json(project_portability.validate_import(dict(data.get("payload") or {}),str(data.get("sha256") or "")))
                return
            if path == "/api/diagnostics/bundle":
                self.send_json(diagnostic_bundle.build_bundle(dict(data.get("runtime") or {}),dict(data.get("database") or {}),list(data.get("failures") or []),list(data.get("events") or [])))
                return
            if path == "/api/instance/guard":
                self.send_json(instance_guard.verify_instance(dict(data.get("runtime") or {}),str(data.get("expected_build") or BUILD),str(data.get("expected_project_path") or ""),int(data.get("fixed_port") or DEFAULT_PORT)))
                return
            if path == "/api/schema/guard":
                raw=db.row("SELECT value FROM meta WHERE key='schema_version'") or {}; self.send_json(schema_guard.evaluate_schema(dict(data.get("database") or db.status()),list(data.get("tables") or db.database_tables()),int(data.get("schema_version") or raw.get("value") or 0),list(data.get("required_tables") or []) or None,int(data.get("minimum_version") or 9)))
                return
            if path == "/api/startup/recovery/plan":
                self.send_json(startup_recovery.plan_startup_recovery(dict(data.get("state") or {})))
                return
            if path == "/api/audit/append":
                self.send_json(audit_trail.append(str(data.get("category") or ""),str(data.get("action") or ""),str(data.get("status") or ""),dict(data.get("payload") or {}),int(data.get("project_id")) if data.get("project_id") is not None else None))
                return
            if path == "/api/audit/verify":
                self.send_json(audit_trail.verify())
                return
            if path == "/api/providers/resilience":
                self.send_json(provider_resilience.score_provider(list(data.get("observations") or [])))
                return
            if path == "/api/alpha/user-readiness":
                self.send_json(alpha_user_readiness.evaluate(dict(data.get("signals") or {}),list(data.get("required") or []) or None))
                return
            if path == "/api/safety/matrix":
                self.send_json(safety_matrix.evaluate(dict(data.get("action") or {})))
                return
            if path == "/api/retention/plan":
                self.send_json(retention_policy.plan_retention(list(data.get("records") or []),int(data.get("keep_recent") or 50),bool(data.get("preserve_failed",True))))
                return
            if path == "/api/resources/envelope":
                self.send_json(resource_envelope.recommend(dict(data.get("host") or {}),list(data.get("models") or [])))
                return
            if path == "/api/mission/proof":
                self.send_json(mission_proof.build(str(data.get("goal") or ""),dict(data.get("stages") or {}),dict(data.get("tests") or {}),dict(data.get("database") or {}),bool(data.get("history_preserved",True)),dict(data.get("provider") or {}),dict(data.get("safety") or {})))
                return
            if path == "/api/alpha/release/evaluate":
                evaluation=alpha_release.evaluate(dict(data.get("signals") or {}),list(data.get("required") or []) or None); self.send_json(evaluation)
                return
            if path == "/api/alpha/release/record":
                evaluation=dict(data.get("evaluation") or {}); self.send_json(alpha_release.record(str(data.get("build") or BUILD),evaluation,str(data.get("proof_sha256") or ""),dict(data.get("detail") or {})))
                return
            if path == "/api/connections/test":
                provider = str(data.get("provider") or "").strip().lower()
                if provider == "ollama":
                    models = ollama_models()
                    names = [str(m.get("name") or "") for m in models]
                    requested = str(data.get("model") or "").strip()
                    model = requested if requested in names else (names[0] if names else "")
                    saved = db.save_connection("ollama", bool(names), model, {"base_url":"http://127.0.0.1:11434"}, "PASS" if names else "FAIL", f"models={len(names)}")
                    self.send_json({"ok": bool(names), "connection": saved, "models": models}, 200 if names else 503)
                    return
                if provider == "openai-compatible":
                    spec=connection_spec.normalize_connection(provider,str(data.get("model") or ""),dict(data.get("settings") or {})); result=external_provider.test_connection(spec["settings"],spec["model"]); saved=db.save_connection(provider,bool(result.get("ok")),str(result.get("model") or ""),spec["settings"],"PASS" if result.get("ok") else "FAIL",f"models={int(result.get('model_count') or 0)}")
                    self.send_json({"ok":bool(result.get("ok")),"connection":saved,"models":result.get("models",[]),"secret_exposed":False},200 if result.get("ok") else 503)
                    return
                raise ValueError("CONNECTION_PROVIDER_NOT_SUPPORTED")
            if path == "/api/db/backup":
                destination = str(data.get("destination_dir") or (DATA_ROOT / "backups"))
                self.send_json({"ok": True, "backup": db.backup_database(destination)})
                return
            if path == "/api/project/open-vscode":
                self.send_json(desktop_tools.open_vscode(str(data.get("workspace") or ""), bool(data.get("dry_run", True))))
                return
            if path == "/api/autodev/queue/add":
                item = db.enqueue_autodev_task(int(data.get("project_id") or 0), str(data.get("goal") or ""), str(data.get("test_command") or ""), int(data.get("max_steps") or 4))
                self.send_json({"ok": True, "item": item})
                return
            if path == "/api/autodev/queue/update":
                item = db.update_autodev_queue(int(data.get("id") or 0), str(data.get("status") or ""), str(data.get("run_id") or ""))
                self.send_json({"ok": True, "item": item})
                return
            if path == "/api/releases/checkpoint":
                source = str(data.get("source") or "")
                checkpoint_root = str(data.get("checkpoint_root") or (DATA_ROOT / "release-checkpoints"))
                info = release_manager.create_checkpoint(source, checkpoint_root, str(data.get("label") or "checkpoint"), bool(data.get("dry_run", False)))
                self.send_json({"ok": True, "checkpoint": info})
                return
            if path == "/api/projects/create":
                project = db.create_project(str(data.get("name") or ""), str(data.get("kind") or "user"), bool(data.get("archived", False)))
                self.send_json({"ok": True, "project": project})
                return
            if path == "/api/projects/delete":
                db.delete_project(int(data.get("project_id") or 0))
                self.send_json({"ok": True})
                return
            if path == "/api/terminal/analyze":
                result = analyze_command(str(data.get("command") or ""))
                self.send_json({"ok": True, "analysis": result.__dict__})
                return
            if path == "/api/templates/run":
                result = run_template(str(data.get("template_id") or ""), model=str(data.get("model") or "qwen2.5-coder:1.5b-instruct"), launch=bool(data.get("launch", True)))
                self.send_json(result, 200 if result.get("ok") else 422)
                return
            if path == "/api/project-loop/configure":
                settings = configure_project_loop(
                    project_id=int(data.get("project_id") or 0),
                    workspace=str(data.get("workspace") or ""),
                    goal=str(data.get("goal") or ""),
                    test_command=str(data.get("test_command") or ""),
                    max_steps=int(data.get("max_steps") or 4),
                    auto_model=bool(data.get("auto_model", True)),
                    model=str(data.get("model") or ""),
                )
                self.send_json({"ok": True, "settings": settings})
                return
            if path == "/api/project-loop/run":
                result = run_project_loop(
                    project_id=int(data.get("project_id") or 0),
                    workspace=str(data.get("workspace") or ""),
                    goal=str(data.get("goal") or ""),
                    test_command=str(data.get("test_command") or ""),
                    max_steps=int(data["max_steps"]) if data.get("max_steps") is not None else None,
                    auto_model=bool(data["auto_model"]) if data.get("auto_model") is not None else None,
                    model=str(data.get("model") or ""),
                )
                self.send_json({"ok": True, "run": result})
                return
            if path == "/api/chat":
                result = run_chat(
                    project_id=int(data.get("project_id") or 0),
                    message=str(data.get("message") or ""),
                    provider=str(data.get("provider") or "ollama"),
                    model=str(data.get("model") or ""),
                    request_id=str(data.get("request_id") or "").strip() or None,
                )
                self.send_json(result, 200 if result.get("ok") else 422)
                return
            self.send_json({"ok": False, "error": "NOT_FOUND"}, 404)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, 400)
        except ProviderError as exc:
            self.send_json({"ok": False, "error": str(exc)}, 502)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 500)


def main() -> int:
    port = DEFAULT_PORT
    args = list(sys.argv[1:])
    if "--port" in args:
        idx = args.index("--port")
        port = int(args[idx + 1])
    db.init_db()
    recovered = db.recover_incomplete_requests()
    recovered_loop_edits = recover_interrupted_edits()
    recovered_loops = db.recover_incomplete_loops()
    ensure_session_token()
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"DMT_CORE_READY http://{HOST}:{port} BUILD={BUILD} PID={os.getpid()} RECOVERED_REQUESTS={recovered} RECOVERED_LOOP_EDITS={len(recovered_loop_edits)} RECOVERED_LOOPS={recovered_loops}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
