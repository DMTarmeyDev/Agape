from __future__ import annotations

from typing import Any
import model_router
import model_scorecard


def choose_adaptive_model(installed_models: list[Any], task: str, attempt: int = 1, failure_category: str = '') -> dict[str, Any]:
    card=model_scorecard.build_scorecard(installed_models,model_router.classify_task(task))
    names=[x['model'] for x in card.get('models',[])]
    if not names:
        return {'ok':False,'model':'','reason':'NO_MODELS','scorecard':card}
    lower={n.lower():n for n in names}
    failure=str(failure_category or '').lower()
    complex_failure=failure in {'syntax','import','assertion','dependency','memory','permission'} or int(attempt or 1)>=2
    if complex_failure:
        for wanted in ('qwen2.5-coder:7b','qwen2.5-coder:7b-instruct'):
            if wanted in lower:
                return {'ok':True,'model':lower[wanted],'reason':'FAILURE_ESCALATION','attempt':int(attempt or 1),'scorecard':card}
    kind=model_router.classify_task(task)
    if kind!='coding' and int(attempt or 1)==1:
        for wanted in ('qwen2.5-coder:1.5b-instruct','qwen2.5-coder:1.5b'):
            if wanted in lower:
                return {'ok':True,'model':lower[wanted],'reason':'FAST_MODEL_FOR_LIGHT_TASK','attempt':1,'scorecard':card}
    return {'ok':True,'model':str(card['recommended']),'reason':'OBSERVED_SCORECARD','attempt':int(attempt or 1),'scorecard':card}
