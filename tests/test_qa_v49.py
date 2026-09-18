from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from agape_mainframe import browser_qa, desktop_qa


def test_browser_qa_status_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_qa, "QA_ROOT", tmp_path)
    monkeypatch.setattr(browser_qa, "LAST_REPORT", tmp_path / "latest.json")
    out=browser_qa.status()
    assert out["ok"] is True
    assert "playwright_python" in out
    assert out["modes"][0]["id"]=="safe"


def test_browser_qa_last_report(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_qa, "QA_ROOT", tmp_path)
    monkeypatch.setattr(browser_qa, "LAST_REPORT", tmp_path / "latest.json")
    (tmp_path / "latest.json").write_text(json.dumps({"status":"PASS","pass_count":4}),encoding="utf-8")
    assert browser_qa.status()["last_report"]["status"]=="PASS"


def test_desktop_status_contract():
    out=desktop_qa.status()
    assert out["ok"] is True
    assert "pywinauto" in out
    assert "vscode_ready" in out


def test_desktop_probe_rejects_non_windows():
    if desktop_qa.os.name != "nt":
        try:
            desktop_qa.probe("vscode")
        except RuntimeError as exc:
            assert "WINDOWS_ONLY" in str(exc)
        else:
            raise AssertionError("expected Windows-only guard")


def test_coding_launch_returns_pid(monkeypatch):
    from agape_mainframe import coding_tools
    class P:
        pid=4321
    monkeypatch.setattr(coding_tools.subprocess,"Popen",lambda *a,**k:P())
    with patch.object(Path,"exists",return_value=True):
        out=coding_tools._launch("fake-editor.exe","")
    assert out["pid"]==4321
