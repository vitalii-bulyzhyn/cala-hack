from types import TracebackType

import httpx

from app.core.config import Settings
from app.integrations.base import ProviderRequestError, require_secret
from app.integrations.dto.cala import (
    CalaKnowledgeQueryResponse,
    CalaKnowledgeSearchResponse,
)


class CalaAdapter:
    """Small async REST boundary around Cala's beta API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-API-KEY": self._api_key,
        }

    async def knowledge_query(
        self,
        query: str,
        *,
        return_entities: bool = True,
    ) -> CalaKnowledgeQueryResponse:
        response = await self._post(
            "/v1/knowledge/query",
            {"input": query, "return_entities": return_entities},
        )
        return CalaKnowledgeQueryResponse.model_validate(response.json())

    async def knowledge_search(
        self,
        query: str,
        *,
        explainability: bool = True,
        return_entities: bool = True,
    ) -> CalaKnowledgeSearchResponse:
        response = await self._post(
            "/v1/knowledge/search",
            {
                "input": query,
                "explainability": explainability,
                "return_entities": return_entities,
            },
        )
        return CalaKnowledgeSearchResponse.model_validate(response.json())

    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        try:
            response = await self._http_client.post(
                f"{self._base_url}{path}",
                headers=self._headers,
                json=payload,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderRequestError(
                provider="cala",
                code="CALA_UNAVAILABLE",
                message="Place research is temporarily unavailable.",
                retryable=True,
            ) from exc
        if response.is_success:
            return response
        retryable = response.status_code == 429 or response.status_code >= 500
        raise ProviderRequestError(
            provider="cala",
            code=("CALA_RATE_LIMITED" if response.status_code == 429 else "CALA_REQUEST_FAILED"),
            message=(
                "Place research is temporarily busy."
                if retryable
                else "Place research could not process this request."
            ),
            retryable=retryable,
            status_code=response.status_code,
        )

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "CalaAdapter":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def create_cala_adapter(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> CalaAdapter:
    api_key = require_secret(settings.cala_api_key, "Cala")
    return CalaAdapter(
        api_key=api_key,
        base_url=settings.cala_base_url,
        timeout_seconds=settings.cala_timeout_seconds,
        http_client=http_client,
    )
