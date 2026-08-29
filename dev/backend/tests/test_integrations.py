import json

import fal_client
import httpx
import pytest
from openai import AsyncOpenAI

from app.core.config import Settings
from app.integrations.base import ProviderNotConfigured
from app.integrations.cala import create_cala_adapter
from app.integrations.fal import create_fal_client
from app.integrations.openai import create_openai_client


def test_factories_reject_missing_credentials(settings: Settings) -> None:
    with pytest.raises(ProviderNotConfigured, match="OpenAI"):
        create_openai_client(settings)
    with pytest.raises(ProviderNotConfigured, match="Cala"):
        create_cala_adapter(settings)
    with pytest.raises(ProviderNotConfigured, match="fal"):
        create_fal_client(settings)


@pytest.mark.asyncio
async def test_openai_factory_is_lazy_and_does_not_make_a_request() -> None:
    settings = Settings(_env_file=None, openai_api_key="test-openai-key")

    client = create_openai_client(settings)

    assert isinstance(client, AsyncOpenAI)
    await client.close()


def test_fal_factory_is_lazy_and_does_not_make_a_request() -> None:
    settings = Settings(_env_file=None, fal_key="test-fal-key")

    client = create_fal_client(settings)

    assert isinstance(client, fal_client.AsyncClient)
    assert client.key == "test-fal-key"


@pytest.mark.asyncio
async def test_cala_adapter_sends_auth_and_validates_provider_dtos() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "results": [{"name": "Sagrada Familia", "city": "Barcelona"}],
                    "entities": [
                        {
                            "id": "entity-1",
                            "name": "Sagrada Familia",
                            "entity_type": "Facility",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "content": "A sourced answer",
                "context": [{"id": "source-1", "content": "Source text"}],
                "explainability": [{"content": "Supported claim", "references": ["source-1"]}],
                "entities": [],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        cala_api_key="test-cala-key",
        cala_base_url="https://api.cala.ai/",
    )
    adapter = create_cala_adapter(settings, http_client=http_client)

    query_response = await adapter.knowledge_query("places in Barcelona")
    search_response = await adapter.knowledge_search("Tell me about Sagrada Familia")

    assert query_response.results[0]["name"] == "Sagrada Familia"
    assert query_response.entities is not None
    assert query_response.entities[0].entity_type == "Facility"
    assert search_response.context[0].id == "source-1"
    assert len(requests) == 2
    assert all(request.headers["X-API-KEY"] == "test-cala-key" for request in requests)
    assert requests[0].url.path == "/v1/knowledge/query"
    assert json.loads(requests[0].content)["input"] == "places in Barcelona"

    await http_client.aclose()
