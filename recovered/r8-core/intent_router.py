from __future__ import annotations
import re

def classify_intent(message: str) -> str:
    text = re.sub(r"\s+", " ", str(message or "").strip().lower())
    if not text:
        return "chat"
    development = (
        "fix", "repair", "debug", "failing", "failure", "test", "tests", "implement",
        "refactor", "build this project", "continue repairing", "until tests pass",
        "project development", "develop this project", "codebase", "bug", "bugs",
    )
    if any(term in text for term in development):
        return "project_development"
    return "chat"
