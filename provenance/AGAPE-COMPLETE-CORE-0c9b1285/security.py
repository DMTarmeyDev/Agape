from __future__ import annotations

import hmac
import secrets
from pathlib import Path

from config import SECURITY_DIR, SESSION_TOKEN_FILE


def ensure_session_token() -> str:
    SECURITY_DIR.mkdir(parents=True, exist_ok=True)
    if SESSION_TOKEN_FILE.exists():
        token = SESSION_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    token = secrets.token_urlsafe(48)
    SESSION_TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        SESSION_TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return token


def session_ok(value: str | None) -> bool:
    if not value:
        return False
    expected = ensure_session_token()
    return hmac.compare_digest(str(value), expected)
