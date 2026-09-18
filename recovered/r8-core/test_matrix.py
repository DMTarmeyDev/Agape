from __future__ import annotations

from typing import Any


def build_test_matrix(planned: dict[str, Any] | None, selected_tests: list[str] | None = None, full_command: str = '') -> dict[str, Any]:
    command=str((planned or {}).get('command') or '').strip(); selected=[]
    for x in list(selected_tests or []):
        v=str(x or '').strip()
        if v and v not in selected: selected.append(v)
    phases=[]
    if selected: phases.append({'name':'targeted','tests':selected,'required':True})
    if command: phases.append({'name':'project','command':command,'required':True})
    if full_command and full_command!=command: phases.append({'name':'full','command':str(full_command),'required':True})
    if not phases: return {'ok':False,'phases':[],'reason':'no_tests_available'}
    return {'ok':True,'phases':phases,'phase_count':len(phases),'stop_on_failure':True}
