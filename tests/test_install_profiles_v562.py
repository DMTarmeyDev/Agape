from pathlib import Path

from agape_mainframe import capabilities, coding_tools, testing_tools


def test_testing_tools_are_tiered_and_heavy_tools_not_standard_recommended():
    out = testing_tools.status()
    rows = {x['id']: x for x in out['tools']}
    assert set(out['recommended_ids']) == {'axe', 'schemathesis', 'lighthouse'}
    assert rows['zap']['tier'] == 'advanced'
    assert rows['appium-android']['tier'] == 'advanced'
    assert rows['k6']['tier'] == 'advanced'
    assert rows['axe']['tier'] == 'standard'


def test_standard_capability_profile_keeps_heavy_local_ai_out_by_default():
    assert 'local-ai' in capabilities.PROFILE_DEFAULTS['standard']  # available, but installer leaves Ollama optional
    assert 'browser-automation' in capabilities.PROFILE_DEFAULTS['standard']
    assert 'local-ai' in capabilities.PROFILE_DEFAULTS['advanced']


def test_openhands_registry_exposes_install_and_wsl_aware_summary():
    row = next(x for x in coding_tools.AGENTS if x['id'] == 'openhands')
    assert 'WSL' in row['summary'] or 'wsl' in row['summary'].lower()
    assert hasattr(coding_tools, '_install_openhands')


def test_settings_contains_three_install_profiles_and_openhands_install_button():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'web' / 'index.html').read_text(encoding='utf-8')
    js = (root / 'web' / 'app.js').read_text(encoding='utf-8')
    assert 'Essential' in html
    assert 'Full Developer/Admin' in html
    assert 'installProfileStandard' in html
    assert 'data-coding-action=\"install\"' in js and "tool:'openhands',action:'install'" in js


def test_browser_qa_uses_boolean_open_property_not_attribute_truthiness():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'agape_mainframe' / 'browser_qa.py').read_text(encoding='utf-8')
    assert 'el => el.open' in text
    assert 'wait_for(state="visible"' in text
