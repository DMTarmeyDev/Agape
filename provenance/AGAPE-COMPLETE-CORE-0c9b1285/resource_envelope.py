from __future__ import annotations
from typing import Any

def recommend(host: dict[str,Any], models: list[str] | None=None) -> dict[str,Any]:
    ram=max(0.0,float(host.get('ram_gb') or host.get('memory_gb') or 0)); cores=max(1,int(host.get('logical_cores') or host.get('cores') or 1)); free=max(0.0,float(host.get('disk_free_gb') or 0)); parallel=1 if ram<16 else min(2,max(1,cores//4)); preferred='qwen2.5-coder:1.5b-instruct' if ram and ram<12 else 'qwen2.5-coder:7b'; names=[str(x) for x in models or []];
    if names and preferred not in names: preferred=names[0]
    warnings=[]
    if ram and ram<8: warnings.append('low_memory')
    if free and free<10: warnings.append('low_disk')
    return {'ok':not warnings,'preferred_model':preferred,'max_parallel_ai':parallel,'max_parallel_tests':min(2,max(1,cores//4)),'warnings':warnings,'host':{'ram_gb':ram,'logical_cores':cores,'disk_free_gb':free}}
