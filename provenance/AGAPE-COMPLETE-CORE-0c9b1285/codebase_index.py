from __future__ import annotations
import hashlib
from pathlib import Path

SKIP={'.git','.venv','venv','node_modules','__pycache__','.mypy_cache','.pytest_cache'}
TEXT_EXT={'.py','.pyi','.js','.mjs','.cjs','.ts','.tsx','.jsx','.json','.md','.txt','.html','.css','.scss','.ps1','.cmd','.bat','.sh','.toml','.ini','.cfg','.yaml','.yml','.xml','.cs','.c','.h','.cpp','.hpp','.rs','.go','.java','.kt','.sql'}

def _inside(root: Path, p: Path)->bool:
    try: p.resolve().relative_to(root.resolve()); return True
    except Exception: return False

def build_index(root, max_files=500):
    base=Path(root).expanduser().resolve(); limit=max(1,min(int(max_files),5000))
    if not base.is_dir(): return {'ok':False,'error':'ROOT_NOT_FOUND','files':[]}
    files=[]; skipped=[]
    for p in sorted(base.rglob('*'),key=lambda x:x.as_posix().lower()):
        rel=p.relative_to(base).as_posix()
        if any(part in SKIP for part in p.relative_to(base).parts): skipped.append(rel); continue
        if len(files)>=limit: break
        if p.is_symlink() or not p.is_file() or not _inside(base,p): skipped.append(rel); continue
        if p.suffix.lower() not in TEXT_EXT and p.name.lower() not in {'makefile','dockerfile'}: skipped.append(rel); continue
        try: raw=p.read_bytes()
        except Exception: skipped.append(rel); continue
        if b'\x00' in raw[:4096]: skipped.append(rel); continue
        files.append({'path':rel,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest().upper()})
    return {'ok':True,'root':str(base),'count':len(files),'files':files,'skipped':skipped[:500],'truncated':len(files)>=limit}
