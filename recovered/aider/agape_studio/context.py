from __future__ import annotations

from dataclasses import dataclass

from .ai import AIRouter
from .aider_tool import AiderService
from .config import StudioConfig
from .connections import ConnectionService
from .database import StudioDatabase
from .extensions import ExtensionHost
from .planning import ToolPlanner
from .projects import ProjectService
from .quality import QUALITY_CATALOG
from .terminal import TerminalService


@dataclass
class StudioContext:
    config: StudioConfig
    db: StudioDatabase
    projects: ProjectService
    terminal: TerminalService
    ai: AIRouter
    connections: ConnectionService
    extensions: ExtensionHost
    aider: AiderService
    planner: ToolPlanner


def build_context(config: StudioConfig, providers=None) -> StudioContext:
    config.data_root.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    db = StudioDatabase(config.data_root / 'agape_studio.sqlite3')
    db.seed_quality_items(QUALITY_CATALOG)
    ai = AIRouter(db, providers=providers)
    aider = AiderService(db)
    return StudioContext(
        config=config,
        db=db,
        projects=ProjectService(db, config.projects_root),
        terminal=TerminalService(db),
        ai=ai,
        connections=ConnectionService(ai),
        extensions=ExtensionHost(config.extensions_root),
        aider=aider,
        planner=ToolPlanner(ai, aider),
    )
