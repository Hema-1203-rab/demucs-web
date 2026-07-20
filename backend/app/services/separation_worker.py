from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from backend.app.services.job_manager import JobManager


class SeparationService(Protocol):
    def separate(self, input_path: Path, output_dir: Path, result_dir: Path) -> dict[str, str]:
        ...


class SeparationWorker:
    def __init__(self, job_manager: JobManager, separation_service: SeparationService) -> None:
        self._job_manager = job_manager
        self._separation_service = separation_service
        self._executor = ThreadPoolExecutor(max_workers=1)

    def submit(
        self,
        *,
        job_id: str,
        input_path: Path,
        output_dir: Path,
        result_dir: Path,
    ) -> Future[None]:
        return self._executor.submit(self._run, job_id, input_path, output_dir, result_dir)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _run(self, job_id: str, input_path: Path, output_dir: Path, result_dir: Path) -> None:
        try:
            self._job_manager.mark_running(job_id)
            raw_outputs = self._separation_service.separate(input_path, output_dir, result_dir)
            outputs = {stem: f"/media/{job_id}/{filename}" for stem, filename in raw_outputs.items()}
            self._job_manager.mark_succeeded(job_id, outputs)
        except Exception as exc:
            self._job_manager.mark_failed(job_id, str(exc) or "Separation failed")
