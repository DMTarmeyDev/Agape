from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest import mock

from agape_mainframe.project_planner import classify_project_type, project_blueprint

BUSINESS_PLAN_PROMPT = """I want to create a professional 2027 business plan for a UK commercial flooring and interiors company. The finished result should be suitable for a bank, investor or business partner. Research current public information. The final output should be a professionally structured document that I can review and download as DOCX and PDF. I do not need software development, Android development, coding agents or developer testing tools for this project unless Agape identifies a genuine reason they are required."""


def test_negated_coding_words_do_not_turn_business_plan_into_development():
    assert classify_project_type(BUSINESS_PLAN_PROMPT, 'auto') == 'document'
    b = project_blueprint(BUSINESS_PLAN_PROMPT, 'auto')
    assert b['project_type'] == 'document'
    assert b['show_coding_options'] is False
    ids = {x['id'] for x in b['tools']}
    assert 'document-studio' in ids
    assert 'appium-android' not in ids
    assert 'aider' not in ids
    assert 'openhands' not in ids


def test_positive_android_request_still_routes_to_development():
    text='Build an Android mobile app and test the APK with Appium.'
    b=project_blueprint(text,'auto')
    assert b['project_type']=='development'
    assert b['subtype']=='android'
    assert b['show_coding_options'] is True


def test_project_first_ui_resets_stale_saved_project_source():
    js=(Path(__file__).resolve().parents[1]/'web/app.js').read_text(encoding='utf-8')
    assert "if($('project'))$('project').value='0';setSourceMode('paste')" in js
    assert "FILE=null" in js


def _load_document_studio():
    root=Path(__file__).resolve().parents[1]
    path=root/'recovered/agape-document-studio/document_studio.py'
    spec=importlib.util.spec_from_file_location('agape_doc_r261',path)
    mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_windows_output_components_bound_long_test_install_paths(tmp_path):
    ds=_load_document_studio()
    long_root=tmp_path/('Agape-R260-ProjectFirst-Test-'+'2'*40)/'data'/'services'/'document-studio'/'outputs'
    title='I want to create a professional 2027 business plan for a UK commercial flooring and interiors company'
    root,folder,name,stamp=ds._windows_output_components(long_root,title,title,'docx',windows=True)
    final=root/(name+'-'+stamp+'.docx')
    assert len(str(final)) < 248
    assert len(folder) <= 36
    assert len(name) <= 72
    assert folder and name


def test_document_create_uses_bounded_runtime_tmp_and_path_guard():
    root=Path(__file__).resolve().parents[1]
    text=(root/'recovered/agape-document-studio/document_studio.py').read_text(encoding='utf-8')
    assert '_windows_output_components(OUTPUTS' in text
    assert 'runtime_tmp=DATA/"runtime-tmp"' in text
    assert 'DOCUMENT_OUTPUT_PATH_TOO_LONG' in text
