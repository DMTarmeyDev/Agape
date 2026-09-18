from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .database import StudioDatabase


class ProjectError(ValueError):
    pass


class ProjectService:
    def __init__(self, db: StudioDatabase, projects_root: Path):
        self.db = db
        self.projects_root = Path(projects_root).resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        value = re.sub(r'[^A-Za-z0-9._ -]+', '', str(name or '')).strip()
        if not value or value in {'.', '..'}:
            raise ProjectError('INVALID_PROJECT_NAME')
        return value

    def create(self, name: str) -> dict[str, Any]:
        clean = self._safe_name(name)
        path = (self.projects_root / clean).resolve()
        if path.parent != self.projects_root:
            raise ProjectError('PROJECT_PATH_ESCAPE')
        path.mkdir(parents=True, exist_ok=True)
        readme = path / 'README.md'
        if not readme.exists():
            readme.write_bytes(f'# {clean}\n'.encode('utf-8'))
        return self.open(path)

    def open(self, path: Path | str) -> dict[str, Any]:
        path = Path(path).expanduser().resolve()
        if not path.is_dir():
            raise ProjectError('PROJECT_NOT_FOUND')
        return self.db.upsert_project(path.name, str(path))

    def recent(self) -> list[dict[str, Any]]:
        return self.db.recent_projects()

    def _resolve_inside(self, project_path: str, relative: str) -> Path:
        root = Path(project_path).resolve()
        if not root.is_dir():
            raise ProjectError('PROJECT_NOT_FOUND')
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ProjectError('PATH_OUTSIDE_PROJECT') from exc
        return target

    def list_files(self, project_path: str, limit: int = 500) -> list[str]:
        root = Path(project_path).resolve()
        if not root.is_dir():
            raise ProjectError('PROJECT_NOT_FOUND')
        out: list[str] = []
        for item in sorted(root.rglob('*')):
            if item.is_file() and '.git' not in item.parts:
                out.append(item.relative_to(root).as_posix())
                if len(out) >= limit:
                    break
        return out

    def read_file(self, project_path: str, relative: str, max_bytes: int = 2_000_000) -> str:
        target = self._resolve_inside(project_path, relative)
        if not target.is_file():
            raise ProjectError('FILE_NOT_FOUND')
        data = target.read_bytes()
        if len(data) > max_bytes:
            raise ProjectError('FILE_TOO_LARGE')
        return data.decode('utf-8')

    def write_file(self, project_path: str, relative: str, content: str) -> dict[str, Any]:
        target = self._resolve_inside(project_path, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = str(content).encode('utf-8')
        target.write_bytes(payload)
        return {'ok': True, 'path': str(target), 'bytes': len(payload)}
