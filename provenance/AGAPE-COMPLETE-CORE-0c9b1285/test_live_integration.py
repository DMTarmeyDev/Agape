from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = "DMT-CORE-V3.1-EARLY-ALPHA-R1"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class FakeOllamaHandler(BaseHTTPRequestHandler):
    chat_count = 0

    def log_message(self, fmt, *args):
        return

    def _json(self, value, status=200):
        raw = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json({"models": [
                {"name": "qwen2.5-coder:1.5b-instruct"},
                {"name": "qwen2.5-coder:7b"},
            ]})
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/api/chat":
            self._json({"error": "not found"}, 404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        FakeOllamaHandler.chat_count += 1
        call = FakeOllamaHandler.chat_count
        if call == 1:
            action = {"action": "inspect", "paths": ["main.py", "test_value.py"]}
        elif call == 2:
            action = {"action": "write_file", "path": "main.py", "content": "VALUE = 2\n", "reason": "Repair failing value test"}
        else:
            action = {"action": "done", "summary": "Goal complete and tests pass."}
        self._json({"message": {"role": "assistant", "content": json.dumps(action)}})


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(url: str, body: dict, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-DMT-Session"] = token
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


sandbox = Path(tempfile.mkdtemp(prefix="dmt-v14-live-"))
proc = None
fake = None
try:
    data = sandbox / "data"
    workflow = sandbox / "workflow"
    workspace = sandbox / "project"
    data.mkdir(parents=True)
    workspace.mkdir(parents=True)
    (workspace / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "test_value.py").write_text("from main import VALUE\nassert VALUE == 2, f'VALUE={VALUE}'\nprint('AUTODEV_TEST_PASS')\n", encoding="utf-8")
    (data / "install-receipt.json").write_text(json.dumps({
        "isolated_real_chat_to_terminal": True,
        "isolated_real_readback": True,
        "template_1_preflight": True,
        "template_2_preflight": True,
        "project_loop_preflight": True,
        "preflight_model": "qwen2.5-coder:7b",
        "package_sha256": "LIVE-INTEGRATION-MOCK",
        "source": "live-integration-mock",
    }), encoding="utf-8")

    fake_port = free_port()
    fake = ThreadingHTTPServer(("127.0.0.1", fake_port), FakeOllamaHandler)
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()

    app_port = free_port()
    env = os.environ.copy()
    env["DMT_DATA_ROOT"] = str(data)
    env["DMT_WORKFLOW_ROOT"] = str(workflow)
    env["DMT_OLLAMA_URL"] = f"http://127.0.0.1:{fake_port}"
    proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "app.py"), "--port", str(app_port)], cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    base = f"http://127.0.0.1:{app_port}"

    version = None
    for _ in range(80):
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=2)
            raise AssertionError(f"APP_EXITED rc={proc.returncode} out={out[-1000:]} err={err[-1000:]}")
        try:
            version = get_json(base + "/api/version")
            break
        except Exception:
            time.sleep(0.1)
    assert version and version["build"] == BUILD, version

    token_path = data / "security" / "local-session-token.txt"
    token = token_path.read_text(encoding="utf-8").strip()
    assert len(token) >= 32

    # Security boundary: mutating API must reject missing session token.
    try:
        post_json(base + "/api/projects/create", {"name": "Should Fail"})
        raise AssertionError("UNAUTHENTICATED_POST_ALLOWED")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403, exc.code

    project = post_json(base + "/api/projects/create", {"name": "Live AutoDev Integration"}, token)["project"]
    test_command = f'"{sys.executable}" test_value.py'
    run = post_json(base + "/api/project-loop/run", {
        "project_id": int(project["id"]),
        "workspace": str(workspace),
        "goal": "Fix the failing project test by changing VALUE to 2, then finish only when the test passes.",
        "test_command": test_command,
        "max_steps": 3,
        "auto_model": True,
        "model": "",
    }, token)["run"]

    assert run["ok"] is True, run
    assert run["overall"] == "PASS", run
    assert run["model"] == "qwen2.5-coder:7b", run
    assert (workspace / "main.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert run["test"]["ok"] is True, run["test"]
    assert run["test"].get("job_id", "").startswith("TERM-")

    history = get_json(base + "/api/terminal/history")["history"]
    project_jobs = [x for x in history if int(x.get("project_id") or 0) == int(project["id"])]
    assert len(project_jobs) >= 3, project_jobs
    assert all(x.get("risk") == "project_test" for x in project_jobs[:3]), project_jobs[:3]

    loop_runs = get_json(base + f"/api/project-loop/runs?project_id={project['id']}")["runs"]
    assert loop_runs and loop_runs[0]["status"] == "PASS", loop_runs

    system = get_json(base + "/api/system-test")
    assert system["ok"] is True, system
    assert system["overall"] == "PASS", system

    print("LIVE_HTTP_CORE_START=PASS")
    print("LIVE_SESSION_SECURITY_403=PASS")
    print("LIVE_PROJECT_CREATE=PASS")
    print("LIVE_AUTO_MODEL_7B=PASS")
    print("LIVE_FAIL_TO_AI_REPAIR=PASS")
    print("LIVE_TERMINAL_TEST_HISTORY=PASS")
    print("LIVE_PROJECT_LOOP_DATABASE=PASS")
    print(f"LIVE_SYSTEM_TEST={system['passed']}/{system['total']} PASS")
    print("LIVE_INTEGRATION=PASS")
finally:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    if fake is not None:
        fake.shutdown()
        fake.server_close()
    shutil.rmtree(sandbox, ignore_errors=True)
