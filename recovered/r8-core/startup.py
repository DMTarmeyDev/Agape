from __future__ import annotations

def browser_url(port: int = 8797) -> str:
    p = int(port)
    if not (1024 <= p <= 65535):
        raise ValueError("PORT_OUT_OF_RANGE")
    return f"http://127.0.0.1:{p}/"

def startup_status(port: int = 8797) -> dict:
    return {"ok": True, "fixed_port": int(port), "url": browser_url(port), "auto_browser": True}
