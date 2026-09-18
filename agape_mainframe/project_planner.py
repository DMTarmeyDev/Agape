from __future__ import annotations
import re
from typing import Any

DOC=re.compile(r"\b(proposal|report|quotation|quote|business plan|document|letter|pdf|docx|presentation|spreadsheet|tender|brochure|policy|memo)\b",re.I)
DEV=re.compile(r"\b(code|coding|software|app|website|web app|github|git|bug|test|python|javascript|powershell|aider|autodev|build project)\b",re.I)
RESEARCH=re.compile(r"\b(research|market|competitor|companies house|sources|evidence|industry|customer|trend|due diligence)\b",re.I)
COMM=re.compile(r"\b(email|send|whatsapp|message|communications|mastodon|matrix)\b",re.I)
BUSINESS=re.compile(r"\b(strategy|business model|commercial plan|forecast|financial model|budget|pricing|go-to-market|roadmap|operating plan)\b",re.I)
AUTOMATION=re.compile(r"\b(automate|automation|workflow|scheduled|scheduler|integration|connector|agent|pipeline|repeated task|batch)\b",re.I)
ANDROID=re.compile(r"\b(android|apk|mobile app|phone app|appium)\b",re.I)
WEB=re.compile(r"\b(website|web app|frontend|browser|react|vue|html|css|playwright)\b",re.I)
WINDOWS=re.compile(r"\b(windows|win32|desktop app|webview2|exe|msix)\b",re.I)
API=re.compile(r"\b(api|backend|server|flask|fastapi|endpoint|rest)\b",re.I)

PROJECT_TYPE_ALIASES={
    "coding":"development","software":"development","developer":"development",
    "docs":"document","documents":"document","planning":"business",
    "workflow":"automation","auto":"auto","other":"general",
}

PROJECT_TYPES={
    "document":{
        "label":"Document","summary":"Create a professional document from supplied information and optional public research.",
        "required_capabilities":["ai-routing","projects","documents"],"recommended_capabilities":["research"],
        "workflow":["Source","Review","Document"],"result_label":"Create document",
    },
    "development":{
        "label":"Software / Coding","summary":"Build, repair or test software in a project workspace with coding-specific tools.",
        "required_capabilities":["ai-routing","projects","development","work-engine"],"recommended_capabilities":["artifacts","browser-automation"],
        "workflow":["Brief","Workspace","Build & test"],"result_label":"Start build",
    },
    "research":{
        "label":"Research","summary":"Gather evidence, compare sources and produce a checked research result.",
        "required_capabilities":["ai-routing","projects","research"],"recommended_capabilities":["documents"],
        "workflow":["Question","Evidence","Report"],"result_label":"Create research result",
    },
    "business":{
        "label":"Business / Planning","summary":"Turn commercial goals and assumptions into a structured, evidence-backed plan.",
        "required_capabilities":["ai-routing","projects","documents","research"],"recommended_capabilities":["artifacts"],
        "workflow":["Goal","Review","Plan"],"result_label":"Create plan",
    },
    "automation":{
        "label":"Automation / Workflow","summary":"Design or build a repeatable workflow, integration or agent-driven process.",
        "required_capabilities":["ai-routing","projects","development","work-engine"],"recommended_capabilities":["artifacts","mcp"],
        "workflow":["Outcome","Workflow","Run & verify"],"result_label":"Build automation",
    },
    "communications":{
        "label":"Communications","summary":"Prepare approved email, messaging or communications work with the relevant connectors only.",
        "required_capabilities":["ai-routing","projects","communications"],"recommended_capabilities":[],
        "workflow":["Message","Review","Send / export"],"result_label":"Prepare communication",
    },
    "general":{
        "label":"Other / Let Agape decide","summary":"Start from the outcome and let Agape choose the smallest suitable capability set.",
        "required_capabilities":["ai-routing","projects"],"recommended_capabilities":[],
        "workflow":["Source","Review","Result"],"result_label":"Create result",
    },
}

CAPABILITY_NAMES={
    "ai-routing":"AI model routing","projects":"Project workspace","documents":"Document Studio",
    "research":"Public research","development":"Software development","work-engine":"Background work",
    "artifacts":"Artifacts & releases","browser-automation":"Browser testing","communications":"Communications","mcp":"Connectors / MCP",
}

def _normalise_project_type(value: str) -> str:
    key=str(value or "").strip().lower().replace("_","-")
    key=PROJECT_TYPE_ALIASES.get(key,key)
    return key if key in PROJECT_TYPES else "auto"

def classify_project_type(description: str, requested_type: str="auto", *, has_file: bool=False) -> str:
    requested=_normalise_project_type(requested_type)
    if requested != "auto": return requested
    text=str(description or "").strip()
    if DEV.search(text): return "development"
    if AUTOMATION.search(text): return "automation"
    if COMM.search(text): return "communications"
    if DOC.search(text) or has_file: return "document"
    if BUSINESS.search(text): return "business"
    if RESEARCH.search(text): return "research"
    return "general"

def _development_subtype(text: str) -> str:
    if ANDROID.search(text): return "android"
    if WEB.search(text): return "web"
    if WINDOWS.search(text): return "windows"
    if API.search(text): return "api"
    return "software"

def project_blueprint(description: str, requested_type: str="auto", *, has_file: bool=False) -> dict[str,Any]:
    text=str(description or "").strip()
    project_type=classify_project_type(text,requested_type,has_file=has_file)
    spec=PROJECT_TYPES[project_type]
    required=list(spec["required_capabilities"]); recommended=list(spec["recommended_capabilities"])
    subtype=""; tools=[]
    def tool(tool_id: str,name: str,reason: str,*,required_now: bool=False,install_id: str=""):
        tools.append({"id":tool_id,"name":name,"reason":reason,"required":required_now,"install_id":install_id})
    if project_type in {"document","business"}:
        tool("document-studio","Document Studio","Creates and validates professional document outputs.",required_now=True)
        tool("research","Research","Adds public evidence only when it materially strengthens the result.")
        tool("office-export","DOCX / PDF export","Produces normal business file formats.",required_now=True)
    elif project_type=="development":
        subtype=_development_subtype(text)
        tool("git","Git","Tracks code changes and supports safe rollback.",required_now=True,install_id="git")
        tool("coding-router","Coding model routing","Chooses a coding-specialist model or your selected model strategy.",required_now=True)
        tool("workspace","Agape workspace","Keeps source, changes, tests and results together.",required_now=True)
        if subtype=="web": tool("playwright","Browser QA","Clicks through the web UI and catches interaction regressions.",install_id="playwright")
        elif subtype=="android":
            tool("android","Android build tools","Builds the Android application.",required_now=True)
            tool("appium-android","Appium Android","Automates an emulator/device when real mobile UI testing is needed.",install_id="appium-android")
        elif subtype=="windows": tool("windows-desktop","Windows desktop QA","Tests the native desktop shell when needed.")
        elif subtype=="api": tool("schemathesis","API testing","Exercises API validation and unusual request combinations.",install_id="schemathesis")
        tool("aider","Aider","Optional repository-aware coding assistant.",install_id="aider-chat")
        tool("openhands","OpenHands","Optional agentic coding environment for larger development jobs.",install_id="openhands")
    elif project_type=="research":
        tool("research","Research","Finds and checks relevant public evidence.",required_now=True)
        tool("source-review","Source review","Keeps evidence separate from unsupported claims.",required_now=True)
        tool("document-export","Report export","Turns the evidence into a finished report when required.")
    elif project_type=="automation":
        tool("workflow-engine","Background work","Runs repeatable multi-step work safely.",required_now=True)
        tool("git","Git","Tracks automation/code changes where implementation is required.",install_id="git")
        tool("connectors","Connectors","Adds only the external systems required by this workflow.")
    elif project_type=="communications": tool("communications","Communications hub","Provides approved message/email connector workflows.",required_now=True)
    else: tool("ai-routing","Agape Router","Chooses the smallest suitable model/tool route.",required_now=True)
    return {
        "ok":True,"project_type":project_type,"project_type_label":spec["label"],"subtype":subtype,"summary":spec["summary"],"description":text,
        "required_capabilities":required,"recommended_capabilities":recommended,
        "capabilities":[{"id":cid,"name":CAPABILITY_NAMES.get(cid,cid.replace('-',' ').title()),"required":True} for cid in required]
            +[{"id":cid,"name":CAPABILITY_NAMES.get(cid,cid.replace('-',' ').title()),"required":False} for cid in recommended if cid not in required],
        "tools":tools,"workflow":list(spec["workflow"]),"result_label":spec["result_label"],
        "show_coding_options":project_type in {"development","automation"},
        "show_document_options":project_type in {"document","business","research"},
        "show_research_options":project_type in {"document","business","research"},
    }
