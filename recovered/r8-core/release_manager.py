from __future__ import annotations
from pathlib import Path
import re, shutil, time

def _safe_label(label: str) -> str:
    value=re.sub(r"[^A-Za-z0-9._-]+","-",str(label or "checkpoint").strip()).strip("-._")
    return value[:60] or "checkpoint"

def create_checkpoint(source: str, checkpoint_root: str, label: str = "checkpoint", dry_run: bool = False) -> dict:
    src=Path(source).expanduser().resolve(); root=Path(checkpoint_root).expanduser().resolve()
    if not src.is_dir(): raise ValueError("CHECKPOINT_SOURCE_NOT_FOUND="+str(src))
    if src.is_symlink(): raise ValueError("CHECKPOINT_SOURCE_SYMLINK_BLOCKED")
    path=root/(time.strftime("%Y%m%d-%H%M%S")+"-"+_safe_label(label))
    if dry_run: return {"ok":True,"dry_run":True,"path":str(path),"source":str(src)}
    root.mkdir(parents=True,exist_ok=True)
    if path.exists(): shutil.rmtree(path)
    shutil.copytree(src,path,symlinks=False)
    return {"ok":True,"dry_run":False,"path":str(path),"source":str(src)}

def restore_checkpoint(checkpoint_path: str, destination: str) -> dict:
    src=Path(checkpoint_path).expanduser().resolve(); dst=Path(destination).expanduser().resolve()
    if not src.is_dir(): raise ValueError("CHECKPOINT_NOT_FOUND="+str(src))
    if src.is_symlink(): raise ValueError("CHECKPOINT_SYMLINK_BLOCKED")
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(src,dst,symlinks=False)
    return {"ok":True,"checkpoint":str(src),"destination":str(dst)}

def list_checkpoints(checkpoint_root: str) -> list[dict]:
    root=Path(checkpoint_root).expanduser().resolve()
    if not root.exists(): return []
    return [{"name":p.name,"path":str(p),"modified":p.stat().st_mtime} for p in sorted(root.iterdir(),reverse=True) if p.is_dir() and not p.is_symlink()]
