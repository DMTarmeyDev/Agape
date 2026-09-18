from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .python_runtime import pip_install_command

TOOLS = [
    {
        "id": "axe",
        "name": "axe accessibility testing",
        "group": "Browser & accessibility",
        "recommended": True,
        "tier": "standard",
        "why": "Checks common accessibility problems such as missing labels, poor semantics and invalid ARIA while Playwright clicks through Agape.",
        "cost": "Small/medium Node download. Best paired with Playwright.",
    },
    {
        "id": "schemathesis",
        "name": "Schemathesis API testing",
        "group": "API",
        "recommended": True,
        "tier": "standard",
        "why": "Generates unusual API requests automatically to find crashes, bad validation and edge cases that normal happy-path tests miss.",
        "cost": "Python package; light compared with a full browser or security suite.",
    },
    {
        "id": "zap",
        "name": "OWASP ZAP security scanner",
        "group": "Security",
        "recommended": False,
        "tier": "advanced",
        "why": "Scans the local Agape web/API surface for common web-security weaknesses. Use safe/passive scans first.",
        "cost": "Full Developer/Admin tool. Installs ZAP plus Java 17+ when required.",
    },
    {
        "id": "lighthouse",
        "name": "Lighthouse CI",
        "group": "Performance & quality",
        "recommended": True,
        "tier": "standard",
        "why": "Measures browser performance, accessibility and web best-practice regressions so a UI change cannot quietly make Agape slower or less usable.",
        "cost": "Node-based tool; requires a current Node runtime.",
    },
    {
        "id": "k6",
        "name": "Grafana k6 load testing",
        "group": "Load & performance",
        "recommended": False,
        "tier": "advanced",
        "why": "Simulates repeated or concurrent requests to show where Agape slows down or fails under load.",
        "cost": "Full Developer/Admin tool. Separate command-line application.",
    },
    {
        "id": "appium-windows",
        "name": "Appium Windows desktop testing",
        "group": "Desktop",
        "recommended": False,
        "tier": "advanced",
        "why": "Adds native Windows application automation for testing launched editors and desktop UI beyond the browser.",
        "cost": "Experimental/heavier. Installs Appium plus a Windows driver; use only when native desktop testing is needed.",
    },
    {
        "id": "appium-android",
        "name": "Appium Android testing",
        "group": "Mobile",
        "recommended": False,
        "tier": "advanced",
        "why": "Lets Agape automate an Android app on an emulator/device for future mobile UI and workflow tests.",
        "cost": "Full Developer/Admin tool. Requires Node 20+, npm 10+, JDK, Android platform tools and UiAutomator2.",
    },
]

PROFILE_TOOLS = {
    "basic": [],
    "standard": ["axe", "schemathesis", "lighthouse"],
    "advanced": ["axe", "schemathesis", "lighthouse", "zap", "k6", "appium-android"],
}


def _which(*names: str) -> str:
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    return ""


def _cmd_ok(args: list[str], timeout: int = 15, env: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout, env=env)
        text = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()
        return cp.returncode == 0, text[:4000]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _run(args: list[str], timeout: int = 900, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout, env=env)
        text = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()
        return {"ok": cp.returncode == 0, "return_code": cp.returncode, "command": subprocess.list2cmdline(args), "output": text[-12000:]}
    except Exception as exc:
        return {"ok": False, "return_code": -1, "command": subprocess.list2cmdline(args), "output": f"{type(exc).__name__}: {exc}"}


def _winget_install(package_id: str, timeout: int = 1800) -> dict[str, Any]:
    winget = _which("winget", "winget.exe")
    if not winget:
        return {"ok": False, "error": "WINGET_NOT_FOUND", "message": "Windows Package Manager (winget) is required for this installer."}
    result = _run([
        winget, "install", "--id", package_id, "-e", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
    ], timeout=timeout)
    # winget may return a non-zero code when the newest package is already present.
    text = str(result.get("output") or "").lower()
    if not result.get("ok") and ("already installed" in text or "no available upgrade" in text):
        result["ok"] = True
    return result


def _find_java() -> str:
    p = _which("java", "java.exe")
    if p:
        return p
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
        for root in filter(None, roots):
            for pat in ("Eclipse Adoptium/jdk-*/bin/java.exe", "Java/jdk-*/bin/java.exe"):
                hits = sorted(Path(root).glob(pat), reverse=True)
                if hits:
                    return str(hits[0])
    return ""


def _java_major(path: str) -> int:
    if not path:
        return 0
    ok, detail = _cmd_ok([path, "-version"], timeout=10)
    if not ok and not detail:
        return 0
    m = re.search(r'version\s+"(\d+)', detail)
    if not m:
        m = re.search(r'openjdk\s+(\d+)', detail, re.I)
    return int(m.group(1)) if m else 0


def _ensure_java17() -> dict[str, Any]:
    java = _find_java()
    major = _java_major(java)
    if java and major >= 17:
        return {"ok": True, "java": java, "major": major, "installed_now": False}
    result = _winget_install("EclipseAdoptium.Temurin.21.JDK")
    if not result.get("ok"):
        return {"ok": False, "stage": "java", **result}
    java = _find_java()
    major = _java_major(java)
    if not java or major < 17:
        return {"ok": False, "stage": "java", "error": "JAVA_17_NOT_DETECTED_AFTER_INSTALL", "detail": java}
    return {"ok": True, "java": java, "major": major, "installed_now": True}


def _node_paths() -> tuple[str, str]:
    node = _which("node", "node.exe")
    npm = _which("npm", "npm.cmd")
    if os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs"
        if not node and (root / "node.exe").exists():
            node = str(root / "node.exe")
        if not npm and (root / "npm.cmd").exists():
            npm = str(root / "npm.cmd")
    return node, npm


def _node_major(node: str) -> int:
    if not node:
        return 0
    ok, detail = _cmd_ok([node, "--version"], timeout=10)
    m = re.search(r"v?(\d+)", detail) if ok else None
    return int(m.group(1)) if m else 0


def _npm_major(npm: str) -> int:
    if not npm:
        return 0
    ok, detail = _cmd_ok([npm, "--version"], timeout=10)
    m = re.search(r"(\d+)", detail) if ok else None
    return int(m.group(1)) if m else 0


def _ensure_node_for_appium() -> dict[str, Any]:
    node, npm = _node_paths()
    if node and npm and _node_major(node) >= 20 and _npm_major(npm) >= 10:
        return {"ok": True, "node": node, "npm": npm, "installed_now": False}
    result = _winget_install("OpenJS.NodeJS.LTS")
    if not result.get("ok"):
        return {"ok": False, "stage": "node", **result}
    node, npm = _node_paths()
    if not node or not npm:
        return {"ok": False, "stage": "node", "error": "NODE_OR_NPM_NOT_DETECTED_AFTER_INSTALL"}
    # Current Appium 3 requires Node ^20.19 || ^22.12 || >=24 and npm >=10.
    if _node_major(node) < 20 or _npm_major(npm) < 10:
        return {"ok": False, "stage": "node", "error": "NODE_OR_NPM_TOO_OLD", "node_major": _node_major(node), "npm_major": _npm_major(npm)}
    return {"ok": True, "node": node, "npm": npm, "installed_now": True}


def _find_appium() -> str:
    p = _which("appium", "appium.cmd")
    if p:
        return p
    if os.name == "nt":
        candidate = Path(os.environ.get("APPDATA", "")) / "npm" / "appium.cmd"
        if candidate.exists():
            return str(candidate)
    return ""


def _find_zap() -> str:
    p = _which("zap", "zaproxy", "zap.bat", "zap.exe")
    if p:
        return p
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
        candidates = [
            r"ZAP\ZAP.exe",
            r"OWASP\Zed Attack Proxy\ZAP.exe",
            r"ZAP\zap.bat",
            r"OWASP\Zed Attack Proxy\zap.bat",
        ]
        for root in filter(None, roots):
            for rel in candidates:
                pth = Path(root) / rel
                if pth.exists():
                    return str(pth)
            for pth in Path(root).glob("ZAP*/ZAP*.exe"):
                return str(pth)
    return ""


def _find_adb() -> str:
    p = _which("adb", "adb.exe")
    if p:
        return p
    if os.name == "nt":
        sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if sdk:
            candidate = Path(sdk) / "platform-tools" / "adb.exe"
            if candidate.exists():
                return str(candidate)
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        common = local / "Android" / "Sdk" / "platform-tools" / "adb.exe"
        if common.exists():
            return str(common)
        packages = local / "Microsoft" / "WinGet" / "Packages"
        if packages.exists():
            for candidate in packages.glob("Google.PlatformTools*/**/adb.exe"):
                return str(candidate)
    return ""


def _sdk_root_from_adb(adb: str) -> str:
    if not adb:
        return ""
    p = Path(adb).resolve()
    if p.parent.name.lower() == "platform-tools":
        return str(p.parent.parent)
    return ""


def _set_user_env(name: str, value: str) -> None:
    if os.name == "nt" and value:
        subprocess.run(["setx", name, value], capture_output=True, text=True, timeout=30)


def _appium_android_status() -> tuple[bool, str]:
    appium = _find_appium()
    if not appium:
        return False, "Appium CLI not found"
    ok, detail = _cmd_ok([appium, "driver", "list", "--installed"], timeout=30)
    if not (ok and "uiautomator2" in detail.lower()):
        return False, "UiAutomator2 driver not installed"
    java = _find_java()
    if _java_major(java) < 9:
        return False, "Java JDK not ready"
    adb = _find_adb()
    if not adb:
        return False, "Android platform-tools/adb not found"
    env = os.environ.copy()
    sdk = env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT") or _sdk_root_from_adb(adb)
    if sdk:
        env["ANDROID_HOME"] = sdk
        env["ANDROID_SDK_ROOT"] = sdk
    if java:
        env["JAVA_HOME"] = str(Path(java).resolve().parent.parent)
    ok, doctor = _cmd_ok([appium, "driver", "doctor", "uiautomator2"], timeout=90, env=env)
    if not ok:
        return False, (doctor[-1800:] if doctor else "Appium doctor failed")
    return True, "UiAutomator2 doctor PASS"


def _installed(tool_id: str) -> tuple[bool, str]:
    if tool_id == "schemathesis":
        ok = importlib.util.find_spec("schemathesis") is not None or bool(_which("schemathesis", "st"))
        return ok, _which("schemathesis", "st") or ("Python package" if ok else "")
    if tool_id == "zap":
        p = _find_zap()
        java = _find_java()
        major = _java_major(java)
        return bool(p and major >= 17), (f"{p} | Java {major}" if p else (f"Java {major}; ZAP missing" if major else "ZAP and Java 17+ required"))
    if tool_id == "k6":
        p = _which("k6"); return bool(p), p
    if tool_id == "lighthouse":
        p = _which("lhci"); return bool(p), p
    if tool_id == "axe":
        npm = _node_paths()[1]
        if not npm:
            return False, "Node/npm not found"
        ok, detail = _cmd_ok([npm, "list", "-g", "@axe-core/playwright", "--depth=0"])
        return ok, detail.splitlines()[-1] if detail else (npm if ok else "")
    if tool_id == "appium-android":
        return _appium_android_status()
    if tool_id == "appium-windows":
        p = _find_appium()
        if not p:
            return False, "Appium CLI not found"
        ok, detail = _cmd_ok([p, "driver", "list", "--installed"], timeout=30)
        return bool(ok and "novawindows" in detail.lower()), p
    return False, ""


def status() -> dict[str, Any]:
    rows = []
    for item in TOOLS:
        installed, detail = _installed(item["id"])
        rows.append({**item, "installed": installed, "detail": detail})
    return {
        "ok": True,
        "tools": rows,
        "recommended_ids": [x["id"] for x in TOOLS if x["recommended"]],
        "profile_tools": PROFILE_TOOLS,
        "note": "Testing tools are profile-aware and optional. Agape does not silently install heavy developer/mobile tools.",
    }


def install(tool_id: str) -> dict[str, Any]:
    tool_id = str(tool_id or "").strip().lower()
    if tool_id not in {x["id"] for x in TOOLS}:
        raise ValueError("UNKNOWN_TESTING_TOOL")
    already, detail = _installed(tool_id)
    if already:
        return {"ok": True, "tool": tool_id, "already_installed": True, "detail": detail, "status_after": status()}

    stages: list[dict[str, Any]] = []
    if tool_id == "schemathesis":
        result = _run(pip_install_command("schemathesis", user=True))
    elif tool_id == "zap":
        java = _ensure_java17(); stages.append({"stage": "java", **java})
        if not java.get("ok"):
            result = {"ok": False, "error": "ZAP_JAVA_PREREQUISITE_FAILED", "output": str(java)}
        else:
            result = _winget_install("ZAP.ZAP"); stages.append({"stage": "zap", **result})
            if result.get("ok") and not _find_zap():
                result = {"ok": False, "error": "ZAP_NOT_DETECTED_AFTER_INSTALL", "output": str(stages[-1])}
    elif tool_id == "k6":
        result = _winget_install("GrafanaLabs.k6")
        if not result.get("ok"):
            # Backward-compatible package query on systems where the short alias is available.
            result = _winget_install("k6")
    elif tool_id in {"axe", "lighthouse", "appium-windows", "appium-android"}:
        node = _ensure_node_for_appium() if tool_id.startswith("appium") else None
        if tool_id.startswith("appium"):
            stages.append({"stage": "node", **(node or {})})
            if not node or not node.get("ok"):
                result = {"ok": False, "error": "APPIUM_NODE_PREREQUISITE_FAILED", "output": str(node)}
                result["tool"] = tool_id
                result["stages"] = stages
                result["status_after"] = status()
                return result
        npm = (node or {}).get("npm") if node else _node_paths()[1]
        if not npm:
            return {"ok": False, "tool": tool_id, "error": "NPM_NOT_FOUND", "message": "Node.js/npm is required for this testing tool.", "status_after": status()}
        if tool_id == "axe":
            result = _run([str(npm), "install", "-g", "@axe-core/playwright", "@playwright/test"])
        elif tool_id == "lighthouse":
            result = _run([str(npm), "install", "-g", "@lhci/cli@0.15.x"])
        else:
            result = _run([str(npm), "install", "-g", "appium"]); stages.append({"stage": "appium", **result})
            appium = _find_appium()
            if result.get("ok") and not appium:
                result = {"ok": False, "error": "APPIUM_NOT_DETECTED_AFTER_INSTALL", "output": str(stages[-1])}
            elif result.get("ok") and tool_id == "appium-windows":
                result = _run([appium, "driver", "install", "--source=npm", "appium-novawindows-driver"])
                stages.append({"stage": "windows-driver", **result})
            elif result.get("ok") and tool_id == "appium-android":
                java = _ensure_java17(); stages.append({"stage": "java", **java})
                if not java.get("ok"):
                    result = {"ok": False, "error": "APPIUM_JAVA_PREREQUISITE_FAILED", "output": str(java)}
                else:
                    adb = _find_adb()
                    if not adb:
                        platform = _winget_install("Google.PlatformTools"); stages.append({"stage": "android-platform-tools", **platform})
                        if not platform.get("ok"):
                            result = {"ok": False, "error": "ANDROID_PLATFORM_TOOLS_INSTALL_FAILED", "output": str(platform)}
                        adb = _find_adb()
                    if result.get("ok") and not adb:
                        result = {"ok": False, "error": "ADB_NOT_DETECTED_AFTER_INSTALL", "output": "Android platform tools installed but adb could not be located."}
                    if result.get("ok"):
                        sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or _sdk_root_from_adb(adb)
                        if sdk:
                            _set_user_env("ANDROID_HOME", sdk); _set_user_env("ANDROID_SDK_ROOT", sdk)
                        java_path = _find_java()
                        if java_path:
                            _set_user_env("JAVA_HOME", str(Path(java_path).resolve().parent.parent))
                        result = _run([appium, "driver", "install", "uiautomator2"]); stages.append({"stage": "uiautomator2", **result})
                        if result.get("ok"):
                            env = os.environ.copy()
                            if sdk:
                                env["ANDROID_HOME"] = sdk; env["ANDROID_SDK_ROOT"] = sdk
                            if java_path:
                                env["JAVA_HOME"] = str(Path(java_path).resolve().parent.parent)
                            doctor = _run([appium, "driver", "doctor", "uiautomator2"], timeout=120, env=env)
                            stages.append({"stage": "doctor", **doctor})
                            result = doctor
                            if not doctor.get("ok"):
                                result["error"] = "APPIUM_ANDROID_DOCTOR_FAILED"
                                result["message"] = "Base tools were installed, but Android SDK/device prerequisites still need attention. Open the details shown by Appium Doctor."
    else:
        raise ValueError("UNSUPPORTED_TESTING_TOOL")

    result["tool"] = tool_id
    if stages:
        result["stages"] = stages
    result["status_after"] = status()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "install"])
    ap.add_argument("tool", nargs="?")
    args = ap.parse_args()
    out = status() if args.action == "status" else install(args.tool or "")
    print(__import__("json").dumps(out, indent=2))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
