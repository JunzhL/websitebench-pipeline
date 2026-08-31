from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


CLONE = Path(__file__).resolve().parents[1]
SITE = CLONE.parent
if str(CLONE) not in sys.path:
    sys.path.insert(0, str(CLONE))


@pytest.fixture(scope="session")
def app_module(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("sur-la-table-runtime")
    runtime = json.loads((SITE / "backend/runtime.json").read_text(encoding="utf-8"))
    runtime_path = root / "runtime.json"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    os.environ["WEBSITEBENCH_SITE_BACKEND_RUNTIME"] = str(runtime_path)
    os.environ["WEBSITEBENCH_ADMIN_TOKEN"] = "test-reset-token"
    sys.modules.pop("app", None)
    return importlib.import_module("app")


@pytest.fixture()
def client(app_module):
    with TestClient(app_module.app, base_url="https://testserver") as value:
        response = value.post(
            "/__admin/reset", headers={"x-websitebench-admin-token":"test-reset-token"}
        )
        assert response.status_code == 200
        yield value
