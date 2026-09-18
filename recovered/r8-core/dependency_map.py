from __future__ import annotations
import ast
from pathlib import Path

SKIP={'.git','.venv','venv','node_modules','__pycache__'}
def build_dependency_map(root,max_files=500):
    base=Path(root).expanduser().resolve(); limit=max(1,min(int(max_files),5000))
    if not base.is_dir(): return {'ok':False,'nodes':[],'edges':[],'skipped':[],'error':'ROOT_NOT_FOUND'}
    py=[]; skipped=[]
    for p in sorted(base.rglob('*.py')):
        rel=p.relative_to(base).as_posix()
        if any(x in SKIP for x in p.relative_to(base).parts) or p.is_symlink(): skipped.append(rel); continue
        py.append(p)
        if len(py)>=limit: break
    module={p.relative_to(base).with_suffix('').as_posix().replace('/','.'):p.relative_to(base).as_posix() for p in py}
    by_tail={k.split('.')[-1]:v for k,v in module.items()}
    edges=[]
    for p in py:
        rel=p.relative_to(base).as_posix()
        try: tree=ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
        except Exception: skipped.append(rel); continue
        names=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import): names.extend(a.name for a in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module: names.append(n.module)
        targets=set()
        for name in names:
            if name in module: targets.add(module[name])
            elif name.split('.')[-1] in by_tail: targets.add(by_tail[name.split('.')[-1]])
            elif name.split('.')[0] in by_tail: targets.add(by_tail[name.split('.')[0]])
        for target in sorted(targets):
            if target!=rel: edges.append({'from':rel,'to':target})
    return {'ok':True,'nodes':sorted(p.relative_to(base).as_posix() for p in py),'edges':edges,'skipped':sorted(set(skipped))}
