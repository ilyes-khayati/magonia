"""Local storage for workspaces, areas, jobs, cached results and conversations (decision 0004).

Workspaces, areas and conversations are deleted softly: they are marked with the time of
deletion, can be restored for 30 days, and are removed for good after that.
"""

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused
    name TEXT NOT NULL,
    settings TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    deleted TEXT  -- when it was deleted; restorable until it is purged
);
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    geometry TEXT NOT NULL,
    area_km2 REAL NOT NULL,
    deleted TEXT,
    UNIQUE (workspace_id, name)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title TEXT,  -- null until named: shown as its first question
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    deleted TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,  -- user or assistant
    content TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',  -- searches, papers found and the citation check
    created TEXT NOT NULL
);
"""

# How long a deleted workspace, area or conversation can be restored
KEEP_DELETED = timedelta(days=30)


def default_path() -> Path:
    """~/.magonia/magonia.db, or the folder named by MAGONIA_DATA_DIR."""
    folder = Path(os.environ.get("MAGONIA_DATA_DIR", Path.home() / ".magonia"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "magonia.db"


def now(timespec: str = "seconds") -> str:
    return datetime.now(UTC).isoformat(timespec=timespec)


class Store:
    """A thin layer over one SQLite file, safe to use from the job threads."""

    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.migrate()
        self.lock = threading.Lock()
        self.purge()
        self.execute(
            "UPDATE jobs SET status = 'failed', error = ?, updated = ? "
            "WHERE status IN ('queued', 'running')",
            ("The API stopped before this job finished. Please run it again.", now()),
        )

    def migrate(self) -> None:
        """Bring a database made by an earlier version up to the current schema."""

        def columns(table: str) -> set[str]:
            return {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}

        with self.db:
            if "details" not in columns("messages"):  # added in 1.3
                self.db.execute(
                    "ALTER TABLE messages ADD COLUMN details TEXT NOT NULL DEFAULT '{}'"
                )
            for table in ("workspaces", "areas"):  # soft deletion, added in 1.5
                if "deleted" not in columns(table):
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN deleted TEXT")
            if "conversation_id" not in columns("messages"):  # several conversations, 1.5
                self.db.execute(
                    "ALTER TABLE messages ADD COLUMN conversation_id INTEGER "
                    "REFERENCES conversations(id) ON DELETE CASCADE"
                )
            # the single conversation each workspace had becomes its first one
            for (workspace_id,) in self.db.execute(
                "SELECT DISTINCT workspace_id FROM messages WHERE conversation_id IS NULL"
            ).fetchall():
                first, last = self.db.execute(
                    "SELECT MIN(created), MAX(created) FROM messages WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone()
                cursor = self.db.execute(
                    "INSERT INTO conversations (workspace_id, created, updated) VALUES (?, ?, ?)",
                    (workspace_id, first, last),
                )
                self.db.execute(
                    "UPDATE messages SET conversation_id = ? "
                    "WHERE workspace_id = ? AND conversation_id IS NULL",
                    (cursor.lastrowid, workspace_id),
                )

    def purge(self) -> None:
        """Remove for good what was deleted more than 30 days ago."""
        before = (datetime.now(UTC) - KEEP_DELETED).isoformat(timespec="seconds")
        for table in ("workspaces", "areas", "conversations"):
            self.execute(f"DELETE FROM {table} WHERE deleted < ?", (before,))

    def execute(self, sql: str, values: tuple = ()) -> sqlite3.Cursor:
        with self.lock, self.db:
            return self.db.execute(sql, values)

    def rows(self, sql: str, values: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, values).fetchall()]

    def row(self, sql: str, values: tuple = ()) -> dict | None:
        found = self.rows(sql, values)
        return found[0] if found else None

    # Settings of this installation, such as the Earth Engine project

    def setting(self, key: str) -> str | None:
        found = self.row("SELECT value FROM settings WHERE key = ?", (key,))
        return found["value"] if found else None

    def set_setting(self, key: str, value: str) -> None:
        self.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # Workspaces

    def create_workspace(self, name: str) -> dict:
        stamp = now()
        cursor = self.execute(
            "INSERT INTO workspaces (name, created, updated) VALUES (?, ?, ?)", (name, stamp, stamp)
        )
        return self.workspace(cursor.lastrowid)

    def workspace(self, workspace_id: int, deleted: bool = False) -> dict | None:
        """A workspace; one that was deleted only when asked for."""
        found = self.row(
            "SELECT * FROM workspaces WHERE id = ? AND (deleted IS NULL OR ?)",
            (workspace_id, deleted),
        )
        if found:
            found["settings"] = json.loads(found["settings"])
        return found

    def workspaces(self, deleted: bool = False) -> list[dict]:
        """The workspaces in use, most recently changed first, or those deleted, latest first."""
        if deleted:
            return self.rows(
                "SELECT id, name, created, updated, deleted FROM workspaces "
                "WHERE deleted IS NOT NULL ORDER BY deleted DESC"
            )
        return self.rows(
            "SELECT id, name, created, updated, deleted FROM workspaces "
            "WHERE deleted IS NULL ORDER BY updated DESC"
        )

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
        self.execute("UPDATE workspaces SET deleted = ? WHERE id = ?", (now(), workspace_id))

    def restore_workspace(self, workspace_id: int) -> None:
        self.execute("UPDATE workspaces SET deleted = NULL WHERE id = ?", (workspace_id,))

    def delete_workspace_forever(self, workspace_id: int) -> None:
        self.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))

    def touch(self, workspace_id: int | None) -> None:
        if workspace_id is not None:
            self.execute("UPDATE workspaces SET updated = ? WHERE id = ?", (now(), workspace_id))

    # Areas

    def create_area(self, workspace_id: int, name: str, geometry: dict, area_km2: float) -> dict:
        # a new area takes the name of a deleted one, which can then no longer be restored
        self.execute(
            "DELETE FROM areas WHERE workspace_id = ? AND name = ? AND deleted IS NOT NULL",
            (workspace_id, name),
        )
        cursor = self.execute(
            "INSERT INTO areas (workspace_id, name, geometry, area_km2) VALUES (?, ?, ?, ?)",
            (workspace_id, name, json.dumps(geometry), area_km2),
        )
        self.touch(workspace_id)
        return self.area(cursor.lastrowid)

    def area(self, area_id: int, deleted: bool = False) -> dict | None:
        found = self.row(
            "SELECT * FROM areas WHERE id = ? AND (deleted IS NULL OR ?)", (area_id, deleted)
        )
        if found:
            found["geometry"] = json.loads(found["geometry"])
        return found

    def areas(self, workspace_id: int) -> list[dict]:
        found = self.rows(
            "SELECT * FROM areas WHERE workspace_id = ? AND deleted IS NULL ORDER BY id",
            (workspace_id,),
        )
        for area in found:
            area["geometry"] = json.loads(area["geometry"])
        return found

    def rename_area(self, area_id: int, name: str) -> None:
        area = self.area(area_id)
        self.execute(
            "DELETE FROM areas WHERE workspace_id = ? AND name = ? AND deleted IS NOT NULL",
            (area["workspace_id"], name),
        )
        self.execute("UPDATE areas SET name = ? WHERE id = ?", (name, area_id))

    def delete_area(self, area_id: int) -> None:
        self.execute("UPDATE areas SET deleted = ? WHERE id = ?", (now(), area_id))

    def restore_area(self, area_id: int) -> None:
        self.execute("UPDATE areas SET deleted = NULL WHERE id = ?", (area_id,))

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

    # Conversations with the assistant, several per workspace

    def create_conversation(self, workspace_id: int, title: str | None = None) -> dict:
        stamp = now("microseconds")  # conversations are ordered by it, often seconds apart
        cursor = self.execute(
            "INSERT INTO conversations (workspace_id, title, created, updated) VALUES (?, ?, ?, ?)",
            (workspace_id, title, stamp, stamp),
        )
        self.touch(workspace_id)
        return self.conversation(cursor.lastrowid)

    CONVERSATION = (
        "SELECT c.*, (SELECT content FROM messages m WHERE m.conversation_id = c.id "
        "AND m.role = 'user' ORDER BY m.id LIMIT 1) AS first_question, "
        "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS messages "
        "FROM conversations c "
    )

    def conversation(self, conversation_id: int, deleted: bool = False) -> dict | None:
        """A conversation, with its first question and how many messages it has."""
        return self.row(
            self.CONVERSATION + "WHERE c.id = ? AND (c.deleted IS NULL OR ?)",
            (conversation_id, deleted),
        )

    def conversations(self, workspace_id: int) -> list[dict]:
        """The conversations of a workspace, the latest first."""
        return self.rows(
            self.CONVERSATION
            + "WHERE c.workspace_id = ? AND c.deleted IS NULL ORDER BY c.updated DESC, c.id DESC",
            (workspace_id,),
        )

    def rename_conversation(self, conversation_id: int, title: str) -> None:
        self.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))

    def delete_conversation(self, conversation_id: int) -> None:
        self.execute("UPDATE conversations SET deleted = ? WHERE id = ?", (now(), conversation_id))

    def restore_conversation(self, conversation_id: int) -> None:
        self.execute("UPDATE conversations SET deleted = NULL WHERE id = ?", (conversation_id,))

    def add_message(
        self, conversation_id: int, role: str, content: str, details: dict | None = None
    ) -> dict:
        conversation = self.conversation(conversation_id, deleted=True)
        stamp = now("microseconds")
        cursor = self.execute(
            "INSERT INTO messages (workspace_id, conversation_id, role, content, details, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation["workspace_id"],
                conversation_id,
                role,
                content,
                json.dumps(details or {}),
                stamp,
            ),
        )
        self.execute("UPDATE conversations SET updated = ? WHERE id = ?", (stamp, conversation_id))
        self.touch(conversation["workspace_id"])
        return self.message(cursor.lastrowid)

    def message(self, message_id: int) -> dict | None:
        found = self.row("SELECT * FROM messages WHERE id = ?", (message_id,))
        if found:
            found["details"] = json.loads(found["details"])
        return found

    def messages(self, conversation_id: int) -> list[dict]:
        found = self.rows(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        )
        for message in found:
            message["details"] = json.loads(message["details"])
        return found
