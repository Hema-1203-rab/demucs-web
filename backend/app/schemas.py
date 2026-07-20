from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class HealthResponse(BaseModel):
    status: str
    demucs_available: bool
    ffmpeg_available: bool
    device: str


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    outputs: dict[str, str] | None
    error: str | None
