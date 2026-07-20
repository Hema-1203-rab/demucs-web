from __future__ import annotations

from backend.app.schemas import JobStatus
from backend.app.services.job_manager import JobManager


def test_job_status_transitions_to_succeeded() -> None:
    manager = JobManager()
    job_id = "job-1"

    manager.create(job_id)
    manager.mark_running(job_id)
    manager.mark_succeeded(job_id, {"vocals": "/media/job-1/vocals.wav"})

    record = manager.get(job_id)
    assert record is not None
    assert record.status == JobStatus.succeeded
    assert record.outputs == {"vocals": "/media/job-1/vocals.wav"}


def test_job_status_transitions_to_failed() -> None:
    manager = JobManager()
    job_id = "job-1"

    manager.create(job_id)
    manager.mark_running(job_id)
    manager.mark_failed(job_id, "failed")

    record = manager.get(job_id)
    assert record is not None
    assert record.status == JobStatus.failed
    assert record.error == "failed"
