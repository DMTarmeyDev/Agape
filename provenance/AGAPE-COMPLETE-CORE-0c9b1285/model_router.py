from __future__ import annotations
import re

def classify_task(task: str) -> str:
    text = str(task or "").lower()
    coding = ("fix", "repair", "debug", "test", "tests", "python", "code", "refactor", "implement", "api", "database", "project")
    return "coding" if any(k in text for k in coding) else "chat"

def _names(model_names):
    result=[]
    for item in model_names or []:
        name=str(item.get("name") or "") if isinstance(item,dict) else str(item)
        if name and name not in result: result.append(name)
    return result

def choose_model(model_names, task: str) -> dict:
    names=_names(model_names)
    if not names:
        return {"ok": False, "model": "", "task_type": classify_task(task), "reason": "NO_MODELS"}
    lower={n.lower():n for n in names}
    kind=classify_task(task)
    wanted=("qwen2.5-coder:7b","qwen2.5-coder:7b-instruct","qwen2.5-coder:3b","qwen2.5-coder:1.5b-instruct") if kind=="coding" else ("qwen2.5-coder:1.5b-instruct","qwen2.5-coder:1.5b","qwen2.5-coder:7b")
    for key in wanted:
        if key in lower:
            return {"ok": True, "model": lower[key], "task_type": kind, "reason": "TASK_ROUTER"}
    def score(name):
        m=re.search(r"(\d+(?:\.\d+)?)b",name.lower())
        size=float(m.group(1)) if m else 0.0
        return (1 if "coder" in name.lower() else 0, size)
    selected=max(names,key=score) if kind=="coding" else names[0]
    return {"ok": True, "model": selected, "task_type": kind, "reason": "BEST_AVAILABLE"}
