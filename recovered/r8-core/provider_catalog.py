from __future__ import annotations
from typing import Any

_PROVIDER_DEFS={
    'ollama': {'kind':'local','online':False,'chat':True,'models':True,'tool_json':True,'secret_required':False},
    'openai-compatible': {'kind':'online','online':True,'chat':True,'models':True,'tool_json':False,'secret_required':True},
}
_ALIASES={'openai':'openai-compatible','openai_compatible':'openai-compatible','local':'ollama'}

def normalize_provider(name: str) -> str:
    value=str(name or '').strip().lower()
    return _ALIASES.get(value,value)

def provider_catalog() -> dict[str,Any]:
    return {'ok':True,'providers':[{'id':k,**v} for k,v in _PROVIDER_DEFS.items()],'default':'ollama','offline_first':True}

def provider_capabilities(name: str) -> dict[str,Any]:
    ident=normalize_provider(name)
    item=_PROVIDER_DEFS.get(ident)
    if not item: return {'ok':False,'provider':ident,'reason':'provider_not_supported'}
    return {'ok':True,'provider':ident,**item}
