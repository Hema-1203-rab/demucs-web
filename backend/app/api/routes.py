from __future__ import annotations

import importlib.util
import shutil
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from backend.app.config import Settings
from backend.app.schemas import CreateJobResponse, HealthResponse, JobResponse, JobStatus
from backend.app.services.file_service import FileService
from backend.app.services.job_manager import JobManager, JobRecord
from backend.app.services.separation_worker import SeparationWorker


def create_router(
    settings: Settings,
    file_service: FileService,
    job_manager: JobManager,
    worker: SeparationWorker,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            demucs_available=importlib.util.find_spec("demucs") is not None,
            ffmpeg_available=shutil.which("ffmpeg") is not None,
            device=_detect_device(),
        )

    @router.post("/jobs", response_model=CreateJobResponse, status_code=status.HTTP_202_ACCEPTED)
    async def create_job(file: UploadFile) -> CreateJobResponse:
        file_service.validate_extension(file.filename)
        job_id = str(uuid.uuid4())
        job_manager.create(job_id)
        try:
            input_path = await file_service.save_upload(file, job_id)
            dirs = file_service.job_dirs(job_id)
            worker.submit(
                job_id=job_id,
                input_path=input_path,
                output_dir=dirs["output"],
                result_dir=dirs["result"],
            )
        except HTTPException as exc:
            job_manager.mark_failed(job_id, str(exc.detail))
            raise
        except Exception:
            job_manager.mark_failed(job_id, "Could not queue separation job")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not queue separation job",
            )
        return CreateJobResponse(job_id=job_id, status=JobStatus.queued)

    @router.get("/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str) -> JobResponse:
        record = job_manager.get(job_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return _job_response(record)

    return router


def create_media_router(file_service: FileService) -> APIRouter:
    router = APIRouter()

    @router.get("/media/{job_id}/{stem}.wav")
    def get_media(job_id: str, stem: str) -> FileResponse:
        path = file_service.media_file(job_id, stem)
        return FileResponse(path, media_type="audio/wav", filename=f"{stem}.wav")

    return router


def _job_response(record: JobRecord) -> JobResponse:
    return JobResponse(
        job_id=record.job_id,
        status=record.status,
        message=record.message,
        outputs=record.outputs,
        error=record.error,
    )


def _detect_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"
