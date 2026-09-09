from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT 'queued',
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    source_path TEXT,
                    options_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    logs_json TEXT NOT NULL DEFAULT '[]',
                    media_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
            if "cancel_requested" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created_at DESC)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clip_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    clip_index INTEGER NOT NULL,
                    rating TEXT NOT NULL,
                    reasons_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, clip_index),
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                )
                """
            )

    def create(
        self,
        job_id: str,
        source_kind: str,
        source_ref: str,
        options: dict[str, Any],
        source_path: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        media_token = secrets.token_urlsafe(24)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, status, progress, stage, source_kind, source_ref,
                    source_path, options_json, media_token, created_at, updated_at
                ) VALUES (?, 'queued', 0, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, source_kind, source_ref, source_path, json.dumps(options), media_token, now, now),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._deserialize(dict(row))

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 100)),)
            ).fetchall()
        return [self._deserialize(dict(row)) for row in rows]

    def recoverable(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE status IN ('queued', 'processing') ORDER BY created_at"
            ).fetchall()
        return [self._deserialize(dict(row)) for row in rows]

    def update(self, job_id: str, **values: Any) -> dict[str, Any]:
        aliases = {"result": "result_json", "logs": "logs_json", "options": "options_json"}
        allowed = {
            "status", "progress", "stage", "source_path", "result_json", "error",
            "logs_json", "options_json", "cancel_requested",
        }
        encoded: dict[str, Any] = {}
        for key, value in values.items():
            column = aliases.get(key, key)
            if column not in allowed:
                raise ValueError(f"Unsupported job field: {key}")
            if column.endswith("_json") and value is not None and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            encoded[column] = value
        encoded["updated_at"] = utc_now()
        assignments = ", ".join(f"{column} = ?" for column in encoded)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?", (*encoded.values(), job_id)
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
        return self.get(job_id)

    def append_log(
        self,
        job_id: str,
        message: str,
        detail: str | None = None,
        level: str = "info",
    ) -> dict[str, Any]:
        job = self.get(job_id)
        entry = {"at": utc_now(), "message": message[:500], "level": level[:20]}
        if detail:
            entry["detail"] = detail[:4000]
        logs = [*job["logs"], entry][-160:]
        return self.update(job_id, logs=logs)

    def save_feedback(self, job_id: str, clip_index: int, rating: str, reasons: list[str]) -> dict[str, Any]:
        # Validate the job first so foreign-key errors become a predictable KeyError.
        self.get(job_id)
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO clip_feedback(job_id, clip_index, rating, reasons_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(job_id, clip_index) DO UPDATE SET
                    rating=excluded.rating, reasons_json=excluded.reasons_json, created_at=excluded.created_at
                """,
                (job_id, int(clip_index), rating, json.dumps(reasons, ensure_ascii=False), now),
            )
        return {"job_id": job_id, "clip_index": int(clip_index), "rating": rating, "reasons": reasons, "created_at": now}

    def feedback(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT clip_index, rating, reasons_json, created_at FROM clip_feedback WHERE job_id = ? ORDER BY clip_index",
                (job_id,),
            ).fetchall()
        return [
            {"clip_index": int(row["clip_index"]), "rating": row["rating"], "reasons": json.loads(row["reasons_json"] or "[]"), "created_at": row["created_at"]}
            for row in rows
        ]

    def delete(self, job_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            if cursor.rowcount == 0:
                raise KeyError(job_id)

    @staticmethod
    def _deserialize(row: dict[str, Any]) -> dict[str, Any]:
        row["options"] = json.loads(row.pop("options_json") or "{}")
        row["result"] = json.loads(row.pop("result_json") or "null")
        row["logs"] = json.loads(row.pop("logs_json") or "[]")
        row["cancel_requested"] = bool(row.get("cancel_requested", 0))
        return row
