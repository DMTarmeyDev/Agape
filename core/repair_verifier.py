from __future__ import annotations

from typing import Any


def verify_repair(before_failure: dict[str,Any], after_test: dict[str,Any], regressions: list[dict[str,Any]] | None = None, budget: dict[str,Any] | None = None, context: dict[str,Any] | None = None) -> dict[str,Any]:
    before=dict(before_failure or {}); after=dict(after_test or {})
    if not before: raise ValueError('BEFORE_FAILURE_REQUIRED')
    tests_pass=bool(after.get('ok') or after.get('passed') or str(after.get('status') or '').upper()=='PASS')
    reg=list(regressions or [])
    regression_failures=[x for x in reg if not (x.get('ok') or x.get('passed') or str(x.get('status') or '').upper()=='PASS')]
    budget_ok=True if budget is None else bool(budget.get('allowed',budget.get('ok',False)))
    context_ok=True if context is None else bool(context.get('safe',True)) and not bool(context.get('unexpected_paths'))
    fixed=tests_pass and not regression_failures and budget_ok and context_ok
    reasons=[]
    if not tests_pass: reasons.append('TARGET_TEST_STILL_FAILING')
    if regression_failures: reasons.append('REGRESSION_FAILURE')
    if not budget_ok: reasons.append('CHANGE_BUDGET_FAILED')
    if not context_ok: reasons.append('CONTEXT_OR_SCOPE_UNSAFE')
    return {'ok':fixed,'fixed':fixed,'tests_pass':tests_pass,'regressions_pass':not regression_failures,'budget_pass':budget_ok,'context_pass':context_ok,'reasons':reasons,'regression_failures':regression_failures}
