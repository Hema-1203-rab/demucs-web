from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path


STEMS = ("vocals", "drums", "bass", "other")
DEFAULT_MODEL = "htdemucs"


@dataclass(frozen=True)
class DemucsRunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class DemucsServiceError(RuntimeError):
    def __init__(self, message: str, run_result: DemucsRunResult | None = None) -> None:
        super().__init__(message)
        self.run_result = run_result


class DemucsService:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name

    def separate(self, input_path: Path, output_dir: Path, result_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)

        command = [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            self.model_name,
            "-o",
            str(output_dir),
            str(input_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        run_result = DemucsRunResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if completed.returncode != 0:
            raise DemucsServiceError("Demucs failed to separate the audio", run_result)

        stem_outputs = self._find_outputs(input_path, output_dir, run_result)
        return self._copy_to_result_dir(stem_outputs, result_dir)

    def _find_outputs(
        self,
        input_path: Path,
        output_dir: Path,
        run_result: DemucsRunResult,
    ) -> dict[str, Path]:
        expected_dir = output_dir / self.model_name / input_path.stem
        outputs: dict[str, Path] = {}
        missing: list[str] = []

        for stem in STEMS:
            expected_path = expected_dir / f"{stem}.wav"
            if expected_path.is_file():
                outputs[stem] = expected_path
                continue

            matches = sorted(output_dir.rglob(f"{stem}.wav"))
            if matches:
                outputs[stem] = matches[0]
            else:
                missing.append(stem)

        if missing:
            observed = sorted(str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file())
            observed_text = ", ".join(observed) if observed else "no output files"
            raise DemucsServiceError(
                f"Missing Demucs output stems: {', '.join(missing)}. Observed: {observed_text}",
                run_result,
            )

        return outputs

    def _copy_to_result_dir(self, stem_outputs: dict[str, Path], result_dir: Path) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for stem in STEMS:
            destination = result_dir / f"{stem}.wav"
            shutil.copy2(stem_outputs[stem], destination)
            normalized[stem] = destination.name
        return normalized


class FakeDemucsService:
    def separate(self, input_path: Path, output_dir: Path, result_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, str] = {}
        for stem in STEMS:
            stem_path = result_dir / f"{stem}.wav"
            self._write_silent_wav(stem_path)
            outputs[stem] = stem_path.name
        return outputs

    def _write_silent_wav(self, path: Path) -> None:
        sample_rate = 8000
        duration_seconds = 1
        frames = b"\x00\x00" * sample_rate * duration_seconds
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(frames)
