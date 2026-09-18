from __future__ import annotations

from typing import Any

TRANSIENT={'timeout','network','provider_busy','rate_limit'}
STOP={'permission','memory','security'}
ESCALATE={'syntax','import','assertion','dependency'}


def decide_retry(attempt: int, failure_category: str, max_attempts: int = 3, consecutive_failures: int = 1) -> dict[str,Any]:
    n=max(1,int(attempt or 1)); maximum=max(1,min(int(max_attempts or 3),8)); category=str(failure_category or 'unknown').lower().strip()
    streak=max(1,int(consecutive_failures or 1))
    if category in STOP: action='stop'; reason='NON_RETRYABLE_FAILURE'
    elif n>=maximum: action='rollback'; reason='RETRY_LIMIT_REACHED'
    elif category in ESCALATE or streak>=2: action='escalate'; reason='REPAIR_OR_MODEL_ESCALATION'
    elif category in TRANSIENT: action='retry'; reason='TRANSIENT_FAILURE'
    else: action='repair'; reason='DETERMINISTIC_REPAIR_REQUIRED'
    backoff=min(60,2**max(0,n-1)) if action=='retry' else 0
    return {'ok':True,'action':action,'reason':reason,'attempt':n,'max_attempts':maximum,'failure_category':category,'backoff_seconds':backoff,'next_attempt':n+1 if action in {'retry','repair','escalate'} else n}
