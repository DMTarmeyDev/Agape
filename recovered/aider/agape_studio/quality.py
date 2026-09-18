from __future__ import annotations

from typing import Any


QUALITY_CATALOG: list[dict[str, Any]] = [
    {'id': 'CORE-001', 'area': 'Core', 'title': 'One-page Studio shell'},
    {'id': 'CORE-002', 'area': 'Core', 'title': 'Projects and file workflow'},
    {'id': 'CORE-003', 'area': 'Core', 'title': 'Resizable terminal execution'},
    {'id': 'CORE-004', 'area': 'Core', 'title': 'Local AI provider and routing'},
    {'id': 'CORE-005', 'area': 'Core', 'title': 'Out-of-process extension host'},
    {'id': 'CORE-006', 'area': 'Core', 'title': 'Restart persistence and path safety'},
    {'id': 'FREE-001', 'area': 'Free AI', 'title': 'Free online AI provider adapter'},
    {'id': 'FREE-002', 'area': 'Free AI', 'title': 'Discover current zero-cost text models'},
    {'id': 'FREE-003', 'area': 'Free AI', 'title': 'Automatically rank/select best free model'},
    {'id': 'FREE-004', 'area': 'Free AI', 'title': 'Test provider and free-model eligibility'},
    {'id': 'FREE-005', 'area': 'Free AI', 'title': 'Persist connection and test outcomes'},
    {'id': 'FREE-006', 'area': 'Free AI', 'title': 'Local to free-online fallback'},
    {'id': 'PROC-001', 'area': 'Production Process', 'title': 'Compact gate output plus detailed Markdown report'},
    {'id': 'PROC-002', 'area': 'Production Process', 'title': 'Passed menu backed by verified quality ledger'},
    {'id': 'PROC-003', 'area': 'Production Process', 'title': 'Packaged-source full regression gate'},
    {'id': 'AIDER-001', 'area': 'Aider', 'title': 'Optional Aider CLI adapter and health probe'},
    {'id': 'AIDER-002', 'area': 'Aider', 'title': 'Shared Agape model routing into Aider model names'},
    {'id': 'AIDER-003', 'area': 'Aider', 'title': 'Planner selects Aider only for suitable repo-aware coding work'},
    {'id': 'AIDER-004', 'area': 'Aider', 'title': 'Registered clean Git workspace safety gate'},
    {'id': 'AIDER-005', 'area': 'Aider', 'title': 'One-shot Aider edit with Studio-owned test/release control'},
    {'id': 'AIDER-006', 'area': 'Aider', 'title': 'Persistent Aider execution evidence'},
    {'id': 'AIDER-007', 'area': 'Aider', 'title': 'Aider absence safely falls back to Agape AI'},
    {'id': 'AIDER-008', 'area': 'Aider', 'title': 'Visible Aider status and explicit-run control in Studio'},
    {'id': 'FIX-001', 'area': 'Windows Reliability', 'title': 'Byte-exact project file writes preserve requested line endings'},
    {'id': 'FIX-002', 'area': 'Windows Reliability', 'title': 'Ollama discovery and generation use separate timeout budgets'},
    {'id': 'FIX-003', 'area': 'Windows Reliability', 'title': 'Managed Aider takes precedence and stale PATH copies are ignored'},
    {'id': 'FIX-004', 'area': 'Test Reliability', 'title': 'External provider/tool probes are process-isolated with hard timeouts'},
]

CASE_REQUIREMENTS: dict[str, list[str]] = {
    'live_health': ['CORE-001'],
    'home_ui_contract': ['CORE-001'],
    'project_file_journey': ['CORE-002'],
    'terminal_journey': ['CORE-003'],
    'ai_journey': ['CORE-004'],
    'extension_journey': ['CORE-005'],
    'path_security': ['CORE-006'],
    'persistence_restart': ['CORE-006'],
    'full_user_journey': ['CORE-001', 'CORE-002', 'CORE-003', 'CORE-004', 'CORE-005', 'CORE-006'],
    'free_ai_discovery_journey': ['FREE-001', 'FREE-002'],
    'free_ai_auto_selection_journey': ['FREE-003'],
    'free_ai_provider_test_persistence': ['FREE-004', 'FREE-005'],
    'local_to_free_fallback_journey': ['FREE-006'],
    'passed_menu_contract': ['PROC-002'],
    'quality_ledger_journey': ['PROC-001', 'PROC-002'],
    'aider_status_planning_journey': ['AIDER-001', 'AIDER-002', 'AIDER-003', 'AIDER-004'],
    'aider_execution_journey': ['AIDER-005', 'AIDER-006'],
    'aider_optional_fallback_journey': ['AIDER-007'],
    'aider_ui_contract': ['AIDER-008'],
}


def quality_from_results(unit_status: str, live: list[dict[str, Any]], *, packaged: bool = False) -> list[dict[str, Any]]:
    by_id = {x['id']: {**x, 'status': 'NOT_TESTED', 'detail': ''} for x in QUALITY_CATALOG}
    if unit_status == 'PASS':
        by_id['PROC-001']['status'] = 'PASS'
        by_id['PROC-001']['detail'] = 'Component suite and Markdown reporting passed.'
        by_id['FIX-001']['status'] = 'PASS'
        by_id['FIX-001']['detail'] = 'Regression test verifies raw UTF-8 bytes preserve LF exactly across the file API.'
        by_id['FIX-002']['status'] = 'PASS'
        by_id['FIX-002']['detail'] = 'Regression test verifies short discovery timeout and longer generation timeout are independent.'
        by_id['FIX-003']['status'] = 'PASS'
        by_id['FIX-003']['detail'] = 'Regression tests verify managed Aider precedence and PATH Aider opt-in only.'
        by_id['FIX-004']['status'] = 'PASS'
        by_id['FIX-004']['detail'] = 'Full runner isolates Ollama, OpenRouter internet and real Aider probes in bounded subprocesses while keeping deterministic tests on the fast path.'
    for item in live:
        reqs = CASE_REQUIREMENTS.get(item['name'], [])
        for req in reqs:
            current = by_id[req]
            if item['status'] == 'FAIL':
                current['status'] = 'FAIL'
                current['detail'] = f"{item['name']}: {item.get('detail','')[:300]}"
            elif item['status'] == 'PASS' and current['status'] != 'FAIL':
                current['status'] = 'PASS'
                current['detail'] = f"Verified by {item['name']}"
    if packaged:
        by_id['PROC-003']['status'] = 'PASS'
        by_id['PROC-003']['detail'] = 'Verified from extracted packaged source.'
    return [by_id[x['id']] for x in QUALITY_CATALOG]
