import asyncio

from app.worker.runtime import run_worker

if __name__ == "__main__":
    asyncio.run(run_worker())
