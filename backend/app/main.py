from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    cases,
    exports,
    health,
    inference_jobs,
    modalities,
    revisions,
    segmentations,
)
from app.core.config import settings
from app.core.errors import ApiError
from app.core.release import RELEASE_VERSION
from app.db.session import get_engine, new_session, run_migrations
from app.services.inference.worker import recover_interrupted_jobs, run_worker_loop


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations(str(get_engine().url))
    with new_session() as session:
        recover_interrupted_jobs(session)
    worker_thread = None
    stop_event = None
    if _app.state.start_inference_worker:
        stop_event = Event()
        worker_thread = Thread(
            target=run_worker_loop,
            args=(stop_event,),
            name="neuroannotate-inference-worker",
            daemon=True,
        )
        _app.state.inference_worker_thread = worker_thread
        worker_thread.start()
    try:
        yield
    finally:
        if stop_event is not None and worker_thread is not None:
            stop_event.set()
            worker_thread.join()


def create_app(*, start_worker: bool = True) -> FastAPI:
    app = FastAPI(title="NeuroAnnotate API", version=RELEASE_VERSION, lifespan=lifespan)
    app.state.start_inference_worker = start_worker
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    for router in (
        health.router,
        cases.router,
        modalities.router,
        segmentations.router,
        inference_jobs.router,
        revisions.router,
        exports.router,
    ):
        app.include_router(router)
    return app


app = create_app()
