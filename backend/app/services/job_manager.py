from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from backend.app.schemas import JobStatus


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    message: str
    outputs: dict[str, str] | None = None
    error: str | None = None


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()

    def create(self, job_id: str) -> JobRecord:
        record = JobRecord(job_id=job_id, status=JobStatus.queued, message="Job queued")
        with self._lock:
            self._jobs[job_id] = record
        return record

    def mark_running(self, job_id: str) -> JobRecord:
        return self._update(job_id, status=JobStatus.running, message="Fake separation is running")

    def mark_succeeded(self, job_id: str, outputs: dict[str, str]) -> JobRecord:
        return self._update(
            job_id,
            status=JobStatus.succeeded,
            message="Separation completed",
            outputs=outputs,
            error=None,
        )

    def mark_failed(self, job_id: str, error: str) -> JobRecord:
        return self._update(
            job_id,
            status=JobStatus.failed,
            message="Separation failed",
            outputs=None,
            error=error,
        )

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        message: str,
        outputs: dict[str, str] | None = None,
        error: str | None = None,
    ) -> JobRecord:
        with self._lock:
            record = self._jobs[job_id]
            record.status = status
            record.message = message
            record.outputs = outputs
            record.error = error
            return record
