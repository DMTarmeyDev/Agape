from __future__ import annotations
import hashlib,re

def _norm(text):
    s=str(text or '').replace('\\','/')
    s=re.sub(r'(?i)line\s+\d+','line #',s)
    s=re.sub(r'0x[0-9a-f]+','0x#',s,flags=re.I)
    s=re.sub(r'(?i)(?:[A-Z]:/[^\s:\n]+|/tmp/[^\s:\n]+)','<path>',s)
    s=re.sub(r'\b\d{4,}\b','#',s)
    return ' '.join(s.split()).lower()

def fingerprint_failure(text): return hashlib.sha256(_norm(text).encode('utf-8')).hexdigest()[:20]
def cluster_failures(failures):
    groups={}
    for i,x in enumerate(failures or []):
        fp=fingerprint_failure(x); groups.setdefault(fp,[]).append({'index':i,'text':str(x)})
    return {'ok':True,'clusters':[{'fingerprint':fp,'count':len(groups[fp]),'members':groups[fp]} for fp in sorted(groups)]}
