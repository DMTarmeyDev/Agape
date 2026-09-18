from __future__ import annotations
import json, urllib.error, urllib.request
from typing import Any


def request_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 10) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Accept":"application/json", "User-Agent":"Agape-Mainframe-V1/1.0"}
    if data is not None: headers["Content-Type"]="application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
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
