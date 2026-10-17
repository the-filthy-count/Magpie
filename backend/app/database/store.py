import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DEFAULTS = dict(concurrency=2, retries=3, timeout=30, rate_limit=0, theme='dark',
                retention_days=90, organisation='organised', filename='', directory=[], advanced={})

class Store:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS destinations (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
              description TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT 'folder',
              is_default INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS jobs (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
              url TEXT NOT NULL, website TEXT NOT NULL, destination_id TEXT NOT NULL,
              destination_name TEXT NOT NULL, destination_path TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL,
              started_at TEXT, completed_at TEXT, files INTEGER NOT NULL DEFAULT 0,
              skipped INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
              speed REAL, current_filename TEXT, file_bytes INTEGER, file_total INTEGER,
              error TEXT, attempts INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, seq);
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS api_tokens (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, digest TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS cookies (
              id TEXT PRIMARY KEY, website TEXT UNIQUE NOT NULL, updated_at TEXT NOT NULL);
            ''')
            if 'total_files' not in {row[1] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute('ALTER TABLE jobs ADD COLUMN total_files INTEGER')
            if not db.execute("SELECT 1 FROM kv WHERE key='settings'").fetchone():
                db.execute('INSERT INTO kv VALUES (?,?)', ('settings', json.dumps(DEFAULTS)))
    @contextmanager
    def db(self):
        with self.lock:
            con = sqlite3.connect(self.path, timeout=15)
            con.row_factory = sqlite3.Row
            try:
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                con.close()
    def all(self, sql, args=()):
        with self.db() as db:
            return [dict(row) for row in db.execute(sql, args)]
    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None
    def execute(self, sql, args=()):
        with self.db() as db:
            return db.execute(sql, args).rowcount
    def get(self, key, default=None):
        row = self.one('SELECT value FROM kv WHERE key=?', (key,))
        return json.loads(row['value']) if row else default
    def set(self, key, value):
        self.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (key, json.dumps(value)))
