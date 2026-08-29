from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas import LivenessResponse, ReadinessResponse
from app.core.dependencies import get_readiness_checker
from app.services.readiness import ReadinessChecker

router = APIRouter()


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(
    response: Response,
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
) -> ReadinessResponse:
    report = await checker.check()
    if report.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
