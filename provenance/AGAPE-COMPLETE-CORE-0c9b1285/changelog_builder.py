from __future__ import annotations

def build_changelog(entries):
    groups={'Added':set(),'Changed':set(),'Fixed':set()}; mapping={'added':'Added','changed':'Changed','fixed':'Fixed'}
    for e in entries or []:
        section=mapping.get(str(e.get('type') or '').lower()); text=str(e.get('text') or '').strip()
        if section and text: groups[section].add(text)
    sections={k:sorted(v) for k,v in groups.items()}; parts=[]
    for k in ('Added','Changed','Fixed'):
        parts.append('## '+k); parts.extend('- '+x for x in sections[k]); parts.append('')
    return {'ok':True,'sections':sections,'text':'\n'.join(parts).rstrip()+'\n'}
