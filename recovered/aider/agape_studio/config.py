from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StudioConfig:
    data_root: Path
    projects_root: Path
    extensions_root: Path
    ui_root: Path
    host: str = '127.0.0.1'
    port: int = 8797

    @classmethod
    def default(cls, project_root: Path | None = None) -> 'StudioConfig':
        project_root = Path(project_root or Path(__file__).resolve().parents[1])
        if os.name == 'nt':
            local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
            docs = Path.home() / 'Documents'
            data_root = Path(os.environ.get('AGAPE_STUDIO_DATA', local / 'AgapeAIStudio' / 'data'))
            projects_root = Path(os.environ.get('AGAPE_STUDIO_PROJECTS', docs / 'Agape AI Studio Projects'))
        else:
            data_root = Path(os.environ.get('AGAPE_STUDIO_DATA', Path.home() / '.agape-ai-studio' / 'data'))
            projects_root = Path(os.environ.get('AGAPE_STUDIO_PROJECTS', Path.home() / 'Agape AI Studio Projects'))
        return cls(
            data_root=data_root,
            projects_root=projects_root,
            extensions_root=project_root / 'extensions',
            ui_root=project_root / 'ui',
        )
