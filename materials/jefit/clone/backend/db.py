"""JEFIT offline clone — business layer over the vendored site-backend seam.

All persistence lives in this site's exclusive SQLite database reached only
through ``websitebench.site_backend`` / ``websitebench.local_clone_auth``
(opened via the generated ``backend/site_backend_integration.py``). Business
tables are prefixed ``jefit_``. Seeding is deterministic (fixed identities,
fixed timestamps) so a reset always reproduces byte-stable business state.

Payment mandate: the checkout accepts ONLY opaque local-sandbox scenario ids.
``reject_payment_keys`` refuses any card-like field before it can reach a
handler, and the Elite purchase writes the order plus membership state in the
same SQLite transaction that consumes the sandbox approval.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

from backend.site_backend_integration import open_site_services
from websitebench.site_backend import PaymentError

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "fixtures" / "catalog.json"

SEED_EPOCH = "2026-08-18T12:00:00Z"
SEED_DAY = "2026-08-18"

# Synthetic seed identities (never the capture account's values).
PRIMARY = {
    "subject_id": "jefit-member-primary",
    "email": "demo.member@example.com",
    "display_name": "jefitdemo",
    "password": "Demo-Pass-2026!",
}
ISOLATION = {
    "subject_id": "jefit-member-isolation",
    "email": "iso.member@example.com",
    "display_name": "isotest",
    "password": "Iso-Pass-2026!",
}
SEED_ACCOUNTS = [PRIMARY, ISOLATION]

ELITE_PLANS = {
    "monthly": {"amount_minor": 1299, "label": "Elite", "coupon": None},
    "yearly": {"amount_minor": 5249, "label": "Elite Annual",
               "coupon": "25%OffFirstYear"},
}

# Any of these keys in a payment payload is a rejected credential-shaped
# field: the sandbox accepts opaque scenario ids only.
PAYMENT_FIELD_RE = re.compile(
    r"(?i)^(card|cc)[-_ ]?(number|no|num)?$|^(pan|cvv|cvc|cvv2|csc)$"
    r"|^exp(iry|iration)?([-_ ]?(month|year|date))?$"
    r"|^(account|routing|iban|swift)[-_ ]?(number|no)?$"
    r"|card|cvv|cvc|iban"
)
CARD_VALUE_RE = re.compile(r"^[\d\s-]{12,23}$")


class PaymentFieldRejected(ValueError):
    """A credential-shaped payment field was submitted."""


_lock = threading.Lock()
_services: tuple[Any, Any] | None = None
# In-memory verification-mail outbox (secret codes are never persisted; the
# same pattern the vendored auth store uses for its own secret-bearing mail).
_verification_outbox: dict[str, dict[str, Any]] = {}
_catalog_cache: dict[str, Any] | None = None


def services() -> tuple[Any, Any]:
    global _services
    with _lock:
        if _services is None:
            backend, auth = open_site_services()
            _ensure_business_schema(backend)
            _seed_all(backend, auth)
            _services = (backend, auth)
    return _services


def backend():
    return services()[0]


def auth():
    return services()[1]


def catalog() -> dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return _catalog_cache


def exercise_by_id(exercise_id: int) -> dict[str, Any] | None:
    for entry in catalog()["exercises"]:
        if entry["id"] == exercise_id:
            return entry
    return None


def routine_fixture_by_id(routine_id: int) -> dict[str, Any] | None:
    for entry in catalog()["routines"]:
        if entry["id"] == routine_id:
            return entry
    return None


BUSINESS_TABLES = (
    "jefit_users",
    "jefit_routines",
    "jefit_routine_days",
    "jefit_day_exercises",
    "jefit_workout_sessions",
    "jefit_session_sets",
    "jefit_body_stats",
    "jefit_posts",
    "jefit_custom_exercises",
    "jefit_orders",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jefit_users (
    id INTEGER PRIMARY KEY,
    subject_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    verify_code_salt BLOB,
    verify_code_hash BLOB,
    account_type TEXT NOT NULL DEFAULT 'free',
    membership_plan TEXT,
    membership_renews_on TEXT,
    current_plan_id INTEGER,
    custom_exercise_count INTEGER NOT NULL DEFAULT 0,
    birthday TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    unit_system TEXT NOT NULL DEFAULT 'Imperial',
    workout_level TEXT NOT NULL DEFAULT 'Beginner',
    top_goal TEXT NOT NULL DEFAULT 'Maintaining',
    privacy_json TEXT NOT NULL DEFAULT '{}',
    email_prefs_json TEXT NOT NULL DEFAULT '{}',
    questionnaire_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS jefit_routines (
    id INTEGER PRIMARY KEY,
    owner_user_id INTEGER,
    name TEXT NOT NULL,
    focus TEXT NOT NULL DEFAULT 'General',
    level TEXT NOT NULL DEFAULT 'Beginner',
    day_tag TEXT NOT NULL DEFAULT 'Day 1',
    description TEXT NOT NULL DEFAULT '',
    code TEXT,
    is_public INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jefit_routine_days (
    id INTEGER PRIMARY KEY,
    routine_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jefit_day_exercises (
    id INTEGER PRIMARY KEY,
    day_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    sets INTEGER NOT NULL DEFAULT 3,
    weight_lbs REAL NOT NULL DEFAULT 10,
    reps INTEGER NOT NULL DEFAULT 8,
    rest_seconds INTEGER NOT NULL DEFAULT 60
);
CREATE TABLE IF NOT EXISTS jefit_workout_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,
    start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jefit_session_sets (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    set_index INTEGER NOT NULL,
    weight_lbs REAL NOT NULL,
    reps INTEGER NOT NULL,
    is_record INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS jefit_body_stats (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    stat TEXT NOT NULL,
    unit TEXT NOT NULL,
    current_value REAL,
    goal_value REAL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, stat)
);
CREATE TABLE IF NOT EXISTS jefit_posts (
    id INTEGER PRIMARY KEY,
    feed TEXT NOT NULL,
    author TEXT NOT NULL,
    user_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    likes INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jefit_custom_exercises (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jefit_orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    plan TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL,
    coupon TEXT,
    status TEXT NOT NULL,
    flow_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
"""

DEFAULT_PRIVACY = {
    "profile": "Everyone",
    "workouts": "Members",
    "progress": "Friends",
    "body_stats": "Myself Only",
}
DEFAULT_EMAIL_PREFS = {
    "training_reports": True,
    "promotional_emails": True,
    "product_tips": True,
}

# Captured body-stats table vocabulary (progress-bodystats capture, in order).
BODY_STATS = [
    ("Weight", "lbs"),
    ("Body Fat", "%"),
    ("Waist", "in"),
    ("Chest", "in"),
    ("Arms", "in"),
    ("Forearms", "in"),
    ("Shoulders", "in"),
    ("Hips", "in"),
    ("Thighs", "in"),
    ("Calves", "in"),
    ("Neck", "in"),
    ("Height", "in"),
]

SEED_POSTS = [
    ("qa", "IronRoutine", "Best rest time for 5x5?",
     "I run a 5x5 split twice a week. Is 90 seconds of rest enough between "
     "compound sets, or should I extend to 3 minutes?", 12, 4),
    ("qa", "LiftLogLena", "Bench press shoulder position",
     "How do you keep your shoulders packed during flat bench? Mine drift "
     "forward on the last reps.", 8, 6),
    ("qa", "GripGains", "Tracking warm-up sets",
     "Do you log warm-up sets separately or fold them into your working "
     "sets when tracking volume?", 5, 3),
    ("qa", "SquatScholar", "Knee wraps vs sleeves",
     "For a beginner squatting twice a week, are sleeves worth it or should "
     "I just train raw for now?", 9, 5),
    ("qa", "TempoTess", "How slow is a tempo rep?",
     "When a plan says tempo squats, what count do you actually use on the "
     "way down?", 4, 2),
    ("qa", "DeloadDan", "When to deload?",
     "Six weeks into a linear progression and my sleep is getting worse. Is "
     "that the classic deload signal?", 11, 7),
    ("popular", "PlateauBreaker", "",
     "Hit a 20 lb PR on deadlift this morning after three months of sticking "
     "to the program. Log everything, trust the process.", 148, 23),
    ("popular", "MorningMover", "",
     "Completed my 50th logged session this year. The streak calendar is the "
     "only motivation I need.", 96, 12),
    ("popular", "KettleCarrie", "",
     "Swapped my lunch break for a 30-minute kettlebell circuit. Energy all "
     "afternoon, no crash.", 74, 9),
    ("popular", "RowRhys", "",
     "Cable seated rows finally clicked once I stopped yanking with my arms. "
     "Elbows to the hips, squeeze, done.", 61, 8),
    ("popular", "CoreCasey", "",
     "Six weeks of the ab plan down. The last week of hanging raises was "
     "brutal but worth it.", 55, 6),
    ("popular", "SteadyState", "",
     "Reminder: a 20-minute walk still counts as a session. Log it and keep "
     "the habit alive.", 43, 5),
]


def _ensure_business_schema(site_backend: Any) -> None:
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.executescript(SCHEMA_SQL)


def _seed_business(connection: sqlite3.Connection) -> None:
    """Deterministic business seed; runs inside a caller transaction."""

    for table in BUSINESS_TABLES:
        connection.execute(f"DELETE FROM {table}")
    connection.execute(
        "DELETE FROM sqlite_sequence WHERE name LIKE 'jefit_%'"
    )

    def add_user(fixture: dict[str, str], user_id: int) -> None:
        connection.execute(
            "INSERT INTO jefit_users(id,subject_id,username,email,created_at,"
            "email_verified,privacy_json,email_prefs_json,birthday,gender,"
            "workout_level,top_goal) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                fixture["subject_id"],
                fixture["display_name"],
                fixture["email"],
                SEED_EPOCH,
                0,
                json.dumps(DEFAULT_PRIVACY),
                json.dumps(DEFAULT_EMAIL_PREFS),
                "1998-03-14" if user_id == 1 else "",
                "Male" if user_id == 1 else "",
                "Intermediate" if user_id == 1 else "Beginner",
                "Strength" if user_id == 1 else "Maintaining",
            ),
        )

    add_user(PRIMARY, 1)
    add_user(ISOLATION, 2)

    def add_routine(rid: int, owner: int | None, name: str, days: list) -> None:
        connection.execute(
            "INSERT INTO jefit_routines(id,owner_user_id,name,focus,level,"
            "day_tag,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (rid, owner, name, "General", "Beginner", "Day 1", SEED_EPOCH,
             SEED_EPOCH),
        )
        for position, (title, entries) in enumerate(days, start=1):
            cursor = connection.execute(
                "INSERT INTO jefit_routine_days(routine_id,position,title) "
                "VALUES (?,?,?)",
                (rid, position, title),
            )
            day_id = cursor.lastrowid
            for slot, entry in enumerate(entries, start=1):
                connection.execute(
                    "INSERT INTO jefit_day_exercises(day_id,position,"
                    "exercise_id,name,sets,weight_lbs,reps,rest_seconds) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (day_id, slot, *entry),
                )

    # Signup auto-creates 'New Routine' (the current plan; the saved list
    # renders it twice — source quirk reproduced at the view layer). Every
    # account owns one because signup always creates it; the isolation actor
    # holds nothing else.
    add_routine(101, 1, "New Routine", [("Day 1", [])])
    add_routine(111, 2, "New Routine", [("Day 1", [])])
    connection.execute(
        "UPDATE jefit_users SET current_plan_id=111 WHERE id=2"
    )
    # The authenticated walk's synthetic construction, mirrored exactly.
    add_routine(
        102,
        1,
        "Strength Base 3-Day",
        [
            ("Day 1", [(2, "Barbell Bench Press", 1, 45.0, 5, 90)]),
            ("Day 2", [(12, "Barbell Squat", 3, 10.0, 8, 60)]),
            ("Day 3", [(21, "Cable Seated Row", 3, 10.0, 8, 60)]),
        ],
    )
    connection.execute(
        "UPDATE jefit_users SET current_plan_id=101 WHERE id=1"
    )

    # One logged session on 2026-08-18: bench 25 lbs x 8 (record).
    connection.execute(
        "INSERT INTO jefit_workout_sessions(id,user_id,session_date,"
        "start_time,end_time,created_at) VALUES (?,?,?,?,?,?)",
        (201, 1, SEED_DAY, "09:00", "09:45", SEED_EPOCH),
    )
    connection.execute(
        "INSERT INTO jefit_session_sets(session_id,exercise_id,name,"
        "set_index,weight_lbs,reps,is_record) VALUES (?,?,?,?,?,?,?)",
        (201, 2, "Barbell Bench Press", 1, 25.0, 8, 1),
    )

    seeded_stats = {"Weight": (185.0, 175.0), "Body Fat": (18.0, 15.0)}
    for stat, unit in BODY_STATS:
        current, goal = seeded_stats.get(stat, (None, None))
        connection.execute(
            "INSERT INTO jefit_body_stats(user_id,stat,unit,current_value,"
            "goal_value,updated_at) VALUES (?,?,?,?,?,?)",
            (1, stat, unit, current, goal, SEED_EPOCH),
        )

    for index, (feed, author, title, body, likes, comments) in enumerate(
        SEED_POSTS, start=1
    ):
        connection.execute(
            "INSERT INTO jefit_posts(id,feed,author,title,body,likes,"
            "comments,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (index, feed, author, title, body, likes, comments, SEED_EPOCH),
        )


def _seed_all(site_backend: Any, auth_store: Any) -> None:
    """Idempotent first-boot seed: accounts + business rows if absent."""

    for account in SEED_ACCOUNTS:
        auth_store.seed_account(**account)
    with site_backend.lifecycle.connection(transaction=True) as connection:
        row = connection.execute("SELECT COUNT(*) FROM jefit_users").fetchone()
        if int(row[0]) == 0:
            _seed_business(connection)


def reset() -> None:
    """Deterministic full reset through the seam, one transaction."""

    site_backend, auth_store = services()
    auth_store.reset_site_state(
        site_reset=_seed_business,
        seed_accounts=[dict(account) for account in SEED_ACCOUNTS],
    )
    _verification_outbox.clear()


def business_state_dump() -> str:
    """Canonical dump of every business table (determinism checks)."""

    site_backend, _ = services()
    chunks: list[str] = []
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        for table in BUSINESS_TABLES:
            rows = connection.execute(
                f"SELECT * FROM {table} ORDER BY 1"
            ).fetchall()
            chunks.append(
                json.dumps(
                    {table: [dict(row) for row in rows]},
                    sort_keys=True,
                    default=str,
                )
            )
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


def user_by_subject(subject_id: str) -> dict[str, Any] | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM jefit_users WHERE subject_id=?", (subject_id,)
        ).fetchone()
        return dict(row) if row else None


def user_by_id(user_id: int) -> dict[str, Any] | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM jefit_users WHERE id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def email_for_login(identifier: str) -> str:
    """Resolve 'username or email' to the auth email (source login field)."""

    site_backend, _ = services()
    candidate = identifier.strip()
    if "@" in candidate:
        return candidate
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT email FROM jefit_users WHERE username=?", (candidate,)
        ).fetchone()
        return str(row[0]) if row else candidate


def create_user_subject(
    connection: sqlite3.Connection, registration: dict[str, Any],
    questionnaire: dict[str, Any] | None = None,
) -> str:
    """subject_factory for registration: create the business user row and the
    signup-auto-created 'New Routine' current plan in the same transaction."""

    subject_id = f"jefit-user-{secrets.token_hex(8)}"
    username = registration["display_name"]
    now = SEED_EPOCH
    cursor = connection.execute(
        "INSERT INTO jefit_users(subject_id,username,email,created_at,"
        "email_verified,privacy_json,email_prefs_json,questionnaire_json) "
        "VALUES (?,?,?,?,0,?,?,?)",
        (
            subject_id,
            username,
            registration["email"],
            now,
            json.dumps(DEFAULT_PRIVACY),
            json.dumps(DEFAULT_EMAIL_PREFS),
            json.dumps(questionnaire or {}),
        ),
    )
    user_id = cursor.lastrowid
    plan = connection.execute(
        "INSERT INTO jefit_routines(owner_user_id,name,created_at,updated_at) "
        "VALUES (?,?,?,?)",
        (user_id, "New Routine", now, now),
    )
    plan_id = plan.lastrowid
    connection.execute(
        "INSERT INTO jefit_routine_days(routine_id,position,title) "
        "VALUES (?,1,'Day 1')",
        (plan_id,),
    )
    connection.execute(
        "UPDATE jefit_users SET current_plan_id=? WHERE id=?",
        (plan_id, user_id),
    )
    for stat, unit in BODY_STATS:
        connection.execute(
            "INSERT INTO jefit_body_stats(user_id,stat,unit,updated_at) "
            "VALUES (?,?,?,?)",
            (user_id, stat, unit, now),
        )
    return subject_id


def update_user_fields(user_id: int, **fields: Any) -> None:
    allowed = {
        "birthday", "gender", "unit_system", "workout_level", "top_goal",
        "privacy_json", "email_prefs_json", "username", "email_verified",
        "custom_exercise_count", "current_plan_id", "account_type",
        "membership_plan", "membership_renews_on", "verify_code_salt",
        "verify_code_hash",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown user fields: {sorted(unknown)}")
    site_backend, _ = services()
    columns = ", ".join(f"{key}=?" for key in fields)
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            f"UPDATE jefit_users SET {columns} WHERE id=?",
            (*fields.values(), user_id),
        )


# ---------------------------------------------------------------------------
# verification mail (in-memory outbox; secrets never persisted)
# ---------------------------------------------------------------------------


def issue_verification_mail(user: dict[str, Any]) -> dict[str, Any]:
    site_backend, _ = services()
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_bytes(16)
    digest = hashlib.sha256(salt + code.encode()).digest()
    update_user_fields(
        user["id"], verify_code_salt=salt, verify_code_hash=digest
    )
    rendered = site_backend.mail.issue(
        "registration", user["email"], {"code": code, "minutes": "30"}
    )
    _verification_outbox[user["subject_id"]] = rendered
    return {"status": "LOCAL_ONLY", "purpose": "registration"}


def verification_mail_for(user: dict[str, Any]) -> dict[str, Any] | None:
    return _verification_outbox.get(user["subject_id"])


def confirm_verification_code(user: dict[str, Any], code: str) -> bool:
    fresh = user_by_id(user["id"])
    if not fresh or not fresh["verify_code_salt"]:
        return False
    digest = hashlib.sha256(
        bytes(fresh["verify_code_salt"]) + code.strip().encode()
    ).digest()
    if not hmac.compare_digest(digest, bytes(fresh["verify_code_hash"])):
        return False
    update_user_fields(
        user["id"], email_verified=1, verify_code_salt=None,
        verify_code_hash=None,
    )
    _verification_outbox.pop(user["subject_id"], None)
    return True


# ---------------------------------------------------------------------------
# routines / plans
# ---------------------------------------------------------------------------


def plans_for_user(user_id: int) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM jefit_routines WHERE owner_user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
        plans = []
        for row in rows:
            plan = dict(row)
            plan["days"] = _plan_days(connection, plan["id"])
            plans.append(plan)
        return plans


def _plan_days(connection: sqlite3.Connection, routine_id: int) -> list[dict]:
    connection.row_factory = sqlite3.Row
    days = []
    for day in connection.execute(
        "SELECT * FROM jefit_routine_days WHERE routine_id=? ORDER BY position",
        (routine_id,),
    ).fetchall():
        entry = dict(day)
        entry["exercises"] = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM jefit_day_exercises WHERE day_id=? "
                "ORDER BY position",
                (day["id"],),
            ).fetchall()
        ]
        days.append(entry)
    return days


def plan_by_id(plan_id: int) -> dict[str, Any] | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM jefit_routines WHERE id=?", (plan_id,)
        ).fetchone()
        if row is None:
            return None
        plan = dict(row)
        plan["days"] = _plan_days(connection, plan_id)
        return plan


def create_plan(
    owner_user_id: int | None,
    name: str = "New Routine",
    *,
    code: str | None = None,
    is_public: bool = False,
) -> dict[str, Any]:
    site_backend, _ = services()
    now = SEED_EPOCH
    with site_backend.lifecycle.connection(transaction=True) as connection:
        cursor = connection.execute(
            "INSERT INTO jefit_routines(owner_user_id,name,code,is_public,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (owner_user_id, name, code, 1 if is_public else 0, now, now),
        )
        plan_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO jefit_routine_days(routine_id,position,title) "
            "VALUES (?,1,'Day 1')",
            (plan_id,),
        )
    return plan_by_id(int(plan_id))


def rename_plan(plan_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        # Source quirk: an emptied routine name is silently ignored.
        return
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE jefit_routines SET name=?, updated_at=? WHERE id=?",
            (name[:120], SEED_EPOCH, plan_id),
        )


def update_plan_meta(plan_id: int, **fields: Any) -> None:
    allowed = {"focus", "level", "day_tag", "description"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown plan fields: {sorted(unknown)}")
    site_backend, _ = services()
    columns = ", ".join(f"{key}=?" for key in fields)
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            f"UPDATE jefit_routines SET {columns} WHERE id=?",
            (*[str(value)[:400] for value in fields.values()], plan_id),
        )


def delete_plan(plan_id: int) -> None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        day_ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM jefit_routine_days WHERE routine_id=?",
                (plan_id,),
            ).fetchall()
        ]
        for day_id in day_ids:
            connection.execute(
                "DELETE FROM jefit_day_exercises WHERE day_id=?", (day_id,)
            )
        connection.execute(
            "DELETE FROM jefit_routine_days WHERE routine_id=?", (plan_id,)
        )
        connection.execute(
            "DELETE FROM jefit_routines WHERE id=?", (plan_id,)
        )
        connection.execute(
            "UPDATE jefit_users SET current_plan_id=NULL "
            "WHERE current_plan_id=?",
            (plan_id,),
        )


def add_day(plan_id: int) -> int:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(position),0) FROM jefit_routine_days "
            "WHERE routine_id=?",
            (plan_id,),
        ).fetchone()
        position = int(row[0]) + 1
        cursor = connection.execute(
            "INSERT INTO jefit_routine_days(routine_id,position,title) "
            "VALUES (?,?,?)",
            (plan_id, position, f"Day {position}"),
        )
        return int(cursor.lastrowid)


def add_day_exercise(day_id: int, exercise_id: int) -> dict[str, Any] | None:
    entry = exercise_by_id(exercise_id)
    if entry is None:
        return None
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(position),0) FROM jefit_day_exercises "
            "WHERE day_id=?",
            (day_id,),
        ).fetchone()
        position = int(row[0]) + 1
        cursor = connection.execute(
            "INSERT INTO jefit_day_exercises(day_id,position,exercise_id,"
            "name,sets,weight_lbs,reps,rest_seconds) VALUES (?,?,?,?,3,10,8,60)",
            (day_id, position, exercise_id, entry["name"]),
        )
        return {
            "id": int(cursor.lastrowid),
            "position": position,
            "exercise_id": exercise_id,
            "name": entry["name"],
            "sets": 3,
            "weight_lbs": 10,
            "reps": 8,
            "rest_seconds": 60,
        }


def update_day_exercise(entry_id: int, **fields: Any) -> None:
    allowed = {"sets", "weight_lbs", "reps", "rest_seconds", "position"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown set fields: {sorted(unknown)}")
    cleaned: dict[str, float] = {}
    for key, value in fields.items():
        number = float(value)
        if not 0 <= number <= 10000:
            raise ValueError(f"{key} out of range")
        cleaned[key] = number
    site_backend, _ = services()
    columns = ", ".join(f"{key}=?" for key in cleaned)
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            f"UPDATE jefit_day_exercises SET {columns} WHERE id=?",
            (*cleaned.values(), entry_id),
        )


def remove_day_exercise(entry_id: int) -> None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "DELETE FROM jefit_day_exercises WHERE id=?", (entry_id,)
        )


def plan_owner(plan_id: int) -> int | None:
    plan = plan_by_id(plan_id)
    return None if plan is None else plan["owner_user_id"]


def day_plan_owner(day_id: int) -> tuple[int | None, int | None]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT r.id, r.owner_user_id FROM jefit_routine_days d "
            "JOIN jefit_routines r ON r.id=d.routine_id WHERE d.id=?",
            (day_id,),
        ).fetchone()
        return (int(row[0]), row[1]) if row else (None, None)


def entry_plan_owner(entry_id: int) -> tuple[int | None, int | None]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT r.id, r.owner_user_id FROM jefit_day_exercises x "
            "JOIN jefit_routine_days d ON d.id=x.day_id "
            "JOIN jefit_routines r ON r.id=d.routine_id WHERE x.id=?",
            (entry_id,),
        ).fetchone()
        return (int(row[0]), row[1]) if row else (None, None)


# ---------------------------------------------------------------------------
# workout logging
# ---------------------------------------------------------------------------


def sessions_for_user(user_id: int, day: str | None = None) -> list[dict]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        query = (
            "SELECT * FROM jefit_workout_sessions WHERE user_id=? "
            + ("AND session_date=? " if day else "")
            + "ORDER BY id"
        )
        args = (user_id, day) if day else (user_id,)
        sessions = []
        for row in connection.execute(query, args).fetchall():
            session = dict(row)
            session["sets"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM jefit_session_sets WHERE session_id=? "
                    "ORDER BY id",
                    (row["id"],),
                ).fetchall()
            ]
            session["volume_lbs"] = sum(
                item["weight_lbs"] * item["reps"] for item in session["sets"]
            )
            sessions.append(session)
        return sessions


def create_session(user_id: int, day: str, start: str, end: str) -> int:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        cursor = connection.execute(
            "INSERT INTO jefit_workout_sessions(user_id,session_date,"
            "start_time,end_time,created_at) VALUES (?,?,?,?,?)",
            (user_id, day, start, end, SEED_EPOCH),
        )
        return int(cursor.lastrowid)


def session_owner(session_id: int) -> int | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT user_id FROM jefit_workout_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        return int(row[0]) if row else None


def log_set(
    session_id: int,
    exercise_id: int,
    weight_lbs: float = 25.0,
    reps: int = 8,
) -> dict[str, Any] | None:
    """Add one logged set; the modal's default set is 25 lbs x 8."""

    entry = exercise_by_id(exercise_id)
    if entry is None:
        return None
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        owner = connection.execute(
            "SELECT user_id FROM jefit_workout_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if owner is None:
            return None
        best = connection.execute(
            "SELECT MAX(s.weight_lbs) FROM jefit_session_sets s "
            "JOIN jefit_workout_sessions w ON w.id=s.session_id "
            "WHERE w.user_id=? AND s.exercise_id=?",
            (int(owner[0]), exercise_id),
        ).fetchone()
        is_record = 1 if best[0] is None or weight_lbs > float(best[0]) else 0
        index_row = connection.execute(
            "SELECT COALESCE(MAX(set_index),0) FROM jefit_session_sets "
            "WHERE session_id=? AND exercise_id=?",
            (session_id, exercise_id),
        ).fetchone()
        cursor = connection.execute(
            "INSERT INTO jefit_session_sets(session_id,exercise_id,name,"
            "set_index,weight_lbs,reps,is_record) VALUES (?,?,?,?,?,?,?)",
            (
                session_id,
                exercise_id,
                entry["name"],
                int(index_row[0]) + 1,
                weight_lbs,
                reps,
                is_record,
            ),
        )
        return {
            "id": int(cursor.lastrowid),
            "name": entry["name"],
            "weight_lbs": weight_lbs,
            "reps": reps,
            "is_record": bool(is_record),
        }


def update_logged_set(set_id: int, weight_lbs: float, reps: int) -> None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "UPDATE jefit_session_sets SET weight_lbs=?, reps=? WHERE id=?",
            (float(weight_lbs), int(reps), set_id),
        )


def set_owner(set_id: int) -> int | None:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        row = connection.execute(
            "SELECT w.user_id FROM jefit_session_sets s "
            "JOIN jefit_workout_sessions w ON w.id=s.session_id WHERE s.id=?",
            (set_id,),
        ).fetchone()
        return int(row[0]) if row else None


# ---------------------------------------------------------------------------
# body stats
# ---------------------------------------------------------------------------


def body_stats_for(user_id: int) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM jefit_body_stats WHERE user_id=? ORDER BY id",
                (user_id,),
            ).fetchall()
        ]


def update_body_stat(
    user_id: int, stat: str, current: float | None, goal: float | None
) -> bool:
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        cursor = connection.execute(
            "UPDATE jefit_body_stats SET current_value=?, goal_value=?, "
            "updated_at=? WHERE user_id=? AND stat=?",
            (current, goal, SEED_EPOCH, user_id, stat),
        )
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# community posts
# ---------------------------------------------------------------------------


def posts_for(feed: str) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM jefit_posts WHERE feed=? ORDER BY id DESC",
                (feed,),
            ).fetchall()
        ]


def create_post(feed: str, user: dict[str, Any], title: str, body: str) -> int:
    if feed not in {"qa", "popular"}:
        raise ValueError("unknown feed")
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        cursor = connection.execute(
            "INSERT INTO jefit_posts(feed,author,user_id,title,body,"
            "created_at) VALUES (?,?,?,?,?,?)",
            (
                feed,
                user["username"],
                user["id"],
                title.strip()[:200],
                body.strip()[:4000],
                SEED_EPOCH,
            ),
        )
        return int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# custom exercises (free-tier limit 0/3) + data controls
# ---------------------------------------------------------------------------


def custom_exercises_for(user_id: int) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM jefit_custom_exercises WHERE user_id=? "
                "ORDER BY id",
                (user_id,),
            ).fetchall()
        ]


def create_custom_exercise(user_id: int, name: str) -> dict[str, Any]:
    name = name.strip()[:120]
    if not name:
        raise ValueError("name is required")
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM jefit_custom_exercises WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if int(count[0]) >= 3:
            raise ValueError("free accounts can create 3 custom exercises")
        cursor = connection.execute(
            "INSERT INTO jefit_custom_exercises(user_id,name,created_at) "
            "VALUES (?,?,?)",
            (user_id, name, SEED_EPOCH),
        )
        connection.execute(
            "UPDATE jefit_users SET custom_exercise_count="
            "(SELECT COUNT(*) FROM jefit_custom_exercises WHERE user_id=?) "
            "WHERE id=?",
            (user_id, user_id),
        )
        return {"id": int(cursor.lastrowid), "name": name,
                "count": int(count[0]) + 1}


def delete_user_data(user_id: int) -> None:
    """Data Controls 'Delete Data': clear the member's business entities."""

    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        plan_ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM jefit_routines WHERE owner_user_id=?",
                (user_id,),
            ).fetchall()
        ]
        for plan_id in plan_ids:
            for day in connection.execute(
                "SELECT id FROM jefit_routine_days WHERE routine_id=?",
                (plan_id,),
            ).fetchall():
                connection.execute(
                    "DELETE FROM jefit_day_exercises WHERE day_id=?",
                    (day[0],),
                )
            connection.execute(
                "DELETE FROM jefit_routine_days WHERE routine_id=?",
                (plan_id,),
            )
        connection.execute(
            "DELETE FROM jefit_routines WHERE owner_user_id=?", (user_id,)
        )
        for session in connection.execute(
            "SELECT id FROM jefit_workout_sessions WHERE user_id=?",
            (user_id,),
        ).fetchall():
            connection.execute(
                "DELETE FROM jefit_session_sets WHERE session_id=?",
                (session[0],),
            )
        connection.execute(
            "DELETE FROM jefit_workout_sessions WHERE user_id=?", (user_id,)
        )
        connection.execute(
            "UPDATE jefit_body_stats SET current_value=NULL, goal_value=NULL "
            "WHERE user_id=?",
            (user_id,),
        )
        connection.execute(
            "DELETE FROM jefit_custom_exercises WHERE user_id=?", (user_id,)
        )
        connection.execute(
            "UPDATE jefit_users SET current_plan_id=NULL, "
            "custom_exercise_count=0 WHERE id=?",
            (user_id,),
        )


def delete_account(user: dict[str, Any]) -> None:
    """Data Controls 'Delete Account': business rows + local auth account."""

    delete_user_data(user["id"])
    site_backend, _ = services()
    with site_backend.lifecycle.connection(transaction=True) as connection:
        connection.execute(
            "DELETE FROM jefit_posts WHERE user_id=?", (user["id"],)
        )
        connection.execute(
            "DELETE FROM jefit_users WHERE id=?", (user["id"],)
        )
        row = connection.execute(
            "SELECT account_id FROM local_auth_accounts WHERE subject_id=?",
            (user["subject_id"],),
        ).fetchone()
        if row is not None:
            connection.execute(
                "DELETE FROM local_auth_sessions WHERE account_id=?",
                (row[0],),
            )
            connection.execute(
                "DELETE FROM local_auth_accounts WHERE account_id=?",
                (row[0],),
            )


def export_csv(user_id: int) -> str:
    """Data Controls export: the member's clone data as CSV text."""

    rows = ["section,name,field,value"]

    def add(section: str, name: str, field: str, value: Any) -> None:
        safe = str(value).replace('"', "'").replace("\n", " ")
        rows.append(f'{section},"{name}",{field},"{safe}"')

    for plan in plans_for_user(user_id):
        add("routine", plan["name"], "focus", plan["focus"])
        add("routine", plan["name"], "level", plan["level"])
        for day in plan["days"]:
            for entry in day["exercises"]:
                add(
                    "routine",
                    plan["name"],
                    f"{day['title']}:{entry['name']}",
                    f"{entry['sets']}x{entry['reps']} @ "
                    f"{entry['weight_lbs']} lbs / {entry['rest_seconds']}s",
                )
    for session in sessions_for_user(user_id):
        for item in session["sets"]:
            add(
                "workout-session",
                session["session_date"],
                item["name"],
                f"set {item['set_index']}: {item['weight_lbs']} lbs x "
                f"{item['reps']}",
            )
    for stat in body_stats_for(user_id):
        add("body-stat", stat["stat"], "current", stat["current_value"])
        add("body-stat", stat["stat"], "goal", stat["goal_value"])
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# membership orders (payment mandate)
# ---------------------------------------------------------------------------


def reject_payment_keys(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        name = str(key)
        if PAYMENT_FIELD_RE.search(name):
            raise PaymentFieldRejected(
                "This sandbox accepts only a simulated payment scenario; "
                "card-like fields are refused and never stored."
            )
        if isinstance(value, str) and CARD_VALUE_RE.fullmatch(value.strip()):
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 12:
                raise PaymentFieldRejected(
                    "This sandbox accepts only a simulated payment scenario; "
                    "card-like values are refused and never stored."
                )


def orders_for(user_id: int) -> list[dict[str, Any]]:
    site_backend, _ = services()
    with site_backend.lifecycle.connection() as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM jefit_orders WHERE user_id=? ORDER BY id",
                (user_id,),
            ).fetchall()
        ]


def purchase_membership(
    user: dict[str, Any], plan: str, scenario_id: str, idempotency_key: str
) -> dict[str, Any]:
    """Consume one sandbox scenario and write order + membership atomically."""

    if plan not in ELITE_PLANS:
        raise ValueError("unknown plan")
    facts = ELITE_PLANS[plan]
    site_backend, _ = services()
    owner = user["subject_id"]
    fingerprint = hashlib.sha256(f"jefit-elite-{plan}".encode()).hexdigest()
    currency = "USD"
    amount = facts["amount_minor"]
    with site_backend.lifecycle.connection(transaction=True) as connection:
        existing = connection.execute(
            "SELECT id,status,flow_id FROM jefit_orders WHERE user_id=? AND "
            "flow_id IN (SELECT flow_id FROM websitebench_payment_attempts "
            "WHERE idempotency_key=? AND owner=?)",
            (user["id"], idempotency_key, owner),
        ).fetchone()
        if existing is not None:
            return {
                "status": "approved",
                "order_id": int(existing[0]),
                "duplicate": True,
            }
        intent = site_backend.payments.create_intent(
            owner=owner,
            amount_minor=amount,
            currency=currency,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            connection=connection,
        )
        flow_id = intent["flow_id"]
        try:
            attempt = site_backend.payments.attempt(
                flow_id=flow_id,
                owner=owner,
                amount_minor=amount,
                currency=currency,
                fingerprint=fingerprint,
                scenario_id=scenario_id,
                idempotency_key=idempotency_key,
                connection=connection,
            )
        except PaymentError:
            raise
        status = attempt["status"]
        if status == "DECLINED":
            return {"status": "declined"}
        if status == "RETRYABLE":
            return {"status": "retryable"}
        site_backend.payments.consume_approval(
            connection,
            flow_id=flow_id,
            owner=owner,
            amount_minor=amount,
            currency=currency,
            fingerprint=fingerprint,
        )
        cursor = connection.execute(
            "INSERT INTO jefit_orders(user_id,plan,amount_minor,currency,"
            "coupon,status,flow_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                user["id"],
                plan,
                amount,
                currency,
                facts["coupon"],
                "approved",
                flow_id,
                SEED_EPOCH,
            ),
        )
        renews = "2027-08-18" if plan == "yearly" else "2026-09-18"
        connection.execute(
            "UPDATE jefit_users SET account_type='elite', membership_plan=?, "
            "membership_renews_on=? WHERE id=?",
            (plan, renews, user["id"]),
        )
        return {"status": "approved", "order_id": int(cursor.lastrowid)}
