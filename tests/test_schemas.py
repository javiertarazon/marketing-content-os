import pytest
from pydantic import ValidationError

from packages.python.core.schemas import (
    ContentRequest,
    JobCreate,
    JobRecord,
    JobStatus,
    WorkerType,
)


def test_content_request_uses_independent_platform_lists() -> None:
    first = ContentRequest(topic="Tema A")
    second = ContentRequest(topic="Tema B")

    first.platforms.append("youtube")

    assert second.platforms == []


def test_content_request_rejects_invalid_duration() -> None:
    with pytest.raises(ValidationError):
        ContentRequest(topic="Tema", duration_seconds=0)


def test_job_create_requires_supported_worker() -> None:
    with pytest.raises(ValidationError):
        JobCreate.model_validate(
            {"worker": "unknown", "request": {"topic": "Tema"}}
        )

    job = JobCreate.model_validate(
        {"worker": WorkerType.research, "request": {"topic": "Tema"}}
    )
    assert job.worker is WorkerType.research


def test_job_record_preserves_render_fields_in_request() -> None:
    request = {
        "topic": "Tema",
        "duration_seconds": 35,
        "script": "Guion de prueba",
        "audio_url": "https://cdn.example.com/audio.wav",
        "research": {"facts": ["Dato"]},
    }
    record = JobRecord.model_validate(
        {
            "job_id": "f2810a6b-75e3-49fd-b7d9-9d6cbef8502e",
            "worker": WorkerType.render,
            "status": JobStatus.queued,
            "request": request,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    )

    assert record.model_dump(mode="json")["request"] == request
