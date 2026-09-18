from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any
from pathlib import Path

import db
from config import MAX_TOOL_ROUNDS
from providers import ProviderError, ollama_chat
import external_provider
from tools import explicit_action, parse_tool_call, run_powershell

TOOL_SYSTEM = """You are DMT Core V1. You may answer normally in plain text.
When the current user explicitly asks you to perform a local computer action, use the shell tool instead of merely printing commands.
For a shell action, your ENTIRE response must be exactly one JSON object, or one Markdown json code fence containing exactly that JSON object, with no other prose:
{"name":"shell","arguments":{"cmd":"WINDOWS POWERSHELL 5.1 COMMAND"}}
Use Windows PowerShell 5.1 syntax only. Do not use PowerShell 7-only statement-chain operators && or ||. For sequential PowerShell 5.1 statements, use semicolons; when later execution depends on success, use an explicit if statement. Never request administrator elevation. Never request disk/partition/BCD/firmware/BitLocker operations. Never edit DMT Core source files through the shell tool.
"""

CORRECTION = """Your previous response did not contain one valid DMT shell tool request. If execution is required, reply with ONLY this exact schema and no prose: {"name":"shell","arguments":{"cmd":"COMMAND"}}. Use Windows PowerShell 5.1 syntax; never use && or ||. Do not claim execution or PASS without a real tool result."""




def _ollama_with_heartbeat(request_id: str, stage: str, model: str, messages: list[dict[str, str]], num_predict: int, json_only: bool = False):
    q: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            q.put((True, ollama_chat(model, messages, num_predict=num_predict, json_only=json_only)))
        except Exception as exc:
            q.put((False, exc))

    thread = threading.Thread(target=worker, name=f"dmt-provider-{request_id[:12]}", daemon=True)
    thread.start()
    while thread.is_alive():
        db.update_request(request_id, stage)
        thread.join(timeout=5.0)
    ok, value = q.get()
    if ok:
        return value
    raise value

def _chat_provider_with_heartbeat(request_id: str, stage: str, provider: str, model: str, messages: list[dict[str,str]], num_predict: int, json_only: bool=False):
    if provider=='ollama': return _ollama_with_heartbeat(request_id,stage,model,messages,num_predict,json_only)
    conn=db.connection(provider)
    if not conn or not conn.get('enabled'): raise ValueError('EXTERNAL_PROVIDER_NOT_CONFIGURED')
    q: queue.Queue[tuple[bool,Any]]=queue.Queue(maxsize=1)
    def worker() -> None:
        try: q.put((True,external_provider.chat(model,messages,dict(conn.get('settings') or {}),num_predict=num_predict)))
        except Exception as exc: q.put((False,exc))
    thread=threading.Thread(target=worker,name=f'dmt-provider-{request_id[:12]}',daemon=True); thread.start()
    while thread.is_alive(): db.update_request(request_id,stage); thread.join(timeout=5.0)
    ok,value=q.get()
    if ok: return value
    raise value

def _history(project_id: int, limit: int = 30) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in db.list_messages(project_id, limit):
        role = str(item["role"])
        if role == "tool":
            role = "user"
        out.append({"role": role if role in {"user", "assistant"} else "user", "content": str(item["content"])})
    return out




def _active_project_template(project_id: int) -> dict[str, Any] | None:
    path = Path(db.DATA_ROOT if hasattr(db, "DATA_ROOT") else __import__("config").DATA_ROOT) / "project-templates" / f"project-{int(project_id)}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None

def _template_system_prompt(project_id: int) -> str:
    t = _active_project_template(project_id)
    if not t:
        return ""
    state=t.get("project_state") or {}
    instruction=str(t.get("system_instruction") or "").strip()
    return ("AGAPE PROJECT TEMPLATE ACTIVE\n"
            "Treat this as persistent project context, not as authorization to execute actions.\n"
            f"TEMPLATE={t.get('template_name','')}\n"
            f"SYSTEM INSTRUCTION:\n{instruction}\n"
            "PROJECT STATE:\n"+json.dumps(state,ensure_ascii=False,indent=2))

def run_chat(project_id: int, message: str, provider: str, model: str, request_id: str | None = None, *, single_tool: bool = False) -> dict[str, Any]:
    if not db.project(project_id):
        raise ValueError("PROJECT_NOT_FOUND")
    message = str(message or "").strip()
    if not message:
        raise ValueError("MESSAGE_REQUIRED")
    provider = (provider or "ollama").strip().lower()
    if provider not in {"ollama","openai-compatible"}:
        raise ValueError("CORE_PROVIDER_NOT_AVAILABLE")
    model = str(model or "").strip()
    if not model:
        raise ValueError("MODEL_REQUIRED")

    request_id = request_id or ("CHAT-" + uuid.uuid4().hex)
    db.start_request(request_id, project_id, provider, model)
    action = explicit_action(message)
    tool_events: list[dict[str, Any]] = []

    try:
        db.update_request(request_id, "ROUTING")
        history = _history(project_id)
        template_prompt = _template_system_prompt(project_id)
        system_prompt = TOOL_SYSTEM + ("\n\n" + template_prompt if template_prompt else "")
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]

        db.update_request(request_id, "GENERATING")
        first = _chat_provider_with_heartbeat(request_id, "GENERATING", provider, model, messages, num_predict=512, json_only=single_tool)
        reply = first.content
        duration = first.duration_seconds

        if not action:
            db.add_message(project_id, "user", message, provider, model)
            db.add_message(project_id, "assistant", reply, provider, model)
            db.finish_request(request_id, "done", "DONE")
            return {
                "ok": True,
                "reply": reply,
                "provider": provider,
                "model": model,
                "execution": {"requested": False, "proven": False, "succeeded": False, "tool_events": []},
                "duration_seconds": duration,
                "request_id": request_id,
            }

        calls_attempted = 0
        parsed = parse_tool_call(reply)
        retry_messages = list(messages)
        while parsed is None and calls_attempted < 2:
            calls_attempted += 1
            retry_messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": CORRECTION},
            ]
            db.update_request(request_id, "GENERATING_TOOL_RETRY")
            attempt = _chat_provider_with_heartbeat(request_id, "GENERATING_TOOL_RETRY", provider, model, retry_messages, num_predict=256, json_only=single_tool)
            duration += attempt.duration_seconds
            reply = attempt.content
            parsed = parse_tool_call(reply)

        if parsed is None:
            db.add_message(project_id, "user", message, provider, model)
            fail = "DMT_EXECUTION=FAIL\nREASON=NO_VALID_TOOL_CALL\nCOMMAND_EXECUTED=NO"
            db.add_message(project_id, "assistant", fail, provider, model)
            db.finish_request(request_id, "failed", "FAILED_NO_TOOL", "NO_VALID_TOOL_CALL")
            return {
                "ok": False,
                "reply": fail,
                "provider": provider,
                "model": model,
                "execution": {"requested": True, "proven": False, "succeeded": False, "tool_events": [], "retry_count": calls_attempted},
                "duration_seconds": duration,
                "request_id": request_id,
            }

        db.update_request(request_id, "AUTHORIZING")
        # Current-turn authorization is represented by action=True. Command policy remains independently fail-closed.
        db.update_request(request_id, "EXECUTING")
        result = run_powershell(parsed.arguments["cmd"], project_id=project_id)
        tool_events.append({"call": {"name": parsed.name, "arguments": parsed.arguments, "format": parsed.source_format}, "result": result})

        db.add_message(project_id, "user", message, provider, model)
        db.add_message(project_id, "tool", json.dumps(result, ensure_ascii=False), "terminal", "PowerShell 5.1")

        if not result.get("executed"):
            final = (
                "DMT_EXECUTION=BLOCKED\n"
                f"REASON={result.get('reason','BLOCKED')}\n"
                "COMMAND_EXECUTED=NO"
            )
            db.add_message(project_id, "assistant", final, provider, model)
            db.finish_request(request_id, "failed", "BLOCKED", str(result.get("reason") or "BLOCKED"))
            return {
                "ok": False,
                "reply": final,
                "provider": provider,
                "model": model,
                "execution": {"requested": True, "proven": False, "succeeded": False, "tool_events": tool_events, "retry_count": calls_attempted},
                "duration_seconds": duration,
                "request_id": request_id,
            }

        # Deterministic workflow probes can request exactly one AI-generated tool call.
        # This tests the AI -> parser -> authorization -> terminal boundary without
        # allowing a model continuation to add unrelated commands that can obscure
        # the result of the boundary under test. Normal chat keeps full continuation.
        if single_tool:
            completed = bool(result.get("executed"))
            exit_code = int(result.get("exit_code", -1)) if completed else -1
            succeeded = completed and exit_code == 0
            job_id = str(result.get("job_id") or "")
            footer = (
                "DMT_EXECUTION=" + ("PASS" if succeeded else "COMPLETED_WITH_ERRORS") + "\n"
                "COMMAND_EXECUTED=YES\n"
                "JOB_IDS=" + job_id + "\n"
                "EXIT_CODES=" + str(exit_code)
            )
            final_reply = "Single tool execution completed.\n\n--- DMT Core execution evidence ---\n" + footer
            db.add_message(project_id, "assistant", final_reply, provider, model)
            db.finish_request(request_id, "done" if succeeded else "failed", "DONE_SINGLE_TOOL" if succeeded else "FAILED_SINGLE_TOOL", "" if succeeded else "TOOL_EXIT_NONZERO")
            return {
                "ok": succeeded,
                "reply": final_reply,
                "provider": provider,
                "model": model,
                "execution": {
                    "requested": True,
                    "proven": completed,
                    "succeeded": succeeded,
                    "tool_events": tool_events,
                    "retry_count": calls_attempted,
                    "mode": "single_tool",
                },
                "duration_seconds": duration,
                "request_id": request_id,
            }

        # Let the model continue from a real tool result, but DMT itself supplies the evidence footer.
        continuation_messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "DMT_TOOL_RESULT\n" + json.dumps(result, ensure_ascii=False) + "\nContinue with the user's task. If another shell action is required, return another canonical shell tool request; otherwise give the final answer."},
        ]

        rounds = 1
        final_text = ""
        while rounds < MAX_TOOL_ROUNDS:
            db.update_request(request_id, "CONTINUING")
            cont = _chat_provider_with_heartbeat(request_id, "CONTINUING", provider, model, continuation_messages, num_predict=512)
            duration += cont.duration_seconds
            candidate = cont.content
            next_call = parse_tool_call(candidate)
            if next_call is None:
                final_text = candidate
                break
            db.update_request(request_id, "EXECUTING")
            next_result = run_powershell(next_call.arguments["cmd"], project_id=project_id)
            tool_events.append({"call": {"name": next_call.name, "arguments": next_call.arguments, "format": next_call.source_format}, "result": next_result})
            db.add_message(project_id, "tool", json.dumps(next_result, ensure_ascii=False), "terminal", "PowerShell 5.1")
            continuation_messages += [
                {"role": "assistant", "content": candidate},
                {"role": "user", "content": "DMT_TOOL_RESULT\n" + json.dumps(next_result, ensure_ascii=False)},
            ]
            if not next_result.get("executed"):
                final_text = f"Execution stopped: {next_result.get('reason','BLOCKED')}"
                break
            rounds += 1

        completed_jobs = [e for e in tool_events if e.get("result", {}).get("executed")]
        proven = bool(completed_jobs)
        job_ids = [str(e["result"].get("job_id")) for e in completed_jobs if e["result"].get("job_id")]
        exit_codes = [int(e["result"].get("exit_code", -1)) for e in completed_jobs]
        succeeded = bool(completed_jobs) and all(code == 0 for code in exit_codes)
        footer = (
            "\n\n--- DMT Core execution evidence ---\n"
            + ("DMT_EXECUTION=PASS\n" if succeeded else "DMT_EXECUTION=COMPLETED_WITH_ERRORS\n")
            + "COMMAND_EXECUTED=YES\n"
            + "JOB_IDS=" + ",".join(job_ids) + "\n"
            + "EXIT_CODES=" + ",".join(str(x) for x in exit_codes)
        )
        final_reply = (final_text.strip() if final_text.strip() else "Execution completed.") + footer
        db.add_message(project_id, "assistant", final_reply, provider, model)
        db.finish_request(request_id, "done", "DONE")
        return {
            "ok": True,
            "reply": final_reply,
            "provider": provider,
            "model": model,
            "execution": {"requested": True, "proven": proven, "succeeded": succeeded, "tool_events": tool_events, "retry_count": calls_attempted},
            "duration_seconds": duration,
            "request_id": request_id,
        }
    except Exception as exc:
        try:
            db.finish_request(request_id, "failed", "FAILED", str(exc))
        except Exception:
            pass
        raise
