from __future__ import annotations

def compare_manifests(old_manifest,new_manifest):
    old=dict(old_manifest or {}); new=dict(new_manifest or {}); a=dict(old.get('files') or {}); b=dict(new.get('files') or {})
    return {'ok':True,'old_build':str(old.get('build') or ''),'new_build':str(new.get('build') or ''),'added_files':sorted(set(b)-set(a)),'removed_files':sorted(set(a)-set(b)),'changed_files':sorted(k for k in set(a)&set(b) if str(a[k])!=str(b[k])),'added_features':sorted(set(new.get('features') or [])-set(old.get('features') or [])),'removed_features':sorted(set(old.get('features') or [])-set(new.get('features') or []))}
