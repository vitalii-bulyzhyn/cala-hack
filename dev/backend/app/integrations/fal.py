import fal_client

from app.core.config import Settings
from app.integrations.base import require_secret


def create_fal_client(settings: Settings) -> fal_client.AsyncClient:
    """Create a fal client without performing an inference request."""
    api_key = require_secret(settings.fal_key, "fal")
    return fal_client.AsyncClient(
        key=api_key,
        default_timeout=settings.fal_result_timeout_seconds,
    )
