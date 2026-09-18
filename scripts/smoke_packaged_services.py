from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except Exception:
        return 0, {}


def wait_for(url: str, predicate, seconds: float = 45.0) -> dict:
    end = time.time() + seconds
    last: dict = {}
    while time.time() < end:
        status, payload = get_json(url)
        last = payload
        if status == 200 and predicate(payload):
            return payload
        time.sleep(0.5)
    raise SystemExit(f"PACKAGED_SERVICE_SMOKE_FAILED url={url} last={last!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-url", required=True)
    parser.add_argument("--workflow-url", required=True)
    args = parser.parse_args()
    document = wait_for(args.document_url.rstrip("/") + "/api/health", lambda p: str(p.get("version") or "") == "R31.16")
    workflow = wait_for(args.workflow_url.rstrip("/") + "/api/health", lambda p: p.get("ok", True) is not False)
    print("PACKAGED_DOCUMENT_SERVICE=PASS", document.get("version"))
    print("PACKAGED_WORKFLOW_SERVICE=PASS", workflow.get("build"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
