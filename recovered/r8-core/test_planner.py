from __future__ import annotations
import json
from pathlib import Path

def plan_tests(root):
    base=Path(root).expanduser().resolve()
    if not base.is_dir(): return {'ok':False,'framework':'none','command':'','reason':'root_not_found'}
    if (base/'pytest.ini').is_file() or (base/'pyproject.toml').is_file() and 'pytest' in (base/'pyproject.toml').read_text(encoding='utf-8',errors='ignore').lower():
        return {'ok':True,'framework':'pytest','command':'python -m pytest -q','reason':'pytest_config'}
    if (base/'tests').is_dir() and any((base/'tests').rglob('test*.py')):
        return {'ok':True,'framework':'unittest','command':'python -m unittest discover -s tests -v','reason':'python_tests_directory'}
    if (base/'SELFTEST.py').is_file():
        return {'ok':True,'framework':'python','command':'python SELFTEST.py','reason':'python_selftest'}
    root_tests=sorted(p for p in base.glob('test_*.py') if p.is_file() and not p.is_symlink())
    if root_tests:
        first=root_tests[0].name
        return {'ok':True,'framework':'python','command':'python '+first,'reason':'python_root_test_file','candidates':[p.name for p in root_tests]}
    package=base/'package.json'
    if package.is_file():
        try:
            obj=json.loads(package.read_text(encoding='utf-8-sig')); scripts=obj.get('scripts') or {}
            if isinstance(scripts,dict) and str(scripts.get('test') or '').strip(): return {'ok':True,'framework':'npm','command':'npm test','reason':'package_json_test'}
        except Exception: pass
    return {'ok':False,'framework':'none','command':'','reason':'no_supported_test_framework'}
