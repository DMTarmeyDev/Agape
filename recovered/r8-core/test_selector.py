from __future__ import annotations
from pathlib import PurePosixPath

def select_tests(changed_files,test_files):
    changed=[str(x).replace('\\','/') for x in (changed_files or [])]; tests=sorted(set(str(x).replace('\\','/') for x in (test_files or [])))
    stems=[]
    for c in changed:
        name=PurePosixPath(c).stem.lower()
        if name not in {'__init__','index','main','app'}: stems.append(name)
    selected=[t for t in tests if any(s and s in PurePosixPath(t).stem.lower() for s in stems)]
    if selected: return {'ok':True,'selected_tests':selected,'mode':'targeted','reason':'module_name_match'}
    return {'ok':True,'selected_tests':tests,'mode':'all','reason':'no_confident_target'}
