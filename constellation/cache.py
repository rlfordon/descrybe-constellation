"""SQLite-backed API cache: every remote payload is paid for once, ever."""

import json
import sqlite3
import threading
import time
from pathlib import Path


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + a lock: FastAPI runs sync endpoints on a
        # threadpool, so cache calls arrive from many threads (default sqlite
        # thread affinity 500s on the first unlucky thread switch)
        self._con = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS api_cache ("
                " key TEXT PRIMARY KEY, value TEXT NOT NULL, fetched_at REAL NOT NULL)"
            )
            self._con.commit()

    def get(self, key):
        with self._lock:
            row = self._con.execute(
                "SELECT value FROM api_cache WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO api_cache (key, value, fetched_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, default=str), time.time()),
            )
            self._con.commit()
        return value

    def get_or(self, key, fetch):
        """Return the cached value for key, or call fetch() and cache its result."""
        hit = self.get(key)
        if hit is not None:
            return hit
        return self.put(key, fetch())

    def stats(self):
        with self._lock:
            (n,) = self._con.execute("SELECT COUNT(*) FROM api_cache").fetchone()
        return {"entries": n, "path": str(self.path)}
