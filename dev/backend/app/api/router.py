from fastapi import APIRouter

from app.api.routes import health, itineraries, preferences, providers

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
api_router.include_router(itineraries.router, prefix="/itineraries", tags=["itineraries"])
api_router.include_router(
    preferences.router,
    prefix="/itineraries",
    tags=["preference learning"],
)
