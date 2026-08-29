from openai import AsyncOpenAI

from app.core.config import Settings
from app.integrations.base import require_secret


def create_openai_client(settings: Settings) -> AsyncOpenAI:
    """Create an OpenAI client only when application code needs one."""
    api_key = require_secret(settings.openai_api_key, "OpenAI")
    return AsyncOpenAI(api_key=api_key, timeout=settings.openai_timeout_seconds)
