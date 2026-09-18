from __future__ import annotations

import re
from typing import Any
import failure_cluster

_RULES=[
 ('timeout',r'(?i)timeout|timed out|exit code 124'),
 ('permission',r'(?i)permission denied|access is denied|unauthorized'),
 ('import',r'(?i)modulenotfounderror|importerror|no module named'),
 ('syntax',r'(?i)syntaxerror|parsererror|unexpected token|invalid syntax'),
 ('assertion',r'(?i)assertionerror|assert .*failed|expected .* got'),
 ('dependency',r'(?i)package .* not found|command not found|executable_not_found|cannot find module'),
 ('network',r'(?i)connection refused|dns|name resolution|http[_ ](?:4|5)\d\d|network'),
 ('memory',r'(?i)memoryerror|out of memory|cannot allocate memory'),
]

def triage_failure(stdout: str = '', stderr: str = '', exit_code: int | None = None) -> dict[str, Any]:
    text=(str(stderr or '')+'\n'+str(stdout or '')).strip()
    category='unknown'
    for name,pat in _RULES:
        if re.search(pat,text): category=name; break
    if exit_code==0 and not text:
        category='none'
    fp=failure_cluster.fingerprint_failure(text or ('exit='+str(exit_code)))
    first=' '.join(text.split())[:500]
    retryable=category in {'timeout','network'}
    severity='high' if category in {'permission','memory'} else ('medium' if category!='none' else 'none')
    return {'ok':True,'category':category,'fingerprint':fp,'exit_code':exit_code,'retryable':retryable,'severity':severity,'summary':first}
