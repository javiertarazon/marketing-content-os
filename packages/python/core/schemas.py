from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class WorkerType(str, Enum):
    research = "research"
    render = "render"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ContentRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    style: str = Field(default="financial-news", min_length=1, max_length=100)
    duration_seconds: int = Field(default=35, ge=1, le=3600)
    platforms: list[str] = Field(default_factory=list)
    source_url: HttpUrl | None = None


class JobCreate(BaseModel):
    worker: WorkerType
    request: ContentRequest


class JobRecord(BaseModel):
    job_id: UUID
    worker: WorkerType
    status: JobStatus
    request: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    created_at: datetime
    updated_at: datetime


class JobCompletion(BaseModel):
    output: dict[str, Any]


class JobFailure(BaseModel):
    error: str = Field(min_length=1, max_length=2000)
