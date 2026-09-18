from __future__ import annotations
import importlib.util, json, os, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from .http_client import request_json
from .state import ROOT, load_settings, save_settings, record_event
from .python_runtime import is_frozen, pip_install_command

MANIFEST_DIR = ROOT / "capabilities"

SERVICE_ENDPOINTS = {
    "r8-core": ("http://127.0.0.1:8797/api/version", "core"),
    "documents": ("http://127.0.0.1:8851/api/health", "document"),
    "work-engine": ("http://127.0.0.1:8820/api/health", "work"),
    "artifacts": ("http://127.0.0.1:8798/api/health", "artifacts"),
    "communications": ("http://127.0.0.1:8806/api/health", "communications"),
    "workflow-bridge": ("http://127.0.0.1:8852/api/health", "workflow_bridge"),
}

PROFILE_DEFAULTS = {
    "basic": ["ai-routing","projects","documents","research"],
    "standard": ["ai-routing","projects","documents","research","work-engine","development","local-ai","artifacts","browser-automation"],
    "advanced": ["ai-routing","projects","documents","research","work-engine","development","local-ai","artifacts","aider","communications","browser-automation","advanced-rag","mcp","public-access"],
}


def manifests() -> list[dict[str, Any]]:
    rows=[]
    for p in sorted(MANIFEST_DIR.glob("*.json")):
        try:
            d=json.loads(p.read_text(encoding="utf-8")); d["_file"]=p.name; rows.append(d)
        except Exception:pass
    return rows


def manifest(cap_id: str) -> dict[str, Any] | None:
    return next((x for x in manifests() if x.get("id")==cap_id),None)


def _module_ready(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def service_status(timeout: float = 0.8) -> dict[str, Any]:
    """Probe optional local services concurrently so one slow service cannot freeze the UI."""
    items=list(SERVICE_ENDPOINTS.items())
    if not items:
        return {}

    def probe(item):
        cid,(url,key)=item
        status,payload=request_json("GET",url,timeout=timeout)
        return key,{"ok":status==200 and isinstance(payload,dict) and payload.get("ok",True) is not False,"http":status,"payload":payload if status==200 else {}}

    out={}
    with ThreadPoolExecutor(max_workers=len(items),thread_name_prefix="agape-service-probe") as pool:
        futures=[pool.submit(probe,item) for item in items]
        for future in as_completed(futures):
            try:
                key,value=future.result()
                out[key]=value
            except Exception as e:
                out["probe_error_"+str(len(out)+1)]={"ok":False,"http":0,"payload":{"error":str(e)}}
    return out


def capability_status(system: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    services=service_status(); settings=load_settings(); enabled=set(settings.get("enabled_capabilities") or [])
    rows=[]
    service_key={"r8-core":"core","documents":"document","work-engine":"work","artifacts":"artifacts","communications":"communications","workflow-bridge":"workflow_bridge"}
    for m in manifests():
        cid=str(m.get("id")); ready=True; reasons=[]
        if cid in service_key:
            ready=bool(services.get(service_key[cid],{}).get("ok"));
            if not ready:reasons.append("service not running")
        for mod in m.get("python_modules") or []:
            if not _module_ready(str(mod)):
                ready=False; reasons.append("missing python package: "+str(mod))
        if cid=="development" and not services.get("core",{}).get("ok"):
            ready=False; reasons.append("R8 project engine not running")
        if cid=="local-ai":
            st=(system or {}).get("tools",{}).get("ollama",{}) if isinstance(system,dict) else {}
            if st and not st.get("ready"):
                ready=False; reasons.append("Ollama not installed")
        rows.append({**m,"enabled":cid in enabled,"ready":ready,"reasons":reasons})
    return rows


def recommend_profile(system: dict[str, Any]) -> dict[str, Any]:
    ram=float(system.get("ram_gb") or 0)
    rec="standard" if ram>=12 else "basic"
    notes=[]
    if ram and ram<10:notes.append("Keep local AI and heavy browser/RAG packs off by default on this memory level.")
    elif ram<20:notes.append("Standard mode is suitable; prefer small local models and install heavy packs only when needed.")
    else:notes.append("This computer has room for more local capabilities, but advanced mode should still be chosen for workflow control rather than hardware alone.")
    if not system.get("has_discrete_gpu"):notes.append("No discrete GPU was detected; cloud AI or small local models are the efficient default.")
    return {"recommended_experience":rec,"notes":notes}


def profile_plan(experience: str, system: dict[str, Any]) -> dict[str, Any]:
    exp=experience if experience in PROFILE_DEFAULTS else "basic"
    desired=list(PROFILE_DEFAULTS[exp]); rows=[]
    by_id={x["id"]:x for x in capability_status(system)}
    for cid in desired:
        m=by_id.get(cid,{"id":cid,"name":cid,"ready":False,"support":[]})
        support=[]
        tool_map={"git":"git","ollama":"ollama","libreoffice":"libreoffice","vscode":"vscode","node":"node","tailscale":"tailscale"}
        module_map={"keyring":"keyring","litellm":"litellm","python-docx":"docx","pypdf":"pypdf","openpyxl":"openpyxl","python-pptx":"pptx","requests-cache":"requests_cache","trafilatura":"trafilatura","playwright":"playwright","aider-chat":"aider","llama-index-core":"llama_index","langchain-text-splitters":"langchain_text_splitters"}
        for sup in m.get("support") or []:
            z=dict(sup);pkg=str(z.get("package") or "");installed=False
            if z.get("kind")=="winget":installed=bool((system.get("tools") or {}).get(tool_map.get(pkg,pkg),{}).get("ready"))
            elif z.get("kind")=="pip":installed=_module_ready(module_map.get(pkg,pkg.replace("-","_")))
            z["installed"]=installed
            z["recommended_now"]=False
            if pkg=="libreoffice":z["recommended_now"]=True
            elif cid=="development" and pkg=="git":z["recommended_now"]=True
            elif cid=="local-ai" and pkg=="ollama" and exp=="advanced" and float(system.get("ram_gb") or 0)>=12:z["recommended_now"]=True
            elif cid=="communications" and pkg=="keyring":z["recommended_now"]=True
            elif cid=="aider" and pkg in {"aider-chat","git"}:z["recommended_now"]=True
            elif cid=="research" and pkg=="requests-cache" and exp!="basic":z["recommended_now"]=True
            support.append(z)
        item={"id":cid,"name":m.get("name",cid),"ready":bool(m.get("ready")),"required":cid in {"ai-routing","projects"},"support":support,"reason":"Included in "+exp.title()+" mode"}
        if cid in {"browser-automation","advanced-rag"} and float(system.get("ram_gb") or 0)<20:
            item["recommended_now"]=False; item["reason"]="Available in Advanced mode, but leave off until needed on this computer."
            for z in item["support"]:z["recommended_now"]=False
        else:item["recommended_now"]=True
        rows.append(item)
    return {"experience":exp,"capabilities":rows,"recommended":recommend_profile(system)}


def apply_profile(experience: str, selected: list[str] | None = None) -> dict[str, Any]:
    exp=experience if experience in PROFILE_DEFAULTS else "basic"
    caps=selected if isinstance(selected,list) and selected else PROFILE_DEFAULTS[exp]
    required={"ai-routing","projects"}
    caps=list(dict.fromkeys([*required,*[str(x) for x in caps]]))
    return save_settings({"experience":exp,"enabled_capabilities":caps,"setup_complete":True,"show_technical_details":exp=="advanced"})

ALLOWED_PIP={
    "keyring":"keyring","litellm":"litellm","python-docx":"python-docx","pypdf":"pypdf","openpyxl":"openpyxl","python-pptx":"python-pptx",
    "requests-cache":"requests-cache","trafilatura":"trafilatura","playwright":"playwright","aider-chat":"aider-chat",
    "llama-index-core":"llama-index-core","langchain-text-splitters":"langchain-text-splitters",
    "pyspellchecker":"pyspellchecker","pywinauto":"pywinauto",
}
ALLOWED_WINGET={
    "git":"Git.Git","ollama":"Ollama.Ollama","libreoffice":"TheDocumentFoundation.LibreOffice","vscode":"Microsoft.VisualStudioCode",
    "node":"OpenJS.NodeJS.LTS","tailscale":"Tailscale.Tailscale",
}


def install_support(kind: str, package: str) -> dict[str, Any]:
    run_id="SETUP-"+time.strftime("%Y%m%d-%H%M%S")
    if kind=="pip":
        if package not in ALLOWED_PIP:raise ValueError("SUPPORT_PACKAGE_NOT_ALLOWLISTED")
        record_event(run_id,"capability-manager","install","START","Installing "+package)
        if is_frozen() and package not in {"aider-chat"}:
            message=(
                "PACKAGED_PIP_EXTENSION_UNSUPPORTED="+package+
                ": this capability must be bundled into Agape or used from the source/Python edition."
            )
            record_event(run_id,"capability-manager","install","FAIL","Install not supported in packaged runtime",message)
            raise RuntimeError(message)
        command=pip_install_command(ALLOWED_PIP[package],user=is_frozen())
        p=subprocess.run(command,capture_output=True,text=True,timeout=900)
        if p.returncode!=0:
            record_event(run_id,"capability-manager","install","FAIL","Install failed",(p.stderr or p.stdout)[-4000:])
            raise RuntimeError("PIP_INSTALL_FAILED="+package+": "+(p.stderr or p.stdout)[-1600:])
        record_event(run_id,"capability-manager","install","PASS","Installed "+package)
        return {"ok":True,"kind":kind,"package":package}
    if kind=="winget":
        if os.name!="nt":raise RuntimeError("WINGET_INSTALL_WINDOWS_ONLY")
        if package not in ALLOWED_WINGET:raise ValueError("SUPPORT_PACKAGE_NOT_ALLOWLISTED")
        record_event(run_id,"capability-manager","install","START","Installing "+package)
        p=subprocess.run(["winget","install","--id",ALLOWED_WINGET[package],"-e","--accept-package-agreements","--accept-source-agreements"],capture_output=True,text=True,timeout=1800)
        if p.returncode not in {0,-1978335189}:
            record_event(run_id,"capability-manager","install","FAIL","Install failed",(p.stderr or p.stdout)[-4000:])
            raise RuntimeError("WINGET_INSTALL_FAILED="+package+": "+(p.stderr or p.stdout)[-1600:])
        record_event(run_id,"capability-manager","install","PASS","Installed "+package)
        return {"ok":True,"kind":kind,"package":package}
    raise ValueError("INSTALL_KIND_MUST_BE_PIP_OR_WINGET")
