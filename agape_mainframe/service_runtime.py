from __future__ import annotations

import os
import runpy
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .state import DATA_ROOT, ROOT

INTERNAL_SERVICE_FLAG = "--agape-internal-service"
SERVICE_SOURCES = {
    "document-studio": ROOT / "recovered" / "agape-document-studio" / "document_studio.py",
    "workflow-bridge": ROOT / "recovered" / "unified-r24" / "app.py",
}


def _pyinstaller_dependency_hints() -> None:
    """Static imports used only so PyInstaller sees dependencies of data-file services.

    The recovered services are executed with runpy from bundled data files. PyInstaller
    cannot inspect those data files for imports, so these imports deliberately live in a
    never-called function that its module graph can still discover.
    """
    import requests  # noqa: F401
    import keyring  # noqa: F401
    import pypdf  # noqa: F401
    import pymupdf  # noqa: F401
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    import odf  # noqa: F401
    import odf.draw  # noqa: F401
    import odf.office  # noqa: F401
    import odf.opendocument  # noqa: F401
    import odf.style  # noqa: F401
    import odf.table  # noqa: F401
    import odf.teletype  # noqa: F401
    import odf.text  # noqa: F401
    import docx  # noqa: F401
    import openpyxl  # noqa: F401
    import pptx  # noqa: F401
    import spellchecker  # noqa: F401
    import llama_index.core  # noqa: F401
    import llama_index.readers.file  # noqa: F401
    import langchain_core.documents  # noqa: F401
    import langchain_text_splitters  # noqa: F401


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def service_source_path(name: str) -> Path:
    try:
        return SERVICE_SOURCES[name]
    except KeyError as exc:
        raise ValueError(f"UNKNOWN_INTERNAL_SERVICE={name}") from exc


def service_working_directory(name: str) -> Path:
    return service_source_path(name).parent


def service_command(name: str, *args: str) -> list[str]:
    """Return a launch command that works in source and frozen builds.

    Source builds use the current Python interpreter. Frozen builds relaunch the Agape
    executable with a hidden service mode instead of incorrectly treating the executable
    as a Python interpreter.
    """
    source = service_source_path(name)
    if is_frozen():
        return [sys.executable, INTERNAL_SERVICE_FLAG, name, *map(str, args)]
    return [sys.executable, str(source), *map(str, args)]


def service_environment_overrides(name: str) -> dict[str, str]:
    services_root = DATA_ROOT / "services"
    services_root.mkdir(parents=True, exist_ok=True)
    if name == "document-studio":
        root = services_root / "document-studio"
        return {
            "AGAPE_DOCUMENT_DATA": str(root),
            "AGAPE_DOCUMENT_TEMPLATES": str(root / "templates"),
            "AGAPE_DOCUMENT_OUTPUTS": str(root / "outputs"),
            "AGAPE_DOCUMENT_SETTINGS": str(root / "settings.json"),
        }
    if name == "workflow-bridge":
        root = services_root / "workflow-r24"
        return {"AGAPE_UNIFIED_DATA": str(root)}
    service_source_path(name)
    return {}


def service_environment(name: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(service_environment_overrides(name))
    return env


def runtime_log_dir() -> Path:
    path = DATA_ROOT / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _service_process_context(source: Path, argv: list[str]) -> Iterator[None]:
    old_argv = list(sys.argv)
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    try:
        sys.argv = [str(source), *argv]
        os.chdir(source.parent)
        source_dir = str(source.parent)
        if source_dir not in sys.path:
            sys.path.insert(0, source_dir)
        yield
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
        sys.path[:] = old_path


def run_internal_service(name: str, argv: list[str] | tuple[str, ...]) -> int:
    source = service_source_path(name)
    if not source.is_file():
        raise RuntimeError(f"INTERNAL_SERVICE_SOURCE_MISSING={source}")
    changed_env: dict[str, str | None] = {}
    for key, value in service_environment_overrides(name).items():
        changed_env[key] = os.environ.get(key)
        os.environ.setdefault(key, value)
    try:
        with _service_process_context(source, [str(x) for x in argv]):
            try:
                runpy.run_path(str(source), run_name="__main__")
            except SystemExit as exc:
                code = exc.code
                if code is None:
                    return 0
                if isinstance(code, int):
                    return code
                raise
        return 0
    finally:
        for key, old in changed_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def dispatch_internal_service(argv: list[str] | None = None) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != INTERNAL_SERVICE_FLAG:
        return None
    if len(args) < 2:
        raise SystemExit("Missing internal service name")
    return run_internal_service(args[1], args[2:])
