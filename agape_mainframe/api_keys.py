from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .platform_paths import user_data_root

PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {"name": "OpenAI / ChatGPT API", "env": "OPENAI_API_KEY", "why": "Use OpenAI models and coding/reasoning services."},
    "anthropic": {"name": "Anthropic / Claude API", "env": "ANTHROPIC_API_KEY", "why": "Use Claude models where configured."},
    "google": {"name": "Google Gemini API", "env": "GOOGLE_API_KEY", "why": "Use Google Gemini models."},
    "openrouter": {"name": "OpenRouter API", "env": "OPENROUTER_API_KEY", "why": "Access multiple hosted model families through one provider."},
    "groq": {"name": "Groq API", "env": "GROQ_API_KEY", "why": "Use supported low-latency hosted open models."},
    "mistral": {"name": "Mistral API", "env": "MISTRAL_API_KEY", "why": "Use hosted Mistral models."},
    "deepseek": {"name": "DeepSeek API", "env": "DEEPSEEK_API_KEY", "why": "Use hosted DeepSeek models."},
    "together": {"name": "Together AI API", "env": "TOGETHER_API_KEY", "why": "Use supported hosted open-source models."},
    "xai": {"name": "xAI API", "env": "XAI_API_KEY", "why": "Use xAI models where configured."},
}

DATA_ROOT = user_data_root()
KEY_FILE = DATA_ROOT / "api-keys.json"

KEYRING_SERVICE = "Agape"

def _keyring_module():
    try:
        import keyring  # type: ignore
        # Trigger backend lookup; some headless Linux installs have no usable backend.
        keyring.get_keyring()
        return keyring
    except Exception:
        return None

def _keyring_get(provider: str) -> str:
    kr=_keyring_module()
    if kr is None:return ""
    try:return str(kr.get_password(KEYRING_SERVICE, PROVIDERS[provider]["env"]) or "")
    except Exception:return ""

def _store_provider(provider: str, value: str) -> str:
    kr=_keyring_module()
    if kr is not None:
        try:
            kr.set_password(KEYRING_SERVICE, PROVIDERS[provider]["env"], value)
            # Remove stale plaintext fallback copy if present.
            fallback=_read_file_only(); fallback.pop(provider,None); _write_file_only(fallback)
            return "os_keyring"
        except Exception:
            pass
    fallback=_read_file_only(); fallback[provider]=value; _write_file_only(fallback)
    return "private_file"


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _read_file_only() -> dict[str, str]:
    if not KEY_FILE.is_file():
        return {}
    try:
        raw = json.loads(KEY_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items() if k in PROVIDERS and str(v).strip()}
    except Exception:
        return {}


def _write_file_only(values: dict[str, str]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = KEY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(values, indent=2), encoding="utf-8")
    _chmod_private(tmp)
    os.replace(tmp, KEY_FILE)
    _chmod_private(KEY_FILE)


def _read_private() -> dict[str, str]:
    out=_read_file_only()
    for provider in PROVIDERS:
        value=_keyring_get(provider)
        if value:out[provider]=value
    return out

def _storage_source(provider: str) -> str:
    if _keyring_get(provider):return "os_keyring"
    if _read_file_only().get(provider):return "private_file"
    return ""

def _candidate_import_files() -> list[Path]:
    out: list[Path] = []
    override = os.environ.get("AGAPE_API_KEYS_FILE", "").strip()
    if override:
        out.append(Path(override).expanduser())
    root = Path(__file__).resolve().parent.parent
    out.extend([root / "API-KEYS.local.json", Path.cwd() / "API-KEYS.local.json"])
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent / "API-KEYS.local.json")
    unique: list[Path] = []
    seen: set[str] = set()
    for p in out:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _normalise_import(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("keys"), dict):
        raw = raw["keys"]
    out: dict[str, str] = {}
    for provider, meta in PROVIDERS.items():
        value = raw.get(provider)
        if not value:
            value = raw.get(meta["env"])
        if isinstance(value, str) and value.strip():
            out[provider] = value.strip()
    return out


def import_key_file(path: str | Path | None = None, *, overwrite: bool = False) -> dict[str, Any]:
    candidates = [Path(path).expanduser()] if path else _candidate_import_files()
    chosen = next((p for p in candidates if p.is_file()), None)
    if chosen is None:
        return {"ok": False, "found": False, "message": "No API-KEYS.local.json file was found."}
    try:
        raw = json.loads(chosen.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "found": True, "message": f"Could not read key file: {exc}"}
    incoming = _normalise_import(raw)
    current = _read_private()
    imported: list[str] = []
    for provider, value in incoming.items():
        if overwrite or not current.get(provider):
            current[provider] = value
            imported.append(provider)
    if imported:
        for provider in imported:
            _store_provider(provider,current[provider])
        export_keys_to_environment()
    return {
        "ok": True,
        "found": True,
        "path": str(chosen),
        "imported": imported,
        "count": len(imported),
        "message": f"Imported {len(imported)} API key(s) into Agape's private local store." if imported else "Key file found; no new keys needed importing.",
    }


def set_key(provider: str, value: str) -> dict[str, Any]:
    provider = str(provider or "").strip().lower()
    value = str(value or "").strip()
    if provider not in PROVIDERS:
        raise ValueError("UNKNOWN_API_KEY_PROVIDER")
    if not value:
        raise ValueError("API_KEY_REQUIRED")
    storage=_store_provider(provider,value)
    os.environ[PROVIDERS[provider]["env"]] = value
    return {"ok": True, "provider": provider, "name": PROVIDERS[provider]["name"], "configured": True, "storage": storage}


def remove_key(provider: str) -> dict[str, Any]:
    provider = str(provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError("UNKNOWN_API_KEY_PROVIDER")
    current = _read_file_only()
    current.pop(provider, None)
    _write_file_only(current)
    kr=_keyring_module()
    if kr is not None:
        try: kr.delete_password(KEYRING_SERVICE, PROVIDERS[provider]["env"])
        except Exception: pass
    os.environ.pop(PROVIDERS[provider]["env"], None)
    return {"ok": True, "provider": provider, "configured": False}


def export_keys_to_environment() -> None:
    for provider, value in _read_private().items():
        env_name = PROVIDERS[provider]["env"]
        if not os.environ.get(env_name):
            os.environ[env_name] = value


def status() -> dict[str, Any]:
    stored = _read_private()
    rows = []
    for provider, meta in PROVIDERS.items():
        source = "environment" if os.environ.get(meta["env"]) else _storage_source(provider)
        rows.append({
            "id": provider,
            "name": meta["name"],
            "env": meta["env"],
            "why": meta["why"],
            "configured": bool(source),
            "source": source,
        })
    import_path = next((str(p) for p in _candidate_import_files() if p.is_file()), "")
    return {
        "ok": True,
        "providers": rows,
        "configured_count": sum(1 for x in rows if x["configured"]),
        "import_file_found": bool(import_path),
        "import_file_path": import_path,
        "storage": "OS credential store when available; otherwise " + str(KEY_FILE),
        "keyring_available": bool(_keyring_module()),
        "note": "Key values are never returned by this API.",
    }


def bootstrap() -> dict[str, Any]:
    export_keys_to_environment()
    # First-run convenience: import a local template-derived file if present.
    # Existing private keys are never overwritten automatically.
    result = import_key_file(overwrite=False)
    export_keys_to_environment()
    return result
