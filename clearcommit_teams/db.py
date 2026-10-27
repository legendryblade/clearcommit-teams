"""SQLite persistence.

The database lives inside the project data folder. Connections are opened per
operation with foreign keys enforced, so bridge calls running on separate
threads never share a mutable connection.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .errors import PersistenceError
from .paths import assert_write_allowed, database_path, resolve_data_dir
from .models import now_utc

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    customer_name TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    rep_name TEXT NOT NULL DEFAULT 'You',
    customer_language TEXT NOT NULL DEFAULT 'en',
    rep_language TEXT NOT NULL DEFAULT 'en',
    occurred_on TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','import','sample')),
    is_sample INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS utterances (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    speaker TEXT NOT NULL CHECK (speaker IN ('customer','rep')),
    original_text TEXT NOT NULL,
    translation TEXT,
    language TEXT NOT NULL,
    display_time TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_utterances_session ON utterances(session_id, seq);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    provider_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    evidence_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    limitations TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON analysis_runs(session_id, created_at);

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    observation TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    proposed_alternative TEXT NOT NULL,
    limitations TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    confidence TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_session ON insights(session_id, created_at);

CREATE TABLE IF NOT EXISTS insight_evidence (
    insight_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    utterance_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    quote TEXT NOT NULL,
    speaker TEXT NOT NULL,
    spoken_at TEXT,
    language TEXT NOT NULL,
    translation TEXT,
    PRIMARY KEY (insight_id, ref)
);

CREATE TABLE IF NOT EXISTS assistant_notes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    limitations TEXT NOT NULL,
    provider_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_session ON assistant_notes(session_id, created_at);

CREATE TABLE IF NOT EXISTS assistant_note_evidence (
    note_id TEXT NOT NULL REFERENCES assistant_notes(id) ON DELETE CASCADE,
    utterance_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    quote TEXT NOT NULL,
    speaker TEXT NOT NULL,
    spoken_at TEXT,
    language TEXT NOT NULL,
    translation TEXT,
    PRIMARY KEY (note_id, ref)
);

CREATE TABLE IF NOT EXISTS playbook_entries (
    id TEXT PRIMARY KEY,
    insight_id TEXT,
    session_id TEXT,
    title TEXT NOT NULL,
    scenario TEXT NOT NULL,
    objection TEXT NOT NULL,
    approved_response TEXT NOT NULL,
    discovery_questions TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL DEFAULT '',
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    evidence_summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved')),
    created_by TEXT NOT NULL DEFAULT '',
    approved_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_playbook_status ON playbook_entries(status, updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_insight ON playbook_entries(insight_id)
    WHERE insight_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS playbook_reviews (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES playbook_entries(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "provider_mode": "mock",
    "base_url": "",
    "model": "",
    "timeout_s": "25",
    "reviewer_name": "",
    # Live capture and interpretation models. Empty means "use the .env value
    # or the built-in accurate default", so an unset app still behaves well.
    "stt_provider": "groq",
    "stt_model": "",
    "tts_voice": "",
    "tts_model": "",
}


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            data_dir = resolve_data_dir()
            path = database_path(data_dir)
        self.path = Path(path).resolve()
        assert_write_allowed(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise PersistenceError(
                "The local workspace database could not complete that change.",
                detail={"reason": type(exc).__name__},
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        try:
            with self.connection() as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                for key, value in DEFAULT_SETTINGS.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO app_settings(key, value) VALUES (?, ?)",
                        (key, value),
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceError(
                "The local workspace database could not be initialized.",
                detail={"reason": type(exc).__name__},
            ) from exc

    def get_settings(self) -> dict:
        with self.connection() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        values = {row["key"]: row["value"] for row in rows}
        merged = {**DEFAULT_SETTINGS, **values}
        try:
            merged["timeout_s"] = float(merged["timeout_s"])
        except (TypeError, ValueError):
            merged["timeout_s"] = 25.0
        return merged

    def save_settings(self, values: dict) -> dict:
        allowed = set(DEFAULT_SETTINGS)
        with self.connection() as conn:
            for key, value in values.items():
                if key not in allowed:
                    continue
                conn.execute(
                    "INSERT INTO app_settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
        return self.get_settings()

    def set_meta(self, key: str, value: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO app_meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_meta(self, key: str, default: str = "") -> str:
        with self.connection() as conn:
            row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def counts(self) -> dict:
        with self.connection() as conn:
            def scalar(sql: str) -> int:
                row = conn.execute(sql).fetchone()
                return int(row[0] if row else 0)

            return {
                "sessions": scalar("SELECT COUNT(*) FROM sessions"),
                "sample_sessions": scalar("SELECT COUNT(*) FROM sessions WHERE is_sample = 1"),
                "utterances": scalar("SELECT COUNT(*) FROM utterances"),
                "insights": scalar("SELECT COUNT(*) FROM insights"),
                "playbook_total": scalar("SELECT COUNT(*) FROM playbook_entries"),
                "playbook_approved": scalar("SELECT COUNT(*) FROM playbook_entries WHERE status = 'approved'"),
                "playbook_draft": scalar("SELECT COUNT(*) FROM playbook_entries WHERE status = 'draft'"),
            }


def timestamp() -> str:
    return now_utc()
