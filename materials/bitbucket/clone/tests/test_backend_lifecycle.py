import copy
from pathlib import Path

import pytest

import app as app_module
from backend import domain
from websitebench.local_clone_auth import LocalAuthStore
from websitebench.site_backend import SiteBackend, SiteBindingError


def test_runtime_identity_and_profiles(client):
    config = app_module.BACKEND.config
    assert config.site_id == "bitbucket"
    assert config.database_filename == "bitbucket.sqlite3"
    assert config.deployment["profiles"]["offline-harbor"] == {
        "mail_adapter": "local-outbox",
        "payment_adapter": "local-sandbox",
        "persistence": "persistent",
    }
    assert set(config.mail["purposes"]) == {"registration", "password-reset"}
    assert config.payments["default_adapter"] == "local-sandbox"
    assert config.payments["stripe_test"] is None


def test_restart_preserves_site_data_and_auth(client):
    database = app_module.BACKEND.lifecycle.database_path
    restarted = SiteBackend.open(
        app_module.BACKEND.config.raw,
        data_root=database.parent,
        migration_hook=domain.migrate,
        seed_hook=domain.seed,
    )
    restarted.lifecycle.initialize()
    restarted_auth = LocalAuthStore(database, site_id="bitbucket")
    restarted_auth.ensure_schema()

    with restarted.lifecycle.connection() as connection:
        project = connection.execute(
            "SELECT name FROM bb_projects WHERE namespace='developer' AND path='platform-demo'"
        ).fetchone()
    assert project["name"] == "platform-demo"
    assert restarted_auth.account_exists("developer@bitbucket.local") is True


def test_foreign_site_binding_is_rejected(client):
    database = app_module.BACKEND.lifecycle.database_path
    foreign = copy.deepcopy(dict(app_module.BACKEND.config.raw))
    foreign["site"]["id"] = "foreign-bitbucket"
    foreign["site"]["label"] = "Foreign Bitbucket"
    foreign["site"]["public_origin"] = "https://foreign-bitbucket.offline.invalid"
    with pytest.raises(SiteBindingError):
        SiteBackend.open(
            foreign,
            data_root=database.parent,
            migration_hook=domain.migrate,
            seed_hook=domain.seed,
        )


def test_backup_restores_into_distinct_bitbucket_database(client, tmp_path: Path):
    backup = tmp_path / "bitbucket-backup.sqlite3"
    app_module.BACKEND.lifecycle.backup(backup)
    assert backup.is_file()

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
        count = connection.execute("SELECT COUNT(*) FROM bb_projects").fetchone()[0]
        binding = connection.execute(
            "SELECT site_id FROM websitebench_site_binding WHERE singleton=1"
        ).fetchone()[0]
    assert count == 2
    assert binding == "bitbucket"
