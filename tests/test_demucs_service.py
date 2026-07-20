from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.app.services.demucs_service import DemucsService, DemucsServiceError


def test_demucs_service_calls_cli_with_argument_list_and_normalizes_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input" / "song.wav"
    output_dir = tmp_path / "output"
    result_dir = tmp_path / "result"
    input_path.parent.mkdir()
    input_path.write_bytes(b"audio")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            "htdemucs",
            "-o",
            str(output_dir),
            str(input_path),
        ]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert "shell" not in kwargs
        demucs_output = output_dir / "htdemucs" / "song"
        demucs_output.mkdir(parents=True)
        for stem in ("vocals", "drums", "bass", "other"):
            (demucs_output / f"{stem}.wav").write_bytes(stem.encode("ascii"))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    run_mock = Mock(side_effect=fake_run)
    monkeypatch.setattr(subprocess, "run", run_mock)

    outputs = DemucsService().separate(input_path, output_dir, result_dir)

    assert outputs == {
        "vocals": "vocals.wav",
        "drums": "drums.wav",
        "bass": "bass.wav",
        "other": "other.wav",
    }
    assert (result_dir / "vocals.wav").read_bytes() == b"vocals"
    assert run_mock.call_count == 1


def test_demucs_service_raises_with_captured_process_output_on_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "song.wav"
    input_path.write_bytes(b"audio")
    command_seen: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        command_seen.extend(command)
        return subprocess.CompletedProcess(command, 2, stdout="some stdout", stderr="some stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(DemucsServiceError) as exc_info:
        DemucsService().separate(input_path, tmp_path / "output", tmp_path / "result")

    assert exc_info.value.run_result is not None
    assert exc_info.value.run_result.command == command_seen
    assert exc_info.value.run_result.returncode == 2
    assert exc_info.value.run_result.stdout == "some stdout"
    assert exc_info.value.run_result.stderr == "some stderr"


def test_demucs_service_raises_when_required_output_stem_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "song.wav"
    output_dir = tmp_path / "output"
    input_path.write_bytes(b"audio")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        demucs_output = output_dir / "htdemucs" / "song"
        demucs_output.mkdir(parents=True)
        for stem in ("vocals", "drums", "bass"):
            (demucs_output / f"{stem}.wav").write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(DemucsServiceError) as exc_info:
        DemucsService().separate(input_path, output_dir, tmp_path / "result")

    assert "Missing Demucs output stems: other" in str(exc_info.value)
    assert not (tmp_path / "result" / "vocals.wav").exists()
