from __future__ import annotations

def analyze_impact(graph, changed_files):
    edges=list((graph or {}).get('edges') or []); changed=sorted(set(str(x) for x in (changed_files or []))); impacted=set(changed); frontier=list(changed); reasons={x:['changed'] for x in changed}
    reverse={}
    for e in edges: reverse.setdefault(str(e.get('to')),set()).add(str(e.get('from')))
    while frontier:
        dep=frontier.pop(0)
        for parent in sorted(reverse.get(dep,set())):
            if parent not in impacted:
                impacted.add(parent); frontier.append(parent); reasons[parent]=[f'depends_on:{dep}']
    return {'ok':True,'changed_files':changed,'impacted_files':sorted(impacted),'reasons':reasons}
