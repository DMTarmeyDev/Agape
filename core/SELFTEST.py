from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
sandbox = Path(tempfile.mkdtemp(prefix="dmt-core-v1-selftest-"))
os.environ["DMT_DATA_ROOT"] = str(sandbox / "data")
sys.path.insert(0, str(root))

try:
    import db
    import tools
    import system_test
    import workflows
    import project_loop

    db.init_db()
    status = db.status()
    assert status["ok"] is True
    assert status["counts"] == {
        "projects": 0,
        "messages": 0,
        "connections": 0,
        "chat_requests": 0,
        "terminal_jobs": 0,
        "project_loop_settings": 0,
        "project_loop_runs": 0,
        "project_loop_steps": 0,
        "autodev_sessions": 0,
        "model_outcomes": 0,
        "run_ledger": 0,
        "test_observations": 0,
        "supervisor_runs": 0,
        "deferred_work": 0,
        "audit_events": 0,
        "alpha_release_runs": 0,
    }

    raw = '{"name":"shell","arguments":{"cmd":"Write-Output \'DMT_CORE_SELFTEST_OK\'"}}'
    fenced = "```json\n" + raw + "\n```"
    assert tools.parse_tool_call(raw).source_format == "json"
    assert tools.parse_tool_call(fenced).source_format == "fenced_json"
    assert tools.parse_tool_call("before " + raw) is None
    assert tools.parse_tool_call(raw + " after") is None
    assert tools.parse_tool_call('{"name":"unknown","arguments":{"cmd":"x"}}') is None
    assert tools.explicit_action("Create the test file now") is True
    # A safety/format constraint must not cancel an explicit execution request.
    assert tools.explicit_action("Create the test file now. Do not merely print PowerShell.") is True
    assert tools.explicit_action("Create and read the test file. Do not claim PASS unless the shell returns the contents.") is True
    # An actual denial of execution must still win.
    assert tools.explicit_action("Do not execute anything, explain only") is False
    assert tools.explicit_action("Do not create the file; explain only") is False
    assert tools.explicit_action("Without running anything, explain the command") is False
    assert tools.explicit_action("How do I create a file in PowerShell?") is False
    assert tools.explicit_action("Show me how to delete a file") is False
    assert tools.explicit_action("Give me the PowerShell code to create a file") is False
    assert tools.explicit_action("Can you create the test file now?") is True
    assert tools.analyze_command("Write-Output 'OK'").allowed is True
    assert tools.analyze_command("bcdedit /enum").allowed is False
    assert tools.analyze_command("Set-Content app.py x").allowed is False
    assert tools.analyze_command("Set-Content config.py x").allowed is False
    assert tools.analyze_command("Set-Content manifest.json x").allowed is False
    assert tools.analyze_command("Set-Content system_test.py x").allowed is False
    assert tools.analyze_command("Set-Content project_loop.py x").allowed is False
    assert tools.analyze_command("Set-Content workflows.py x").allowed is False
    assert [x['id'] for x in workflows.list_templates()] == ['system-stress','snake-game']
    assert '<canvas' in workflows.SNAKE_HTML
    assert "localStorage.setItem('dmt-snake-best'" in workflows.SNAKE_HTML

    # Project Loop static/safety checks.
    choice = project_loop.auto_select_model(["qwen2.5-coder:1.5b-instruct", "qwen2.5-coder:7b"], task="Fix failing project tests")
    assert choice["model"] == "qwen2.5-coder:7b"
    workspace = sandbox / "project-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "main.py").write_text("print('ok')\n", encoding="utf-8")
    assert project_loop.validate_workspace(str(workspace)) == workspace.resolve()
    assert project_loop.safe_file(workspace.resolve(), "main.py", must_exist=True).name == "main.py"
    try:
        project_loop.safe_file(workspace.resolve(), "../escape.txt")
        raise AssertionError("PATH_TRAVERSAL_NOT_BLOCKED")
    except ValueError as exc:
        assert "TRAVERSAL" in str(exc)
    assert project_loop.validate_test_command('python -m pytest -q') == 'python -m pytest -q'
    try:
        project_loop.validate_test_command('python -m pytest -q; Remove-Item x')
        raise AssertionError("UNSAFE_TEST_COMMAND_NOT_BLOCKED")
    except ValueError:
        pass

    # Crash recovery must turn prior running requests into interrupted records.
    p = db.create_project("Recovery Probe")
    db.start_request("SELFTEST-ABANDONED", int(p["id"]), "ollama", "test-model")
    assert db.recover_incomplete_requests() == 1
    recovered = db.row("SELECT status,stage,error FROM chat_requests WHERE request_id=?", ("SELFTEST-ABANDONED",))
    assert recovered == {"status": "interrupted", "stage": "INTERRUPTED_RESTART", "error": "PROCESS_RESTARTED"}
    db.delete_project(int(p["id"]))

    terminal = "SKIP_NON_WINDOWS"
    if os.name == "nt":
        result = tools.run_powershell("Write-Output 'DMT_CORE_SELFTEST_OK'")
        assert result["executed"] is True
        assert result["exit_code"] == 0
        assert result["stdout"].strip() == "DMT_CORE_SELFTEST_OK"
        terminal = "PASS"

    print("DMT_CORE_V1_SELFTEST=PASS")
    print("FRESH_DATABASE=PASS")
    print("RAW_JSON_TOOL=PASS")
    print("WHOLE_FENCED_JSON_TOOL=PASS")
    print("PROSE_JSON_REJECT=PASS")
    print("UNKNOWN_TOOL_REJECT=PASS")
    print("AUTHORIZATION_CONSTRAINT_REGRESSION=PASS")
    print("EXPLICIT_DENIAL_REGRESSION=PASS")
    print("INFORMATIONAL_ACTION_REGRESSION=PASS")
    print("CRASH_REQUEST_RECOVERY=PASS")
    print("PROTECTED_COMMAND_BLOCK=PASS")
    print("SOURCE_CHANGE_BLOCK=PASS")
    print("FIRST_RUN_SYSTEM_TEST_MODULE=PASS")
    print("TEMPLATE_CATALOG=PASS")
    print("SNAKE_PAYLOAD_STATIC=PASS")
    print("PROJECT_LOOP_MODEL_ROUTER=PASS")
    print("PROJECT_LOOP_WORKSPACE_GUARD=PASS")
    print("PROJECT_LOOP_TEST_COMMAND_GUARD=PASS")
    print("TERMINAL_SELFTEST=" + terminal)
finally:
    shutil.rmtree(sandbox, ignore_errors=True)
