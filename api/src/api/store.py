"""Local storage for workspaces, areas, jobs and cached results (decision 0004)."""

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused
    name TEXT NOT NULL,
    settings TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    geometry TEXT NOT NULL,
    area_km2 REAL NOT NULL,
    UNIQUE (workspace_id, name)
);
CREATE TABLE IF NOT EXISTS results (
    key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    area_id INTEGER REFERENCES areas(id) ON DELETE SET NULL,
    request TEXT NOT NULL,
    result_key TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
"""


def default_path() -> Path:
    """~/.magonia/magonia.db, or the folder named by MAGONIA_DATA_DIR."""
    folder = Path(os.environ.get("MAGONIA_DATA_DIR", Path.home() / ".magonia"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "magonia.db"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    """A thin layer over one SQLite file, safe to use from the job threads."""

    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.execute(
            "UPDATE jobs SET status = 'failed', error = ?, updated = ? "
            "WHERE status IN ('queued', 'running')",
            ("The API stopped before this job finished. Please run it again.", now()),
        )

    def execute(self, sql: str, values: tuple = ()) -> sqlite3.Cursor:
        with self.lock, self.db:
            return self.db.execute(sql, values)

    def rows(self, sql: str, values: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, values).fetchall()]

    def row(self, sql: str, values: tuple = ()) -> dict | None:
        found = self.rows(sql, values)
        return found[0] if found else None

    # Workspaces

    def create_workspace(self, name: str) -> dict:
        stamp = now()
        cursor = self.execute(
            "INSERT INTO workspaces (name, created, updated) VALUES (?, ?, ?)", (name, stamp, stamp)
        )
        return self.workspace(cursor.lastrowid)

    def workspace(self, workspace_id: int) -> dict | None:
        found = self.row("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        if found:
            found["settings"] = json.loads(found["settings"])
        return found

    def workspaces(self) -> list[dict]:
        return self.rows("SELECT id, name, created, updated FROM workspaces ORDER BY updated DESC")

    def update_workspace(self, workspace_id: int, name: str | None, settings: dict | None) -> None:
        if name is not None:
            self.execute("UPDATE workspaces SET name = ? WHERE id = ?", (name, workspace_id))
        if settings is not None:
            self.execute(
                "UPDATE workspaces SET settings = ? WHERE id = ?",
                (json.dumps(settings), workspace_id),
            )
        self.touch(workspace_id)

    def delete_workspace(self, workspace_id: int) -> None:
        self.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))

    def touch(self, workspace_id: int | None) -> None:
        if workspace_id is not None:
            self.execute("UPDATE workspaces SET updated = ? WHERE id = ?", (now(), workspace_id))

    # Areas

    def create_area(self, workspace_id: int, name: str, geometry: dict, area_km2: float) -> dict:
        cursor = self.execute(
            "INSERT INTO areas (workspace_id, name, geometry, area_km2) VALUES (?, ?, ?, ?)",
            (workspace_id, name, json.dumps(geometry), area_km2),
        )
        self.touch(workspace_id)
        return self.area(cursor.lastrowid)

    def area(self, area_id: int) -> dict | None:
        found = self.row("SELECT * FROM areas WHERE id = ?", (area_id,))
        if found:
            found["geometry"] = json.loads(found["geometry"])
        return found

    def areas(self, workspace_id: int) -> list[dict]:
        found = self.rows("SELECT * FROM areas WHERE workspace_id = ? ORDER BY id", (workspace_id,))
        for area in found:
            area["geometry"] = json.loads(area["geometry"])
        return found

    def rename_area(self, area_id: int, name: str) -> None:
        self.execute("UPDATE areas SET name = ? WHERE id = ?", (name, area_id))

    def delete_area(self, area_id: int) -> None:
        self.execute("DELETE FROM areas WHERE id = ?", (area_id,))

    # Jobs and cached results

    def create_job(
        self, request: dict, key: str, workspace_id: int | None, area_id: int | None, status: str
    ) -> int:
        stamp = now()
        cursor = self.execute(
            "INSERT INTO jobs (workspace_id, area_id, request, result_key, status, created, "
            "updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, area_id, json.dumps(request), key, status, stamp, stamp),
        )
        self.touch(workspace_id)
        return cursor.lastrowid

    def set_job(self, job_id: int, status: str, error: str | None = None) -> None:
        self.execute(
            "UPDATE jobs SET status = ?, error = ?, updated = ? WHERE id = ?",
            (status, error, now(), job_id),
        )

    def job(self, job_id: int) -> dict | None:
        found = self.row("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if found:
            found["request"] = json.loads(found["request"])
        return found

    def jobs(self, workspace_id: int) -> list[dict]:
        found = self.rows("SELECT * FROM jobs WHERE workspace_id = ? ORDER BY id", (workspace_id,))
        for job in found:
            job["request"] = json.loads(job["request"])
        return found

    def save_result(self, key: str, response: dict) -> None:
        self.execute(
            "INSERT OR REPLACE INTO results (key, response, created) VALUES (?, ?, ?)",
            (key, json.dumps(response), now()),
        )

    def result(self, key: str) -> dict | None:
        found = self.row("SELECT response FROM results WHERE key = ?", (key,))
        return json.loads(found["response"]) if found else None
