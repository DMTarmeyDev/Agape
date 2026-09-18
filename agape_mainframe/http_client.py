from __future__ import annotations
import json, os, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from typing import Any


def _request_json_once(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 10, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    merged = {"Accept":"application/json", "User-Agent":"Agape-Mainframe-V1/1.0"}
    if data is not None:
        merged["Content-Type"]="application/json"
    if headers:
        merged.update({str(k):str(v) for k,v in headers.items() if str(k).strip()})
    req = urllib.request.Request(url, data=data, headers=merged, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw=r.read()
            try:return int(r.status), json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except Exception:return int(r.status), {"text": raw.decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as e:
        raw=e.read()
        try:payload=json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except Exception:payload={"error":raw.decode("utf-8", errors="replace")}
        return int(e.code), payload
    except Exception as e:
        return 0, {"error":str(e), "type":type(e).__name__}


def _is_loopback(url: str) -> bool:
    try:
        host=(urllib.parse.urlparse(url).hostname or "").strip().lower()
        return host in {"127.0.0.1","localhost","::1"}
    except Exception:
        return False


def _session_required(status: int, payload: Any) -> bool:
    if int(status or 0) != 403:
        return False
    if isinstance(payload,dict):
        detail=" ".join(str(payload.get(k) or "") for k in ("error","message","detail","code"))
    else:
        detail=str(payload or "")
    detail=detail.upper()
    return "SESSION_REQUIRED" in detail or "LOCAL_SESSION_TOKEN_REQUIRED" in detail


def _local_core_session_headers(timeout: int = 4) -> dict[str,str]:
    """Read the existing Core session token server-side only.

    This deliberately never exposes the token to the browser. It is used only for
    loopback Mainframe -> local-service retries when a protected legacy endpoint
    answers with SESSION_REQUIRED.
    """
    core_url=str(os.environ.get("AGAPE_CORE_URL") or "http://127.0.0.1:8797").rstrip("/")
    status,payload=_request_json_once("GET",core_url+"/api/version",timeout=timeout)
    if status!=200 or not isinstance(payload,dict):
        return {}
    data_path=str(payload.get("data_path") or "").strip()
    if not data_path:
        return {}
    try:
        token=(Path(data_path)/"security"/"local-session-token.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return {}
    if len(token)<20:
        return {}
    return {"X-DMT-Session":token}


def request_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 10, headers: dict[str,str] | None = None) -> tuple[int, Any]:
    """JSON HTTP helper with one safe local-session compatibility retry.

    Normal Mainframe browser calls remain sessionless. Only server-side calls to a
    loopback child service can receive the Core local-session header, and only after
    that service explicitly rejects the first request with SESSION_REQUIRED.
    """
    status,payload=_request_json_once(method,url,body=body,timeout=timeout,headers=headers)
    if method.upper() in {"GET","HEAD","OPTIONS"} or not _is_loopback(url) or not _session_required(status,payload):
        return status,payload
    retry_headers=dict(headers or {})
    retry_headers.update(_local_core_session_headers())
    if "X-DMT-Session" not in retry_headers:
        return status,payload
    return _request_json_once(method,url,body=body,timeout=timeout,headers=retry_headers)
