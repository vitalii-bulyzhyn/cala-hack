import asyncio
import logging
import os
import signal
import socket
from contextlib import suppress
from time import monotonic
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.repositories.generation_runs import GenerationRunStore
from app.services.provider_content_generation import create_content_generation_pipeline
from app.worker.processor import GenerationProcessor
from app.worker.queue import RedisGenerationQueue

logger = logging.getLogger(__name__)


async def run_worker(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)
    worker_id = f"{resolved.worker_name}:{socket.gethostname()}:{os.getpid()}"
    database = Database(resolved.database_url)
    queue = RedisGenerationQueue(
        resolved.redis_url,
        queue_key=resolved.generation_queue_key,
        heartbeat_key=f"{resolved.worker_heartbeat_key}:{socket.gethostname()}",
        connect_timeout_seconds=resolved.redis_connect_timeout_seconds,
        operation_timeout_seconds=resolved.redis_operation_timeout_seconds,
    )
    store = GenerationRunStore(
        database.session_factory,
        lease_seconds=resolved.worker_lease_seconds,
    )
    pipeline = create_content_generation_pipeline(resolved)
    processor = GenerationProcessor(
        store,
        pipeline,
        worker_id=worker_id,
        heartbeat_seconds=resolved.worker_heartbeat_seconds,
        retry_base_seconds=resolved.generation_retry_base_seconds,
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signal_name, stop_event.set)

    heartbeat_task = asyncio.create_task(
        _publish_process_heartbeat(queue, resolved, worker_id, stop_event)
    )
    logger.info("Generation worker %s started", worker_id)
    next_reconcile = 0.0
    try:
        while not stop_event.is_set():
            try:
                if monotonic() >= next_reconcile:
                    await store.terminalize_exhausted()
                    await _process_with_shutdown(processor, None, stop_event)
                    next_reconcile = monotonic() + resolved.worker_reconcile_seconds
                    if stop_event.is_set():
                        break

                raw_run_id = await _dequeue_safely(queue, resolved.worker_poll_seconds)
                run_id = _parse_run_id(raw_run_id)
                if run_id is not None:
                    await _process_with_shutdown(processor, run_id, stop_event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Generation worker loop failed; retrying (%s)",
                    type(exc).__name__,
                )
                await asyncio.sleep(resolved.worker_poll_seconds)
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await queue.close()
        close_pipeline = getattr(pipeline, "aclose", None)
        if close_pipeline is not None:
            await close_pipeline()
        await database.close()
        logger.info("Generation worker %s stopped", worker_id)


async def _dequeue_safely(queue: RedisGenerationQueue, timeout_seconds: int) -> str | None:
    try:
        return await queue.dequeue(timeout_seconds)
    except Exception:
        logger.warning("Redis wake-up queue is unavailable; using Postgres reconciliation")
        await asyncio.sleep(timeout_seconds)
        return None


def _parse_run_id(raw_run_id: str | None) -> UUID | None:
    if raw_run_id is None:
        return None
    try:
        return UUID(raw_run_id)
    except ValueError:
        logger.warning("Ignoring invalid generation wake-up value")
        return None


async def _process_with_shutdown(
    processor: GenerationProcessor,
    run_id: UUID | None,
    stop_event: asyncio.Event,
) -> bool:
    processing = asyncio.create_task(processor.process_once(run_id))
    stopping = asyncio.create_task(stop_event.wait())
    done, _ = await asyncio.wait({processing, stopping}, return_when=asyncio.FIRST_COMPLETED)
    if processing in done:
        stopping.cancel()
        with suppress(asyncio.CancelledError):
            await stopping
        return await processing

    try:
        return await asyncio.wait_for(asyncio.shield(processing), timeout=25)
    except TimeoutError:
        processing.cancel()
        with suppress(asyncio.CancelledError):
            await processing
        return False


async def _publish_process_heartbeat(
    queue: RedisGenerationQueue,
    settings: Settings,
    worker_id: str,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            await queue.publish_heartbeat(worker_id, settings.worker_heartbeat_ttl_seconds)
        except Exception:
            logger.warning("Could not publish worker heartbeat")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.worker_heartbeat_seconds)
        except TimeoutError:
            pass
