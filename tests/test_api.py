from __future__ import annotations

import time
import uuid
import subprocess
from pathlib import Path
from threading import Event
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.demucs_service import FakeDemucsService


def make_client(tmp_path: Path, max_size: int = 1024, separation_service: object | None = None) -> TestClient:
    app = create_app(
        Settings(jobs_root=tmp_path, max_upload_size_bytes=max_size),
        separation_service=separation_service or FakeDemucsService(),
    )
    return TestClient(app)


def wait_for_status(client: TestClient, job_id: str, status: str, timeout: float = 2.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] == status:
            return last_payload
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {status}; last payload: {last_payload}")


def test_health_endpoint(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert isinstance(response.json()["demucs_available"], bool)


def test_frontend_index_is_served(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "Demucs 四轨分离" in response.text


def test_upload_creates_job_and_fake_outputs(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("song.wav", b"not really wav but acceptable for milestone 1", "audio/wav")},
    )

    assert response.status_code == 202
    payload = response.json()
    uuid.UUID(payload["job_id"])
    assert payload["status"] == "queued"

    job_dir = tmp_path / payload["job_id"]
    assert (job_dir / "input" / "source.wav").is_file()
    status_payload = wait_for_status(client, payload["job_id"], "succeeded")
    for stem in ("vocals", "drums", "bass", "other"):
        assert (job_dir / "result" / f"{stem}.wav").is_file()

    outputs = status_payload["outputs"]
    assert outputs["vocals"] == f"/media/{payload['job_id']}/vocals.wav"

    media_response = client.get(outputs["vocals"])
    assert media_response.status_code == 200
    assert media_response.headers["content-type"].startswith("audio/wav")


def test_media_rejects_invalid_stem(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"

    response = client.get(f"/media/{job_id}/../secret.wav")

    assert response.status_code == 404


def test_upload_can_report_running_before_success(tmp_path: Path) -> None:
    service = BlockingSeparationService()
    client = make_client(tmp_path, separation_service=service)

    response = client.post(
        "/api/jobs",
        files={"file": ("song.wav", b"audio", "audio/wav")},
    )
    job_id = response.json()["job_id"]

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    wait_for_status(client, job_id, "running")

    service.release()
    payload = wait_for_status(client, job_id, "succeeded")

    assert payload["outputs"]["drums"] == f"/media/{job_id}/drums.wav"


def test_upload_reports_failed_when_worker_fails(tmp_path: Path) -> None:
    client = make_client(tmp_path, separation_service=FailingSeparationService())

    response = client.post(
        "/api/jobs",
        files={"file": ("song.wav", b"audio", "audio/wav")},
    )
    job_id = response.json()["job_id"]

    payload = wait_for_status(client, job_id, "failed")

    assert response.status_code == 202
    assert payload["outputs"] is None
    assert payload["error"] == "mock separation failed"


def test_upload_rejects_bad_extension(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("song.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_empty_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("song.mp3", b"", "audio/mpeg")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_upload_rejects_too_large_file(tmp_path: Path) -> None:
    client = make_client(tmp_path, max_size=4)

    response = client.post(
        "/api/jobs",
        files={"file": ("song.flac", b"12345", "audio/flac")},
    )

    assert response.status_code == 413
    assert "File is too large" in response.json()["detail"]


def test_get_missing_job_returns_404(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/jobs/12345678-1234-5678-1234-567812345678")

    assert response.status_code == 404


def test_create_mix_and_download_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(tmp_path)
    run_mock = Mock(side_effect=fake_ffmpeg_success)
    monkeypatch.setattr(subprocess, "run", run_mock)
    job_id = create_succeeded_job(client)

    response = client.post(f"/api/jobs/{job_id}/mixes", json={"stems": ["bass", "vocals"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "stems": ["vocals", "bass"],
        "play_url": f"/media/{job_id}/mixes/mix-vocals-bass.wav",
        "download_url": f"/media/{job_id}/mixes/mix-vocals-bass.wav/download",
    }
    play_response = client.get(payload["play_url"])
    assert play_response.status_code == 200
    assert play_response.headers["content-type"].startswith("audio/wav")

    download_response = client.get(payload["download_url"])
    assert download_response.status_code == 200
    assert "attachment" in download_response.headers["content-disposition"]
    assert run_mock.call_count == 1


def test_create_mix_rejects_missing_job(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/jobs/12345678-1234-5678-1234-567812345678/mixes",
        json={"stems": ["vocals"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


def test_create_mix_rejects_job_that_has_not_succeeded(tmp_path: Path) -> None:
    service = BlockingSeparationService()
    client = make_client(tmp_path, separation_service=service)
    upload_response = client.post(
        "/api/jobs",
        files={"file": ("song.wav", b"audio", "audio/wav")},
    )
    job_id = upload_response.json()["job_id"]
    wait_for_status(client, job_id, "running")

    response = client.post(f"/api/jobs/{job_id}/mixes", json={"stems": ["vocals"]})

    assert response.status_code == 409
    assert response.json()["detail"] == "只有分离完成后才能生成合并音轨"
    service.release()
    wait_for_status(client, job_id, "succeeded")


def test_create_mix_reports_missing_source_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    job_id = create_succeeded_job(client)
    (tmp_path / job_id / "result" / "other.wav").unlink()

    response = client.post(f"/api/jobs/{job_id}/mixes", json={"stems": ["other"]})

    assert response.status_code == 500
    assert response.json()["detail"] == "选中的源音轨文件不存在"


def test_create_mix_reports_ffmpeg_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(tmp_path)

    def fake_failure(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_failure)
    job_id = create_succeeded_job(client)

    response = client.post(f"/api/jobs/{job_id}/mixes", json={"stems": ["vocals", "drums"]})

    assert response.status_code == 500
    assert response.json()["detail"] == "合并音轨生成失败，请确认 FFmpeg 可用后重试"


def test_mix_media_rejects_path_traversal(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    job_id = "12345678-1234-5678-1234-567812345678"

    response = client.get(f"/media/{job_id}/mixes/../vocals.wav")

    assert response.status_code == 404


def create_succeeded_job(client: TestClient) -> str:
    response = client.post(
        "/api/jobs",
        files={"file": ("song.wav", b"audio", "audio/wav")},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    wait_for_status(client, job_id, "succeeded")
    return job_id


def fake_ffmpeg_success(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    assert "shell" not in kwargs
    Path(command[-1]).write_bytes(b"mixed")
    return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")


class BlockingSeparationService:
    def __init__(self) -> None:
        self.started = Event()
        self.released = Event()

    def separate(self, input_path: Path, output_dir: Path, result_dir: Path) -> dict[str, str]:
        self.started.set()
        assert self.released.wait(timeout=2)
        result_dir.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, str] = {}
        for stem in ("vocals", "drums", "bass", "other"):
            path = result_dir / f"{stem}.wav"
            path.write_bytes(b"audio")
            outputs[stem] = path.name
        return outputs

    def release(self) -> None:
        self.released.set()


class FailingSeparationService:
    def separate(self, input_path: Path, output_dir: Path, result_dir: Path) -> dict[str, str]:
        raise RuntimeError("mock separation failed")
