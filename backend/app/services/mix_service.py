from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path


STEM_ORDER = ("vocals", "drums", "bass", "other")
ALLOWED_STEMS = frozenset(STEM_ORDER)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MixResult:
    stems: list[str]
    filename: str
    path: Path
    cached: bool


class MixServiceError(RuntimeError):
    pass


class MixValidationError(ValueError):
    pass


class MixService:
    def normalize_stems(self, stems: list[str]) -> list[str]:
        if not stems:
            raise MixValidationError("请至少选择一个音轨")
        if len(stems) > len(STEM_ORDER):
            raise MixValidationError("最多只能选择四个音轨")

        seen: set[str] = set()
        for stem in stems:
            if stem not in ALLOWED_STEMS:
                raise MixValidationError("包含不支持的音轨")
            if stem in seen:
                raise MixValidationError("不能重复选择同一个音轨")
            seen.add(stem)

        return [stem for stem in STEM_ORDER if stem in seen]

    def create_mix(self, result_dir: Path, stems: list[str]) -> MixResult:
        normalized = self.normalize_stems(stems)
        sources = [result_dir / f"{stem}.wav" for stem in normalized]
        missing = [stem for stem, path in zip(normalized, sources) if not path.is_file()]
        if missing:
            raise MixServiceError("选中的源音轨文件不存在")

        mix_dir = result_dir / "mixes"
        mix_dir.mkdir(parents=True, exist_ok=True)
        filename = self.mix_filename(normalized)
        destination = mix_dir / filename
        if destination.is_file():
            return MixResult(stems=normalized, filename=filename, path=destination, cached=True)

        temp_path = destination.with_name(f".{destination.stem}.tmp.wav")
        if temp_path.exists():
            temp_path.unlink()

        command = self._build_command(sources, temp_path)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            if temp_path.exists():
                temp_path.unlink()
            logger.error(
                "FFmpeg mix failed with return code %s. stdout=%s stderr=%s",
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )
            raise MixServiceError("合并音轨生成失败，请确认 FFmpeg 可用后重试")

        if not temp_path.is_file():
            logger.error("FFmpeg mix reported success but did not create output: %s", temp_path)
            raise MixServiceError("合并音轨生成失败")

        temp_path.replace(destination)
        return MixResult(stems=normalized, filename=filename, path=destination, cached=False)

    def mix_filename(self, stems: list[str]) -> str:
        normalized = self.normalize_stems(stems)
        return f"mix-{'-'.join(normalized)}.wav"

    def _build_command(self, sources: list[Path], output_path: Path) -> list[str]:
        command = ["ffmpeg", "-y"]
        for source in sources:
            command.extend(["-i", str(source)])
        command.extend(
            [
                "-filter_complex",
                f"amix=inputs={len(sources)}:duration=longest:dropout_transition=0:normalize=0",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
        )
        return command
