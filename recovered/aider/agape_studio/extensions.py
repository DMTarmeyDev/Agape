from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class ExtensionError(RuntimeError):
    pass


class ExtensionHost:
    def __init__(self, extensions_root: Path):
        self.extensions_root = Path(extensions_root)

    def discover(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.extensions_root.exists():
            return out
        for manifest_path in sorted(self.extensions_root.glob('*/extension.json')):
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest['_root'] = str(manifest_path.parent)
                out.append(manifest)
            except Exception:
                continue
        return out

    def _find(self, extension_id: str) -> dict[str, Any]:
        for manifest in self.discover():
            if manifest.get('id') == extension_id:
                return manifest
        raise ExtensionError('EXTENSION_NOT_FOUND')

    def run(self, extension_id: str, action: str, payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
        manifest = self._find(extension_id)
        actions = manifest.get('actions') or []
        if action not in actions:
            raise ExtensionError('EXTENSION_ACTION_NOT_ALLOWED')
        entry = Path(manifest['_root']) / str(manifest.get('entry', 'extension.py'))
        if not entry.is_file():
            raise ExtensionError('EXTENSION_ENTRY_NOT_FOUND')
        request = json.dumps({'action': action, 'payload': payload})
        proc = subprocess.run(
            [sys.executable, str(entry)],
            input=request,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 30)),
            shell=False,
        )
        if proc.returncode != 0:
            raise ExtensionError('EXTENSION_FAILED: ' + proc.stderr.strip())
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ExtensionError('EXTENSION_INVALID_JSON') from exc
        return {'ok': True, 'extension': extension_id, 'action': action, 'result': result}
