from __future__ import annotations
import os, platform
from pathlib import Path

APP_NAME = "Agape"

def platform_name() -> str:
    return platform.system().lower()

def user_data_root() -> Path:
    override = os.environ.get("AGAPE_MAINFRAME_DATA")
    if override:
        return Path(override).expanduser().resolve()
    system = platform_name()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / "Agape-Mainframe-V3" / "data").resolve()
    if system == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_NAME / "data").resolve()
    xdg = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return (xdg / "agape" / "data").resolve()

def security_root() -> Path:
    override = os.environ.get("AGAPE_SECURITY_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    system = platform_name()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / "Agape" / "Security").resolve()
    if system == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_NAME / "Security").resolve()
    xdg = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return (xdg / "agape" / "security").resolve()
