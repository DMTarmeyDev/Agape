from __future__ import annotations
import re
from typing import Any
from .state import load_settings
from .project_planner import classify_project_type, project_blueprint

DOC=re.compile(r"\b(proposal|report|quotation|quote|business plan|document|letter|pdf|docx|presentation|spreadsheet|tender|brochure|policy|memo)\b",re.I)
DEV=re.compile(r"\b(code|coding|software|app|website|web app|github|git|bug|test|python|javascript|powershell|aider|autodev|build project)\b",re.I)
RESEARCH=re.compile(r"\b(research|market|competitor|companies house|sources|evidence|industry|customer|trend|due diligence)\b",re.I)
COMM=re.compile(r"\b(email|send|whatsapp|message|communications|mastodon|matrix)\b",re.I)


def plan(task: str, *, has_file: bool=False, project_id: int=0, quality: str="gold", project_type: str="") -> dict[str, Any]:
    text=str(task or "").strip()
    chosen=classify_project_type(text,project_type or "auto",has_file=has_file)
    if chosen in {"document","business"}:route="document";caps=["documents","research","ai-routing"]
    elif chosen in {"development","automation"}:route="development";caps=["development","ai-routing","work-engine"]
    elif chosen=="communications":route="communications";caps=["communications","ai-routing"]
    elif chosen=="research":route="research";caps=["research","documents","ai-routing"]
    else:route="general";caps=["ai-routing","projects"]
    title={"document":"Create the finished document","development":"Build or repair the project","research":"Research and produce the result","communications":"Prepare and send the communication","general":"Ask Agape"}[route]
    steps=[
        "Source: use the single source you selected as the factual starting point.",
        "Review: fill the brief with AI, surface only unresolved information, and keep technical choices hidden unless needed.",
        "Result: create, validate and return the finished output while preserving versions for AI revisions.",
    ]
    blockers=[]
    if route=="development" and not project_id:blockers.append("Choose or create a project workspace for code changes.")
    result={"ok":True,"route":route,"project_type":chosen,"project_blueprint":project_blueprint(text,chosen,has_file=has_file),"title":title,"capabilities":caps,"quality":quality,"steps":steps,"decision_count":3,"blockers":blockers}
    if route=="development":
        settings=load_settings()
        result["coding"]={
            "model_mode":settings.get("coding_model_mode","auto-coding"),
            "agent":settings.get("coding_agent","auto"),
            "manager":settings.get("code_manager","agape"),
        }
    return result
