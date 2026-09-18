from __future__ import annotations
import re
PROTECTED={'security.py','manifest.json','tools.py','workflows.py','system_test.py'}

def evaluate_change(change):
    c=dict(change or {}); files=[str(x).replace('\\','/').lower() for x in (c.get('files') or [])]; cmd=str(c.get('command') or '').lower(); reasons=[]
    destructive=any(x in cmd for x in ('format ', 'diskpart', 'bcdedit', 'reg delete', 'remove-item c:\\', 'remove-item c:/', 'rm -rf /'))
    if destructive: return {'ok':True,'decision':'block','risk':'critical','reasons':['known_destructive_command']}
    protected=any(f.split('/')[-1] in PROTECTED for f in files)
    if protected: reasons.append('protected_file')
    if bool(c.get('admin')) or bool(c.get('system_settings')): reasons.append('admin_or_system_change')
    if bool(c.get('package_install')): reasons.append('package_install')
    if bool(c.get('network_download')): reasons.append('network_download')
    if reasons: return {'ok':True,'decision':'approval_required','risk':'high','reasons':reasons}
    return {'ok':True,'decision':'allow','risk':'low','reasons':['ordinary_project_edit']}
