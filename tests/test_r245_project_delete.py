from __future__ import annotations
import sqlite3
from pathlib import Path
from unittest import mock
from agape_mainframe import bridge


def make_db(path: Path) -> None:
    con=sqlite3.connect(path)
    try:
        con.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE projects(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL DEFAULT 'user',
          archived INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          role TEXT NOT NULL,
          content TEXT NOT NULL
        );
        INSERT INTO projects(id,name,kind,archived) VALUES(1,'Old user project','user',0);
        INSERT INTO projects(id,name,kind,archived) VALUES(2,'System project','system',0);
        INSERT INTO messages(project_id,role,content) VALUES(1,'user','old source');
        """)
        con.commit()
    finally:
        con.close()


def test_delete_user_project_cascades_core_rows(tmp_path: Path):
    db=tmp_path/'core.sqlite3'; make_db(db)
    with mock.patch.object(bridge,'_find_core_db',return_value=db):
        result=bridge.delete_project(1)
    assert result['ok'] is True and result['deleted'] is True and result['project_id']==1
    con=sqlite3.connect(db)
    try:
        assert con.execute('SELECT COUNT(*) FROM projects WHERE id=1').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM messages WHERE project_id=1').fetchone()[0]==0
    finally: con.close()


def test_delete_rejects_non_user_project(tmp_path: Path):
    db=tmp_path/'core.sqlite3'; make_db(db)
    with mock.patch.object(bridge,'_find_core_db',return_value=db):
        try:
            bridge.delete_project(2)
        except ValueError as exc:
            assert str(exc)=='PROJECT_DELETE_FORBIDDEN'
        else:
            raise AssertionError('system project deletion must be rejected')


def test_mainframe_wires_delete_route_and_projects_button():
    root=Path(__file__).resolve().parents[1]
    server=(root/'agape_mainframe/server.py').read_text(encoding='utf-8')
    js=(root/'web/app.js').read_text(encoding='utf-8')
    css=(root/'web/styles.css').read_text(encoding='utf-8')
    assert 'if u.path=="/api/projects/delete"' in server
    assert 'bridge_delete_project' in server
    assert 'data-delete-pid' in js
    assert "api('/api/projects/delete'" in js
    assert 'window.confirm' in js
    assert 'Existing generated results remain in Results & versions.' in js
    assert '.project-delete' in css
