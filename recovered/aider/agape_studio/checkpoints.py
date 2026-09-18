from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CheckpointService:
    def __init__(self, checkpoint_root: Path):
        self.root = Path(checkpoint_root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                h.update(chunk)
        return h.hexdigest().upper()

    def create(self, project_path: str, name: str = 'checkpoint') -> dict[str, Any]:
        src = Path(project_path).resolve()
        if not src.is_dir():
            raise ValueError('PROJECT_NOT_FOUND')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        dest = self.root / f'{stamp}-{name}'
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        files = []
        for path in sorted(dest.rglob('*')):
            if path.is_file():
                files.append({'path': path.relative_to(dest).as_posix(), 'sha256': self._hash_file(path)})
        manifest = {'project': str(src), 'checkpoint': str(dest), 'files': files}
        (dest / 'checkpoint-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        return {'ok': True, 'path': str(dest), 'files': len(files)}
