import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from core.schemas import (
    JobCompletion,
    JobCreate,
    JobFailure,
    JobRecord,
    JobStatus,
    WorkerType,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
WORKER_API_TOKEN = os.environ.get("WORKER_API_TOKEN", "")


def get_connection() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no esta configurada")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id UUID PRIMARY KEY,
                worker TEXT NOT NULL CHECK (worker IN ('research', 'render')),
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
                request JSONB NOT NULL,
                output JSONB,
                error TEXT,
                lease_token TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS jobs_queue_idx ON jobs (worker, created_at) WHERE status = 'queued'"
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="Marketing Content OS API", version="1.0.0", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:3001,http://localhost:3000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Worker-Lease"],
)


def require_worker_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not WORKER_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WORKER_API_TOKEN no esta configurado",
        )
    expected = f"Bearer {WORKER_API_TOKEN}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de worker invalido",
            headers={"WWW-Authenticate": "Bearer"},
        )


def serialize_job(row: dict) -> JobRecord:
    return JobRecord(
        job_id=row["job_id"],
        worker=row["worker"],
        status=row["status"],
        request=row["request"],
        output=row["output"],
        error=row["error"],
        attempts=row["attempts"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se puede conectar a PostgreSQL",
        ) from exc
    return {"status": "ok"}


@app.post("/v1/jobs", response_model=JobRecord, status_code=status.HTTP_201_CREATED)
def create_job(job: JobCreate) -> JobRecord:
    job_id = UUID(bytes=secrets.token_bytes(16), version=4)
    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO jobs (job_id, worker, status, request)
            VALUES (%s, %s, 'queued', %s::jsonb)
            RETURNING *
            """,
            (job_id, job.worker.value, json.dumps(job.request.model_dump(mode="json"))),
        ).fetchone()
    return serialize_job(row)


@app.get("/v1/jobs", response_model=list[JobRecord])
def list_jobs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[JobRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return [serialize_job(row) for row in rows]


@app.get("/v1/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: UUID) -> JobRecord:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id = %s", (job_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return serialize_job(row)


@app.post("/v1/jobs/next", dependencies=[Depends(require_worker_token)])
def reserve_job(
    worker: WorkerType,
) -> dict | None:
    lease_token = secrets.token_urlsafe(32)
    with get_connection() as connection:
        row = connection.execute(
            """
            WITH next_job AS (
                SELECT job_id FROM jobs
                WHERE worker = %s AND status = 'queued'
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs
            SET status = 'running', lease_token = %s,
                attempts = attempts + 1, updated_at = now()
            WHERE job_id = (SELECT job_id FROM next_job)
            RETURNING *
            """,
            (worker.value, lease_token),
        ).fetchone()
    if row is None:
        return None
    record = serialize_job(row).model_dump(mode="json")
    record["lease_token"] = lease_token
    return record


def update_leased_job(
    job_id: UUID,
    lease_token: str | None,
    *,
    new_status: JobStatus,
    output: dict | None = None,
    error: str | None = None,
) -> JobRecord:
    if not lease_token:
        raise HTTPException(status_code=401, detail="Falta el token de reserva del trabajo")
    with get_connection() as connection:
        row = connection.execute(
            """
            UPDATE jobs
            SET status = %s, output = %s::jsonb, error = %s,
                lease_token = NULL, updated_at = now()
            WHERE job_id = %s AND status = 'running' AND lease_token = %s
            RETURNING *
            """,
            (
                new_status.value,
                json.dumps(output) if output is not None else None,
                error,
                job_id,
                lease_token,
            ),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="Reserva invalida o trabajo no activo")
    return serialize_job(row)


@app.post("/v1/jobs/{job_id}/complete", response_model=JobRecord)
def complete_job(
    job_id: UUID,
    completion: JobCompletion,
    lease_token: Annotated[str | None, Header(alias="X-Worker-Lease")] = None,
    _: None = Depends(require_worker_token),
) -> JobRecord:
    if not lease_token:
        raise HTTPException(status_code=401, detail="Falta el token de reserva del trabajo")

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id = %s AND status = 'running' AND lease_token = %s FOR UPDATE",
            (job_id, lease_token),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=409, detail="Reserva invalida o trabajo no activo")

        if row["worker"] == WorkerType.research.value:
            required = {"research", "script", "audio_url"}
            missing = required.difference(completion.output)
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=f"El resultado de investigacion no incluye: {', '.join(sorted(missing))}",
                )
            render_request = {**row["request"], **completion.output}
            connection.execute(
                """
                INSERT INTO jobs (job_id, worker, status, request)
                VALUES (%s, 'render', 'queued', %s::jsonb)
                """,
                (
                    UUID(bytes=secrets.token_bytes(16), version=4),
                    json.dumps(render_request),
                ),
            )

        updated = connection.execute(
            """
            UPDATE jobs
            SET status = 'succeeded', output = %s::jsonb, error = NULL,
                lease_token = NULL, updated_at = now()
            WHERE job_id = %s
            RETURNING *
            """,
            (json.dumps(completion.output), job_id),
        ).fetchone()
    return serialize_job(updated)


@app.post("/v1/jobs/{job_id}/fail", response_model=JobRecord)
def fail_job(
    job_id: UUID,
    failure: JobFailure,
    lease_token: Annotated[str | None, Header(alias="X-Worker-Lease")] = None,
    _: None = Depends(require_worker_token),
) -> JobRecord:
    return update_leased_job(
        job_id, lease_token, new_status=JobStatus.failed, error=failure.error
    )
