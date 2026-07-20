from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import create_media_router, create_router
from backend.app.config import Settings, settings
from backend.app.services.demucs_service import DemucsService
from backend.app.services.file_service import FileService
from backend.app.services.job_manager import JobManager
from backend.app.services.separation_worker import SeparationService, SeparationWorker


def create_app(
    app_settings: Settings = settings,
    separation_service: SeparationService | None = None,
) -> FastAPI:
    app = FastAPI(title="Demucs Web MVP")
    file_service = FileService(app_settings)
    job_manager = JobManager()
    worker = SeparationWorker(job_manager, separation_service or DemucsService())
    app.include_router(create_router(app_settings, file_service, job_manager, worker))
    app.include_router(create_media_router(file_service))
    frontend_dir = Path("frontend")
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    app.state.settings = app_settings
    app.state.job_manager = job_manager
    app.state.worker = worker

    @app.on_event("shutdown")
    def shutdown_worker() -> None:
        worker.shutdown()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    return app


app = create_app()
