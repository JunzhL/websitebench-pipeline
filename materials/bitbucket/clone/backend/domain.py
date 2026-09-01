"""Site-local Bitbucket project and collaboration domain."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS bb_schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bb_profiles(
  subject_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, first_name TEXT NOT NULL,
  last_name TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bb_pending_profiles(
  session_digest TEXT PRIMARY KEY, username TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bb_projects(
  project_id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL, path TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL,
  owner_subject TEXT NOT NULL, default_branch TEXT NOT NULL DEFAULT 'main', readme INTEGER NOT NULL,
  gitignore TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '', topics_json TEXT NOT NULL DEFAULT '[]',
  notifications TEXT NOT NULL DEFAULT 'global', archived INTEGER NOT NULL DEFAULT 0,
  forked_from INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(namespace,path)
);
CREATE TABLE IF NOT EXISTS bb_members(project_id INTEGER NOT NULL, subject_id TEXT NOT NULL,
  role TEXT NOT NULL, PRIMARY KEY(project_id,subject_id));
CREATE TABLE IF NOT EXISTS bb_branches(project_id INTEGER NOT NULL, name TEXT NOT NULL,
  head_sha TEXT NOT NULL, protected INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  PRIMARY KEY(project_id,name));
CREATE TABLE IF NOT EXISTS bb_files(project_id INTEGER NOT NULL, branch TEXT NOT NULL,
  path TEXT NOT NULL, content TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id,branch,path));
CREATE TABLE IF NOT EXISTS bb_commits(project_id INTEGER NOT NULL, sha TEXT NOT NULL,
  branch TEXT NOT NULL, message TEXT NOT NULL, author_name TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(project_id,sha));
CREATE TABLE IF NOT EXISTS bb_releases(project_id INTEGER NOT NULL, tag TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT NOT NULL, released_at TEXT NOT NULL,
  PRIMARY KEY(project_id,tag));
CREATE TABLE IF NOT EXISTS bb_issues(project_id INTEGER NOT NULL, iid INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, labels_json TEXT NOT NULL,
  assignee TEXT, milestone TEXT, author_subject TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id,iid));
CREATE TABLE IF NOT EXISTS bb_merge_requests(project_id INTEGER NOT NULL, iid INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT NOT NULL, source_branch TEXT NOT NULL, target_branch TEXT NOT NULL,
  status TEXT NOT NULL, draft INTEGER NOT NULL, reviewer TEXT, author_subject TEXT NOT NULL,
  changes_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id,iid));
CREATE TABLE IF NOT EXISTS bb_comments(comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL, object_type TEXT NOT NULL, object_iid INTEGER NOT NULL,
  author_subject TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bb_pipelines(project_id INTEGER NOT NULL, pipeline_id INTEGER NOT NULL,
  ref TEXT NOT NULL, sha TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id,pipeline_id));
CREATE TABLE IF NOT EXISTS bb_jobs(project_id INTEGER NOT NULL, job_id INTEGER NOT NULL,
  pipeline_id INTEGER NOT NULL, name TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
  allow_failure INTEGER NOT NULL, log_text TEXT NOT NULL, PRIMARY KEY(project_id,job_id));
CREATE TABLE IF NOT EXISTS bb_activity(activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id TEXT NOT NULL, project_id INTEGER, object_type TEXT NOT NULL, object_ref TEXT NOT NULL,
  action TEXT NOT NULL, status TEXT NOT NULL, detail_path TEXT NOT NULL, editable INTEGER NOT NULL,
  cancellable INTEGER NOT NULL, created_at TEXT NOT NULL);
"""

NOW = "2026-08-30T20:00:00Z"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate(connection: sqlite3.Connection) -> None:
    # SiteDatabaseLifecycle owns the surrounding transaction. executescript()
    # commits implicitly, so execute each additive statement through that
    # existing transaction instead.
    for statement in SCHEMA.split(";"):
        statement = statement.strip()
        if statement:
            connection.execute(statement)
    connection.execute(
        "INSERT OR IGNORE INTO bb_schema_migrations VALUES (?,?)",
        ("001-bitbucket-projects", NOW),
    )


def seed(connection: sqlite3.Connection) -> None:
    migrate(connection)
    if connection.execute("SELECT 1 FROM bb_projects WHERE namespace='atlassianlabs' AND path='atlascode'").fetchone():
        return
    cursor = connection.execute(
        "INSERT INTO bb_projects(namespace,path,name,description,visibility,owner_subject,default_branch,readme,gitignore,license,topics_json,notifications,archived,forked_from,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("atlassianlabs", "atlascode", "atlascode", "Atlassian for VS Code brings Jira and Bitbucket Cloud into your editor.", "public", "system:bitbucket", "main", 1, "Node", "Apache-2.0", json.dumps(["atlassian", "vscode", "typescript"]), "global", 0, None, "2018-11-13T00:00:00Z", NOW),
    )
    project_id = int(cursor.lastrowid)
    connection.execute("INSERT INTO bb_members VALUES (?,?,?)", (project_id, "system:bitbucket", "Owner"))
    commits = [
        ("7c4d9a21", "Merge pull request #814 from dependabot/npm_and_yarn"),
        ("51a83f0d", "Update extension dependencies"),
        ("a864b197", "Improve pull request review experience"),
        ("0f2ca95e", "Document local development workflow"),
    ]
    for sha, message in commits:
        connection.execute("INSERT INTO bb_commits VALUES (?,?,?,?,?,?)", (project_id, sha, "main", message, "Bitbucket Contributor", NOW))
    connection.executemany("INSERT INTO bb_branches VALUES (?,?,?,?,?)", [
        (project_id, "main", "7c4d9a21", 1, NOW),
        (project_id, "release/3.4.0", "51a83f0d", 0, NOW),
        (project_id, "feature/pull-request-review", "a864b197", 0, NOW),
    ])
    files = {
        "README.md": "# Atlassian for VS Code\n\nBring Jira and Bitbucket Cloud into Visual Studio Code.\n",
        "LICENSE": "Apache License 2.0\n",
        "bitbucket-pipelines.yml": "pipelines:\n  default:\n    - step:\n        script: [npm test]\n",
        "package.json": "{\"name\": \"atlascode\", \"private\": true}\n",
    }
    for path, content in files.items():
        connection.execute("INSERT INTO bb_files VALUES (?,?,?,?,?)", (project_id, "main", path, content, NOW))
    connection.executemany("INSERT INTO bb_releases VALUES (?,?,?,?,?)", [
        (project_id, "v3.4.0", "Atlascode 3.4.0", "Source archive and extension package.", "2026-08-25T00:00:00Z"),
        (project_id, "v3.3.2", "Atlascode 3.3.2", "Maintenance download.", "2026-07-18T00:00:00Z"),
        (project_id, "v3.3.1", "Atlascode 3.3.1", "Source archive.", "2026-06-12T00:00:00Z"),
    ])
    connection.execute("INSERT INTO bb_issues VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project_id, 814, "Pull request review loses selected file", "The selected file should remain visible after navigation.", "opened", json.dumps(["bug", "pull-request"]), "Developer", "3.5", "system:bitbucket", "2026-08-04T11:54:25Z", NOW))
    connection.execute("INSERT INTO bb_merge_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (project_id, 814, "Improve pull request review experience", "Preserve the selected file while reviewing a pull request.", "feature/pull-request-review", "main", "opened", 0, "Reviewer", "system:bitbucket", json.dumps(["src/pullrequests/prView.ts", "src/pullrequests/fileTree.ts"]), "2026-08-28T12:15:05Z", NOW))
    connection.execute("INSERT INTO bb_pipelines VALUES (?,?,?,?,?,?,?,?)", (project_id, 4453, "main", "7c4d9a21", "success", "push", "2026-08-28T17:21:01Z", "2026-08-28T21:27:37Z"))
    connection.executemany("INSERT INTO bb_jobs VALUES (?,?,?,?,?,?,?,?)", [
        (project_id, 445301, 4453, "test", "test", "success", 0, "Build setup\nRunning npm test\nAll tests passed\nJob succeeded"),
        (project_id, 445302, 4453, "package extension", "release", "success", 0, "Packaging VS Code extension\nArtifact created\nJob succeeded"),
    ])
    connection.execute("INSERT OR IGNORE INTO bb_profiles VALUES (?,?,?,?,?,?)", ("fixture:developer", "developer", "Demo", "Developer", "Builds and reviews local projects.", NOW))
    connection.execute("INSERT OR IGNORE INTO bb_profiles VALUES (?,?,?,?,?,?)", ("fixture:reviewer", "reviewer", "Demo", "Reviewer", "Reviews local pull requests.", NOW))
    demo = connection.execute(
        "INSERT INTO bb_projects(namespace,path,name,description,visibility,owner_subject,default_branch,readme,gitignore,license,topics_json,notifications,archived,forked_from,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("developer", "platform-demo", "platform-demo", "Seeded offline developer project.", "private", "fixture:developer", "main", 1, "Python", "MIT", json.dumps(["demo", "ci"]), "watch", 0, None, NOW, NOW),
    )
    demo_id = int(demo.lastrowid)
    connection.execute("INSERT INTO bb_members VALUES (?,?,?)", (demo_id, "fixture:developer", "Owner"))
    connection.execute("INSERT INTO bb_branches VALUES (?,?,?,?,?)", (demo_id, "main", "a1b2c3d4", 1, NOW))
    connection.execute("INSERT INTO bb_files VALUES (?,?,?,?,?)", (demo_id, "main", "README.md", "# Platform demo\n", NOW))
    connection.execute("INSERT INTO bb_commits VALUES (?,?,?,?,?,?)", (demo_id, "a1b2c3d4", "main", "Initial commit", "Demo Developer", NOW))
    connection.execute("INSERT INTO bb_activity(subject_id,project_id,object_type,object_ref,action,status,detail_path,editable,cancellable,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", ("fixture:developer", demo_id, "project", "platform-demo", "created", "active", "/developer/platform-demo", 1, 1, NOW))


def reset(connection: sqlite3.Connection) -> None:
    for table in ("bb_activity", "bb_comments", "bb_jobs", "bb_pipelines", "bb_merge_requests", "bb_issues", "bb_releases", "bb_commits", "bb_files", "bb_branches", "bb_members", "bb_projects", "bb_pending_profiles", "bb_profiles"):
        connection.execute(f"DELETE FROM {table}")
    seed(connection)


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def row(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    value = cursor.fetchone()
    return dict(value) if value else None


def slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not clean:
        raise ValueError("Project name is required.")
    return clean[:80]


def project_by_path(connection: sqlite3.Connection, namespace: str, path: str) -> dict[str, Any] | None:
    return row(connection.execute("SELECT * FROM bb_projects WHERE namespace=? AND path=?", (namespace, path)))


def member_role(connection: sqlite3.Connection, project_id: int, subject_id: str) -> str | None:
    value = connection.execute("SELECT role FROM bb_members WHERE project_id=? AND subject_id=?", (project_id, subject_id)).fetchone()
    return str(value[0]) if value else None


def activity(connection: sqlite3.Connection, subject_id: str, project_id: int | None, object_type: str, object_ref: str, action: str, status: str, detail_path: str, *, editable: bool = True, cancellable: bool = True) -> None:
    connection.execute("INSERT INTO bb_activity(subject_id,project_id,object_type,object_ref,action,status,detail_path,editable,cancellable,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (subject_id, project_id, object_type, object_ref, action, status, detail_path, int(editable), int(cancellable), now()))
