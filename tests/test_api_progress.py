import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

API_DIRECTORY = Path(__file__).parents[1] / "apps" / "api"
sys.path.insert(0, str(API_DIRECTORY))
sys.path.insert(0, str(Path(__file__).parents[1] / "packages" / "python"))
os.environ["WORKER_API_TOKEN"] = "pytest-worker-token"

import main as api


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return FakeCursor(self.row)


def test_worker_progress_requires_valid_authentication_and_lease(monkeypatch) -> None:
    job_id = UUID("f2810a6b-75e3-49fd-b7d9-9d6cbef8502e")
    monkeypatch.setattr(api, "init_database", lambda: None)
    now = datetime.now(timezone.utc)
    row = {
        "job_id": job_id,
        "worker": "render",
        "status": "running",
        "request": {"topic": "Video de prueba"},
        "progress": {"stage": "rendering", "message": "Renderizando", "percent": 60},
        "output": None,
        "error": None,
        "attempts": 1,
        "created_at": now,
        "updated_at": now,
    }
    monkeypatch.setattr(api, "get_connection", lambda: FakeConnection(row))

    with TestClient(api.app) as client:
        unauthorized = client.post(
            f"/v1/jobs/{job_id}/progress",
            json={"stage": "rendering", "message": "Renderizando", "percent": 60},
            headers={"X-Worker-Lease": "lease-token"},
        )
        assert unauthorized.status_code == 401

        response = client.post(
            f"/v1/jobs/{job_id}/progress",
            json={"stage": "rendering", "message": "Renderizando", "percent": 60},
            headers={
                "Authorization": "Bearer pytest-worker-token",
                "X-Worker-Lease": "lease-token",
            },
        )

    assert response.status_code == 200
    assert response.json()["progress"]["percent"] == 60
