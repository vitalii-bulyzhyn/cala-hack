import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.api.schemas import DependencyCheck, ReadinessResponse
from app.core.config import Settings

logger = logging.getLogger(__name__)
Probe = Callable[[], Awaitable[None]]


async def ping_postgres(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def ping_redis(redis_url: str) -> None:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()


class ReadinessChecker:
    def __init__(
        self,
        settings: Settings,
        *,
        postgres_probe: Probe | None = None,
        redis_probe: Probe | None = None,
    ) -> None:
        self._timeout_seconds = settings.readiness_timeout_seconds
        self._postgres_probe = postgres_probe or (lambda: ping_postgres(settings.database_url))
        self._redis_probe = redis_probe or (lambda: ping_redis(settings.redis_url))

    async def _run_probe(self, name: str, probe: Probe, *, required: bool) -> DependencyCheck:
        started_at = perf_counter()
        try:
            await asyncio.wait_for(probe(), timeout=self._timeout_seconds)
            result = "ok"
        except Exception as exc:
            logger.warning("Readiness check failed for %s (%s)", name, type(exc).__name__)
            result = "error"

        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        return DependencyCheck(status=result, required=required, latency_ms=latency_ms)

    async def check(self) -> ReadinessResponse:
        postgres, redis = await asyncio.gather(
            self._run_probe("postgres", self._postgres_probe, required=True),
            self._run_probe("redis", self._redis_probe, required=False),
        )
        checks = {"postgres": postgres, "redis": redis}
        overall_status = (
            "ready"
            if all(check.status == "ok" for check in checks.values() if check.required)
            else "not_ready"
        )
        return ReadinessResponse(status=overall_status, checks=checks)
