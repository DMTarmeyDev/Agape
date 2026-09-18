from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3


class StudioDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        statements = [
            'CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
            '''CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                last_opened TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                state_json TEXT NOT NULL DEFAULT '{}'
            )''',
            '''CREATE TABLE IF NOT EXISTS ai_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS terminal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT,
                argv_json TEXT NOT NULL,
                exit_code INTEGER,
                stdout TEXT NOT NULL DEFAULT '',
                stderr TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS extension_state (
                extension_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                state_json TEXT NOT NULL DEFAULT '{}'
            )''',
            '''CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS connection_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                latency_ms INTEGER,
                source TEXT NOT NULL DEFAULT 'test',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS quality_items (
                item_id TEXT PRIMARY KEY,
                area TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                passed_at TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS tool_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool TEXT NOT NULL,
                project_path TEXT,
                task TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''',
        ]
        with self._lock:
            conn = self.connect()
            try:
                for stmt in statements:
                    conn.execute(stmt)
                conn.execute('INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)', ('schema_version', str(SCHEMA_VERSION)))
                conn.commit()
            finally:
                conn.close()

    def quick_check(self) -> bool:
        with self._lock:
            conn = self.connect()
            try:
                row = conn.execute('PRAGMA quick_check').fetchone()
                return bool(row and row[0] == 'ok')
            finally:
                conn.close()

    def upsert_project(self, name: str, path: str) -> dict[str, Any]:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    '''INSERT INTO projects(name,path,last_opened) VALUES (?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(path) DO UPDATE SET name=excluded.name,last_opened=CURRENT_TIMESTAMP''',
                    (name, path),
                )
                conn.commit()
                row = conn.execute('SELECT * FROM projects WHERE path=?', (path,)).fetchone()
                return dict(row)
            finally:
                conn.close()

    def recent_projects(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            conn = self.connect()
            try:
                rows = conn.execute('SELECT * FROM projects ORDER BY last_opened DESC, id DESC LIMIT ?', (int(limit),)).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def project_registered(self, path: str) -> bool:
        with self._lock:
            conn = self.connect()
            try:
                row = conn.execute('SELECT 1 FROM projects WHERE path=? LIMIT 1', (str(Path(path).resolve()),)).fetchone()
                return bool(row)
            finally:
                conn.close()

    def add_ai_history(self, project_path: str | None, role: str, content: str, model: str | None = None) -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute('INSERT INTO ai_history(project_path,role,content,model) VALUES (?,?,?,?)', (project_path, role, content, model))
                conn.commit()
            finally:
                conn.close()

    def add_terminal_history(self, project_path: str | None, argv: list[str], exit_code: int, stdout: str, stderr: str) -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    'INSERT INTO terminal_history(project_path,argv_json,exit_code,stdout,stderr) VALUES (?,?,?,?,?)',
                    (project_path, json.dumps(argv), int(exit_code), stdout, stderr),
                )
                conn.commit()
            finally:
                conn.close()

    def record_connection_test(self, provider: str, model: str | None, status: str, detail: str, latency_ms: int | None = None, source: str = 'test') -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    '''INSERT INTO connection_tests(provider,model,status,detail,latency_ms,source)
                       VALUES (?,?,?,?,?,?)''',
                    (provider, model, status, detail[:2000], latency_ms, source),
                )
                conn.commit()
            finally:
                conn.close()

    def connection_test_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            conn = self.connect()
            try:
                rows = conn.execute(
                    'SELECT * FROM connection_tests ORDER BY id DESC LIMIT ?', (max(1, min(int(limit), 500)),)
                ).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def record_tool_run(self, tool: str, project_path: str | None, task: str, status: str, result: dict[str, Any]) -> None:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    'INSERT INTO tool_runs(tool,project_path,task,status,result_json) VALUES (?,?,?,?,?)',
                    (str(tool), project_path, str(task)[:4000], str(status).upper(), json.dumps(result, ensure_ascii=False)[:24000]),
                )
                conn.commit()
            finally:
                conn.close()

    def tool_run_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            conn = self.connect()
            try:
                rows = conn.execute(
                    'SELECT * FROM tool_runs ORDER BY id DESC LIMIT ?', (max(1, min(int(limit), 500)),)
                ).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    def seed_quality_items(self, items: list[dict[str, Any]]) -> None:
        with self._lock:
            conn = self.connect()
            try:
                for item in items:
                    conn.execute(
                        '''INSERT OR IGNORE INTO quality_items(item_id,area,title,status,detail,evidence)
                           VALUES (?,?,?,?,?,?)''',
                        (str(item['id']), str(item['area']), str(item['title']), 'NOT_TESTED', '', ''),
                    )
                conn.commit()
            finally:
                conn.close()

    def set_quality_item(self, item_id: str, area: str, title: str, status: str, detail: str = '', evidence: str = '') -> None:
        normalized = str(status).upper()
        passed_sql = "CURRENT_TIMESTAMP" if normalized == 'PASS' else 'NULL'
        with self._lock:
            conn = self.connect()
            try:
                conn.execute(
                    f'''INSERT INTO quality_items(item_id,area,title,status,detail,evidence,updated_at,passed_at)
                        VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,{passed_sql})
                        ON CONFLICT(item_id) DO UPDATE SET
                          area=excluded.area,title=excluded.title,status=excluded.status,
                          detail=excluded.detail,evidence=excluded.evidence,updated_at=CURRENT_TIMESTAMP,
                          passed_at=CASE WHEN excluded.status='PASS' THEN CURRENT_TIMESTAMP ELSE quality_items.passed_at END''',
                    (item_id, area, title, normalized, detail[:4000], evidence[:4000]),
                )
                conn.commit()
            finally:
                conn.close()

    def quality_status(self) -> dict[str, Any]:
        with self._lock:
            conn = self.connect()
            try:
                rows = [dict(x) for x in conn.execute('SELECT * FROM quality_items ORDER BY area,item_id').fetchall()]
            finally:
                conn.close()
        passed = [x for x in rows if x['status'] == 'PASS']
        open_items = [x for x in rows if x['status'] != 'PASS']
        return {'ok': True, 'total': len(rows), 'passed_count': len(passed), 'open_count': len(open_items), 'passed': passed, 'open': open_items}

    def table_counts(self) -> dict[str, int]:
        tables = ['projects', 'ai_history', 'terminal_history', 'extension_state', 'settings', 'connection_tests', 'quality_items', 'tool_runs']
        with self._lock:
            conn = self.connect()
            try:
                return {table: int(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]) for table in tables}
            finally:
                conn.close()
