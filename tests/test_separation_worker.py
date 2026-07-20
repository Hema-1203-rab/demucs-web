from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from backend.app.schemas import JobStatus
from backend.app.services.job_manager import JobManager
from backend.app.services.separation_worker import SeparationWorker


def test_separation_worker_runs_one_job_at_a_time(tmp_path: Path) -> None:
    manager = JobManager()
    service = SerialBlockingService()
    worker = SeparationWorker(manager, service)
    manager.create("job-1")
    manager.create("job-2")

    first_future = worker.submit(
        job_id="job-1",
        input_path=tmp_path / "one.wav",
        output_dir=tmp_path / "one-output",
        result_dir=tmp_path / "one-result",
    )
    second_future = worker.submit(
        job_id="job-2",
        input_path=tmp_path / "two.wav",
        output_dir=tmp_path / "two-output",
        result_dir=tmp_path / "two-result",
    )

    assert service.first_started.wait(timeout=2)
    assert manager.get("job-1").status == JobStatus.running
    assert manager.get("job-2").status == JobStatus.queued

    service.release_first.set()
    first_future.result(timeout=2)
    assert service.second_started.wait(timeout=2)
    second_future.result(timeout=2)

    assert manager.get("job-1").status == JobStatus.succeeded
    assert manager.get("job-2").status == JobStatus.succeeded
    worker.shutdown()


class SerialBlockingService:
    def __init__(self) -> None:
        self.calls = 0
        self.first_started = Event()
        self.second_started = Event()
        self.release_first = Event()

    def separate(self, input_path: Path, output_dir: Path, result_dir: Path) -> dict[str, str]:
        self.calls += 1
        if self.calls == 1:
            self.first_started.set()
            assert self.release_first.wait(timeout=2)
        else:
            self.second_started.set()
        result_dir.mkdir(parents=True, exist_ok=True)
        return {
            "vocals": "vocals.wav",
            "drums": "drums.wav",
            "bass": "bass.wav",
            "other": "other.wav",
        }
