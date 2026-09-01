"""HackerRank clone business schema and deterministic seed data."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


DEMO_SUBJECT = "fixture:learner"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate(connection: sqlite3.Connection) -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS hr_schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hr_profiles (
          subject_id TEXT PRIMARY KEY,
          username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          full_name TEXT NOT NULL,
          bio TEXT NOT NULL DEFAULT '',
          preferred_language TEXT NOT NULL DEFAULT 'python3',
          email_notifications INTEGER NOT NULL DEFAULT 1 CHECK(email_notifications IN (0,1)),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hr_pending_profiles (
          session_digest TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          full_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hr_saved_challenges (
          subject_id TEXT NOT NULL,
          challenge_slug TEXT NOT NULL,
          saved_at TEXT NOT NULL,
          PRIMARY KEY(subject_id, challenge_slug)
        );
        CREATE TABLE IF NOT EXISTS hr_drafts (
          subject_id TEXT NOT NULL,
          challenge_slug TEXT NOT NULL,
          language TEXT NOT NULL,
          source TEXT NOT NULL,
          custom_input TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL,
          PRIMARY KEY(subject_id, challenge_slug)
        );
        CREATE TABLE IF NOT EXISTS hr_runs (
          run_id INTEGER PRIMARY KEY AUTOINCREMENT,
          subject_id TEXT NOT NULL,
          challenge_slug TEXT NOT NULL,
          language TEXT NOT NULL,
          source TEXT NOT NULL,
          custom_input TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          stdout TEXT NOT NULL,
          stderr TEXT NOT NULL,
          test_summary TEXT NOT NULL,
          runtime_ms INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hr_submissions (
          submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
          subject_id TEXT NOT NULL,
          challenge_slug TEXT NOT NULL,
          language TEXT NOT NULL,
          source TEXT NOT NULL,
          status TEXT NOT NULL,
          score INTEGER NOT NULL,
          runtime_ms INTEGER NOT NULL,
          memory_kb INTEGER NOT NULL,
          feedback TEXT NOT NULL,
          version INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hr_activity (
          activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
          subject_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          href TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """
    for statement in schema.split(";"):
        statement = statement.strip()
        if statement:
            connection.execute(statement)
    connection.execute(
        "INSERT OR IGNORE INTO hr_schema_migrations(version, applied_at) VALUES (1, ?)",
        (now(),),
    )


def seed(connection: sqlite3.Connection) -> None:
    migrate(connection)
    stamp = "2026-09-01T12:00:00+00:00"
    connection.execute(
        "INSERT OR IGNORE INTO hr_profiles(subject_id, username, full_name, bio, preferred_language, email_notifications, created_at) VALUES (?,?,?,?,?,?,?)",
        (DEMO_SUBJECT, "demo_learner", "Demo Learner", "Practicing algorithms one challenge at a time.", "python3", 1, stamp),
    )
    connection.execute(
        "INSERT OR IGNORE INTO hr_saved_challenges(subject_id, challenge_slug, saved_at) VALUES (?,?,?)",
        (DEMO_SUBJECT, "solve-me-first", stamp),
    )
    if connection.execute(
        "SELECT 1 FROM hr_submissions WHERE subject_id=? AND challenge_slug=?",
        (DEMO_SUBJECT, "solve-me-first"),
    ).fetchone() is None:
        source = "def solveMeFirst(a, b):\n    return a + b\n"
        cursor = connection.execute(
            "INSERT INTO hr_submissions(subject_id, challenge_slug, language, source, status, score, runtime_ms, memory_kb, feedback, version, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (DEMO_SUBJECT, "solve-me-first", "python3", source, "Accepted", 100, 18, 14832, "All 3 local fixture tests passed.", 1, stamp),
        )
        connection.execute(
            "INSERT INTO hr_activity(subject_id, kind, title, status, href, created_at) VALUES (?,?,?,?,?,?)",
            (DEMO_SUBJECT, "submission", "Solve Me First", "Accepted", f"/challenges/solve-me-first/submissions/{cursor.lastrowid}", stamp),
        )


def reset(connection: sqlite3.Connection) -> None:
    for table in (
        "hr_activity",
        "hr_submissions",
        "hr_runs",
        "hr_drafts",
        "hr_saved_challenges",
        "hr_pending_profiles",
        "hr_profiles",
    ):
        connection.execute(f"DELETE FROM {table}")
    seed(connection)
