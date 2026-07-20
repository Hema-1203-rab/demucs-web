from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.config import Settings
from backend.app.services.file_service import FileService


def test_validate_extension_accepts_supported_formats(tmp_path: Path) -> None:
    service = FileService(Settings(jobs_root=tmp_path))

    assert service.validate_extension("song.mp3") == ".mp3"
    assert service.validate_extension("song.WAV") == ".wav"
    assert service.validate_extension("song.flac") == ".flac"


def test_validate_extension_rejects_unsupported_format(tmp_path: Path) -> None:
    service = FileService(Settings(jobs_root=tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        service.validate_extension("song.txt")

    assert exc_info.value.status_code == 400


def test_create_job_dirs_uses_uuid_directory(tmp_path: Path) -> None:
    service = FileService(Settings(jobs_root=tmp_path))
    job_id = "12345678-1234-5678-1234-567812345678"

    paths = service.create_job_dirs(job_id)

    assert paths["root"] == tmp_path.resolve() / job_id
    assert (tmp_path / job_id / "input").is_dir()
    assert (tmp_path / job_id / "output").is_dir()
    assert (tmp_path / job_id / "logs").is_dir()
    assert (tmp_path / job_id / "result").is_dir()
