from __future__ import annotations
import pathlib, tempfile
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]


def test_source_template_is_a_real_dropdown_and_old_button_list_is_removed():
    html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
    js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
    assert 'id="sourceTemplateSelect"' in html
    assert 'id="loadSourceTemplate"' in html
    assert 'Blank source' in html
    assert 'projectStarterDetails' not in html
    assert 'projectStarterList' not in html
    assert "window.AGAPE_PROJECT_TEMPLATES" in js
    assert "Loaded template:" in js


def test_builtin_system_test_template_is_bundled_and_data_driven():
    templates=(ROOT/'web'/'project_templates.js').read_text(encoding='utf-8')
    assert 'agape-source-input-system-test' in templates
    assert 'Agape full-system source test' in templates
    assert '# AGAPE SOURCE INPUT TEST TEMPLATE' in templates
    assert '# 20. Agape system test' in templates
    assert 'Source accepted: PASS / FAIL' in templates
    assert 'flooring-recycling-north-west' in templates
    assert 'northstar-2027-synthetic-business-plan-test' in templates
    assert 'NorthStar 2027 business plan' in templates


def test_session_retry_is_server_side_loopback_only():
    from agape_mainframe import http_client
    first=(403,{'ok':False,'error':'SESSION_REQUIRED'})
    second=(200,{'ok':True,'accepted':True})
    with patch.object(http_client,'_request_json_once',side_effect=[first,second]) as req, patch.object(http_client,'_local_core_session_headers',return_value={'X-DMT-Session':'x'*40}):
        status,payload=http_client.request_json('POST','http://127.0.0.1:8852/api/document/intake',{'x':1},timeout=5)
    assert status==200 and payload.get('accepted') is True
    assert req.call_count==2
    retry_headers=req.call_args_list[1].kwargs.get('headers') or {}
    assert retry_headers.get('X-DMT-Session')=='x'*40


def test_session_retry_never_sends_local_token_to_remote_host():
    from agape_mainframe import http_client
    first=(403,{'ok':False,'error':'SESSION_REQUIRED'})
    with patch.object(http_client,'_request_json_once',return_value=first) as req, patch.object(http_client,'_local_core_session_headers',return_value={'X-DMT-Session':'x'*40}) as token:
        status,payload=http_client.request_json('POST','https://example.com/api/write',{'x':1},timeout=5)
    assert status==403
    assert req.call_count==1
    token.assert_not_called()


def test_core_session_token_is_loaded_from_data_path_without_being_returned_to_browser():
    from agape_mainframe import http_client
    with tempfile.TemporaryDirectory() as td:
        data=pathlib.Path(td); (data/'security').mkdir(); (data/'security'/'local-session-token.txt').write_text('t'*48,encoding='utf-8')
        with patch.object(http_client,'_request_json_once',return_value=(200,{'data_path':str(data)})):
            headers=http_client._local_core_session_headers()
    assert headers=={'X-DMT-Session':'t'*48}
