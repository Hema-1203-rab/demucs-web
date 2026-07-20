from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from backend.app.config import Settings


ALLOWED_STEMS = frozenset({"vocals", "drums", "bass", "other"})


class FileService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_extension(self, filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in self.settings.allowed_extensions:
            allowed = ", ".join(sorted(self.settings.allowed_extensions))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type. Allowed extensions: {allowed}",
            )
        return suffix

    def create_job_dirs(self, job_id: str) -> dict[str, Path]:
        paths = self.job_dirs(job_id)
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def job_dirs(self, job_id: str) -> dict[str, Path]:
        root = self._safe_job_root(job_id)
        return {
            "root": root,
            "input": root / "input",
            "output": root / "output",
            "logs": root / "logs",
            "result": root / "result",
        }

    async def save_upload(self, upload: UploadFile, job_id: str) -> Path:
        suffix = self.validate_extension(upload.filename)
        paths = self.create_job_dirs(job_id)
        input_path = paths["input"] / f"source{suffix}"
        total = 0

        with input_path.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.settings.max_upload_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File is too large. Limit is {self.settings.max_upload_size_bytes} bytes",
                    )
                output.write(chunk)

        if total == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        return input_path

    def result_dir(self, job_id: str) -> Path:
        return self._safe_job_root(job_id) / "result"

    def media_file(self, job_id: str, stem: str) -> Path:
        if stem not in ALLOWED_STEMS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
        path = (self.result_dir(job_id) / f"{stem}.wav").resolve()
        result_dir = self.result_dir(job_id).resolve()
        if result_dir != path.parent:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media path")
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")
        return path

    def _safe_job_root(self, job_id: str) -> Path:
        try:
            parsed = uuid.UUID(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc

        jobs_root = self.settings.jobs_root.resolve()
        root = (jobs_root / str(parsed)).resolve()
        if jobs_root != root and jobs_root not in root.parents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job path")
        return root
