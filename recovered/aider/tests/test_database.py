import tempfile
import unittest
from pathlib import Path

from agape_studio.database import StudioDatabase
from agape_studio.settings import SettingsService


class DatabaseTests(unittest.TestCase):
    def test_schema_quick_check_and_settings(self):
        with tempfile.TemporaryDirectory() as td:
            db = StudioDatabase(Path(td) / 'studio.sqlite3')
            self.assertTrue(db.quick_check())
            settings = SettingsService(db)
            settings.set('theme', {'name': 'dark'})
            self.assertEqual(settings.get('theme'), {'name': 'dark'})
            self.assertEqual(db.table_counts()['projects'], 0)


if __name__ == '__main__': unittest.main()

class DatabaseMigrationTests(unittest.TestCase):
    def test_v01_database_upgrades_without_losing_project_history(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'studio.sqlite3'
            conn = sqlite3.connect(path)
            conn.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,path TEXT NOT NULL UNIQUE,last_opened TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,state_json TEXT NOT NULL DEFAULT "{}")')
            conn.execute('CREATE TABLE ai_history (id INTEGER PRIMARY KEY AUTOINCREMENT,project_path TEXT,role TEXT NOT NULL,content TEXT NOT NULL,model TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            conn.execute('CREATE TABLE terminal_history (id INTEGER PRIMARY KEY AUTOINCREMENT,project_path TEXT,argv_json TEXT NOT NULL,exit_code INTEGER,stdout TEXT NOT NULL DEFAULT "",stderr TEXT NOT NULL DEFAULT "",created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            conn.execute('CREATE TABLE extension_state (extension_id TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1,state_json TEXT NOT NULL DEFAULT "{}")')
            conn.execute('CREATE TABLE settings (key TEXT PRIMARY KEY,value_json TEXT NOT NULL)')
            conn.execute('INSERT INTO meta(key,value) VALUES (?,?)', ('schema_version','1'))
            conn.execute('INSERT INTO projects(name,path) VALUES (?,?)', ('Old Project','C:/old/project'))
            conn.execute('INSERT INTO ai_history(project_path,role,content,model) VALUES (?,?,?,?)', ('C:/old/project','user','hello','old-model'))
            conn.commit(); conn.close()
            db = StudioDatabase(path)
            self.assertTrue(db.quick_check())
            self.assertEqual(db.recent_projects()[0]['name'], 'Old Project')
            self.assertEqual(db.table_counts()['projects'], 1)
            self.assertEqual(db.table_counts()['ai_history'], 1)
            self.assertIn('connection_tests', db.table_counts())
            self.assertIn('quality_items', db.table_counts())
            self.assertIn('tool_runs', db.table_counts())
            self.assertEqual(db.table_counts()['tool_runs'], 0)
