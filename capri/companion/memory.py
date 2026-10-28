"""Inspectable SQLite memory. Facts come from explicit edits, never inference."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Memory:
    def __init__(self, directory):
        self.path = Path(directory) / 'capri-memory.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY, content TEXT NOT NULL,
                    source TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS dialogue (
                    id INTEGER PRIMARY KEY, role TEXT NOT NULL,
                    content TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, session TEXT NOT NULL,
                    state TEXT NOT NULL, project TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def remember(self, text):
        text = text.strip()
        if not text or len(text) > 2000:
            raise ValueError('A memory needs 1–2000 characters.')
        with self.connect() as db:
            return db.execute('INSERT INTO facts(content,source,created_at) VALUES (?,?,?)',
                              (text, 'explicit_user_edit', timestamp())).lastrowid

    def forget(self, item_id):
        with self.connect() as db:
            return db.execute('DELETE FROM facts WHERE id=?', (int(item_id),)).rowcount == 1

    def facts(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM facts ORDER BY id')]

    def say(self, role, text):
        if role not in ('user', 'assistant'):
            raise ValueError('Invalid dialogue role')
        with self.connect() as db:
            db.execute('INSERT INTO dialogue(role,content,created_at) VALUES (?,?,?)',
                       (role, text[:16000], timestamp()))

    def recent(self, count=20):
        with self.connect() as db:
            rows = db.execute('SELECT role,content FROM dialogue ORDER BY id DESC LIMIT ?', (count,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def event(self, item):
        with self.connect() as db:
            inserted = db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)',
                       (item['id'], item['source'], item['session'], item['state'],
                        item['project'], item['timestamp'])).rowcount
            db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY rowid DESC LIMIT 10000)')
        return bool(inserted)

    def events(self, limit=100):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events ORDER BY rowid DESC LIMIT ?', (limit,))]

    def clear_dialogue(self):
        with self.connect() as db:
            db.execute('DELETE FROM dialogue')

    def clear_events(self):
        with self.connect() as db:
            db.execute('DELETE FROM events')

    def export(self, target):
        with self.connect() as db:
            result = {table: [dict(r) for r in db.execute(f'SELECT * FROM {table}')]
                      for table in ('facts', 'dialogue', 'events')}
        Path(target).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

