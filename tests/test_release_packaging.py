from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_bundles_internal_service_assets_on_all_platforms():
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert text.count("recovered/agape-document-studio") >= 3
    assert text.count("recovered/unified-r24") >= 3
    assert "--agape-internal-service document-studio" in text
    assert "--agape-internal-service workflow-bridge" in text


def test_build_requirements_include_service_runtime_dependencies():
    build = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
    runtime = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
    assert "-r requirements-runtime.txt" in build
    for dependency in ("requests", "keyring", "pypdf", "pymupdf", "python-docx", "openpyxl", "python-pptx"):
        assert dependency in runtime


def test_version_metadata_matches_public_v55_line():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "agape_mainframe" / "__init__.py").read_text(encoding="utf-8")
    assert 'version = "5.5.0"' in pyproject
    assert '__version__ = "5.5.0"' in package
