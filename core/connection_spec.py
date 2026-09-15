from __future__ import annotations
import urllib.parse
from typing import Any
from provider_catalog import normalize_provider, provider_capabilities

_SECRET_FIELDS={'api_key','token','secret','password','authorization','bearer'}

def _safe_base_url(value: str, online: bool) -> str:
    url=str(value or '').strip().rstrip('/')
    if not url: return ''
    p=urllib.parse.urlparse(url)
    if p.scheme not in {'http','https'} or not p.hostname: raise ValueError('CONNECTION_BASE_URL_INVALID')
    loopback=p.hostname.lower() in {'127.0.0.1','localhost','::1'}
    if online and p.scheme!='https' and not loopback: raise ValueError('ONLINE_PROVIDER_REQUIRES_HTTPS')
    return url

def normalize_connection(provider: str, model: str='', settings: dict[str,Any] | None=None) -> dict[str,Any]:
    ident=normalize_provider(provider); caps=provider_capabilities(ident)
    if not caps.get('ok'): raise ValueError('CONNECTION_PROVIDER_NOT_SUPPORTED')
    src=dict(settings or {})
    for key in src:
        if str(key).lower() in _SECRET_FIELDS and str(src.get(key) or '').strip(): raise ValueError('PLAINTEXT_SECRET_NOT_ALLOWED')
    online=bool(caps.get('online')); default='http://127.0.0.1:11434' if ident=='ollama' else ''
    base=_safe_base_url(str(src.get('base_url') or default),online)
    key_env=str(src.get('api_key_env') or '').strip()
    if key_env and not key_env.replace('_','').isalnum(): raise ValueError('API_KEY_ENV_INVALID')
    out={'base_url':base}
    if ident=='openai-compatible': out['api_key_env']=key_env; out['models_path']=str(src.get('models_path') or '/v1/models'); out['chat_path']=str(src.get('chat_path') or '/v1/chat/completions')
    return {'ok':True,'provider':ident,'model':str(model or '').strip(),'settings':out,'secret_storage':'environment_reference_only','plaintext_secret_stored':False}

def redact_connection(value: dict[str,Any]) -> dict[str,Any]:
    out=dict(value or {}); settings=dict(out.get('settings') or out.get('settings_json') or {}) if isinstance(out.get('settings') or out.get('settings_json') or {},dict) else {}
    for k in list(settings):
        if str(k).lower() in _SECRET_FIELDS: settings[k]='[REDACTED]'
    out['settings']=settings; out.pop('settings_json',None); return out
