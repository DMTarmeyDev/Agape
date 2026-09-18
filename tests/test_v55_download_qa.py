from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_download_proxy_uses_current_workflow_bridge_not_legacy_8840():
    src=(ROOT/'agape_mainframe'/'server.py').read_text(encoding='utf-8')
    assert 'url=R24+path' in src
    assert 'http://127.0.0.1:8840"+path' not in src


def test_review_disclosure_and_download_manager_contract():
    html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
    js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
    for marker in ['missingDetails','missingSummary','researchProgress','researchBar','briefChangeDetails','downloadManagerButton','downloadManagerPanel','downloadManagerItems']:
        assert marker in html
    assert '<details id="missingDetails"' in html
    assert '<details id="briefChangeDetails"' in html
    assert 'startResearchProgress' in js and 'finishResearchProgress' in js
    assert 'downloadManagedFile' in js and 'Estimated remaining' in js
    assert 'Retry download' in js and 'Download again' in js and 'Open folder' in js


def test_workflow_bridge_capability_reports_current_port():
    text=(ROOT/'capabilities'/'workflow-bridge.json').read_text(encoding='utf-8')
    assert '"port": 8852' in text


def test_full_dummy_browser_qa_script_is_bundled():
    script=(ROOT/'scripts'/'full_dummy_qa.py')
    assert script.is_file()
    text=script.read_text(encoding='utf-8')
    for marker in ['prepare_with_ai','research_own_progress_bar','download_finished_docx_real_click','retry_pdf_download_real_click','validate_browser_pdf']:
        assert marker in text


def test_download_manager_is_current_job_only_and_creation_failures_do_not_say_retry_download():
    js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
    assert "String(item.jobId || '') === currentJob" in js
    assert "DOWNLOAD_MANAGER.items = [];" in js
    assert "DOWNLOAD_MANAGER.items = fresh.slice(0,80);" in js
    assert "Result creation stopped before a new file was produced" in js


def test_document_studio_build_marker_rejects_stale_child_service():
    bridge=(ROOT/'agape_mainframe'/'bridge.py').read_text(encoding='utf-8')
    studio=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    marker='R31.16-document-path-reliability-r2'
    assert marker in bridge and marker in studio
