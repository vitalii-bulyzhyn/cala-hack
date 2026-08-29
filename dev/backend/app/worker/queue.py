import asyncio
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis


class GenerationQueue(Protocol):
    async def enqueue(self, run_id: UUID) -> None: ...


class RedisGenerationQueue:
    def __init__(
        self,
        redis_url: str,
        *,
        queue_key: str,
        heartbeat_key: str,
        connect_timeout_seconds: float = 2.0,
        operation_timeout_seconds: float = 5.0,
    ) -> None:
        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=connect_timeout_seconds,
            socket_timeout=None,
        )
        self._queue_key = queue_key
        self._heartbeat_key = heartbeat_key
        self._operation_timeout_seconds = operation_timeout_seconds

    async def enqueue(self, run_id: UUID) -> None:
        async with asyncio.timeout(self._operation_timeout_seconds):
            await self._client.rpush(self._queue_key, str(run_id))

    async def dequeue(self, timeout_seconds: int) -> str | None:
        async with asyncio.timeout(timeout_seconds + self._operation_timeout_seconds):
            item = await self._client.blpop(self._queue_key, timeout=timeout_seconds)
        return None if item is None else item[1]

    async def publish_heartbeat(self, worker_id: str, ttl_seconds: int) -> None:
        async with asyncio.timeout(self._operation_timeout_seconds):
            await self._client.set(self._heartbeat_key, worker_id, ex=ttl_seconds)

    async def read_heartbeat(self) -> str | None:
        async with asyncio.timeout(self._operation_timeout_seconds):
            return await self._client.get(self._heartbeat_key)

    async def close(self) -> None:
        await self._client.aclose()
