from __future__ import annotations

def required_capabilities() -> list[str]:
    return [
        "core_system_test", "session_security", "project_loop", "connection_manager",
        "database_manager", "model_router", "autodev_queue", "release_checkpoints",
        "fixed_startup", "terminal_history",
    ]

def evaluate_readiness(signals: dict) -> dict:
    required=required_capabilities()
    missing=[name for name in required if not bool((signals or {}).get(name))]
    return {"ok": not missing, "overall": "PASS" if not missing else "FAIL", "required": required, "missing": missing, "passed": len(required)-len(missing), "total": len(required)}
