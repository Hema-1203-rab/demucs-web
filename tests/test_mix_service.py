from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.app.services.mix_service import MixService, MixServiceError, MixValidationError


def make_result_dir(tmp_path: Path) -> Path:
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    for stem in ("vocals", "drums", "bass", "other"):
        (result_dir / f"{stem}.wav").write_bytes(stem.encode("ascii"))
    return result_dir


def fake_success(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert "shell" not in kwargs
    Path(command[-1]).write_bytes(b"mixed")
    return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")


def test_mix_service_generates_single_stem_mix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_dir = make_result_dir(tmp_path)
    run_mock = Mock(side_effect=fake_success)
    monkeypatch.setattr(subprocess, "run", run_mock)

    result = MixService().create_mix(result_dir, ["vocals"])

    assert result.stems == ["vocals"]
    assert result.filename == "mix-vocals.wav"
    assert result.path.read_bytes() == b"mixed"
    assert run_mock.call_count == 1
    command = run_mock.call_args.args[0]
    assert command[:4] == ["ffmpeg", "-y", "-i", str(result_dir / "vocals.wav")]
    assert "amix=inputs=1:duration=longest:dropout_transition=0:normalize=0" in command


def test_mix_service_generates_multiple_stem_mix_in_fixed_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_dir = make_result_dir(tmp_path)
    run_mock = Mock(side_effect=fake_success)
    monkeypatch.setattr(subprocess, "run", run_mock)

    result = MixService().create_mix(result_dir, ["bass", "vocals"])

    assert result.stems == ["vocals", "bass"]
    assert result.filename == "mix-vocals-bass.wav"
    command = run_mock.call_args.args[0]
    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        str(result_dir / "vocals.wav"),
        "-i",
        str(result_dir / "bass.wav"),
        "-filter_complex",
        "amix=inputs=2:duration=longest:dropout_transition=0:normalize=0",
        "-c:a",
        "pcm_s16le",
        str(result_dir / "mixes" / ".mix-vocals-bass.tmp.wav"),
    ]


def test_mix_service_generates_four_stem_mix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_dir = make_result_dir(tmp_path)
    run_mock = Mock(side_effect=fake_success)
    monkeypatch.setattr(subprocess, "run", run_mock)

    result = MixService().create_mix(result_dir, ["other", "bass", "drums", "vocals"])

    assert result.stems == ["vocals", "drums", "bass", "other"]
    assert result.filename == "mix-vocals-drums-bass-other.wav"
    assert "amix=inputs=4:duration=longest:dropout_transition=0:normalize=0" in run_mock.call_args.args[0]


@pytest.mark.parametrize(
    ("stems", "message"),
    [
        ([], "请至少选择一个音轨"),
        (["vocals", "guitar"], "包含不支持的音轨"),
        (["vocals", "vocals"], "不能重复选择同一个音轨"),
    ],
)
def test_mix_service_rejects_invalid_stems(stems: list[str], message: str, tmp_path: Path) -> None:
    result_dir = make_result_dir(tmp_path)

    with pytest.raises(MixValidationError) as exc_info:
        MixService().create_mix(result_dir, stems)

    assert str(exc_info.value) == message


def test_mix_service_raises_when_source_stem_is_missing(tmp_path: Path) -> None:
    result_dir = make_result_dir(tmp_path)
    (result_dir / "bass.wav").unlink()

    with pytest.raises(MixServiceError) as exc_info:
        MixService().create_mix(result_dir, ["bass"])

    assert str(exc_info.value) == "选中的源音轨文件不存在"


def test_mix_service_deletes_temp_file_when_ffmpeg_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_dir = make_result_dir(tmp_path)

    def fake_failure(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(command, 1, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", fake_failure)

    with pytest.raises(MixServiceError) as exc_info:
        MixService().create_mix(result_dir, ["vocals", "drums"])

    assert str(exc_info.value) == "合并音轨生成失败，请确认 FFmpeg 可用后重试"
    assert not (result_dir / "mixes" / ".mix-vocals-drums.tmp.wav").exists()
    assert not (result_dir / "mixes" / "mix-vocals-drums.wav").exists()


def test_mix_service_reuses_cached_mix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_dir = make_result_dir(tmp_path)
    mix_dir = result_dir / "mixes"
    mix_dir.mkdir()
    cached_path = mix_dir / "mix-vocals-bass.wav"
    cached_path.write_bytes(b"cached")
    run_mock = Mock()
    monkeypatch.setattr(subprocess, "run", run_mock)

    result = MixService().create_mix(result_dir, ["bass", "vocals"])

    assert result.cached is True
    assert result.path == cached_path
    assert result.path.read_bytes() == b"cached"
    assert run_mock.call_count == 0
