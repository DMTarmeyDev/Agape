from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .state import DATA_ROOT, load_settings
from .python_runtime import is_frozen

QA_ROOT = DATA_ROOT / "qa" / "browser"
QA_ROOT.mkdir(parents=True, exist_ok=True)
LAST_REPORT = QA_ROOT / "latest.json"


def _playwright_importable() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def _browser_candidates() -> list[str]:
    out: list[str] = []
    env = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if env:
        out.append(env)
    # Prefer Playwright's own tested browser build when it is installed.
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            managed = str(pw.chromium.executable_path or "")
            if managed:
                out.append(managed)
        finally:
            pw.stop()
    except Exception:
        pass
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            out.append(p)
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", "")
        pf86 = os.environ.get("ProgramFiles(x86)", "")
        out.extend([
            str(Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(Path(local) / "Chromium" / "Application" / "chrome.exe"),
        ])
    return [p for p in dict.fromkeys(out) if p and Path(p).exists()]


def _load_last() -> dict[str, Any] | None:
    try:
        raw = json.loads(LAST_REPORT.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def status() -> dict[str, Any]:
    candidates = _browser_candidates()
    return {
        "ok": True,
        "playwright_python": _playwright_importable(),
        "browser_executable": candidates[0] if candidates else "",
        "browser_candidates": candidates,
        "report_root": str(QA_ROOT),
        "last_report": _load_last(),
        "modes": [
            {"id": "safe", "name": "Safe real-click regression", "summary": "Clicks navigation, source modes, settings, diagnostics and coding-tool controls without starting AI work or external installers."},
        ],
    }


def install_chromium() -> dict[str, Any]:
    if not _playwright_importable():
        raise RuntimeError("PLAYWRIGHT_PYTHON_NOT_INSTALLED")
    if is_frozen():
        # The packaged executable is not a Python interpreter. Run Playwright's
        # already-bundled CLI entry point in-process instead of `Agape.exe -m`.
        from playwright.__main__ import main as playwright_main
        old_argv=list(sys.argv)
        try:
            sys.argv=["playwright","install","chromium"]
            try:
                playwright_main()
            except SystemExit as exc:
                code=int(exc.code or 0) if isinstance(exc.code,(int,type(None))) else 1
                if code != 0:
                    raise RuntimeError(f"PLAYWRIGHT_CHROMIUM_INSTALL_FAILED: exit={code}")
        finally:
            sys.argv=old_argv
        return {"ok": True, "installed": "chromium"}
    p = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if p.returncode != 0:
        raise RuntimeError("PLAYWRIGHT_CHROMIUM_INSTALL_FAILED: " + (p.stderr or p.stdout)[-2000:])
    return {"ok": True, "installed": "chromium"}


def _record_step(steps: list[dict[str, Any]], name: str, fn) -> None:
    started = time.perf_counter()
    try:
        detail = fn()
        steps.append({"name": name, "status": "PASS", "ms": round((time.perf_counter() - started) * 1000), "detail": detail or ""})
    except Exception as exc:
        steps.append({"name": name, "status": "FAIL", "ms": round((time.perf_counter() - started) * 1000), "detail": f"{type(exc).__name__}: {exc}"})
        raise


def run(base_url: str = "http://127.0.0.1:8850", mode: str = "safe") -> dict[str, Any]:
    if mode != "safe":
        raise ValueError("QA_MODE_NOT_SUPPORTED")
    if not _playwright_importable():
        raise RuntimeError("PLAYWRIGHT_PYTHON_NOT_INSTALLED")

    from playwright.sync_api import sync_playwright

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = QA_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    original_settings = load_settings()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    executable = (_browser_candidates() or [""])[0] or None
    report: dict[str, Any]

    try:
        with sync_playwright() as p:
            launch_args: dict[str, Any] = {"headless": True}
            if executable:
                launch_args["executable_path"] = executable
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=False)
            page = context.new_page()
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            _record_step(steps, "open_home", lambda: page.goto(base_url, wait_until="networkidle", timeout=30000).status)
            page.screenshot(path=str(run_dir / "01-home.png"), full_page=True)
            _record_step(steps, "health_indicator", lambda: page.locator("#status").wait_for(state="visible", timeout=8000))

            def click_nav(name: str):
                page.locator(f'nav button[data-page="{name}"]').click()
                page.locator(f"#{name}.page.active").wait_for(state="visible", timeout=5000)
                return name
            for i, name in enumerate(("projects", "results", "workspace", "settings", "home"), start=2):
                _record_step(steps, f"nav_{name}", lambda n=name: click_nav(n))
                page.screenshot(path=str(run_dir / f"{i:02d}-{name}.png"), full_page=True)

            def source_mode(name: str):
                page.locator(f'.source-mode[data-source-mode="{name}"]').click()
                page.locator(f'.source-mode[data-source-mode="{name}"].selected').wait_for(state="visible", timeout=3000)
                return name
            for name in ("upload", "project", "paste"):
                _record_step(steps, f"source_mode_{name}", lambda n=name: source_mode(n))
            def workspace_todo_cycle():
                click_nav("workspace")
                page.locator("#workspaceAddTodo").click()
                page.locator("#todoInput").fill("Browser QA temporary to-do")
                page.locator("#todoForm button[type=submit]").click()
                row = page.locator("#todoList .todo-row").first
                row.wait_for(state="visible", timeout=3000)
                row.click(button="right")
                menu = page.locator("#workspaceContextMenu")
                menu.wait_for(state="visible", timeout=3000)
                menu.get_by_role("menuitem", name="Mark complete").click()
                row = page.locator("#todoList .todo-row").first
                row.wait_for(state="visible", timeout=3000)
                row.click(button="right")
                menu.wait_for(state="visible", timeout=3000)
                menu.get_by_role("menuitem", name="Delete").click()
                return "workspace todo right-click/complete/delete pass"
            _record_step(steps, "workspace_todo_cycle", workspace_todo_cycle)
            click_nav("home")


            def type_source():
                page.locator("#sourceText").fill("Agape browser QA test source. This text must not be submitted to an AI provider.")
                page.locator("#task").fill("Browser QA only. Do not run the work.")
                return page.locator("#sourceText").input_value()
            _record_step(steps, "type_source_without_submission", type_source)

            _record_step(steps, "open_settings", lambda: click_nav("settings"))
            page.locator("#settings").wait_for(state="visible", timeout=5000)

            def cycle_select(selector: str, values: list[str]):
                seen = []
                for value in values:
                    page.locator(selector).select_option(value)
                    actual = page.locator(selector).input_value()
                    if actual != value:
                        raise AssertionError(f"{selector} expected {value}, got {actual}")
                    seen.append(actual)
                return seen
            _record_step(steps, "coding_model_dropdown", lambda: cycle_select("#settingCodingModel", ["local-first", "cloud-first", "auto-coding"]))
            _record_step(steps, "coding_agent_dropdown", lambda: cycle_select("#settingCodingAgent", ["aider", "openhands", "open-interpreter", "compare", "auto"]))
            _record_step(steps, "code_manager_dropdown", lambda: cycle_select("#settingCodeManager", ["vscode", "theia-full", "theia-lite", "agape"]))

            def save_and_verify_coding():
                page.locator("#settingCodingModel").select_option(str(original_settings.get("coding_model_mode") or "auto-coding"))
                page.locator("#settingCodingAgent").select_option(str(original_settings.get("coding_agent") or "auto"))
                page.locator("#settingCodeManager").select_option(str(original_settings.get("code_manager") or "agape"))
                page.locator("#saveCodingTools").click()
                page.wait_for_timeout(500)
                res = page.request.get(base_url + "/api/setup/status")
                data = res.json()
                settings = data.get("settings") or {}
                expected = {
                    "coding_model_mode": original_settings.get("coding_model_mode") or "auto-coding",
                    "coding_agent": original_settings.get("coding_agent") or "auto",
                    "code_manager": original_settings.get("code_manager") or "agape",
                }
                for key, value in expected.items():
                    if settings.get(key) != value:
                        raise AssertionError(f"persisted {key} expected {value}, got {settings.get(key)}")
                return expected
            _record_step(steps, "save_coding_defaults_real_click", save_and_verify_coding)

            _record_step(steps, "refresh_coding_tools_real_click", lambda: (page.locator("#refreshCodingTools").click(), page.wait_for_timeout(400), "clicked")[-1])
            _record_step(steps, "coding_status_rendered", lambda: page.locator("#codingToolStatus .tool-card").count())

            def advanced_diagnostics():
                adv = page.locator("#advancedSettings")
                # The boolean HTML `open` attribute is commonly returned as an empty
                # string when present, so get_attribute("open") is not a safe truth test.
                if not bool(adv.evaluate("el => el.open")):
                    page.locator("#advancedSettings > summary").click()
                refresh_services = page.locator("#refreshServices")
                refresh_services.wait_for(state="attached", timeout=5000)

                if not refresh_services.is_visible():
                    parent_details = refresh_services.locator("xpath=ancestor::details[1]")

                    if parent_details.count() > 0:
                        summary = parent_details.locator("summary").first

                        if summary.is_visible():
                            summary.click()

                refresh_services.wait_for(state="visible", timeout=10000)
                refresh_services.click()
                page.locator("#refreshEvents").click()

                # Do not assume an async diagnostics request finishes in 600 ms.
                # Wait for the real services result to appear in the UI.
                try:
                    page.wait_for_function(
                        "() => { const el = document.querySelector('#services'); return !!(el && el.textContent && el.textContent.trim().length > 0); }",
                        timeout=10000,
                    )
                except Exception as exc:
                    raise AssertionError(
                        "services diagnostics did not render within 10 seconds"
                    ) from exc
                if not page.locator("#services").inner_text().strip():
                    raise AssertionError("services diagnostics stayed empty")
                if not page.locator("#events").inner_text().strip():
                    raise AssertionError("events diagnostics stayed empty")
                return "diagnostics populated"
            _record_step(steps, "advanced_diagnostics_real_clicks", advanced_diagnostics)

            def experience_roundtrip():
                original = str(original_settings.get("experience") or "basic")
                page.locator("#settingExperience").select_option(original)
                page.locator("#saveExperience").click()
                page.wait_for_timeout(500)
                return page.locator("#settingExperience").input_value()
            _record_step(steps, "experience_save_real_click", experience_roundtrip)

            def quality_roundtrip():
                original = str(original_settings.get("quality") or "standard")
                page.locator("#settingQuality").select_option(original)
                page.locator("#saveQuality").click()
                page.wait_for_timeout(400)
                return page.locator("#settingQuality").input_value()
            _record_step(steps, "quality_save_real_click", quality_roundtrip)

            page.screenshot(path=str(run_dir / "06-settings-final.png"), full_page=True)
            context.close()
            browser.close()

        failed = [s for s in steps if s["status"] != "PASS"]
        result_status = "PASS" if not failed and not page_errors else "FAIL"
        report = {
            "ok": result_status == "PASS",
            "status": result_status,
            "mode": mode,
            "base_url": base_url,
            "started_at": started_at,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "steps": steps,
            "pass_count": sum(1 for s in steps if s["status"] == "PASS"),
            "fail_count": sum(1 for s in steps if s["status"] != "PASS"),
            "console_errors": console_errors,
            "page_errors": page_errors,
            "artifacts_dir": str(run_dir),
            "screenshots": [str(p) for p in sorted(run_dir.glob("*.png"))],
            "safety": {
                "ai_submission_clicked": False,
                "external_install_clicked": False,
                "project_recovery_clicked": False,
            },
        }
    except Exception as exc:
        report = {
            "ok": False,
            "status": "FAIL",
            "mode": mode,
            "base_url": base_url,
            "started_at": started_at,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "steps": steps,
            "pass_count": sum(1 for s in steps if s["status"] == "PASS"),
            "fail_count": max(1, sum(1 for s in steps if s["status"] != "PASS")),
            "console_errors": console_errors,
            "page_errors": page_errors,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-6000:],
            "artifacts_dir": str(run_dir),
            "screenshots": [str(p) for p in sorted(run_dir.glob("*.png"))],
        }
    LAST_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8850")
    args = ap.parse_args()
    out = run(args.base_url)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out.get("ok") else 2)
