from __future__ import annotations

import json
from typing import Any

from .database import StudioDatabase


class SettingsService:
    def __init__(self, db: StudioDatabase):
        self.db = db

    def set(self, key: str, value: Any) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                'INSERT INTO settings(key,value_json) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',
                (str(key), json.dumps(value)),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, key: str, default: Any = None) -> Any:
        conn = self.db.connect()
        try:
            row = conn.execute('SELECT value_json FROM settings WHERE key=?', (str(key),)).fetchone()
            return default if row is None else json.loads(row[0])
        finally:
            conn.close()
