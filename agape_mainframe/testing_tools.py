from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
from typing import Any
from .python_runtime import pip_install_command

TOOLS = [
    {
        "id": "axe",
        "name": "axe accessibility testing",
        "group": "Browser & accessibility",
        "recommended": True,
        "why": "Checks common accessibility problems such as missing labels, poor semantics and invalid ARIA while Playwright clicks through Agape.",
        "cost": "Small/medium Node download. Best paired with Playwright.",
    },
    {
        "id": "schemathesis",
        "name": "Schemathesis API testing",
        "group": "API",
        "recommended": True,
        "why": "Generates unusual API requests automatically to find crashes, bad validation and edge cases that normal happy-path tests miss.",
        "cost": "Python package; light compared with a full browser or security suite.",
    },
    {
        "id": "zap",
        "name": "OWASP ZAP security scanner",
        "group": "Security",
        "recommended": True,
        "why": "Scans the local Agape web/API surface for common web-security weaknesses. Use safe/passive scans first.",
        "cost": "Larger desktop install and Java runtime requirement.",
    },
    {
        "id": "lighthouse",
        "name": "Lighthouse CI",
        "group": "Performance & quality",
        "recommended": True,
        "why": "Measures browser performance, accessibility and web best-practice regressions so a UI change cannot quietly make Agape slower or less usable.",
        "cost": "Node-based tool; requires a current Node runtime.",
    },
    {
        "id": "k6",
        "name": "Grafana k6 load testing",
        "group": "Load & performance",
        "recommended": False,
        "why": "Simulates repeated or concurrent requests to show where Agape slows down or fails under load.",
        "cost": "Separate command-line application. Mainly useful before server/public deployments.",
    },
    {
        "id": "appium-windows",
        "name": "Appium Windows desktop testing",
        "group": "Desktop",
        "recommended": False,
        "why": "Adds native Windows application automation for testing launched editors and desktop UI beyond the browser.",
        "cost": "Experimental/heavier. Installs Appium plus a Windows driver; use only when native desktop testing is needed.",
    },
    {
        "id": "appium-android",
        "name": "Appium Android testing",
        "group": "Mobile",
        "recommended": False,
        "why": "Lets Agape automate an Android app on an emulator/device for future mobile UI and workflow tests.",
        "cost": "Heavier mobile toolchain; Android SDK/device setup is also required.",
    },
]


def _which(*names: str) -> str:
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    return ""


def _cmd_ok(args: list[str], timeout: int = 15) -> tuple[bool, str]:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
        text = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()
        return cp.returncode == 0, text[:2000]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _installed(tool_id: str) -> tuple[bool, str]:
    if tool_id == "schemathesis":
        ok = importlib.util.find_spec("schemathesis") is not None or bool(_which("schemathesis", "st"))
        return ok, _which("schemathesis", "st") or ("Python package" if ok else "")
    if tool_id == "zap":
        p = _which("zap", "zaproxy", "zap.bat", "zap.exe")
        if not p and os.name == "nt":
            for candidate in (
                os.path.expandvars(r"%ProgramFiles%\ZAP\ZAP.exe"),
                os.path.expandvars(r"%ProgramFiles%\OWASP\Zed Attack Proxy\ZAP.exe"),
            ):
                if candidate and os.path.exists(candidate): p = candidate; break
        return bool(p), p
    if tool_id == "k6":
        p = _which("k6"); return bool(p), p
    if tool_id == "lighthouse":
        p = _which("lhci"); return bool(p), p
    if tool_id == "axe":
        npm = _which("npm", "npm.cmd")
        if not npm: return False, "Node/npm not found"
        ok, detail = _cmd_ok([npm, "list", "-g", "@axe-core/playwright", "--depth=0"])
        return ok, detail.splitlines()[-1] if detail else (npm if ok else "")
    if tool_id in {"appium-windows", "appium-android"}:
        p = _which("appium", "appium.cmd")
        if not p: return False, ""
        driver = "uiautomator2" if tool_id == "appium-android" else "novawindows"
        ok, detail = _cmd_ok([p, "driver", "list", "--installed"], timeout=20)
        return bool(ok and driver.lower() in detail.lower()), p
    return False, ""


def status() -> dict[str, Any]:
    rows=[]
    for item in TOOLS:
        installed, detail = _installed(item["id"])
        rows.append({**item, "installed": installed, "detail": detail})
    return {
        "ok": True,
        "tools": rows,
        "recommended_ids": [x["id"] for x in TOOLS if x["recommended"]],
        "note": "All testing tools are optional. Agape does not silently install them.",
    }


def _run(args: list[str], timeout: int = 900) -> dict[str, Any]:
    try:
        cp=subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
        text=((cp.stdout or "")+"\n"+(cp.stderr or "")).strip()
        return {"ok":cp.returncode==0,"return_code":cp.returncode,"command":subprocess.list2cmdline(args),"output":text[-12000:]}
    except Exception as exc:
        return {"ok":False,"return_code":-1,"command":subprocess.list2cmdline(args),"output":f"{type(exc).__name__}: {exc}"}


def install(tool_id: str) -> dict[str, Any]:
    tool_id=str(tool_id or "").strip().lower()
    if tool_id not in {x["id"] for x in TOOLS}:
        raise ValueError("UNKNOWN_TESTING_TOOL")
    already, detail=_installed(tool_id)
    if already:
        return {"ok":True,"tool":tool_id,"already_installed":True,"detail":detail}
    if tool_id == "schemathesis":
        result=_run(pip_install_command("schemathesis",user=True))
    elif tool_id == "zap":
        winget=_which("winget", "winget.exe")
        if not winget:return {"ok":False,"tool":tool_id,"error":"WINGET_NOT_FOUND","message":"Use the official ZAP Windows installer or install winget first."}
        result=_run([winget,"install","--id=ZAP.ZAP","-e","--accept-package-agreements","--accept-source-agreements"])
    elif tool_id == "k6":
        winget=_which("winget", "winget.exe")
        if not winget:return {"ok":False,"tool":tool_id,"error":"WINGET_NOT_FOUND","message":"Use the official k6 Windows installer or install winget first."}
        result=_run([winget,"install","k6","--source","winget","--accept-package-agreements","--accept-source-agreements"])
    elif tool_id in {"axe","lighthouse","appium-windows","appium-android"}:
        npm=_which("npm", "npm.cmd")
        if not npm:return {"ok":False,"tool":tool_id,"error":"NPM_NOT_FOUND","message":"Node.js/npm is required for this testing tool."}
        if tool_id == "axe":
            result=_run([npm,"install","-g","@axe-core/playwright","@playwright/test"])
        elif tool_id == "lighthouse":
            result=_run([npm,"install","-g","@lhci/cli@0.15.x"])
        else:
            result=_run([npm,"install","-g","appium"])
            if result.get("ok"):
                appium=_which("appium", "appium.cmd") or "appium"
                if tool_id == "appium-android":
                    result=_run([appium,"driver","install","uiautomator2"])
                else:
                    result=_run([appium,"driver","install","--source=npm","appium-novawindows-driver"])
    else:
        raise ValueError("UNSUPPORTED_TESTING_TOOL")
    result["tool"]=tool_id
    result["status_after"]=status()
    return result


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("action", choices=["status","install"])
    ap.add_argument("tool", nargs="?")
    args=ap.parse_args()
    out=status() if args.action=="status" else install(args.tool or "")
    print(__import__("json").dumps(out, indent=2))
    return 0 if out.get("ok") else 2

if __name__ == "__main__":
    raise SystemExit(main())
