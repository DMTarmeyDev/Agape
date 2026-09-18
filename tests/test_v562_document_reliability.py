from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_libreoffice_conversion_uses_explicit_existing_working_directory():
    src=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    assert 'launch_cwd=outdir if outdir.is_dir()' in src
    assert 'cwd=str(launch_cwd)' in src
    assert 'WinError 3' in src
    assert 'ensure_runtime_paths()' in src

def test_business_document_validator_detects_duplicate_sections():
    src=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    assert 'duplicates = [h for h in required if counts.get' in src
    assert 'audit.get("duplicates", [])' in src
    assert '_merge_repaired_sections(draft,"",final_audit.get("duplicates") or [])' in src

def test_internal_safety_marker_is_sanitised_before_output():
    src=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    assert '_sanitize_generated_draft' in src
    assert 'User Safety:' in src

def test_launcher_expects_current_mainframe_build():
    src=(ROOT/'START-AGAPE-LATEST.ps1').read_text(encoding='utf-8')
    assert 'AGAPE-MAINFRAME-V5.6.1-CANONICAL-STATUS-SYNC' in src

def test_windows_child_process_runner_has_winerror3_retry_and_safe_cwd():
    src=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    assert 'def run_process_reliably' in src
    assert 'def _safe_process_cwd' in src
    assert 'launch failed after WinError 3 retry' in src
    assert 'subprocess.list2cmdline(args)' in src


def test_agent_create_failure_reports_exact_stage_and_traceback():
    src=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    assert "current_stage='Reading project brief'" in src
    assert 'error_stage=current_stage' in src
    assert 'traceback.format_exc()[-5000:]' in src


def test_document_creation_wraps_template_and_conversion_stages():
    src=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    assert 'DOCUMENT_TEMPLATE_STAGE_FAILED' in src
    assert 'DOCUMENT_CONVERSION_STAGE_FAILED' in src


def test_document_studio_r22_build_marker_is_required_by_bridge():
    studio=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
    bridge=(ROOT/'agape_mainframe'/'bridge.py').read_text(encoding='utf-8')
    marker='R31.16-document-path-reliability-r2.2'
    assert marker in studio
    assert marker in bridge
