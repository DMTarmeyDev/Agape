from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import importlib.util
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid

import research_router
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BUILD = "AGAPE-UNIFIED-R4.7-TARGETED-VALIDATION-REPAIR"
DEFAULT_PORT = 8852
CORE_URL = os.environ.get("AGAPE_CORE_URL", "http://127.0.0.1:8797").rstrip("/")
WORK_URL = os.environ.get("AGAPE_WORK_URL", "http://127.0.0.1:8820").rstrip("/")
DOC_URL = os.environ.get("AGAPE_DOC_URL", "http://127.0.0.1:8800").rstrip("/")
ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
TEMPLATE_FILE = ROOT / "templates" / "templates.json"
DATA_ROOT = Path(os.environ.get("AGAPE_UNIFIED_DATA", str(Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "Agape-Unified-R2.4" / "data"))).resolve()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
JOBS_FILE = DATA_ROOT / "jobs.json"
INTAKES_FILE = DATA_ROOT / "intakes.json"
SETTINGS_FILE = DATA_ROOT / "settings.json"
PREVIOUS_SETTINGS_FILE = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "Agape-Unified-R2.3" / "data" / "settings.json"

ROUTER_IDS = {"agape", "litellm"}
DEFAULT_SETTINGS = {
    "setup_complete": False,
    "router": "agape",
    "ui_theme": "forest",
    "gold_reviewer_count": 3,
    "gold_reviewer_ids": [],
    "gold_lead_reviewer": "auto",
}

LOCK = threading.RLock()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)



def load_settings() -> dict[str, Any]:
    with LOCK:
        if not SETTINGS_FILE.exists() and PREVIOUS_SETTINGS_FILE.exists():
            previous = read_json_file(PREVIOUS_SETTINGS_FILE, {})
            if isinstance(previous, dict):
                migrated = dict(DEFAULT_SETTINGS)
                for key in DEFAULT_SETTINGS:
                    if key in previous:
                        migrated[key] = previous[key]
                atomic_json(SETTINGS_FILE, migrated)
        raw = read_json_file(SETTINGS_FILE, {})
        out = dict(DEFAULT_SETTINGS)
        if isinstance(raw, dict):
            out.update({k: raw[k] for k in DEFAULT_SETTINGS if k in raw})
        if str(out.get("router") or "agape") not in ROUTER_IDS:
            out["router"] = "agape"
        out["setup_complete"] = bool(out.get("setup_complete"))
        try:
            out["gold_reviewer_count"] = max(2, min(10, int(out.get("gold_reviewer_count") or 3)))
        except Exception:
            out["gold_reviewer_count"] = 3
        ids = out.get("gold_reviewer_ids") if isinstance(out.get("gold_reviewer_ids"), list) else []
        out["gold_reviewer_ids"] = list(dict.fromkeys(str(x).strip().lower() for x in ids if str(x).strip()))[:10]
        out["gold_lead_reviewer"] = str(out.get("gold_lead_reviewer") or "auto").strip().lower() or "auto"
        return out


def save_settings(value: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    if "router" in value:
        router = str(value.get("router") or "").strip().lower()
        if router not in ROUTER_IDS:
            raise ValueError("UNSUPPORTED_ROUTER=" + router)
        if router == "litellm":
            status = router_status()
            lite = next((x for x in status["options"] if x["id"] == "litellm"), {})
            if not lite.get("ready"):
                raise ValueError("LITELLM_ROUTER_NOT_READY: install/test LiteLLM and make at least one model available first")
        current["router"] = router
    if "setup_complete" in value:
        current["setup_complete"] = bool(value.get("setup_complete"))
    if "ui_theme" in value:
        theme = str(value.get("ui_theme") or "forest").strip().lower()
        if theme in {"forest", "navy", "sand", "dark"}:
            current["ui_theme"] = theme
    if "gold_reviewer_count" in value:
        try:
            current["gold_reviewer_count"] = max(2, min(10, int(value.get("gold_reviewer_count") or 10)))
        except Exception:
            raise ValueError("GOLD_REVIEWER_COUNT_MUST_BE_2_TO_10")
    if "gold_reviewer_ids" in value:
        raw_ids = value.get("gold_reviewer_ids")
        if raw_ids is None:
            raw_ids = []
        if not isinstance(raw_ids, list):
            raise ValueError("GOLD_REVIEWER_IDS_MUST_BE_LIST")
        current["gold_reviewer_ids"] = list(dict.fromkeys(str(x).strip().lower() for x in raw_ids if str(x).strip()))[:10]
    if "gold_lead_reviewer" in value:
        current["gold_lead_reviewer"] = str(value.get("gold_lead_reviewer") or "auto").strip().lower() or "auto"
    with LOCK:
        atomic_json(SETTINGS_FILE, current)
    return current


def ollama_model_names() -> list[str]:
    status, payload = http_json("GET", "http://127.0.0.1:11434/api/tags", timeout=3)
    if status != 200 or not isinstance(payload, dict):
        return []
    names = []
    for row in payload.get("models") or []:
        if isinstance(row, dict) and row.get("name"):
            names.append(str(row["name"]))
    return names


def _env_model(env_name: str, prefix: str, provider: str) -> dict[str, Any] | None:
    model = str(os.environ.get(env_name) or "").strip()
    if not model:
        return None
    actual = model if model.startswith(prefix + "/") else prefix + "/" + model
    return {"actual_model": actual, "document_provider": provider, "document_model": model.split("/", 1)[-1], "source": env_name}


def litellm_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Local Ollama is automatically discoverable and needs no API secret.
    local = ollama_model_names()
    preferred = ["qwen2.5-coder:1.5b-instruct", "qwen2.5-coder:7b"]
    ordered = [x for x in preferred if x in local] + [x for x in local if x not in preferred]
    for name in ordered[:4]:
        rows.append({
            "actual_model": "ollama/" + name,
            "document_provider": "ollama",
            "document_model": name,
            "api_base": "http://127.0.0.1:11434",
            "source": "ollama",
        })
    # Cloud models are intentionally explicit: a key alone is not enough to guess a model name.
    specs = [
        ("AGAPE_LITELLM_OPENAI_MODEL", "openai", "chatgpt"),
        ("AGAPE_LITELLM_ANTHROPIC_MODEL", "anthropic", "claude"),
        ("AGAPE_LITELLM_GEMINI_MODEL", "gemini", "gemini"),
        ("AGAPE_LITELLM_OPENROUTER_MODEL", "openrouter", "openrouter"),
        ("AGAPE_LITELLM_GROQ_MODEL", "groq", "groq"),
        ("AGAPE_LITELLM_XAI_MODEL", "xai", "xai"),
    ]
    for env_name, prefix, provider in specs:
        row = _env_model(env_name, prefix, provider)
        if row:
            rows.append(row)
    return rows


def router_status() -> dict[str, Any]:
    settings = load_settings()
    lite_installed = importlib.util.find_spec("litellm") is not None
    candidates = litellm_candidates() if lite_installed else []
    services = get_services()
    agape_ready = bool(services.get("core", {}).get("ok") and services.get("document", {}).get("ok"))
    lite_ready = bool(lite_installed and candidates)
    return {
        "ok": True,
        "selected": settings["router"],
        "setup_complete": settings["setup_complete"],
        "options": [
            {
                "id": "agape",
                "name": "Agape Router",
                "recommended": True,
                "ready": agape_ready,
                "summary": "Project-aware Agape routing. Uses project context, task type, complexity and existing Agape model outcomes.",
                "detail": "Default. Keeps Core/Document Studio routing and local-first project logic.",
            },
            {
                "id": "litellm",
                "name": "LiteLLM Router",
                "recommended": False,
                "ready": lite_ready,
                "installed": lite_installed,
                "candidate_count": len(candidates),
                "candidates": [{k: v for k, v in x.items() if k not in {"api_key"}} for x in candidates[:8]],
                "summary": "Optional provider/deployment router using the LiteLLM Python SDK.",
                "detail": "LiteLLM chooses a concrete model/deployment; Agape still owns project workflow, tools, safety and document execution.",
            },
        ],
    }


def install_litellm() -> dict[str, Any]:
    if importlib.util.find_spec("litellm") is not None:
        return {"ok": True, "already_installed": True, "status": router_status()}
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "litellm"],
        capture_output=True, text=True, timeout=420,
    )
    if proc.returncode != 0:
        raise RuntimeError("LITELLM_INSTALL_FAILED: " + (proc.stderr or proc.stdout or "unknown error")[-1800:])
    return {"ok": True, "already_installed": False, "status": router_status()}


def _litellm_model_list() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = []
    by_id: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(litellm_candidates()):
        mid = f"agape-{i}-{uuid.uuid5(uuid.NAMESPACE_URL, item['actual_model']).hex[:10]}"
        params = {"model": item["actual_model"]}
        if item.get("api_base"):
            params["api_base"] = item["api_base"]
        row = {"model_name": "agape-auto", "litellm_params": params, "model_info": {"id": mid}}
        rows.append(row)
        by_id[mid] = item
    return rows, by_id


def litellm_route_decision(task: str = "general", execute_test: bool = False) -> dict[str, Any]:
    if importlib.util.find_spec("litellm") is None:
        raise RuntimeError("LITELLM_NOT_INSTALLED")
    model_list, by_id = _litellm_model_list()
    if not model_list:
        raise RuntimeError("LITELLM_NO_CONFIGURED_MODELS: Ollama or explicit AGAPE_LITELLM_*_MODEL configuration is required")
    from litellm import Router  # type: ignore
    router = Router(
        model_list=model_list,
        routing_strategy="cost-based-routing",
        enable_pre_call_checks=True,
        allowed_fails=2,
        cooldown_time=30,
    )
    messages = [
        {"role": "system", "content": "Agape router probe. Select a healthy deployment for the requested task."},
        {"role": "user", "content": f"Task class: {task}. Reply only OK."},
    ]
    deployment = None
    try:
        deployment = router.get_available_deployment(model="agape-auto", messages=messages)
    except Exception:
        deployment = None
    selected_id = str(((deployment or {}).get("model_info") or {}).get("id") or "") if isinstance(deployment, dict) else ""
    selected = by_id.get(selected_id)
    test_response = None
    if execute_test:
        response = router.completion(model="agape-auto", messages=messages, max_tokens=4, timeout=45)
        hidden = getattr(response, "_hidden_params", {}) or {}
        response_id = str(hidden.get("model_id") or "")
        selected = by_id.get(response_id) or selected
        test_response = str(getattr(getattr(response, "choices", [None])[0], "message", None).content if getattr(response, "choices", None) else "")[:80]
    if not selected:
        # One-deployment or router-version compatibility fallback. This is still a LiteLLM-configured deployment.
        selected = litellm_candidates()[0]
    return {
        "router": "litellm",
        "task": task,
        "provider": selected.get("document_provider"),
        "model": selected.get("document_model"),
        "litellm_model": selected.get("actual_model"),
        "source": selected.get("source"),
        "strategy": "cost-based-routing",
        "test_response": test_response,
    }


def router_decision(task: str = "general", execute_test: bool = False) -> dict[str, Any]:
    selected = str(load_settings().get("router") or "agape")
    if selected == "litellm":
        return litellm_route_decision(task, execute_test=execute_test)
    return {"router": "agape", "task": task, "provider": "auto", "model": "auto", "strategy": "project-aware-agape"}


def test_router(router_id: str | None = None) -> dict[str, Any]:
    chosen = str(router_id or load_settings().get("router") or "agape").lower()
    if chosen == "litellm":
        decision = litellm_route_decision("general", execute_test=True)
        return {"ok": True, "router": "litellm", "decision": decision}
    if chosen != "agape":
        raise ValueError("UNSUPPORTED_ROUTER=" + chosen)
    services = get_services()
    if not services["core"]["ok"] or not services["document"]["ok"]:
        raise RuntimeError("AGAPE_ROUTER_DEPENDENCY_UNAVAILABLE")
    evidence: dict[str, Any] = {"services": {k: bool(v.get("ok")) for k, v in services.items()}}
    try:
        projects = [x for x in get_projects() if not bool(x.get("archived")) and str(x.get("kind") or "user") == "user"]
        if projects:
            pid = int(projects[0]["id"])
            status, rec = core_get(f"/api/models/recommend?project_id={pid}&task=router%20self%20test", timeout=20)
            evidence["project_recommend"] = rec
            evidence["project_recommend_http"] = status
    except Exception as exc:
        evidence["project_recommend_warning"] = str(exc)
    return {"ok": True, "router": "agape", "decision": router_decision("general"), "evidence": evidence}

def load_jobs() -> list[dict[str, Any]]:
    with LOCK:
        rows = read_json_file(JOBS_FILE, [])
        return rows if isinstance(rows, list) else []


def save_jobs(rows: list[dict[str, Any]]) -> None:
    with LOCK:
        atomic_json(JOBS_FILE, rows[-300:])


def load_intakes() -> list[dict[str, Any]]:
    with LOCK:
        rows = read_json_file(INTAKES_FILE, [])
        return rows if isinstance(rows, list) else []


def save_intakes(rows: list[dict[str, Any]]) -> None:
    with LOCK:
        atomic_json(INTAKES_FILE, rows[-200:])


def get_intake(intake_id: str) -> dict[str, Any] | None:
    for row in reversed(load_intakes()):
        if str(row.get("id")) == str(intake_id):
            return row
    return None


def save_intake(row: dict[str, Any]) -> dict[str, Any]:
    rows = load_intakes()
    rows.append(row)
    save_intakes(rows)
    return row


def get_job(job_id: str) -> dict[str, Any] | None:
    for row in reversed(load_jobs()):
        if str(row.get("id")) == str(job_id):
            return row
    return None


def update_job(job_id: str, **updates: Any) -> dict[str, Any]:
    with LOCK:
        rows = load_jobs()
        found = None
        for row in rows:
            if str(row.get("id")) == str(job_id):
                row.update(updates)
                row["updated_at"] = now_iso()
                found = row
                break
        if found is None:
            raise KeyError(job_id)
        save_jobs(rows)
        return dict(found)


def _progress_value(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except Exception:
        return 0.0


def update_progress(job_id: str, value: Any) -> float:
    """Store overall progress monotonically; nested workers may reset their local percent."""
    with LOCK:
        rows = load_jobs()
        for row in rows:
            if str(row.get("id")) == str(job_id):
                old = _progress_value(row.get("progress"))
                new = max(old, _progress_value(value))
                row["progress"] = round(new, 1)
                row["updated_at"] = now_iso()
                save_jobs(rows)
                return row["progress"]
        # Some compatibility helpers/tests execute a worker without a persisted parent job.
        # Progress is telemetry only and must never block the real work.
        return _progress_value(value)


def add_event(job_id: str, stage: str, message: str, status: str = "INFO", detail: Any = None, progress: Any = None) -> None:
    with LOCK:
        rows = load_jobs()
        for row in rows:
            if str(row.get("id")) == str(job_id):
                events = row.setdefault("events", [])
                events.append({"ts": now_iso(), "stage": stage, "status": status, "message": message, "detail": detail})
                row["stage"] = stage
                row["message"] = message
                if progress is not None:
                    row["progress"] = round(max(_progress_value(row.get("progress")), _progress_value(progress)), 1)
                row["updated_at"] = now_iso()
                save_jobs(rows)
                return
        raise KeyError(job_id)


def http_json(method: str, url: str, body: Any = None, timeout: int = 10, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw.strip() else {}
            except Exception:
                payload = {"raw": raw}
            return int(response.status), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except Exception:
            payload = {"raw": raw}
        payload.setdefault("http_status", int(exc.code))
        return int(exc.code), payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def get_core_version() -> dict[str, Any]:
    status, payload = http_json("GET", CORE_URL + "/api/version", timeout=4)
    if status != 200 or not isinstance(payload, dict):
        return {"ok": False, "error": payload.get("error", "Core unavailable") if isinstance(payload, dict) else "Core unavailable"}
    out = dict(payload)
    out["ok"] = True
    return out


def core_headers() -> dict[str, str]:
    version = get_core_version()
    data_path = str(version.get("data_path") or "").strip()
    if data_path:
        token_path = Path(data_path) / "security" / "local-session-token.txt"
        try:
            token = token_path.read_text(encoding="utf-8").strip()
            if token:
                return {"X-DMT-Session": token}
        except Exception:
            pass
    return {}


def core_get(path: str, timeout: int = 10) -> tuple[int, Any]:
    return http_json("GET", CORE_URL + path, timeout=timeout, headers=core_headers())


def core_post(path: str, body: Any, timeout: int = 300) -> tuple[int, Any]:
    return http_json("POST", CORE_URL + path, body=body, timeout=timeout, headers=core_headers())


def doc_get(path: str, timeout: int = 15) -> tuple[int, Any]:
    return http_json("GET", DOC_URL + path, timeout=timeout)


def doc_post(path: str, body: Any, timeout: int = 1200) -> tuple[int, Any]:
    return http_json("POST", DOC_URL + path, body=body, timeout=timeout)


def connected_quality_providers(force: bool = False) -> list[dict[str, Any]]:
    status, payload = doc_get('/api/provider-connections/status' + ('?force=1' if force else ''), timeout=20)
    if status != 200 or not isinstance(payload, dict):
        return []
    rows = [dict(x) for x in (payload.get('providers') or []) if isinstance(x, dict) and bool(x.get('connected'))]
    rows.sort(key=lambda x: float(x.get('review_score') or 0), reverse=True)
    return rows


def quality_status() -> dict[str, Any]:
    rows = connected_quality_providers(False)
    settings = load_settings()
    return {
        'ok': True,
        'connected_count': len(rows),
        'gold_ready': len(rows) >= 2,
        'max_reviewers': 10,
        'minimum_reviewers': 2,
        'default_reviewer_count': int(settings.get('gold_reviewer_count') or 10),
        'default_reviewer_ids': list(settings.get('gold_reviewer_ids') or []),
        'default_lead_reviewer': str(settings.get('gold_lead_reviewer') or 'auto'),
        'providers': [
            {
                'id': x.get('id'), 'name': x.get('name'), 'recommended_model': x.get('recommended_model'),
                'review_score': x.get('review_score'), 'connected': True
            } for x in rows[:10]
        ],
        'gold_policy': 'Choose 2-10 connected reviewer/model pairs. Automatic mode selects the strongest connected providers for this review; custom mode uses the exact selected providers. One successful reviewer acts as lead synthesis.'
    }


def _normalise_reviewer_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(x).strip().lower() for x in value if str(x).strip()))[:10]


def choose_gold_review_team(providers: list[dict[str, Any]], job: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    try:
        requested_count = max(2, min(10, int(job.get('reviewer_count') or settings.get('gold_reviewer_count') or 10)))
    except Exception:
        requested_count = 10
    requested_ids = _normalise_reviewer_ids(job.get('reviewer_ids')) if 'reviewer_ids' in job else _normalise_reviewer_ids(settings.get('gold_reviewer_ids'))
    available = {str(x.get('id') or '').strip().lower(): x for x in providers if str(x.get('id') or '').strip()}
    mode = 'custom' if requested_ids else 'automatic'
    if requested_ids:
        reviewer_ids = [x for x in requested_ids if x in available][:10]
        unavailable = [x for x in requested_ids if x not in available]
        requested_count = len(requested_ids)
    else:
        reviewer_ids = [str(x.get('id')).strip().lower() for x in providers[:requested_count] if str(x.get('id') or '').strip()]
        unavailable = []
    # Reviewer availability is checked again at runtime by Document Studio. Do not fail an
    # already-created document merely because fewer than two configured reviewers are ready.
    # The review engine can add healthy local Ollama or return the validated first document
    # with a review-unavailable diagnostic.
    lead = str(job.get('lead_reviewer') or settings.get('gold_lead_reviewer') or 'auto').strip().lower() or 'auto'
    if lead != 'auto' and lead not in reviewer_ids:
        lead = 'auto'
    return {
        'mode': mode,
        'requested_count': requested_count,
        'used_count': len(reviewer_ids),
        'available_count': len(providers),
        'reviewers': reviewer_ids,
        'unavailable_selected': unavailable,
        'lead_reviewer': lead,
    }


def get_services() -> dict[str, Any]:
    core_status, core = http_json("GET", CORE_URL + "/api/version", timeout=3)
    work_status, work = http_json("GET", WORK_URL + "/api/health", timeout=3)
    doc_status, doc = http_json("GET", DOC_URL + "/api/health", timeout=3)
    return {
        "core": {"ok": core_status == 200, "status": core_status, "detail": core},
        "work": {"ok": work_status == 200 and bool((work or {}).get("ok", True)), "status": work_status, "detail": work},
        "document": {"ok": doc_status == 200 and bool((doc or {}).get("ok", True)), "status": doc_status, "detail": doc},
    }


def get_projects() -> list[dict[str, Any]]:
    status, payload = core_get("/api/projects?scope=all", timeout=10)
    if status != 200:
        raise RuntimeError("PROJECT_API_FAILED: " + json.dumps(payload, ensure_ascii=False)[:600])
    if isinstance(payload, dict):
        rows = payload.get("projects") or []
    else:
        rows = payload if isinstance(payload, list) else []
    return [dict(x) for x in rows if isinstance(x, dict)]


def project_by_id(project_id: int) -> dict[str, Any] | None:
    for project in get_projects():
        try:
            if int(project.get("id")) == int(project_id):
                return project
        except Exception:
            continue
    return None


def safe_core_get(path: str) -> Any:
    status, payload = core_get(path, timeout=15)
    if status == 200:
        return payload
    return {"ok": False, "http_status": status, "error": payload}


def get_project_bundle(project_id: int) -> dict[str, Any]:
    project = project_by_id(project_id)
    if not project:
        raise RuntimeError("PROJECT_NOT_FOUND")
    quoted = urllib.parse.quote(str(project_id))
    template = safe_core_get(f"/api/project-template/status?project_id={quoted}")
    loop_settings = safe_core_get(f"/api/project-loop/settings?project_id={quoted}")
    loop_runs = safe_core_get(f"/api/project-loop/runs?project_id={quoted}")
    messages = safe_core_get(f"/api/messages?project_id={quoted}")
    return {"project": project, "template": template, "loop_settings": loop_settings, "loop_runs": loop_runs, "messages": messages}


def flatten_text(value: Any, depth: int = 0) -> list[str]:
    if depth > 8:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if len(text) >= 2 else []
    if isinstance(value, dict):
        priority = [
            "system_instruction", "plain_text", "instructions", "instruction", "goal", "description", "purpose",
            "project_brief", "content", "text", "summary", "notes", "context"
        ]
        found: list[str] = []
        used = set()
        for key in priority:
            if key in value:
                used.add(key)
                found.extend(flatten_text(value.get(key), depth + 1))
        for key, item in value.items():
            if key not in used and key not in {"id", "created_at", "updated_at", "status", "ok", "hash"}:
                found.extend(flatten_text(item, depth + 1))
        return found
    if isinstance(value, list):
        out: list[str] = []
        for item in value[:100]:
            out.extend(flatten_text(item, depth + 1))
        return out
    return []


def unique_text(parts: list[str], max_chars: int = 100000) -> str:
    out: list[str] = []
    seen = set()
    size = 0
    for part in parts:
        p = " ".join(str(part).split()) if "\n" not in str(part) else str(part).strip()
        key = p[:500]
        if not p or key in seen:
            continue
        seen.add(key)
        if size + len(p) + 2 > max_chars:
            break
        out.append(p)
        size += len(p) + 2
    return "\n\n".join(out)


def load_templates() -> list[dict[str, Any]]:
    data = read_json_file(TEMPLATE_FILE, [])
    return data if isinstance(data, list) else []


def template_by_id(template_id: str) -> dict[str, Any]:
    for row in load_templates():
        if row.get("id") == template_id:
            return row
    for row in load_templates():
        if row.get("id") == "auto":
            return row
    return {"id": "auto", "label": "Auto", "route": "auto"}


def determine_route(project: dict[str, Any], bundle: dict[str, Any], instruction: str, template: dict[str, Any], project_info: str = "") -> tuple[str, str]:
    explicit = str(template.get("route") or "auto")
    if explicit in {"document", "project_loop"}:
        return explicit, "Selected template"

    text = " ".join([
        str(project.get("name") or ""),
        str(project.get("description") or ""),
        str(instruction or ""),
        str(project_info or ""),
        unique_text(flatten_text(bundle.get("template")), 12000),
    ]).lower()

    doc_words = (
        "business plan", "business proposal", "proposal", "quotation", "quote", "document", "report", "letter",
        "presentation", "brochure", "commercial plan", "strategy document", "write a plan", "create a plan"
    )
    if any(word in text for word in doc_words):
        return "document", "Document/business content detected"

    settings = bundle.get("loop_settings") if isinstance(bundle.get("loop_settings"), dict) else {}
    saved = settings.get("settings") if isinstance(settings, dict) else {}
    saved = saved if isinstance(saved, dict) else {}
    workspace = str(saved.get("workspace") or "").strip()
    if workspace:
        return "project_loop", "Saved executable workspace found"

    return "blocked", "No document intent and no saved executable workspace"


def map_document_type(project: dict[str, Any], instruction: str, template: dict[str, Any]) -> str:
    explicit = str(template.get("doc_type") or "").strip()
    if explicit:
        return explicit
    text = (str(project.get("name") or "") + " " + str(instruction or "")).lower()
    if "quotation" in text or "quote" in text:
        return "Quotation"
    if "project plan" in text:
        return "Project Plan"
    if "report" in text:
        return "Business Report"
    return "Business Proposal"


def ai_fill_to_structured_form(ai_fill: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for field_id, row in (ai_fill.get('fields') or {}).items():
        if isinstance(row, dict):
            value = str(row.get('value') or '').strip()
        else:
            value = str(row or '').strip()
        if value:
            out[str(field_id)] = value
    return out


def intake_field_stats(ai_fill: dict[str, Any]) -> tuple[int, int]:
    nonempty = 0
    none_count = 0
    fields = ai_fill.get("fields") if isinstance(ai_fill, dict) else {}
    for row in fields.values() if isinstance(fields, dict) else []:
        value = str((row or {}).get("value") if isinstance(row, dict) else row or "").strip()
        if value:
            nonempty += 1
        if not value or value.lower() == "none":
            none_count += 1
    return nonempty, none_count


PUBLIC_RESEARCHABLE_FIELDS = {
    "organisation","industry","geography","product_service","problem_need","target_audience",
    "value_proposition","budget_pricing","success_metrics","competitors_alternatives","constraints","research_focus",
}


def _researchable_field(field_id: str) -> bool:
    return str(field_id or "") in PUBLIC_RESEARCHABLE_FIELDS


def public_research_opportunities(intake: dict[str,Any], ai_fill: dict[str,Any] | None = None, include_plan: bool = True) -> list[dict[str,Any]]:
    ai_fill=ai_fill if isinstance(ai_fill,dict) else (intake.get("ai_fill") if isinstance(intake.get("ai_fill"),dict) else {})
    out=[]; seen=set()
    for q in unresolved_questions(ai_fill):
        fid=str(q.get("field_id") or "")
        if not _researchable_field(fid):
            continue
        label=str(q.get("label") or fid.replace("_"," ").title())
        question=(f"Find current reliable public information for {label.lower()} relevant to "
                  f"{str(intake.get('project_name') or ai_fill.get('project_name') or ai_fill.get('title') or 'this project')}. "
                  "Prefer official, primary and current sources; include URLs and do not infer private facts.")
        key=(fid,question.casefold())
        if key not in seen:
            seen.add(key); out.append({"field_id":fid,"label":label,"question":question,"reason":str(q.get("reason") or "Public evidence may improve this field."),"researchable":True})
    if include_plan and not intake.get("public_research"):
        context=" ".join([
            str(intake.get("project_info") or ""), str(intake.get("instruction") or ""),
            str(ai_fill.get("research_focus") or ""),
        ]).casefold()
        research_words=(
            "research","public information","public evidence","market","competitor","regulation","grant",
            "funding","tender","procurement","statistics","evidence","industry trend","feasibility",
        )
        if any(word in context for word in research_words):
            plan=intake.get("research_plan") if isinstance(intake.get("research_plan"),dict) else {}
            subject=(plan.get("subject") or {}).get("primary") if isinstance(plan.get("subject"),dict) else ""
            subject=str(subject or "business").replace("_"," ")
            question=(f"Find current authoritative public evidence that could materially improve this {subject} project, "
                      "including relevant market, competitor, regulatory, funding, procurement, pricing or trend evidence where applicable. "
                      "Prefer official and primary sources, retain URLs, and do not infer private facts.")
            key=("research_focus",question.casefold())
            if key not in seen:
                seen.add(key); out.append({"field_id":"research_focus","label":"Additional useful public information","question":question,
                                           "reason":"The project asks for evidence or research that can be strengthened with current public sources.","researchable":True})
    return out[:8]


def set_intake_project(intake_id: str, project_id: int, project_name: str) -> dict[str,Any]:
    intake=get_intake(intake_id)
    if not intake: raise ValueError("INTAKE_NOT_FOUND")
    updated=dict(intake); updated["project_id"]=int(project_id or 0); updated["project_name"]=str(project_name or intake.get("project_name") or "").strip()
    save_intake(updated); return updated


def _public_research_evidence_text(package: dict[str,Any], max_chars: int = 48000) -> str:
    rows=[]; used=0
    for src in package.get("sources") or []:
        if not isinstance(src,dict): continue
        piece=(f"SOURCE: {src.get('title') or 'Public source'}\\nURL: {src.get('url') or ''}\\n"
               f"PROVIDER: {src.get('search_provider') or src.get('source_kind') or ''}\\n"
               f"EVIDENCE: {str(src.get('text') or src.get('snippet') or '')[:4500]}\\n")
        if used+len(piece)>max_chars: break
        rows.append(piece); used+=len(piece)
    return "\\n".join(rows)

def unresolved_questions(ai_fill: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    fields = ai_fill.get("fields") if isinstance(ai_fill, dict) else {}
    for field_id, row in fields.items() if isinstance(fields, dict) else []:
        row_dict = row if isinstance(row, dict) else {"value": row}
        value = str(row_dict.get("value") or "").strip()
        status = str(row_dict.get("status") or "").strip().lower()
        if value and value.lower() != "none" and status != "unresolved":
            continue
        label = str(field_id).replace("_", " ").strip().title()
        reason = str(row_dict.get("reason") or "Agape could not responsibly infer this from the uploaded source and available evidence.").strip()
        out.append({
            "field_id": str(field_id),
            "label": label,
            "question": f"Please provide {label.lower()} if it is known and relevant.",
            "reason": reason,
            "researchable": _researchable_field(str(field_id)),
        })
    return out


def _intake_structured_preserve(ai_fill: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for field_id, row in (ai_fill.get("fields") or {}).items():
        value = str((row or {}).get("value") if isinstance(row, dict) else row or "").strip()
        if value and value.lower() != "none":
            out[str(field_id)] = value
    return out


def improve_intake_with_ai(intake_id: str) -> dict[str, Any]:
    intake = get_intake(intake_id)
    if not intake:
        raise ValueError("INTAKE_NOT_FOUND")
    current = intake.get("ai_fill") if isinstance(intake.get("ai_fill"), dict) else {}
    before_questions = unresolved_questions(current)
    opportunities = public_research_opportunities(intake,current,include_plan=True)
    if not opportunities:
        updated = dict(intake)
        updated["extra_information_opportunities"] = []
        updated["last_gap_fill"] = {"at": now_iso(), "status": "NO_PUBLIC_GAPS", "before": len(before_questions), "after": len(before_questions)}
        save_intake(updated)
        return updated

    design = current.get("design") if isinstance(current.get("design"), dict) else {}
    route_choice = router_decision("planning")
    subject_text = research_subject_text(str(intake.get("project_name") or ""), str(intake.get("project_info") or ""), str(intake.get("instruction") or ""), current, intake.get("upload") if isinstance(intake.get("upload"),dict) else {})
    research_body={
        "title":str(intake.get("project_name") or current.get("project_name") or current.get("title") or "Agape project"),
        "context":subject_text[:50000],
        "questions":[{"question":x["question"],"preferred_sources":["official","primary","current"]} for x in opportunities[:6]],
        "research_depth":"balanced",
    }
    rstatus, package=doc_post("/api/public-research",research_body,timeout=720)
    if rstatus!=200 or not isinstance(package,dict) or package.get("ok") is False:
        raise RuntimeError("PUBLIC_RESEARCH_FAILED: "+json.dumps(package,ensure_ascii=False)[:1800])
    evidence=_public_research_evidence_text(package)
    missing_labels = ", ".join(x["label"] for x in opportunities if x.get("label"))
    research_instruction = "\n\n".join(x for x in [
        str(intake.get("project_info") or "").strip(),
        str(intake.get("instruction") or "").strip(),
        (
            "AGAPE PUBLIC-INFORMATION PASS. Use the supplied PUBLIC RESEARCH EVIDENCE to improve only facts that can be supported by those sources. "
            "Fields/topics being researched: "+missing_labels+". Preserve all user-supplied fields exactly. Prefer official/primary evidence. "
            "Never invent private facts, customers, contracts, internal revenue, approvals, credentials or unpublished prices. If evidence is insufficient, leave that field as None."
        ),
    ] if x)
    body = {
        "title": str(current.get("title") or current.get("project_name") or intake.get("project_name") or "Agape Document"),
        "instructions": research_instruction[:160000],
        "app": str(design.get("app") or "writer"), "doc_type": str(design.get("doc_type") or "Business Proposal"),
        "theme": str(design.get("theme") or "Executive Navy"), "template_id": str(design.get("template_id") or ""),
        "format": str(design.get("format") or "docx"), "also_pdf": True, "auto_template": True,
        "ai_model": str(route_choice.get("model") or "auto"), "ai_provider": str(route_choice.get("provider") or "auto"),
        "research_enabled": True, "research_depth": "balanced", "ingestion_engine": "direct", "rag_enabled": True,
        "rag_top_k": 12, "instruction_upload_ids": [str(intake.get("upload_id") or "")],
        "structured_form": _intake_structured_preserve(current), "force_fill_missing": False,
        "research_evidence": package,
    }
    status, improved = doc_post("/api/ai-fill-form", body, timeout=720)
    if status != 200 or not isinstance(improved, dict) or improved.get("ok") is False:
        raise RuntimeError("MISSING_INFORMATION_AI_FILL_FAILED: " + json.dumps(improved, ensure_ascii=False)[:1800])
    field_count, none_count = intake_field_stats(improved)
    questions = unresolved_questions(improved)
    updated = dict(intake)
    updated.update({
        "ai_fill": improved, "field_count": field_count, "none_count": none_count,
        "design": improved.get("design") if isinstance(improved.get("design"), dict) else design,
        "best_model": improved.get("best_model_selection") if isinstance(improved.get("best_model_selection"), dict) else improved.get("provider") or {},
        "router": str(route_choice.get("router") or intake.get("router") or "agape"), "router_decision": route_choice,
        "research_plan": research_router.recommend_sources(subject_text, 10), "unresolved_questions": questions,
        "public_research": package,
        "extra_information_opportunities": [],
        "last_gap_fill": {"at": now_iso(), "status": "PASS", "before": len(before_questions), "after": len(questions),
                          "resolved": max(0, len(before_questions)-len(questions)), "sources_checked":len(package.get("sources") or []), "router": route_choice},
    })
    updated["extra_information_opportunities"]=public_research_opportunities(updated,improved,include_plan=False)
    save_intake(updated)
    return updated


def apply_intake_answers(intake_id: str, answers: dict[str, Any]) -> dict[str, Any]:
    intake = get_intake(intake_id)
    if not intake:
        raise ValueError("INTAKE_NOT_FOUND")
    ai_fill = dict(intake.get("ai_fill") or {})
    fields = dict(ai_fill.get("fields") or {})
    changed = []
    for field_id, raw in (answers or {}).items():
        value = str(raw or "").strip()
        if not value:
            continue
        fields[str(field_id)] = {
            "value": value,
            "status": "supplied",
            "confidence": 1.0,
            "reason": "Supplied directly by the user after Agape's missing-information review.",
            "sources": [],
        }
        changed.append(str(field_id))
    ai_fill["fields"] = fields
    field_count, none_count = intake_field_stats(ai_fill)
    updated = dict(intake)
    updated.update({
        "ai_fill": ai_fill, "field_count": field_count, "none_count": none_count,
        "unresolved_questions": unresolved_questions(ai_fill),
        "last_user_answers": {"at": now_iso(), "fields": changed},
    })
    updated["extra_information_opportunities"]=public_research_opportunities(updated,ai_fill,include_plan=True)
    save_intake(updated)
    return updated


def revise_intake_with_ai(intake_id: str, instruction: str) -> dict[str, Any]:
    intake = get_intake(intake_id)
    if not intake:
        raise ValueError("INTAKE_NOT_FOUND")
    instruction = str(instruction or "").strip()
    if not instruction:
        raise ValueError("REVISION_INSTRUCTION_REQUIRED")
    current = intake.get("ai_fill") if isinstance(intake.get("ai_fill"), dict) else {}
    design = current.get("design") if isinstance(current.get("design"), dict) else {}
    route_choice = router_decision("planning")
    revision_instruction = "\n\n".join(x for x in [
        str(intake.get("project_info") or "").strip(),
        str(intake.get("instruction") or "").strip(),
        "USER REVISION INSTRUCTION: " + instruction,
        "Update the completed document brief to follow the new instruction. Preserve facts and fields that are not affected. Do not invent private facts. Return the complete form, not only changed fields.",
    ] if x)
    body = {
        "title": str(current.get("title") or current.get("project_name") or intake.get("project_name") or "Agape Document"),
        "instructions": revision_instruction[:160000],
        "app": str(design.get("app") or "writer"),
        "doc_type": str(design.get("doc_type") or "Business Proposal"),
        "theme": str(design.get("theme") or "Executive Navy"),
        "template_id": str(design.get("template_id") or ""),
        "format": str(design.get("format") or "docx"),
        "also_pdf": True,
        "auto_template": True,
        "ai_model": str(route_choice.get("model") or "auto"),
        "ai_provider": str(route_choice.get("provider") or "auto"),
        "research_enabled": True,
        "research_depth": "balanced",
        "ingestion_engine": "direct",
        "rag_enabled": True,
        "rag_top_k": 10,
        "instruction_upload_ids": [str(intake.get("upload_id") or "")],
        "structured_form": _intake_structured_preserve(current),
        "force_fill_missing": True,
    }
    status, revised = doc_post("/api/ai-fill-form", body, timeout=720)
    if status != 200 or not isinstance(revised, dict) or revised.get("ok") is False:
        raise RuntimeError("FORM_AI_REVISION_FAILED: " + json.dumps(revised, ensure_ascii=False)[:1800])
    field_count, none_count = intake_field_stats(revised)
    revisions = list(intake.get("form_revisions") or [])
    revisions.append({"at": now_iso(), "instruction": instruction, "previous": current})
    updated = dict(intake)
    updated.update({
        "ai_fill": revised,
        "field_count": field_count,
        "none_count": none_count,
        "unresolved_questions": unresolved_questions(revised),
        "form_revisions": revisions[-20:],
        "last_form_revision": {"at": now_iso(), "instruction": instruction, "router": route_choice},
    })
    updated["extra_information_opportunities"]=public_research_opportunities(updated,revised,include_plan=True)
    save_intake(updated)
    return updated


def _previous_draft(job: dict[str, Any]) -> str:
    result = job.get("result") if isinstance(job, dict) else None
    if not isinstance(result, dict):
        return ""
    # Gold Standard's lead-synthesised draft is the true current version.
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    draft = str(review.get("revised_draft") or "").strip()
    if draft:
        return draft
    agent = result.get("agent") if isinstance(result.get("agent"), dict) else {}
    return str(agent.get("draft") or "").strip()


def revise_job_with_ai(job_id: str, instruction: str, quality_mode: str = "") -> dict[str, Any]:
    old = get_job(job_id)
    if not old:
        raise ValueError("JOB_NOT_FOUND")
    instruction = str(instruction or "").strip()
    if not instruction:
        raise ValueError("REVISION_INSTRUCTION_REQUIRED")
    prior = _previous_draft(old)
    lineage_root = str(old.get("lineage_root") or old.get("revision_of") or old.get("id") or job_id)
    revision_number = int(old.get("revision_number") or 1) + 1
    context = []
    if prior:
        context.append("PREVIOUS GENERATED DOCUMENT (revise this; preserve unaffected content):\n" + prior[:100000])
    if old.get("project_info"):
        context.append(str(old.get("project_info")))
    row = new_job({
        "project_id": int(old.get("project_id") or 0),
        "intake_id": str(old.get("intake_id") or ""),
        "instruction": "REVISION REQUEST: " + instruction,
        "project_info": "\n\n".join(context),
        "quality_mode": str(quality_mode or old.get("quality_mode") or "standard"),
        "reviewer_count": old.get("reviewer_count"),
        "reviewer_ids": old.get("reviewer_ids") or [],
        "lead_reviewer": old.get("lead_reviewer") or "auto",
        "router": old.get("router") or load_settings().get("router"),
        "template_id": old.get("template_id") or "auto",
        "document_theme": old.get("document_theme") or "Executive Navy",
        "format": old.get("format") or "docx",
        "also_pdf": old.get("also_pdf", True),
        "revision_of": str(old.get("id") or job_id),
        "lineage_root": lineage_root,
        "revision_number": revision_number,
        "revision_instruction": instruction,
    })
    return row


def research_subject_text(project_name: str, project_info: str, extra_instruction: str, ai_fill: dict[str, Any], upload: dict[str, Any]) -> str:
    parts = [project_name, project_info, extra_instruction, str(upload.get("preview") or "")]
    fields = ai_fill.get("fields") if isinstance(ai_fill, dict) else {}
    if isinstance(fields, dict):
        for key, row in fields.items():
            value = row.get("value") if isinstance(row, dict) else row
            if value:
                parts.append(str(key) + ": " + str(value))
    design = ai_fill.get("design") if isinstance(ai_fill, dict) and isinstance(ai_fill.get("design"), dict) else {}
    parts.extend([str(design.get("doc_type") or ""), str(design.get("template_name") or "")])
    return "\n".join(x for x in parts if str(x).strip())[:160000]


def research_plan_instruction(plan: dict[str, Any]) -> str:
    rows = []
    for i, src in enumerate((plan or {}).get("sources") or [], 1):
        if not isinstance(src, dict):
            continue
        state = "READY" if src.get("ready") else "CONNECT IF NEEDED"
        rows.append(f"{i}. {src.get('name')} ({state}) - {src.get('summary')} - {src.get('reason')}")
    if not rows:
        return ""
    subject = ((plan or {}).get("subject") or {}).get("primary") or "general"
    return (
        "AGAPE RESEARCH SOURCE PLAN\n"
        f"Project subject: {subject}. Agape ranked these as the best sources for this job. "
        "Prefer official/primary sources for factual claims; use social/community sources for discovery and sentiment, not as sole proof.\n"
        + "\n".join(rows)
    )


_SOURCE_FIELD_LABELS = {
    "organisation": ("organisation", "organization", "company", "proposer"),
    "recipient": ("recipient", "decision maker", "decision-maker"),
    "industry": ("industry", "sector"),
    "geography": ("geography", "market", "region", "country"),
    "product_service": ("product service", "product/service", "product", "service", "initiative"),
    "problem_need": ("problem need", "problem/need", "problem", "need", "opportunity"),
    "document_purpose": ("document purpose", "purpose"),
    "decision_requested": ("decision requested", "decision/action requested", "action requested"),
    "target_audience": ("target audience", "audience"),
    "value_proposition": ("value proposition", "key benefit"),
    "budget_pricing": ("budget pricing", "budget/pricing", "budget", "pricing", "commercial terms"),
    "timeline": ("timeline", "target date", "deadline"),
    "success_metrics": ("success metrics", "success measures", "measures of success"),
    "competitors_alternatives": ("competitors alternatives", "competitors/alternatives", "competitors", "alternatives"),
    "constraints": ("constraints", "risks", "must-not-change"),
    "tone": ("tone", "voice"),
    "research_focus": ("research focus",),
}


def _usable_source_value(value: str) -> str:
    value = re.sub(r"^\s*\d+[.)]\s*", "", str(value or "")).strip()
    value = value.strip(' \t\r\n-–—:;"\'')
    low = value.casefold()
    if not value or low in {"none", "unknown", "n/a", "not known", "not specified", "not provided", "not mentioned"}:
        return ""
    if any(x in low for x in ("no reliable or relevant value", "could not be established", "inventing one would violate")):
        return ""
    return value[:4000]


def deterministic_source_fields(project_name: str, project_info: str, extra_instruction: str = "") -> dict[str, str]:
    """Extract high-confidence facts before AI form completion.

    These values are deliberately conservative. They are either explicit labelled
    values in the saved source or facts stated directly in the project title. The
    AI can fill or research everything else, but it may not erase these facts by
    returning an all-None form.
    """
    out: dict[str, str] = {}
    text = "\n".join(x for x in (str(project_info or ""), str(extra_instruction or "")) if x)
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", raw).strip()
        if not line or len(line) > 9000:
            continue
        for fid, labels in _SOURCE_FIELD_LABELS.items():
            if fid in out:
                continue
            for label in labels:
                m = re.match(r"^" + re.escape(label) + r"\s*(?:/[^:=]{1,40})?\s*[:=]\s*(.+)$", line, flags=re.I)
                if m:
                    value = _usable_source_value(m.group(1))
                    if value:
                        out[fid] = value
                    break

    title = _usable_source_value(project_name)
    low = title.casefold()
    if title and "business plan" in low:
        prefix = re.split(r"\bbusiness\s+plan\b", title, maxsplit=1, flags=re.I)[0].strip(" -–—:|,")
        if prefix and len(prefix) >= 3:
            out.setdefault("organisation", prefix)
        out.setdefault("document_purpose", "Business plan")
        year = re.search(r"\b(20\d{2})\b", title)
        if year:
            out.setdefault("timeline", year.group(1))
    if "commercial interiors" in low:
        out.setdefault("industry", "Commercial interiors")
        out.setdefault("product_service", "Commercial interiors")

    # Explicit money statements in user/project context are safe to preserve.
    if "budget_pricing" not in out:
        m = re.search(r"\b(?:budget|funding|investment)\s*(?:is|of|:|=)?\s*((?:£|GBP\s*)[0-9][0-9,]*(?:\.\d{1,2})?)", text, flags=re.I)
        if m:
            out["budget_pricing"] = m.group(1).strip()
    return out


def _apply_source_seeds(ai_fill: dict[str, Any], seeds: dict[str, str]) -> dict[str, Any]:
    if not isinstance(ai_fill, dict):
        ai_fill = {}
    fields = ai_fill.get("fields") if isinstance(ai_fill.get("fields"), dict) else {}
    fields = dict(fields)
    for fid, value in seeds.items():
        fields[fid] = {
            "value": value,
            "status": "supplied",
            "confidence": 1.0,
            "reason": "Extracted directly from the saved project title/source before AI completion.",
            "sources": [],
        }
    ai_fill["fields"] = fields
    return ai_fill


def established_field_count(ai_fill: dict[str, Any]) -> int:
    fields = ai_fill.get("fields") if isinstance(ai_fill, dict) else {}
    count = 0
    for row in fields.values() if isinstance(fields, dict) else []:
        row = row if isinstance(row, dict) else {"value": row}
        value = str(row.get("value") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if value and value.casefold() != "none" and status != "unresolved":
            count += 1
    return count


def _create_document_intake_once(body: dict[str, Any]) -> dict[str, Any]:
    file_name = Path(str(body.get('name') or '')).name
    data_base64 = str(body.get('data_base64') or '').strip()
    if not file_name or not data_base64:
        raise ValueError('SOURCE_DOCUMENT_REQUIRED')
    if len(data_base64) > 36 * 1024 * 1024:
        raise ValueError('SOURCE_DOCUMENT_TOO_LARGE_MAX_25MB')

    project_id = int(body.get('project_id') or 0)
    project = project_by_id(project_id) if project_id > 0 else None
    project_name = str(body.get('project_name') or (project or {}).get('name') or Path(file_name).stem or 'Agape Document').strip()
    project_info = str(body.get('project_info') or '').strip()[:120000]
    extra_instruction = str(body.get('instruction') or '').strip()[:20000]
    selected_template = template_by_id(str(body.get('template_id') or 'auto'))

    status, uploaded = doc_post('/api/upload-instruction', {'name': file_name, 'data_base64': data_base64}, timeout=240)
    if status != 200 or not isinstance(uploaded, dict) or not (uploaded.get('upload') or {}).get('id'):
        raise RuntimeError('DOCUMENT_INGEST_FAILED: ' + json.dumps(uploaded, ensure_ascii=False)[:1200])
    upload = dict(uploaded['upload'])
    upload_id = str(upload.get('id'))

    default_doc_type = map_document_type(project or {'name': project_name}, extra_instruction + ' ' + file_name, selected_template)
    instructions = '\n\n'.join(x for x in [
        project_info,
        extra_instruction,
        'Use the uploaded source document as the primary factual authority. A conservative spelling/grammar checker has already inspected the extracted text; treat names, figures and supplied facts as authoritative. Complete every document-creation field. Do not invent private facts. For information that is genuinely unavailable or irrelevant, use None rather than guessing.'
    ] if x)
    route_choice = router_decision('planning')
    source_seeds = deterministic_source_fields(project_name, project_info, extra_instruction)
    fill_body = {
        'title': project_name,
        'instructions': instructions,
        'app': 'writer',
        'doc_type': default_doc_type,
        'theme': str(body.get('document_theme') or 'Executive Navy'),
        'template_id': str(selected_template.get('document_template_id') or ''),
        'format': str(body.get('format') or 'docx'),
        'also_pdf': bool(body.get('also_pdf', True)),
        'auto_template': True,
        'ai_model': str(route_choice.get('model') or 'auto'),
        'ai_provider': str(route_choice.get('provider') or 'auto'),
        'research_enabled': False,
        'research_depth': 'quick',
        'ingestion_engine': 'direct',
        'rag_enabled': False,
        'rag_top_k': 8,
        'instruction_upload_ids': [upload_id],
        'structured_form': source_seeds,
        'force_fill_missing': True,
    }
    fstatus, ai_fill = doc_post('/api/ai-fill-form', fill_body, timeout=480)
    if fstatus != 200 or not isinstance(ai_fill, dict) or ai_fill.get('ok') is False:
        raise RuntimeError('FULL_FORM_AI_FILL_FAILED: ' + json.dumps(ai_fill, ensure_ascii=False)[:1600])

    ai_fill = _apply_source_seeds(ai_fill, source_seeds)
    nonempty, none_count = intake_field_stats(ai_fill)
    established_count = established_field_count(ai_fill)
    design = ai_fill.get('design') if isinstance(ai_fill.get('design'), dict) else {}
    model = ai_fill.get('best_model_selection') if isinstance(ai_fill.get('best_model_selection'), dict) else ai_fill.get('provider') or {}
    subject_text = research_subject_text(project_name, project_info, extra_instruction, ai_fill, upload)
    research_plan = research_router.recommend_sources(subject_text, 10)
    intake_id = 'AGI-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6].upper()
    row = {
        'id': intake_id, 'created_at': now_iso(), 'prepare_request_id': str(body.get('prepare_request_id') or ''), 'project_id': project_id, 'source_project_id': int(body.get('source_project_id') or 0), 'project_name': project_name,
        'source_mode': str(body.get('source_mode') or 'upload'),
        'source_name': file_name, 'upload_id': upload_id, 'upload': upload, 'writing_check': upload.get('writing_check') if isinstance(upload.get('writing_check'), dict) else {}, 'project_info': project_info,
        'instruction': extra_instruction, 'ai_fill': ai_fill, 'field_count': nonempty, 'established_count': established_count, 'none_count': none_count, 'source_seed_count': len(source_seeds), 'source_seed_fields': sorted(source_seeds),
        'design': design, 'best_model': model, 'router': str(route_choice.get('router') or 'agape'),
        'router_decision': route_choice, 'research_plan': research_plan,
        'unresolved_questions': unresolved_questions(ai_fill),
    }
    row['extra_information_opportunities']=public_research_opportunities(row,ai_fill,include_plan=True)
    save_intake(row)
    return row


INTAKE_CREATE_LOCK = threading.RLock()

def create_document_intake(body: dict[str, Any]) -> dict[str, Any]:
    """Idempotent intake creation for restart-safe Mainframe source preparation."""
    key=str(body.get("prepare_request_id") or "").strip()[:160]
    with INTAKE_CREATE_LOCK:
        if key:
            for row in reversed(load_intakes()):
                if str(row.get("prepare_request_id") or "")==key:
                    return row
        return _create_document_intake_once(body)


def submit_work_health_probe() -> dict[str, Any]:
    status, payload = http_json("POST", WORK_URL + "/api/jobs", body={"kind": "service_health", "payload": {"recover": False}, "priority": 80}, timeout=5)
    if status not in {200, 201, 202} or not isinstance(payload, dict) or not payload.get("job_id"):
        raise RuntimeError("WORK_ENGINE_QUEUE_FAILED: " + json.dumps(payload, ensure_ascii=False)[:500])
    jid = str(payload["job_id"])
    deadline = time.time() + 25
    latest = None
    while time.time() < deadline:
        s, state = http_json("GET", WORK_URL + "/api/status", timeout=4)
        if s == 200 and isinstance(state, dict):
            for row in state.get("jobs") or []:
                if str(row.get("id")) == jid:
                    latest = row
                    if str(row.get("state") or "").upper() in {"PASS", "FAIL", "CANCELLED"}:
                        return {"job_id": jid, "job": row}
        time.sleep(0.35)
    return {"job_id": jid, "job": latest, "warning": "Probe still running after 25 seconds"}


def wait_multi_review(review_job_id: str, unified_job_id: str, timeout: int = 720) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_stage = ''
    while time.time() < deadline:
        status, state = doc_get('/api/multi-review/status?id=' + urllib.parse.quote(review_job_id), timeout=15)
        if status == 200 and isinstance(state, dict):
            local_progress = _progress_value(state.get('progress'))
            update_progress(unified_job_id, 65.0 + (21.0 * local_progress / 100.0))
            stage = str(state.get('stage') or '')
            if stage and stage != last_stage:
                add_event(unified_job_id, 'Gold review', stage, progress=65.0 + (21.0 * local_progress / 100.0))
                last_stage = stage
            current = str(state.get('state') or '').lower()
            if current == 'ready':
                return state
            if current in {'unavailable','skipped'}:
                return state
            if current == 'failed':
                raise RuntimeError('MULTI_AI_REVIEW_FAILED: ' + str(state.get('error') or 'unknown error'))
        time.sleep(1.0)
    raise RuntimeError('MULTI_AI_REVIEW_TIMEOUT')




def _validation_failure_details(payload: Any) -> dict[str, list[str]] | None:
    if not isinstance(payload, dict):
        return None
    text = str(payload.get("error") or "")
    marker = "GENERATED_DOCUMENT_VALIDATION_FAILED="
    if marker not in text:
        return None
    raw = text.split(marker, 1)[1].strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    missing = [str(x).strip() for x in (obj.get("missing") or []) if str(x).strip()]
    short = [str(x).strip() for x in (obj.get("short") or []) if str(x).strip()]
    duplicates = [str(x).strip() for x in (obj.get("duplicates") or []) if str(x).strip()]
    artifacts = [str(x).strip() for x in (obj.get("artifacts") or []) if str(x).strip()]
    return {"missing": missing, "short": short, "duplicates": duplicates, "artifacts": artifacts}


def _business_quality_contract(doc_type: str) -> str:
    kind = str(doc_type or "").strip().lower()
    if "business" not in kind and "proposal" not in kind and "plan" not in kind:
        return ""
    return (
        "\n\nAGAPE BUSINESS-DOCUMENT QUALITY CONTRACT:\n"
        "Before finalising, ensure the document contains substantive, decision-ready sections for "
        "TAM / SAM / SOM, Customer Personas, Recommendation / Next Step, and Sources / Evidence when relevant to the supplied project. "
        "Do not leave these as headings only. Use supplied or researched evidence where available, label assumptions clearly, "
        "and never invent private customers, revenue, contracts, approvals or unsupported market figures. "
        "There must be one authoritative version of each section: do not duplicate Executive Summary, market, financial, risk or recommendation sections. "
        "Before finalising, reconcile repeated figures, dates and assumptions so the document does not present competing financial forecasts or valuations."
    )


def _validation_repair_instruction(details: dict[str, list[str]], attempt: int) -> str:
    missing = details.get("missing") or []
    short = details.get("short") or []
    duplicates = details.get("duplicates") or []
    artifacts = details.get("artifacts") or []
    lines = [
        "AGAPE TARGETED VALIDATION REPAIR PASS " + str(attempt) + ".",
        "Regenerate the complete document, preserving all supplied facts and already-strong sections.",
    ]
    if missing:
        lines.append("The validator says these required sections are MISSING and must be added with substantive content: " + "; ".join(missing) + ".")
    if short:
        lines.append("The validator says these sections are TOO SHORT and must be expanded with useful analysis, evidence, assumptions, implications and concrete detail: " + "; ".join(short) + ".")
    if duplicates:
        lines.append("The validator found DUPLICATE versions of these sections. Return exactly one reconciled authoritative section for each: " + "; ".join(duplicates) + ".")
    if artifacts:
        lines.append("Remove internal/formatting artefacts from the client document: " + "; ".join(artifacts) + ".")
    lines.extend([
        "For Sources / Evidence, include a clear evidence/source section rather than merely saying research is required.",
        "For Recommendation / Next Step, state a concrete recommendation and specific next actions.",
        "For TAM / SAM / SOM, distinguish the three levels and show the basis/assumptions for estimates; do not fabricate unsupported figures.",
        "For Customer Personas, describe specific target customer types, pains, buying roles, needs and decision criteria.",
        "Return a complete professional document that can pass validation, not a patch fragment.",
    ])
    return "\n".join(lines)



def _doc_agent_create(body: dict[str, Any], unified_job_id: str, attempt: int = 0) -> tuple[int, Any]:
    """Start long document creation asynchronously and poll its status.

    R31.16 keeps long document creation asynchronous and exposes live stage/heartbeat progress across planning, research,
    drafting and repair. Older Document Studio builds remain supported by
    falling back to the legacy synchronous endpoint when /start is absent.
    """
    bands = [(22.0, 58.0), (58.0, 70.0), (70.0, 80.0)]
    band_start, band_end = bands[min(max(int(attempt), 0), len(bands)-1)]
    update_progress(unified_job_id, band_start)
    status, started = doc_post('/api/agent-create/start', body, timeout=30)
    if status == 404:
        add_event(unified_job_id, 'Document creation', 'Older Document Studio detected; using compatibility mode', progress=band_start)
        result = doc_post('/api/agent-create', body, timeout=7200)
        if result[0] == 200:
            update_progress(unified_job_id, band_end)
        return result
    if status not in (200, 202) or not isinstance(started, dict):
        return status, started
    doc_job_id = str(started.get('job_id') or '').strip()
    # Compatibility for test/fake/older bridges that return a completed payload directly.
    if not doc_job_id:
        return status, started
    label = f'Document worker started ({doc_job_id})'
    if attempt:
        label += f' for validation repair pass {attempt}'
    add_event(unified_job_id, 'Document creation', label)
    last_stage = ''
    last_activity = ''
    last_parent_touch = 0.0
    connection_failures = 0
    while True:
        q = urllib.parse.quote(doc_job_id)
        poll_status, state = doc_get('/api/agent-create/status?id=' + q, timeout=20)
        if poll_status == 200 and isinstance(state, dict):
            connection_failures = 0
            if state.get('ok') is False:
                return 500, {'error': str(state.get('error') or 'AGENT_CREATE_JOB_NOT_FOUND')}
            local_progress = _progress_value(state.get('progress'))
            update_progress(unified_job_id, band_start + ((band_end - band_start) * local_progress / 100.0))
            stage = str(state.get('stage') or '').strip()
            activity = str(state.get('message') or stage or 'Creating document with AI').strip()
            if stage and stage != last_stage:
                add_event(unified_job_id, 'Document creation', stage)
                last_stage = stage
            # Keep the parent Mainframe job visibly alive while a provider call is in flight.
            # This updates human-facing status without adding an event every two seconds.
            now = time.time()
            if activity and (activity != last_activity or now - last_parent_touch >= 10.0):
                try:
                    update_job(unified_job_id, stage='Document creation', message=activity)
                except Exception:
                    pass
                last_activity = activity
                last_parent_touch = now
            current = str(state.get('state') or '').lower()
            if current == 'ready':
                update_progress(unified_job_id, band_end)
                result = state.get('result')
                return 200, result if isinstance(result, dict) else {'ok': False, 'error': 'AGENT_CREATE_RESULT_MISSING'}
            if current == 'failed':
                return 500, {'error': str(state.get('error') or 'AGENT_CREATE_FAILED')}
        else:
            connection_failures += 1
            if connection_failures in (1, 5, 20):
                add_event(unified_job_id, 'Document creation', f'Status connection interrupted; retrying ({connection_failures})')
            if connection_failures >= 60:
                return 0, {'error': 'DOCUMENT_STUDIO_STATUS_UNREACHABLE_AFTER_RETRIES', 'detail': state}
        time.sleep(2.0)


def _provider_action_required(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower() if isinstance(payload,(dict,list)) else str(payload or '').lower()
    return any(x in text for x in ('no_ready_ai_provider','no_configured_ai_provider_available','provider_preflight_failed'))


def _transient_document_failure(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower() if isinstance(payload,(dict,list)) else str(payload or '').lower()
    markers = ('timed out','timeout','temporarily unavailable','connection reset','connection aborted','remote end closed','status_unreachable','service unavailable')
    return any(x in text for x in markers)


def create_with_validation_repair(create_body: dict[str, Any], job_id: str, max_repairs: int = 2) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    body = dict(create_body)
    base_instructions = str(body.get("instructions") or "") + _business_quality_contract(str(body.get("doc_type") or ""))
    body["instructions"] = base_instructions
    history: list[dict[str, Any]] = []
    last_payload: Any = None
    validation_repairs = 0
    transient_retries = 0
    max_transient_retries = 2
    while validation_repairs <= max_repairs:
        status, created = _doc_agent_create(body, job_id, validation_repairs)
        last_payload = created
        if status == 200 and isinstance(created, dict) and created.get('ok') is not False:
            if validation_repairs:
                add_event(job_id, 'Validation repair', f'Document passed validation after repair pass {validation_repairs}', 'PASS')
            return created, history

        if _provider_action_required(created):
            detail = json.dumps(created, ensure_ascii=False)[:1400] if isinstance(created,(dict,list)) else str(created)[:1400]
            raise RuntimeError('ACTION_REQUIRED: No usable AI provider is ready. Open Settings > AI connections, reconnect/test ChatGPT or another online provider, or start/test Ollama. Provider check: ' + detail)

        if _transient_document_failure(created) and transient_retries < max_transient_retries:
            transient_retries += 1
            add_event(job_id, 'Document creation', f'Temporary AI/service timeout; retrying safely ({transient_retries}/{max_transient_retries})', 'RETRY')
            # Automatic routing lets Document Studio fail over to another connected provider.
            body = dict(body)
            body['ai_provider'] = 'auto'
            body['ai_model'] = 'auto'
            time.sleep(min(6, transient_retries * 2))
            continue

        details = _validation_failure_details(created)
        history.append({"attempt": len(history) + 1, "http_status": status, "validation": details, "payload": created if isinstance(created, dict) else str(created)[:1000]})
        if not details or validation_repairs >= max_repairs:
            break
        validation_repairs += 1
        repair_progress = 58 if validation_repairs == 1 else 70
        add_event(job_id, 'Validation repair', 'Repairing document sections: ' + ', '.join((details.get('missing') or []) + (details.get('short') or [])), progress=repair_progress)
        repair_route = router_decision('repair')
        body = dict(create_body)
        body['instructions'] = base_instructions + "\n\n" + _validation_repair_instruction(details, validation_repairs)
        body['ai_provider'] = str(repair_route.get('provider') or body.get('ai_provider') or 'auto')
        body['ai_model'] = str(repair_route.get('model') or body.get('ai_model') or 'auto')
        body['research_enabled'] = True
        body['research_depth'] = 'deep'
        body['rag_enabled'] = True

    if _transient_document_failure(last_payload):
        raise RuntimeError('AI_DOCUMENT_CREATE_TRANSIENT_FAILURE_AFTER_RETRIES: ' + json.dumps(last_payload, ensure_ascii=False)[:1800])
    if _validation_failure_details(last_payload):
        raise RuntimeError('AI_DOCUMENT_CREATE_FAILED_AFTER_VALIDATION_REPAIR: ' + json.dumps(last_payload, ensure_ascii=False)[:1800])
    raise RuntimeError('AI_DOCUMENT_CREATE_FAILED: ' + json.dumps(last_payload, ensure_ascii=False)[:1800])

def run_document(job: dict[str, Any], bundle: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    project = bundle['project']
    instruction = str(job.get('instruction') or '').strip()
    edited_text = str(job.get('project_info') or '').strip()
    intake = get_intake(str(job.get('intake_id') or '')) if job.get('intake_id') else None
    quality_mode = str(job.get('quality_mode') or 'standard').lower()

    if intake:
        fill = intake.get('ai_fill') if isinstance(intake.get('ai_fill'), dict) else {}
        route_choice = intake.get('router_decision') if isinstance(intake.get('router_decision'), dict) else router_decision('business_writing')
        design = fill.get('design') if isinstance(fill.get('design'), dict) else {}
        fields = ai_fill_to_structured_form(fill)
        title = str(fill.get('title') or fill.get('project_name') or intake.get('project_name') or project.get('name') or 'Agape Document').strip()
        source_instruction = '\n\n'.join(x for x in [
            str(intake.get('project_info') or '').strip(),
            edited_text,
            str(intake.get('instruction') or '').strip(),
            instruction,
            research_plan_instruction(intake.get('research_plan') if isinstance(intake.get('research_plan'), dict) else {}),
            'Use the uploaded source as the primary factual authority. Produce a complete professional deliverable. Preserve supplied facts. Clearly label assumptions and never invent private facts.'
        ] if x)
        theme_value = str(job.get('document_theme') or 'auto').strip()
        if theme_value.lower() == 'auto':
            theme_value = str(design.get('theme') or 'Executive Navy')
        create_body = {
            'title': title,
            'instructions': source_instruction,
            'app': str(design.get('app') or 'writer'),
            'doc_type': str(design.get('doc_type') or map_document_type(project, instruction, template)),
            'theme': theme_value,
            'template_id': str(design.get('template_id') or template.get('document_template_id') or ''),
            'format': str(job.get('format') or design.get('format') or 'docx'),
            'also_pdf': bool(job.get('also_pdf', True)),
            'filename': str(design.get('filename') or title),
            'auto_template': not bool(design.get('template_id')),
            'ai_model': str(route_choice.get('model') or 'auto'),
            'ai_provider': str(route_choice.get('provider') or 'auto'),
            'research_enabled': quality_mode == 'gold',
            'research_depth': 'deep' if quality_mode == 'gold' else 'balanced',
            'ingestion_engine': 'direct',
            'rag_enabled': quality_mode == 'gold',
            'rag_top_k': 8,
            'instruction_upload_ids': [str(intake.get('upload_id'))],
            'structured_form': fields,
            'ai_form_completed': True,
        }
        add_event(job['id'], 'Creating', 'Creating the first validated document with the best available AI', progress=20)
        created, validation_repairs = create_with_validation_repair(create_body, job['id'], max_repairs=2)
        initial_files = [x for x in (created.get('files') or []) if isinstance(x, dict) and x.get('ok')]
        if not initial_files:
            raise RuntimeError('AI_DOCUMENT_CREATE_RETURNED_NO_VALIDATED_FILES')
        if quality_mode != 'gold':
            return {
                'route': 'document', 'quality_mode': 'standard', 'doc_type': create_body['doc_type'],
                'files': initial_files, 'primary': initial_files[0], 'agent': created,
                'form_fill': {'field_count': intake.get('field_count'), 'none_count': intake.get('none_count'), 'best_model': intake.get('best_model')},
                'router': route_choice, 'validation_repairs': validation_repairs,
            }

        providers = connected_quality_providers(True)
        team = choose_gold_review_team(providers, job)
        reviewers = team['reviewers']
        availability = f"{team['used_count']}/{team['requested_count']} requested reviewers available"
        add_event(job['id'], 'Gold review', availability + ': ' + ', '.join(reviewers), progress=65)
        review_body = {
            'title': title,
            'draft': str(created.get('draft') or '').strip(),
            'reviewers': reviewers,
            'lead_reviewer': team['lead_reviewer'],
            'context': {
                'structured_form': fields, 'app': create_body['app'], 'doc_type': create_body['doc_type'],
                'theme': create_body['theme'], 'template': create_body['template_id'], 'audit': created.get('audit')
            }
        }
        rstatus, started = doc_post('/api/multi-review/start', review_body, timeout=30)
        if rstatus not in {200, 201, 202} or not isinstance(started, dict) or not started.get('job_id'):
            raise RuntimeError('MULTI_AI_REVIEW_START_FAILED: ' + json.dumps(started, ensure_ascii=False)[:1200])
        review = wait_multi_review(str(started['job_id']), job['id'])
        if str(review.get('state') or '').lower() in {'unavailable','skipped'}:
            reason=str(review.get('error') or 'NO_READY_REVIEW_PROVIDER')
            add_event(job['id'], 'Gold review', 'Reviewers unavailable; delivering the validated first document instead of failing the result', progress=92)
            update_progress(job['id'], 94)
            return {
                'route': 'document', 'quality_mode': 'gold', 'doc_type': create_body['doc_type'],
                'files': initial_files, 'primary': initial_files[0], 'agent': created,
                'form_fill': {'field_count': intake.get('field_count'), 'none_count': intake.get('none_count'), 'best_model': intake.get('best_model')},
                'router': route_choice, 'validation_repairs': validation_repairs,
                'review': {
                    'completed': False, 'degraded': True, 'status': 'unavailable', 'reason': reason,
                    'reviewers': review.get('reviewers') or reviewers, 'errors': review.get('errors') or [],
                    'requested_count': team['requested_count'], 'used_count': 0,
                    'available_count': team['available_count'], 'selection_mode': team['mode'],
                    'unavailable_selected': team['unavailable_selected']
                },
            }
        lead = review.get('lead') if isinstance(review.get('lead'), dict) else {}
        revised = str(lead.get('revised_draft') or '').strip()
        if not revised:
            raise RuntimeError('MULTI_AI_LEAD_RETURNED_NO_REVISED_DRAFT')
        add_event(job['id'], 'Finalising', 'Lead reviewer merged the strongest ideas; rebuilding and validating the final document', progress=88)
        recreate = {
            'title': title, 'app': create_body['app'], 'doc_type': create_body['doc_type'], 'theme': create_body['theme'],
            'template_id': create_body['template_id'], 'format': create_body['format'], 'filename': create_body['filename'],
            'also_pdf': create_body['also_pdf'], 'content': revised
        }
        fstatus, final = doc_post('/api/review/recreate', recreate, timeout=900)
        if fstatus != 200 or not isinstance(final, dict):
            raise RuntimeError('GOLD_FINAL_RECREATE_FAILED: ' + json.dumps(final, ensure_ascii=False)[:1600])
        final_files = [x for x in (final.get('files') or []) if isinstance(x, dict) and x.get('ok')]
        if not final_files:
            raise RuntimeError('GOLD_FINAL_RECREATE_RETURNED_NO_VALIDATED_FILES')
        update_progress(job['id'], 94)
        return {
            'route': 'document', 'quality_mode': 'gold', 'doc_type': create_body['doc_type'], 'files': final_files,
            'primary': final_files[0], 'agent': created,
            'review': {
                'reviewers': reviewers, 'requested_count': team['requested_count'], 'used_count': team['used_count'],
                'available_count': team['available_count'], 'selection_mode': team['mode'],
                'unavailable_selected': team['unavailable_selected'], 'average_score': review.get('average_score'),
                'lead_requested': team['lead_reviewer'],
                'lead_provider': lead.get('lead_provider'), 'lead_provider_name': lead.get('lead_provider_name'),
                'lead_model': lead.get('lead_model'), 'final_summary': lead.get('final_summary'),
                'revised_draft': revised,
                'accepted_changes': lead.get('accepted_changes') or [], 'reviews': review.get('reviews') or []
            },
            'form_fill': {'field_count': intake.get('field_count'), 'none_count': intake.get('none_count'), 'best_model': intake.get('best_model')},
            'router': route_choice, 'validation_repairs': validation_repairs,
        }

    saved_text = edited_text or unique_text(flatten_text(bundle.get('template')), 85000)
    if not saved_text and not instruction:
        raise RuntimeError('PROJECT_INFORMATION_MISSING')
    content_parts = []
    if saved_text:
        content_parts.append('PROJECT INFORMATION\n' + saved_text)
    if instruction:
        content_parts.append('CURRENT REQUEST\n' + instruction)
    content_parts.append('Create a complete, decision-ready deliverable from the supplied project information. Preserve supplied facts. Clearly label assumptions and do not invent private facts.')
    content = '\n\n'.join(content_parts)
    doc_type = map_document_type(project, instruction, template)
    body = {
        'title': str(project.get('name') or 'Agape Project'), 'app': 'writer', 'doc_type': doc_type,
        'theme': str(job.get('document_theme') or 'Executive Navy'), 'template_id': str(template.get('document_template_id') or ''),
        'format': str(job.get('format') or 'docx'), 'content': content, 'template_auto_selected': True,
        'template_auto_reason': 'Agape Unified routed saved project information to Document Studio',
    }
    add_event(job['id'], 'Working', f'Creating {doc_type} in Document Studio', progress=25)
    status, primary = doc_post('/api/create', body, timeout=1200)
    if status != 200 or not isinstance(primary, dict) or not primary.get('ok'):
        raise RuntimeError('DOCUMENT_CREATE_FAILED: ' + json.dumps(primary, ensure_ascii=False)[:1500])
    results = [primary]
    if bool(job.get('also_pdf')) and str(body['format']).lower() != 'pdf':
        pdf_body = dict(body); pdf_body['format'] = 'pdf'
        s2, pdf = doc_post('/api/create', pdf_body, timeout=1200)
        if s2 == 200 and isinstance(pdf, dict) and pdf.get('ok'):
            results.append(pdf)
    return {'route': 'document', 'quality_mode': 'legacy', 'doc_type': doc_type, 'files': results, 'primary': primary}


def run_project_loop(job: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    project = bundle["project"]
    settings_wrap = bundle.get("loop_settings") if isinstance(bundle.get("loop_settings"), dict) else {}
    settings = settings_wrap.get("settings") if isinstance(settings_wrap, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    workspace = str(settings.get("workspace") or "").strip()
    if not workspace:
        raise RuntimeError("PROJECT_LOOP_WORKSPACE_MISSING")

    saved_goal = str(settings.get("goal") or "").strip()
    instruction = str(job.get("instruction") or "").strip()
    goal = saved_goal
    if instruction:
        goal = (saved_goal + "\n\nCURRENT REQUEST:\n" + instruction).strip()
    project_info = str(job.get("project_info") or "").strip()
    if project_info:
        goal = (goal + "\n\nPROJECT INFORMATION / USER EDITS:\n" + project_info).strip()
    if not goal:
        saved_text = unique_text(flatten_text(bundle.get("template")), 30000)
        goal = saved_text or str(project.get("name") or "Complete this project")

    active_router = str(job.get('router') or load_settings().get('router') or 'agape')
    loop_auto_model = True if settings.get("auto_model") is None else bool(settings.get("auto_model"))
    loop_model = str(settings.get("model") or "")
    loop_router_decision = {"router": "agape", "provider": "auto", "model": loop_model or "auto", "task": "coding"}
    if active_router == 'litellm':
        loop_router_decision = litellm_route_decision('coding')
        if str(loop_router_decision.get('provider') or '') != 'ollama':
            raise RuntimeError('ACTION_REQUIRED: LiteLLM selected a cloud model, but the recovered R8 Project Loop currently accepts local Ollama models. Choose Agape Router for this code project or configure an Ollama deployment for LiteLLM.')
        loop_auto_model = False
        loop_model = str(loop_router_decision.get('model') or '')
        if not loop_model:
            raise RuntimeError('ACTION_REQUIRED: LiteLLM did not return an Ollama model for Project Loop.')
    payload = {
        "project_id": int(project["id"]),
        "workspace": workspace,
        "goal": goal,
        "test_command": str(settings.get("test_command") or ""),
        "max_steps": int(settings.get("max_steps") or 4),
        "auto_model": loop_auto_model,
        "model": loop_model,
    }
    add_event(job["id"], "Working", "Running bounded Project Loop", progress=25)
    status, result = core_post("/api/project-loop/run", payload, timeout=1800)
    if status != 200:
        raise RuntimeError("PROJECT_LOOP_FAILED: " + json.dumps(result, ensure_ascii=False)[:1500])
    run = result.get("run") if isinstance(result, dict) else result
    overall = str((run or {}).get("overall") or (result or {}).get("overall") or "").upper() if isinstance(run, dict) or isinstance(result, dict) else ""
    if overall == "FAIL":
        raise RuntimeError("PROJECT_LOOP_REPORTED_FAIL: " + json.dumps(run, ensure_ascii=False)[:1500])
    update_progress(job['id'], 90)
    return {"route": "project_loop", "run": run, "response": result, "workspace": workspace, "router": loop_router_decision}


def execute_job(job_id: str) -> None:
    """Execute only the capability path selected for this job.

    Document jobs do not probe the Work Engine or unrelated services. Project
    Loop jobs do not start/check Document Studio. This keeps the selected
    workflow fast and removes legacy branches once a route is known.
    """
    try:
        job = get_job(job_id)
        if not job:
            return
        update_job(job_id, status="RUNNING", started_at=now_iso(), progress=max(5, _progress_value(job.get("progress"))))
        add_event(job_id, "Preparing", "Loading the selected source", progress=8)
        add_event(job_id, "Preparing", "AI router: " + str(job.get('router') or load_settings().get('router') or 'agape'), progress=10)
        intake = get_intake(str(job.get('intake_id') or '')) if job.get('intake_id') else None

        if int(job.get('project_id') or 0) > 0:
            bundle = get_project_bundle(int(job['project_id']))
        elif intake:
            bundle = {
                'project': {'id': 0, 'name': str(intake.get('project_name') or 'Agape Document'), 'kind': 'document'},
                'template': {}, 'loop_settings': {'settings': {}}, 'loop_runs': {'runs': []}, 'messages': {'messages': []}
            }
        else:
            raise RuntimeError('PROJECT_OR_SOURCE_DOCUMENT_REQUIRED')

        project = bundle['project']
        template = template_by_id(str(job.get('template_id') or 'auto'))
        if intake:
            route, reason = 'document', 'Prepared source and AI-completed brief'
        else:
            route, reason = determine_route(project, bundle, str(job.get('instruction') or ''), template, str(job.get('project_info') or ''))
        update_job(job_id, route=route, route_reason=reason, project_name=project.get('name'), work_probe=None)
        add_event(job_id, "Preparing", f"Route selected: {route} — {reason}", progress=15)

        if route == "document":
            # The chosen path needs only Document Studio. Do not probe or queue
            # work on Core/Work Engine again after intake preparation.
            dstatus, dpayload = doc_get('/api/health', timeout=4)
            if dstatus != 200 or not isinstance(dpayload, dict) or dpayload.get('ok', True) is False:
                raise RuntimeError('DOCUMENT_STUDIO_UNAVAILABLE')
            result = run_document(get_job(job_id) or job, bundle, template)
        elif route == "project_loop":
            core_status, _ = http_json("GET", CORE_URL + "/api/version", timeout=4)
            if core_status != 200:
                raise RuntimeError('CORE_SERVICE_UNAVAILABLE')
            work_probe = None
            work_status, work_payload = http_json("GET", WORK_URL + "/api/health", timeout=4)
            if work_status == 200 and isinstance(work_payload, dict) and work_payload.get('ok', True) is not False:
                try:
                    add_event(job_id, 'Preparing', 'Checking background work service')
                    work_probe = submit_work_health_probe()
                except Exception as probe_error:
                    add_event(job_id, 'Preparing', 'Background work probe unavailable; project execution can continue', 'WARN', str(probe_error))
            update_job(job_id, work_probe=work_probe)
            result = run_project_loop(get_job(job_id) or job, bundle)
        else:
            raise RuntimeError("ACTION_REQUIRED: Choose a document source or save an executable Project Loop workspace before rerunning this project.")

        add_event(job_id, "Validating", "Checking returned result", progress=96)
        if not isinstance(result, dict):
            raise RuntimeError("EXECUTOR_RETURNED_NO_RESULT")

        update_job(job_id, status="PASS", result=result, completed_at=now_iso(), message="Complete", progress=100)
        add_event(job_id, "Complete", "Project work completed", "PASS", progress=100)
    except Exception as exc:
        detail = str(exc)
        status = "BLOCKED" if detail.startswith("ACTION_REQUIRED:") else "FAIL"
        try:
            update_job(job_id, status=status, error=detail, completed_at=now_iso(), message=detail)
            add_event(job_id, "Action required" if status == "BLOCKED" else "Failed", detail, status, traceback.format_exc()[-4000:])
        except Exception:
            pass


def new_job(body: dict[str, Any]) -> dict[str, Any]:
    project_id = int(body.get('project_id') or 0)
    intake_id = str(body.get('intake_id') or '').strip()
    intake = get_intake(intake_id) if intake_id else None
    if project_id <= 0 and not intake:
        raise ValueError('PROJECT_OR_SOURCE_DOCUMENT_REQUIRED')
    project = project_by_id(project_id) if project_id > 0 else None
    if project_id > 0 and not project:
        raise ValueError('PROJECT_NOT_FOUND')
    if intake_id and not intake:
        raise ValueError('INTAKE_NOT_FOUND')
    if intake and project_id <= 0:
        project = {'id': 0, 'name': str(intake.get('project_name') or 'Agape Document')}
    job_router = str(body.get('router') or load_settings().get('router') or 'agape').lower()
    if job_router not in ROUTER_IDS:
        raise ValueError('UNSUPPORTED_ROUTER=' + job_router)
    if job_router == 'litellm':
        lite = next((x for x in router_status()['options'] if x['id'] == 'litellm'), {})
        if not lite.get('ready'):
            raise ValueError('LITELLM_ROUTER_NOT_READY')
    job_id = "AGU-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()
    row = {
        "id": job_id,
        "build": BUILD,
        "project_id": project_id,
        "project_name": project.get("name"),
        "intake_id": intake_id,
        "revision_of": str(body.get("revision_of") or ""),
        "lineage_root": str(body.get("lineage_root") or ""),
        "revision_number": max(1, int(body.get("revision_number") or 1)),
        "revision_instruction": str(body.get("revision_instruction") or "").strip(),
        "quality_mode": str(body.get("quality_mode") or "standard").lower(),
        "reviewer_count": max(2, min(10, int(body.get("reviewer_count") or load_settings().get("gold_reviewer_count") or 3))),
        "reviewer_ids": _normalise_reviewer_ids(body.get("reviewer_ids")) if "reviewer_ids" in body else _normalise_reviewer_ids(load_settings().get("gold_reviewer_ids")),
        "lead_reviewer": str(body.get("lead_reviewer") or load_settings().get("gold_lead_reviewer") or "auto").strip().lower() or "auto",
        "router": job_router,
        "instruction": str(body.get("instruction") or "").strip(),
        "project_info": str(body.get("project_info") or "").strip()[:120000],
        "template_id": str(body.get("template_id") or "auto"),
        "ui_theme": str(body.get("ui_theme") or "forest"),
        "document_theme": str(body.get("document_theme") or "Executive Navy"),
        "format": str(body.get("format") or "docx"),
        "also_pdf": bool(body.get("also_pdf", True)),
        "research_plan": dict((intake or {}).get("research_plan") or {}) if intake else {},
        "status": "QUEUED",
        "stage": "Queued",
        "message": "Queued",
        "progress": 3,
        "route": "",
        "route_reason": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "started_at": "",
        "completed_at": "",
        "events": [{"ts": now_iso(), "stage": "Queued", "status": "INFO", "message": "Work accepted", "detail": None}],
        "result": None,
        "error": "",
    }
    rows = load_jobs()
    rows.append(row)
    save_jobs(rows)
    threading.Thread(target=execute_job, args=(job_id,), daemon=True, name="AgapeUnifiedJob-" + job_id).start()
    return row


def allowed_result_files(job: dict[str, Any]) -> list[Path]:
    result = job.get("result") if isinstance(job, dict) else None
    files: list[Path] = []
    if isinstance(result, dict):
        for item in result.get("files") or []:
            if isinstance(item, dict) and item.get("file"):
                try:
                    files.append(Path(str(item["file"])).resolve())
                except Exception:
                    pass
    return files


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    size = int(handler.headers.get("Content-Length", "0") or 0)
    if size > 50 * 1024 * 1024:
        raise ValueError("REQUEST_TOO_LARGE")
    raw = handler.rfile.read(size) if size else b"{}"
    obj = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    if not isinstance(obj, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return obj


class Handler(BaseHTTPRequestHandler):
    server_version = "AgapeUnified/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _static(self, path: str) -> None:
        name = path.lstrip("/") or "index.html"
        if name == "":
            name = "index.html"
        target = (WEB_ROOT / name).resolve()
        if WEB_ROOT not in target.parents and target != WEB_ROOT:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        raw = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime in {"application/javascript", "application/json"} else ""))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/api/health":
                return send_json(self, 200, {"ok": True, "build": BUILD, "port": self.server.server_address[1], "services": get_services()})
            if u.path == "/api/services":
                return send_json(self, 200, {"ok": True, "services": get_services()})
            if u.path == "/api/settings":
                return send_json(self, 200, {"ok": True, "settings": load_settings(), "router_status": router_status()})
            if u.path == "/api/router/status":
                return send_json(self, 200, router_status())
            if u.path == "/api/templates":
                return send_json(self, 200, {"ok": True, "templates": load_templates()})
            if u.path == "/api/quality-status":
                return send_json(self, 200, quality_status())
            if u.path == "/api/research/sources":
                return send_json(self, 200, research_router.all_source_status())
            if u.path == "/api/research/recommend":
                text = str((q.get("q") or [""])[0])
                return send_json(self, 200, research_router.recommend_sources(text, 10))
            if u.path.startswith("/api/intakes/"):
                intake_id = u.path.strip("/").split("/")[2]
                row = get_intake(intake_id)
                return send_json(self, 200 if row else 404, {"ok": bool(row), "intake": row} if row else {"error": "INTAKE_NOT_FOUND"})
            if u.path == "/api/projects":
                rows = [x for x in get_projects() if not bool(x.get("archived")) and str(x.get("kind") or "user") == "user"]
                return send_json(self, 200, {"ok": True, "projects": rows})
            if u.path == "/api/project":
                pid = int((q.get("project_id") or ["0"])[0])
                return send_json(self, 200, {"ok": True, **get_project_bundle(pid)})
            if u.path == "/api/jobs":
                limit = min(100, max(1, int((q.get("limit") or ["50"])[0])))
                return send_json(self, 200, {"ok": True, "jobs": list(reversed(load_jobs()))[:limit]})
            if u.path.startswith("/api/jobs/") and u.path.endswith("/download"):
                parts = u.path.strip("/").split("/")
                job_id = parts[2]
                index = int((q.get("index") or ["0"])[0])
                job = get_job(job_id)
                if not job:
                    return send_json(self, 404, {"error": "JOB_NOT_FOUND"})
                files = allowed_result_files(job)
                if index < 0 or index >= len(files):
                    return send_json(self, 404, {"error": "RESULT_FILE_NOT_FOUND"})
                target = files[index]
                if not target.exists() or not target.is_file():
                    return send_json(self, 404, {"error": "RESULT_FILE_MISSING_ON_DISK", "path": str(target)})
                raw = target.read_bytes()
                mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Disposition", f'attachment; filename="{target.name.replace(chr(34), "")}"')
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if u.path.startswith("/api/jobs/"):
                job_id = u.path.strip("/").split("/")[2]
                job = get_job(job_id)
                return send_json(self, 200 if job else 404, {"ok": bool(job), "job": job} if job else {"error": "JOB_NOT_FOUND"})
            if u.path == "/api/advanced/work-status":
                status, payload = http_json("GET", WORK_URL + "/api/status", timeout=5)
                return send_json(self, 200 if status == 200 else 502, {"ok": status == 200, "status": status, "work": payload})
            if u.path == "/":
                return self._static("index.html")
            if u.path.startswith("/web/"):
                return self._static(u.path[len("/web/"):])
            return self._static(u.path)
        except Exception as exc:
            return send_json(self, 500, {"error": str(exc), "type": type(exc).__name__})

    def do_POST(self) -> None:
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == "/api/settings":
                body = read_body(self)
                saved = save_settings(body)
                return send_json(self, 200, {"ok": True, "settings": saved, "router_status": router_status()})
            if u.path == "/api/router/test":
                body = read_body(self)
                return send_json(self, 200, test_router(str(body.get("router") or "") or None))
            if u.path == "/api/router/install-litellm":
                return send_json(self, 200, install_litellm())
            if u.path == "/api/research/credential-support/install":
                return send_json(self, 200, research_router.install_credential_support())
            if u.path == "/api/research/connect":
                body = read_body(self)
                result = research_router.save_secret(str(body.get("source_id") or ""), str(body.get("secret") or ""))
                return send_json(self, 200, {**result, "status": research_router.all_source_status()})
            if u.path == "/api/research/disconnect":
                body = read_body(self)
                result = research_router.delete_secret(str(body.get("source_id") or ""))
                return send_json(self, 200, {**result, "status": research_router.all_source_status()})
            if u.path == "/api/research/test":
                body = read_body(self)
                return send_json(self, 200, research_router.connector_test(str(body.get("source_id") or "")))
            if u.path == "/api/document/intake":
                row = create_document_intake(read_body(self))
                return send_json(self, 200, {"ok": True, "intake": row})
            if u.path.startswith("/api/intakes/") and u.path.endswith("/project"):
                intake_id = u.path.strip("/").split("/")[2]
                payload = read_body(self)
                row = set_intake_project(intake_id, int(payload.get("project_id") or 0), str(payload.get("project_name") or ""))
                return send_json(self, 200, {"ok": True, "intake": row})
            if u.path.startswith("/api/intakes/") and u.path.endswith("/improve"):
                intake_id = u.path.strip("/").split("/")[2]
                row = improve_intake_with_ai(intake_id)
                return send_json(self, 200, {"ok": True, "intake": row})
            if u.path.startswith("/api/intakes/") and u.path.endswith("/answers"):
                intake_id = u.path.strip("/").split("/")[2]
                body = read_body(self)
                row = apply_intake_answers(intake_id, body.get("answers") if isinstance(body.get("answers"), dict) else {})
                return send_json(self, 200, {"ok": True, "intake": row})
            if u.path.startswith("/api/intakes/") and u.path.endswith("/revise"):
                intake_id = u.path.strip("/").split("/")[2]
                payload = read_body(self)
                row = revise_intake_with_ai(intake_id, str(payload.get("instruction") or ""))
                return send_json(self, 200, {"ok": True, "intake": row})
            if u.path == "/api/jobs":
                row = new_job(read_body(self))
                return send_json(self, 202, {"ok": True, "job": row, "job_id": row["id"], "status_url": "/api/jobs/" + row["id"]})
            if u.path.startswith("/api/jobs/") and u.path.endswith("/revise"):
                job_id = u.path.strip("/").split("/")[2]
                payload = read_body(self)
                row = revise_job_with_ai(job_id, str(payload.get("instruction") or ""), str(payload.get("quality_mode") or ""))
                return send_json(self, 202, {"ok": True, "job": row, "job_id": row["id"], "revision_of": job_id})
            if u.path.startswith("/api/jobs/") and u.path.endswith("/retry"):
                job_id = u.path.strip("/").split("/")[2]
                old = get_job(job_id)
                if not old:
                    return send_json(self, 404, {"error": "JOB_NOT_FOUND"})
                override = read_body(self)
                row = new_job({
                    "project_id": old.get("project_id"), "instruction": old.get("instruction"), "template_id": old.get("template_id"),
                    "ui_theme": old.get("ui_theme"), "document_theme": old.get("document_theme"), "format": old.get("format"), "also_pdf": old.get("also_pdf"),
                    "intake_id": old.get("intake_id"), "quality_mode": override.get("quality_mode") or old.get("quality_mode"), "project_info": old.get("project_info"),
                    "reviewer_count": override.get("reviewer_count") or old.get("reviewer_count"),
                    "reviewer_ids": override.get("reviewer_ids") if "reviewer_ids" in override else old.get("reviewer_ids"),
                    "lead_reviewer": override.get("lead_reviewer") or old.get("lead_reviewer"),
                    "router": override.get("router") or old.get("router") or load_settings().get('router')
                })
                return send_json(self, 202, {"ok": True, "job": row, "retried_from": job_id})
            if u.path == "/api/open-result":
                body = read_body(self)
                job = get_job(str(body.get("job_id") or ""))
                index = int(body.get("index") or 0)
                if not job:
                    return send_json(self, 404, {"error": "JOB_NOT_FOUND"})
                files = allowed_result_files(job)
                if index < 0 or index >= len(files):
                    return send_json(self, 404, {"error": "RESULT_FILE_NOT_FOUND"})
                target = files[index]
                status, payload = http_json("POST", DOC_URL + "/api/open-file", body={"path": str(target)}, timeout=10)
                return send_json(self, 200 if status == 200 else 502, {"ok": status == 200, "result": payload, "path": str(target)})
            if u.path == "/api/open-result-folder":
                body = read_body(self)
                job = get_job(str(body.get("job_id") or ""))
                index = int(body.get("index") or 0)
                if not job:
                    return send_json(self, 404, {"error": "JOB_NOT_FOUND"})
                files = allowed_result_files(job)
                if index < 0 or index >= len(files):
                    return send_json(self, 404, {"error": "RESULT_FILE_NOT_FOUND"})
                target = files[index]
                if not target.exists() or not target.is_file():
                    return send_json(self, 404, {"error": "RESULT_FILE_MISSING_ON_DISK", "path": str(target)})
                if os.environ.get("AGAPE_QA_NO_EXTERNAL_OPEN", "").strip() == "1":
                    return send_json(self, 200, {"ok": True, "simulated": True, "path": str(target), "folder": str(target.parent)})
                try:
                    if os.name == "nt":
                        subprocess.Popen(["explorer.exe", "/select," + str(target)])
                    elif sys.platform == "darwin":
                        subprocess.Popen(["open", "-R", str(target)])
                    else:
                        subprocess.Popen(["xdg-open", str(target.parent)])
                    return send_json(self, 200, {"ok": True, "path": str(target), "folder": str(target.parent)})
                except Exception as exc:
                    return send_json(self, 500, {"error": "OPEN_RESULT_FOLDER_FAILED: " + str(exc), "path": str(target)})
            return send_json(self, 404, {"error": "NOT_FOUND"})
        except ValueError as exc:
            return send_json(self, 400, {"error": str(exc)})
        except Exception as exc:
            return send_json(self, 500, {"error": str(exc), "type": type(exc).__name__})


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
    print(f"AGAPE_UNIFIED_READY=http://127.0.0.1:{port}", flush=True)
    print(f"BUILD={BUILD}", flush=True)
    print(f"DATA_ROOT={DATA_ROOT}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    serve(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
