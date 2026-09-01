"""Site-local GitLab project and collaboration domain."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS gl_schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gl_profiles(
  subject_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, first_name TEXT NOT NULL,
  last_name TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gl_pending_profiles(
  session_digest TEXT PRIMARY KEY, username TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gl_projects(
  project_id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL, path TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL,
  owner_subject TEXT NOT NULL, default_branch TEXT NOT NULL DEFAULT 'main', readme INTEGER NOT NULL,
  gitignore TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '', topics_json TEXT NOT NULL DEFAULT '[]',
  notifications TEXT NOT NULL DEFAULT 'global', archived INTEGER NOT NULL DEFAULT 0,
  forked_from INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(namespace,path)
);
CREATE TABLE IF NOT EXISTS gl_members(project_id INTEGER NOT NULL, subject_id TEXT NOT NULL,
  role TEXT NOT NULL, PRIMARY KEY(project_id,subject_id));
CREATE TABLE IF NOT EXISTS gl_branches(project_id INTEGER NOT NULL, name TEXT NOT NULL,
  head_sha TEXT NOT NULL, protected INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  PRIMARY KEY(project_id,name));
CREATE TABLE IF NOT EXISTS gl_files(project_id INTEGER NOT NULL, branch TEXT NOT NULL,
  path TEXT NOT NULL, content TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id,branch,path));
CREATE TABLE IF NOT EXISTS gl_commits(project_id INTEGER NOT NULL, sha TEXT NOT NULL,
  branch TEXT NOT NULL, message TEXT NOT NULL, author_name TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(project_id,sha));
CREATE TABLE IF NOT EXISTS gl_releases(project_id INTEGER NOT NULL, tag TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT NOT NULL, released_at TEXT NOT NULL,
  PRIMARY KEY(project_id,tag));
CREATE TABLE IF NOT EXISTS gl_issues(project_id INTEGER NOT NULL, iid INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, labels_json TEXT NOT NULL,
  assignee TEXT, milestone TEXT, author_subject TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id,iid));
CREATE TABLE IF NOT EXISTS gl_merge_requests(project_id INTEGER NOT NULL, iid INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT NOT NULL, source_branch TEXT NOT NULL, target_branch TEXT NOT NULL,
  status TEXT NOT NULL, draft INTEGER NOT NULL, reviewer TEXT, author_subject TEXT NOT NULL,
  changes_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id,iid));
CREATE TABLE IF NOT EXISTS gl_comments(comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL, object_type TEXT NOT NULL, object_iid INTEGER NOT NULL,
  author_subject TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gl_pipelines(project_id INTEGER NOT NULL, pipeline_id INTEGER NOT NULL,
  ref TEXT NOT NULL, sha TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id,pipeline_id));
CREATE TABLE IF NOT EXISTS gl_jobs(project_id INTEGER NOT NULL, job_id INTEGER NOT NULL,
  pipeline_id INTEGER NOT NULL, name TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
  allow_failure INTEGER NOT NULL, log_text TEXT NOT NULL, PRIMARY KEY(project_id,job_id));
CREATE TABLE IF NOT EXISTS gl_activity(activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        "INSERT OR IGNORE INTO gl_schema_migrations VALUES (?,?)",
        ("001-gitlab-projects", NOW),
    )


def seed(connection: sqlite3.Connection) -> None:
    migrate(connection)
    if connection.execute("SELECT 1 FROM gl_projects WHERE namespace='gitlab-org' AND path='gitlab-runner'").fetchone():
        return
    cursor = connection.execute(
        "INSERT INTO gl_projects(namespace,path,name,description,visibility,owner_subject,default_branch,readme,gitignore,license,topics_json,notifications,archived,forked_from,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("gitlab-org", "gitlab-runner", "gitlab-runner", "GitLab Runner runs CI/CD jobs and sends results back to GitLab.", "public", "system:gitlab", "main", 1, "Go", "MIT", json.dumps(["hacktoberfest", "golang"]), "global", 0, None, "2015-04-27T00:00:00Z", NOW),
    )
    project_id = int(cursor.lastrowid)
    connection.execute("INSERT INTO gl_members VALUES (?,?,?)", (project_id, "system:gitlab", "Owner"))
    commits = [
        ("877127da", "Merge branch 'docs-i18n/-GITTECHA-868-fr-FR-1' into 'main'"),
        ("3439512c", "Product Docs AI Translation: GITTECHA-868 #1"),
        ("ea8684ad", "Update runner image"),
        ("6208dbeb", "Update runner base image"),
    ]
    for sha, message in commits:
        connection.execute("INSERT INTO gl_commits VALUES (?,?,?,?,?,?)", (project_id, sha, "main", message, "GitLab Contributor", NOW))
    connection.executemany("INSERT INTO gl_branches VALUES (?,?,?,?,?)", [
        (project_id, "main", "877127da", 1, NOW),
        (project_id, "duo/fix/k8s-eviction", "f8de4912", 0, NOW),
        (project_id, "machine-heartbeat-labels", "47e82fe2", 0, NOW),
    ])
    files = {
        "README.md": "# GitLab Runner\n\nGitLab Runner runs CI/CD jobs and returns results to GitLab.\n",
        "LICENSE": "MIT License\n",
        ".gitlab-ci.yml": "stages: [test, release]\n",
        "go.mod": "module gitlab.com/gitlab-org/gitlab-runner\n",
    }
    for path, content in files.items():
        connection.execute("INSERT INTO gl_files VALUES (?,?,?,?,?)", (project_id, "main", path, content, NOW))
    connection.executemany("INSERT INTO gl_releases VALUES (?,?,?,?,?)", [
        (project_id, "v19.3.1", "GitLab Runner 19.3.1", "Patch release with 42 assets.", "2026-08-25T00:00:00Z"),
        (project_id, "v19.2.3", "GitLab Runner 19.2.3", "Patch release with 42 assets.", "2026-08-25T00:00:00Z"),
        (project_id, "v19.3.0", "GitLab Runner 19.3.0", "Release with source archives.", "2026-08-19T00:00:00Z"),
    ])
    connection.execute("INSERT INTO gl_issues VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project_id, 39658, "Service variables cannot reference other service variables", "Service variables are expanded in a single pass.", "opened", json.dumps(["backend", "bug::functional", "devops::verify"]), "Developer", "19.4", "system:gitlab", "2026-08-04T11:54:25Z", NOW))
    connection.execute("INSERT INTO gl_merge_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (project_id, 7266, "Allow relative GIT_CLONE_PATH without custom_build_dir", "Allow relative paths below CI_PROJECT_DIR.", "dir", "main", "opened", 0, "Maintainer", "system:gitlab", json.dumps(["common/build.go", "common/build_test.go", "shells/abstract.go"]), "2026-08-28T12:15:05Z", NOW))
    connection.execute("INSERT INTO gl_pipelines VALUES (?,?,?,?,?,?,?,?)", (project_id, 51039, "main", "ea8684ad", "success", "push", "2026-08-28T17:21:01Z", "2026-08-28T21:27:37Z"))
    connection.executemany("INSERT INTO gl_jobs VALUES (?,?,?,?,?,?,?,?)", [
        (project_id, 16175628836, 51039, "rebase on main", "rebase", "failed", 1, "Preparing environment\nChecking rebase\nERROR: branch needs attention\nJob failed"),
        (project_id, 16175628835, 51039, "hosted runners bridge bleeding edge", "postrelease", "success", 0, "Preparing environment\nRunning bridge verification\nJob succeeded"),
    ])
    connection.execute("INSERT OR IGNORE INTO gl_profiles VALUES (?,?,?,?,?,?)", ("fixture:developer", "developer", "Demo", "Developer", "Builds and reviews local projects.", NOW))
    demo = connection.execute(
        "INSERT INTO gl_projects(namespace,path,name,description,visibility,owner_subject,default_branch,readme,gitignore,license,topics_json,notifications,archived,forked_from,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("developer", "platform-demo", "platform-demo", "Seeded offline developer project.", "private", "fixture:developer", "main", 1, "Python", "MIT", json.dumps(["demo", "ci"]), "watch", 0, None, NOW, NOW),
    )
    demo_id = int(demo.lastrowid)
    connection.execute("INSERT INTO gl_members VALUES (?,?,?)", (demo_id, "fixture:developer", "Owner"))
    connection.execute("INSERT INTO gl_branches VALUES (?,?,?,?,?)", (demo_id, "main", "a1b2c3d4", 1, NOW))
    connection.execute("INSERT INTO gl_files VALUES (?,?,?,?,?)", (demo_id, "main", "README.md", "# Platform demo\n", NOW))
    connection.execute("INSERT INTO gl_commits VALUES (?,?,?,?,?,?)", (demo_id, "a1b2c3d4", "main", "Initial commit", "Demo Developer", NOW))
    connection.execute("INSERT INTO gl_activity(subject_id,project_id,object_type,object_ref,action,status,detail_path,editable,cancellable,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", ("fixture:developer", demo_id, "project", "platform-demo", "created", "active", "/developer/platform-demo", 1, 1, NOW))


def reset(connection: sqlite3.Connection) -> None:
    for table in ("gl_activity", "gl_comments", "gl_jobs", "gl_pipelines", "gl_merge_requests", "gl_issues", "gl_releases", "gl_commits", "gl_files", "gl_branches", "gl_members", "gl_projects", "gl_pending_profiles", "gl_profiles"):
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
    return row(connection.execute("SELECT * FROM gl_projects WHERE namespace=? AND path=?", (namespace, path)))


def member_role(connection: sqlite3.Connection, project_id: int, subject_id: str) -> str | None:
    value = connection.execute("SELECT role FROM gl_members WHERE project_id=? AND subject_id=?", (project_id, subject_id)).fetchone()
    return str(value[0]) if value else None


def activity(connection: sqlite3.Connection, subject_id: str, project_id: int | None, object_type: str, object_ref: str, action: str, status: str, detail_path: str, *, editable: bool = True, cancellable: bool = True) -> None:
    connection.execute("INSERT INTO gl_activity(subject_id,project_id,object_type,object_ref,action,status,detail_path,editable,cancellable,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (subject_id, project_id, object_type, object_ref, action, status, detail_path, int(editable), int(cancellable), now()))
