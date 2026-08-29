import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.itinerary_schemas import ErrorDetail, ErrorResponse
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import Database
from app.services.activity_recommendations import create_activity_recommendation_algorithm
from app.services.preference_learning import PreferenceLearningAlgorithm
from app.services.readiness import ReadinessChecker
from app.worker.queue import GenerationQueue, RedisGenerationQueue

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    readiness_checker: ReadinessChecker | None = None,
    database: Database | None = None,
    generation_queue: GenerationQueue | None = None,
    preference_learning_algorithm: PreferenceLearningAlgorithm | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    resolved_database = database or Database(resolved_settings.database_url)
    resolved_queue = generation_queue or RedisGenerationQueue(
        resolved_settings.redis_url,
        queue_key=resolved_settings.generation_queue_key,
        heartbeat_key=resolved_settings.worker_heartbeat_key,
        connect_timeout_seconds=resolved_settings.redis_connect_timeout_seconds,
        operation_timeout_seconds=resolved_settings.redis_operation_timeout_seconds,
    )
    resolved_preference_algorithm = (
        preference_learning_algorithm or create_activity_recommendation_algorithm(resolved_settings)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_settings.media_storage_path.mkdir(parents=True, exist_ok=True)
        yield
        if generation_queue is None:
            await resolved_queue.close()  # type: ignore[attr-defined]
        if preference_learning_algorithm is None:
            await resolved_preference_algorithm.aclose()  # type: ignore[attr-defined]
        if database is None:
            await resolved_database.close()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.4.0",
        openapi_url=f"{resolved_settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.readiness_checker = readiness_checker or ReadinessChecker(resolved_settings)
    application.state.database = resolved_database
    application.state.generation_queue = resolved_queue
    application.state.preference_learning_algorithm = resolved_preference_algorithm
    application.mount(
        resolved_settings.media_url_path,
        StaticFiles(directory=resolved_settings.media_storage_path, check_dir=False),
        name="generated-media",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def add_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled API error (%s), request_id=%s",
            type(exc).__name__,
            request.state.request_id,
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="The service encountered an unexpected error.",
                retryable=True,
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))

    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()
