import base64
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.integrations.media_storage import LocalMediaStore, MediaStorageError

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        for chunk in self._chunks:
            yield chunk


def _store(
    tmp_path: Path,
    handler: httpx.AsyncBaseTransport,
    *,
    max_bytes: int = 1_000,
) -> tuple[LocalMediaStore, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)
    return (
        LocalMediaStore(
            root=tmp_path,
            timeout_seconds=1,
            max_bytes=max_bytes,
            max_pixels=1_000_000,
            http_client=client,
        ),
        client,
    )


def _assert_storage_empty(path: Path) -> None:
    assert list(path.rglob("*")) == []


@pytest.mark.asyncio
async def test_copies_https_provider_image_to_confined_owned_path(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "image/png; charset=binary"},
            content=PNG_BYTES,
        )

    store, client = _store(tmp_path, httpx.MockTransport(handler))
    image_id = uuid4()

    stored = await store.copy_from_provider(
        source_url="https://fal.example/generated/image",
        image_id=image_id,
        expected_content_type="image/jpeg",
    )

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert stored.storage_key == f"{image_id}.png"
    assert stored.public_url == f"/{image_id}.png"
    assert stored.content_type == "image/png"
    assert stored.byte_count > 8
    assert stored.width == stored.height == 1
    assert (tmp_path / stored.storage_key).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert not list(tmp_path.glob("*.tmp"))

    await store.aclose()
    assert client.is_closed is False
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_url",
    [
        "http://fal.example/image.png",
        "ftp://fal.example/image.png",
        "https:///image.png",
        "https://user@fal.example/image.png",
        "https://user:password@fal.example/image.png",
    ],
)
async def test_rejects_unsafe_source_url_before_network_access(
    tmp_path: Path,
    source_url: str,
) -> None:
    async def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    store, client = _store(tmp_path, httpx.MockTransport(unexpected_request))

    with pytest.raises(MediaStorageError) as raised:
        await store.copy_from_provider(
            source_url=source_url,
            image_id=uuid4(),
            expected_content_type="image/png",
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_INVALID_URL"
    assert raised.value.retryable is False
    _assert_storage_empty(tmp_path)
    await client.aclose()


@pytest.mark.asyncio
async def test_rejects_declared_content_length_over_limit(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "image/png", "content-length": "999"},
            content=b"",
        )

    store, client = _store(tmp_path, httpx.MockTransport(handler), max_bytes=32)

    with pytest.raises(MediaStorageError) as raised:
        await store.copy_from_provider(
            source_url="https://fal.example/oversized.png",
            image_id=uuid4(),
            expected_content_type="image/png",
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_TOO_LARGE"
    assert raised.value.retryable is False
    _assert_storage_empty(tmp_path)
    await client.aclose()


@pytest.mark.asyncio
async def test_rejects_chunked_body_when_stream_crosses_limit(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "image/png"},
            stream=ChunkedStream(b"1234", b"5678", b"9"),
        )

    store, client = _store(tmp_path, httpx.MockTransport(handler), max_bytes=8)

    with pytest.raises(MediaStorageError) as raised:
        await store.copy_from_provider(
            source_url="https://fal.example/chunked.png",
            image_id=uuid4(),
            expected_content_type="image/png",
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_TOO_LARGE"
    _assert_storage_empty(tmp_path)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "content_type", "expected_content_type"),
    [
        (b"not-an-image", "text/html", None),
        (b"", "image/png", "image/png"),
    ],
)
async def test_rejects_empty_or_unsupported_image_content(
    tmp_path: Path,
    content: bytes,
    content_type: str,
    expected_content_type: str | None,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": content_type},
            content=content,
        )

    store, client = _store(tmp_path, httpx.MockTransport(handler))

    with pytest.raises(MediaStorageError) as raised:
        await store.copy_from_provider(
            source_url="https://fal.example/invalid",
            image_id=uuid4(),
            expected_content_type=expected_content_type,
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_INVALID_CONTENT"
    assert raised.value.retryable is False
    _assert_storage_empty(tmp_path)
    await client.aclose()


@pytest.mark.asyncio
async def test_uses_expected_supported_type_when_response_omits_type(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=PNG_BYTES)

    store, client = _store(tmp_path, httpx.MockTransport(handler))
    image_id = uuid4()

    stored = await store.copy_from_provider(
        source_url="https://fal.example/untyped",
        image_id=image_id,
        expected_content_type="image/png",
    )

    assert stored.content_type == "image/png"
    assert stored.storage_key == f"{image_id}.png"
    assert (tmp_path / stored.storage_key).read_bytes() == PNG_BYTES
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_retryable"),
    [(404, False), (429, True), (503, True)],
)
async def test_maps_http_download_failures(
    tmp_path: Path,
    status_code: int,
    expected_retryable: bool,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    store, client = _store(tmp_path, httpx.MockTransport(handler))

    with pytest.raises(MediaStorageError) as raised:
        await store.copy_from_provider(
            source_url="https://fal.example/unavailable.png",
            image_id=uuid4(),
            expected_content_type="image/png",
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_UNAVAILABLE"
    assert raised.value.retryable is expected_retryable
    _assert_storage_empty(tmp_path)
    await client.aclose()


@pytest.mark.asyncio
async def test_maps_network_timeout_as_retryable(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    store, client = _store(tmp_path, httpx.MockTransport(handler))

    with pytest.raises(MediaStorageError) as raised:
        await store.copy_from_provider(
            source_url="https://fal.example/slow.png",
            image_id=uuid4(),
            expected_content_type="image/png",
        )

    assert raised.value.code == "IMAGE_DOWNLOAD_UNAVAILABLE"
    assert raised.value.retryable is True
    _assert_storage_empty(tmp_path)
    await client.aclose()


@pytest.mark.asyncio
async def test_rejects_loopback_provider_target(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "image/png"},
            content=PNG_BYTES,
        )

    store, client = _store(tmp_path, httpx.MockTransport(handler))

    try:
        with pytest.raises(MediaStorageError) as raised:
            await store.copy_from_provider(
                source_url="https://127.0.0.1/private.png",
                image_id=uuid4(),
                expected_content_type="image/png",
            )

        assert raised.value.code == "IMAGE_DOWNLOAD_INVALID_URL"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rejects_private_target_on_redirect_before_following_it(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "fal.example":
            return httpx.Response(
                302,
                request=request,
                headers={"location": "https://10.0.0.8/private.png"},
            )
        raise AssertionError(f"private redirect was followed: {request.url}")

    store, client = _store(tmp_path, httpx.MockTransport(handler))

    try:
        with pytest.raises(MediaStorageError) as raised:
            await store.copy_from_provider(
                source_url="https://fal.example/redirect.png",
                image_id=uuid4(),
                expected_content_type="image/png",
            )

        assert raised.value.code == "IMAGE_DOWNLOAD_INVALID_URL"
        assert raised.value.retryable is False
        assert [str(request.url) for request in requests] == ["https://fal.example/redirect.png"]
        _assert_storage_empty(tmp_path)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_malformed_url_is_mapped_to_safe_storage_error(tmp_path: Path) -> None:
    async def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    store, client = _store(tmp_path, httpx.MockTransport(unexpected_request))

    try:
        with pytest.raises(MediaStorageError) as raised:
            await store.copy_from_provider(
                source_url="https://[not-a-valid-ipv6/image.png",
                image_id=uuid4(),
                expected_content_type="image/png",
            )

        assert raised.value.code == "IMAGE_DOWNLOAD_INVALID_URL"
        assert raised.value.retryable is False
        _assert_storage_empty(tmp_path)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "declared_type", "expected_type"),
    [
        (PNG_BYTES, "image/jpeg", "image/jpeg"),
        (b"\xff\xd8\xfftest-jpeg", "image/png", "image/png"),
        (b"not-really-a-png", "image/png", "image/png"),
        (PNG_BYTES, "application/octet-stream", "image/jpeg"),
    ],
)
async def test_rejects_mime_and_byte_signature_mismatch(
    tmp_path: Path,
    content: bytes,
    declared_type: str,
    expected_type: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": declared_type},
            content=content,
        )

    store, client = _store(tmp_path, httpx.MockTransport(handler))

    try:
        with pytest.raises(MediaStorageError) as raised:
            await store.copy_from_provider(
                source_url="https://fal.example/mismatched-image",
                image_id=uuid4(),
                expected_content_type=expected_type,
            )

        assert raised.value.code == "IMAGE_DOWNLOAD_INVALID_CONTENT"
        assert raised.value.retryable is False
        _assert_storage_empty(tmp_path)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_maps_filesystem_oserror_to_retryable_storage_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "image/png"},
            content=PNG_BYTES,
        )

    def fail_write(destination: Path, data: bytes) -> None:
        del destination, data
        raise OSError("disk intentionally unavailable")

    monkeypatch.setattr(LocalMediaStore, "_write_atomically", staticmethod(fail_write))
    store, client = _store(tmp_path, httpx.MockTransport(handler))

    try:
        with pytest.raises(MediaStorageError) as raised:
            await store.copy_from_provider(
                source_url="https://fal.example/generated.png",
                image_id=uuid4(),
                expected_content_type="image/png",
            )

        assert raised.value.code == "IMAGE_STORAGE_UNAVAILABLE"
        assert raised.value.retryable is True
        assert "disk intentionally unavailable" not in raised.value.message
        _assert_storage_empty(tmp_path)
    finally:
        await client.aclose()
