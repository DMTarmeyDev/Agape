from __future__ import annotations
import json, os, platform, shutil, subprocess, sys
from pathlib import Path
from typing import Any
from .python_runtime import runtime_detail as python_runtime_detail


def _run(args: list[str], timeout: int = 8) -> str:
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return (p.stdout or "").strip()
    except Exception:return ""


def _ps(script: str, timeout: int = 10) -> Any:
    if os.name != "nt": return None
    out=_run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-Command",script],timeout)
    if not out:return None
    try:return json.loads(out)
    except Exception:return out


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _exists(paths: list[str]) -> str:
    for p in paths:
        if p and Path(os.path.expandvars(p)).exists():return str(Path(os.path.expandvars(p)))
    return ""


def probe() -> dict[str, Any]:
    ram_gb=0.0; free_ram_gb=0.0; cpu=platform.processor() or platform.machine(); gpu=[]; os_info=platform.platform(); disk_free_gb=0.0
    if os.name=="nt":
        sysinfo=_ps("$o=Get-CimInstance Win32_OperatingSystem; $c=Get-CimInstance Win32_Processor|Select-Object -First 1; $g=@(Get-CimInstance Win32_VideoController|Select-Object Name,AdapterRAM); $d=Get-PSDrive -Name C; [pscustomobject]@{os=$o.Caption;version=$o.Version;build=$o.BuildNumber;ram_kb=$o.TotalVisibleMemorySize;free_kb=$o.FreePhysicalMemory;cpu=$c.Name;gpu=$g;disk_free=$d.Free}|ConvertTo-Json -Depth 5")
        if isinstance(sysinfo,dict):
            try:ram_gb=round(float(sysinfo.get("ram_kb") or 0)/1024/1024,1)
            except Exception:pass
            try:free_ram_gb=round(float(sysinfo.get("free_kb") or 0)/1024/1024,1)
            except Exception:pass
            try:disk_free_gb=round(float(sysinfo.get("disk_free") or 0)/1024/1024/1024,1)
            except Exception:pass
            cpu=str(sysinfo.get("cpu") or cpu); os_info=" ".join(str(sysinfo.get(k) or "") for k in ("os","version","build")).strip() or os_info
            rawg=sysinfo.get("gpu") or []
            if isinstance(rawg,dict):rawg=[rawg]
            gpu=[str(x.get("Name") or "") for x in rawg if isinstance(x,dict) and x.get("Name")]
    if not ram_gb and hasattr(os,"sysconf"):
        try:ram_gb=round(os.sysconf("SC_PAGE_SIZE")*os.sysconf("SC_PHYS_PAGES")/1024**3,1)
        except Exception:pass
    if not disk_free_gb:
        try:disk_free_gb=round(shutil.disk_usage(str(Path.home())).free/1024**3,1)
        except Exception:pass

    localapp=os.environ.get("LOCALAPPDATA",""); programfiles=os.environ.get("ProgramFiles",""); programfiles86=os.environ.get("ProgramFiles(x86)","")
    tools={
        "python":python_runtime_detail(),
        "git":{"ready":bool(_which("git")),"path":_which("git")},
        "node":{"ready":bool(_which("node")),"path":_which("node")},
        "ollama":{"ready":bool(_which("ollama")),"path":_which("ollama")},
        "winget":{"ready":bool(_which("winget")),"path":_which("winget")},
        "vscode":{"ready":bool(_which("code")),"path":_which("code")},
        "aider":{"ready":bool(_which("aider")),"path":_which("aider")},
        "openhands":{"ready":bool(_which("openhands")),"path":_which("openhands")},
        "open_interpreter":{"ready":bool(_which("open-interpreter") or _which("interpreter")),"path":_which("open-interpreter") or _which("interpreter")},
        "theia":{"ready":False,"path":""},
        "wsl":{"ready":bool(_which("wsl")),"path":_which("wsl")},
        "docker":{"ready":bool(_which("docker")),"path":_which("docker")},
        "libreoffice":{"ready":False,"path":""},
        "webview2":{"ready":False,"path":""},
    }
    theia=_exists([f"{localapp}\\Programs\\Theia IDE\\Theia IDE.exe",f"{localapp}\\Programs\\TheiaIDE\\Theia IDE.exe",f"{programfiles}\\Theia IDE\\Theia IDE.exe",f"{programfiles86}\\Theia IDE\\Theia IDE.exe"])
    if theia:tools["theia"]={"ready":True,"path":theia}
    lo=_exists([f"{programfiles}\\LibreOffice\\program\\soffice.exe",f"{programfiles86}\\LibreOffice\\program\\soffice.exe"])
    if lo:tools["libreoffice"]={"ready":True,"path":lo}
    wv=_exists([f"{programfiles86}\\Microsoft\\EdgeWebView\\Application",f"{programfiles}\\Microsoft\\EdgeWebView\\Application"])
    if wv:tools["webview2"]={"ready":True,"path":wv}
    has_discrete=any(any(k in g.lower() for k in ("nvidia","radeon","arc")) for g in gpu)
    hardware_class="low"
    if ram_gb>=24:hardware_class="high"
    elif ram_gb>=12:hardware_class="medium"
    local_model="small"
    if ram_gb>=24 and has_discrete:local_model="medium"
    elif ram_gb<10:local_model="avoid"
    return {
        "ok":True,"os":os_info,"platform":sys.platform,"cpu":cpu,"gpu":gpu,"ram_gb":ram_gb,"free_ram_gb":free_ram_gb,
        "disk_free_gb":disk_free_gb,"hardware_class":hardware_class,"has_discrete_gpu":has_discrete,
        "local_model_recommendation":local_model,"tools":tools,
        "existing_roots":{
            "r8_core": str(Path(localapp)/"DMT-Core-V3.1"/"SecondBrain"/"dmt-second-brain") if localapp else "",
            "mainframe": str(Path(localapp)/"Agape-Mainframe-V1") if localapp else "",
        }
    }
