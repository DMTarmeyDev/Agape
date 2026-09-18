from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from agape_mainframe import service_runtime


def test_source_service_command_uses_python_and_script_path():
    with patch.object(service_runtime, "is_frozen", return_value=False):
        command = service_runtime.service_command("workflow-bridge", "--port", "9999")
    assert command[0] == sys.executable
    assert Path(command[1]).resolve() == service_runtime.service_source_path("workflow-bridge").resolve()
    assert command[-2:] == ["--port", "9999"]


def test_frozen_service_command_relaunches_agape_not_python_script():
    with patch.object(service_runtime, "is_frozen", return_value=True):
        command = service_runtime.service_command("document-studio", "--port", "9998")
    assert command == [
        sys.executable,
        service_runtime.INTERNAL_SERVICE_FLAG,
        "document-studio",
        "--port",
        "9998",
    ]
    assert "document_studio.py" not in " ".join(command)


def test_service_environment_uses_writable_mainframe_data(tmp_path: Path):
    with patch.object(service_runtime, "DATA_ROOT", tmp_path):
        doc = service_runtime.service_environment_overrides("document-studio")
        workflow = service_runtime.service_environment_overrides("workflow-bridge")
    assert Path(doc["AGAPE_DOCUMENT_DATA"]) == tmp_path / "services" / "document-studio"
    assert Path(doc["AGAPE_DOCUMENT_SETTINGS"]) == tmp_path / "services" / "document-studio" / "settings.json"
    assert Path(workflow["AGAPE_UNIFIED_DATA"]) == tmp_path / "services" / "workflow-r24"


def test_internal_service_runner_restores_process_context(tmp_path: Path):
    script = tmp_path / "app.py"
    output = tmp_path / "seen.txt"
    script.write_text(
        "import os,sys,pathlib\n"
        f"pathlib.Path({str(output)!r}).write_text(os.getcwd()+'\\n'+'|'.join(sys.argv[1:])+'\\n'+os.environ.get('AGAPE_UNIFIED_DATA',''))\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    old_cwd = Path.cwd()
    old_env = os.environ.get("AGAPE_UNIFIED_DATA")
    with patch.dict(service_runtime.SERVICE_SOURCES, {"workflow-bridge": script}, clear=False), patch.object(service_runtime, "DATA_ROOT", tmp_path / "data"):
        code = service_runtime.run_internal_service("workflow-bridge", ["--port", "1234"])
    assert code == 7
    lines = output.read_text(encoding="utf-8").splitlines()
    assert Path(lines[0]) == tmp_path
    assert lines[1] == "--port|1234"
    assert Path(lines[2]) == tmp_path / "data" / "services" / "workflow-r24"
    assert Path.cwd() == old_cwd
    assert os.environ.get("AGAPE_UNIFIED_DATA") == old_env


def test_non_service_arguments_are_not_intercepted():
    assert service_runtime.dispatch_internal_service(["--no-browser"]) is None
