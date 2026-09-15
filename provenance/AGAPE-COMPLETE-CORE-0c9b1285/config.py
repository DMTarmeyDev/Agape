from __future__ import annotations

import os
from pathlib import Path

BUILD = "DMT-CORE-V3.1-EARLY-ALPHA-R1"
HOST = "127.0.0.1"
DEFAULT_PORT = 8797


def data_root() -> Path:
    override = os.environ.get("DMT_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Documents" / "DMT-CORE-V3.0" / "second-brain-data").resolve()


DATA_ROOT = data_root()
DB_PATH = DATA_ROOT / "dmt_core.sqlite3"
SECURITY_DIR = DATA_ROOT / "security"
SESSION_TOKEN_FILE = SECURITY_DIR / "local-session-token.txt"
LOG_DIR = DATA_ROOT / "logs"
REPORT_DIR = DATA_ROOT / "reports"

# New namespace: legacy R-series localStorage is never read by Core V1.
BROWSER_NAMESPACE = "dmt-core-v3.1"

# Provider and execution limits.
OLLAMA_URL = os.environ.get("DMT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("DMT_OLLAMA_TIMEOUT", "180"))
MAX_TOOL_ROUNDS = 3
MAX_COMMAND_CHARS = 6000
TERMINAL_TIMEOUT_SECONDS = 120

WORKFLOW_ROOT = Path(os.environ.get("DMT_WORKFLOW_ROOT", str(DATA_ROOT.parent / "workflow-output"))).expanduser().resolve()
