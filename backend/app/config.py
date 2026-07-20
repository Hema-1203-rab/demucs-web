from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    jobs_root: Path = Path(os.getenv("DEMUCS_JOBS_ROOT", "data/jobs"))
    max_upload_size_bytes: int = int(os.getenv("DEMUCS_MAX_UPLOAD_SIZE_BYTES", 100 * 1024 * 1024))
    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset({".mp3", ".wav", ".flac"})
    )


settings = Settings()
