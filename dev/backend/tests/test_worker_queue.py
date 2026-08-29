import asyncio
from uuid import uuid4

import pytest

from app.worker.queue import RedisGenerationQueue


class BlockingRedis:
    async def rpush(self, *_: object) -> None:
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_notification_is_bounded_when_redis_never_responds() -> None:
    queue = RedisGenerationQueue(
        "redis://localhost:6379/15",
        queue_key="test:generation",
        heartbeat_key="test:heartbeat",
        operation_timeout_seconds=0.01,
    )
    queue._client = BlockingRedis()  # type: ignore[assignment]

    with pytest.raises(TimeoutError):
        await queue.enqueue(uuid4())

    await queue.close()
