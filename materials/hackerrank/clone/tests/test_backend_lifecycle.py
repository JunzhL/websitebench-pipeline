import copy
from pathlib import Path

import pytest

import app as app_module
from backend import domain
from websitebench.site_backend import SiteBackend, SiteBindingError


def test_runtime_identity_and_profiles(client):
    config = app_module.BACKEND.config
    assert config.site_id == "hackerrank"
    assert config.database_filename == "hackerrank.sqlite3"
    assert config.deployment["profiles"]["offline-harbor"] == {
        "mail_adapter": "local-outbox",
        "payment_adapter": "local-sandbox",
        "persistence": "persistent",
    }
    assert set(config.mail["purposes"]) == {"registration", "password-reset"}
    assert config.payments["default_adapter"] == "local-sandbox"
    assert config.payments["stripe_test"] is None


def test_restart_and_backup_preserve_site_data(signed_in, tmp_path: Path):
    signed_in.post(
        "/profile",
        data={"full_name": "Persistent Learner", "bio": "Survives restart."},
    )
    database = app_module.BACKEND.lifecycle.database_path
    restarted = SiteBackend.open(
        app_module.BACKEND.config.raw,
        data_root=database.parent,
        migration_hook=domain.migrate,
        seed_hook=domain.seed,
    )
    restarted.lifecycle.initialize()
    with restarted.lifecycle.connection() as connection:
        assert connection.execute(
            "SELECT full_name FROM hr_profiles WHERE subject_id=?", (domain.DEMO_SUBJECT,)
        ).fetchone()[0] == "Persistent Learner"

    backup = tmp_path / "hackerrank-backup.sqlite3"
    restarted.lifecycle.backup(backup)
    restore_root = tmp_path / "restored"
    restored = SiteBackend.open(
        app_module.BACKEND.config.raw,
        data_root=restore_root,
        migration_hook=domain.migrate,
        seed_hook=domain.seed,
    )
    restored.lifecycle.initialize()
    restored.lifecycle.restore(backup)
    with restored.lifecycle.connection() as connection:
        assert connection.execute(
            "SELECT full_name FROM hr_profiles WHERE subject_id=?", (domain.DEMO_SUBJECT,)
        ).fetchone()[0] == "Persistent Learner"


def test_foreign_site_binding_is_rejected(client):
    database = app_module.BACKEND.lifecycle.database_path
    foreign = copy.deepcopy(dict(app_module.BACKEND.config.raw))
    foreign["site"]["id"] = "foreign-hackerrank"
    foreign["site"]["label"] = "Foreign HackerRank"
    foreign["site"]["public_origin"] = "https://foreign-hackerrank.offline.invalid"
    with pytest.raises(SiteBindingError):
        SiteBackend.open(
            foreign,
            data_root=database.parent,
            migration_hook=domain.migrate,
            seed_hook=domain.seed,
        )
