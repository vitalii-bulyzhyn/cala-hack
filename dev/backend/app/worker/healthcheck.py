import asyncio
import socket

from app.core.config import get_settings
from app.services.readiness import ping_postgres
from app.worker.queue import RedisGenerationQueue


async def check_worker() -> None:
    settings = get_settings()
    queue = RedisGenerationQueue(
        settings.redis_url,
        queue_key=settings.generation_queue_key,
        heartbeat_key=f"{settings.worker_heartbeat_key}:{socket.gethostname()}",
        connect_timeout_seconds=settings.redis_connect_timeout_seconds,
        operation_timeout_seconds=settings.redis_operation_timeout_seconds,
    )
    try:
        heartbeat, _ = await asyncio.gather(
            queue.read_heartbeat(),
            ping_postgres(settings.database_url),
        )
        expected_prefix = f"{settings.worker_name}:{socket.gethostname()}:"
        if heartbeat is None or not heartbeat.startswith(expected_prefix):
            raise SystemExit(1)
    finally:
        await queue.close()


if __name__ == "__main__":
    asyncio.run(check_worker())
