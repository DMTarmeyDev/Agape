from __future__ import annotations
FAST_TYPES={'Quotation','Business Letter','Meeting Minutes','Project Plan'}
DEEP_HINTS={'deep research','market sizing','investment','financial forecast','competitor analysis','legal research','technical architecture research'}

def choose_lane(doc_type='',research=False,rag=False,source_chars=0,instructions=''):
    s=(instructions or '').lower()
    if research or any(x in s for x in DEEP_HINTS):return {'lane':'DEEP','reason':'research_or_deep_intent'}
    if doc_type in FAST_TYPES and source_chars>0:return {'lane':'FAST','reason':'structured_supplied_facts'}
    if doc_type=='Business Proposal' and source_chars>0 and not rag:return {'lane':'STANDARD','reason':'proposal_requires_more_reasoning'}
    return {'lane':'STANDARD','reason':'default'}
