from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.schemas import ProviderStatus, ProviderStatusResponse
from app.core.config import Settings
from app.core.dependencies import get_app_settings

router = APIRouter()


@router.get("/status", response_model=ProviderStatusResponse)
async def provider_status(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ProviderStatusResponse:
    return ProviderStatusResponse(
        providers={
            "openai": ProviderStatus(
                configured=settings.openai_configured,
                model=settings.openai_model,
            ),
            "cala": ProviderStatus(
                configured=settings.cala_configured,
                base_url=settings.cala_base_url,
            ),
            "fal": ProviderStatus(
                configured=settings.fal_configured,
                model=settings.fal_image_model,
            ),
        }
    )
