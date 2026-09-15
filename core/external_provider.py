from __future__ import annotations
import json, os, time, urllib.error, urllib.request, urllib.parse
from dataclasses import dataclass
from typing import Any

class ExternalProviderError(RuntimeError): pass
@dataclass
class ExternalReply:
    provider: str
    model: str
    content: str
    duration_seconds: float
    raw: dict[str,Any]

def _join(base: str, path: str) -> str:
    return str(base or '').rstrip('/')+'/'+str(path or '').lstrip('/')

def _key(settings: dict[str,Any]) -> str:
    ref=str(settings.get('api_key_env') or '').strip()
    if not ref: raise ExternalProviderError('EXTERNAL_API_KEY_ENV_REQUIRED')
    value=str(os.environ.get(ref,'')).strip()
    if not value: raise ExternalProviderError('EXTERNAL_API_KEY_ENV_NOT_SET')
    return value

def _request(method: str, url: str, key: str, body: dict[str,Any] | None=None, timeout: int=30) -> dict[str,Any]:
    data=json.dumps(body).encode('utf-8') if body is not None else None
    req=urllib.request.Request(url,data=data,method=method,headers={'Accept':'application/json','Content-Type':'application/json','Authorization':'Bearer '+key})
    try:
        with urllib.request.urlopen(req,timeout=max(1,min(int(timeout),120))) as resp: raw=resp.read().decode('utf-8','replace')
    except urllib.error.HTTPError as exc:
        raise ExternalProviderError('EXTERNAL_HTTP_'+str(exc.code)) from None
    except Exception as exc:
        raise ExternalProviderError('EXTERNAL_TRANSPORT_ERROR:'+type(exc).__name__) from None
    try: obj=json.loads(raw)
    except Exception: raise ExternalProviderError('EXTERNAL_INVALID_JSON') from None
    if not isinstance(obj,dict): raise ExternalProviderError('EXTERNAL_RESPONSE_NOT_OBJECT')
    return obj

def list_models(settings: dict[str,Any], timeout: int=20) -> list[dict[str,Any]]:
    obj=_request('GET',_join(str(settings.get('base_url') or ''),str(settings.get('models_path') or '/v1/models')),_key(settings),None,timeout)
    data=obj.get('data') if isinstance(obj.get('data'),list) else obj.get('models',[])
    return [x for x in data if isinstance(x,dict)]

def chat(model: str, messages: list[dict[str,str]], settings: dict[str,Any], timeout: int=60, num_predict: int=512) -> ExternalReply:
    if not str(model or '').strip(): raise ExternalProviderError('EXTERNAL_MODEL_REQUIRED')
    body={'model':str(model),'messages':messages,'temperature':0,'max_tokens':max(1,min(int(num_predict),4096))}
    started=time.monotonic(); obj=_request('POST',_join(str(settings.get('base_url') or ''),str(settings.get('chat_path') or '/v1/chat/completions')),_key(settings),body,timeout); duration=time.monotonic()-started
    choices=obj.get('choices') or []; content=''
    if choices and isinstance(choices[0],dict): content=str((choices[0].get('message') or {}).get('content') or choices[0].get('text') or '')
    if not content: raise ExternalProviderError('EXTERNAL_EMPTY_REPLY')
    return ExternalReply('openai-compatible',str(model),content,duration,obj)

def test_connection(settings: dict[str,Any], requested_model: str='') -> dict[str,Any]:
    models=list_models(settings); names=[str(x.get('id') or x.get('name') or '') for x in models if str(x.get('id') or x.get('name') or '')]
    model=str(requested_model or '').strip(); selected=model if model in names else (names[0] if names else model)
    return {'ok':bool(names),'provider':'openai-compatible','models':models,'model':selected,'model_count':len(names),'secret_exposed':False}
