import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import ClassVar
from urllib.parse import quote, urljoin, urlsplit
from uuid import UUID, uuid4

import httpx


@dataclass(frozen=True)
class StoredMedia:
    storage_key: str
    public_url: str
    content_type: str
    byte_count: int


@dataclass(eq=False)
class MediaStorageError(Exception):
    code: str
    message: str
    retryable: bool


class LocalMediaStore:
    """Copy trusted provider images into app-owned local persistent storage."""

    _EXTENSIONS: ClassVar[dict[str, str]] = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }
    _REDIRECT_STATUSES: ClassVar[set[int]] = {301, 302, 303, 307, 308}
    _MAX_REDIRECTS: ClassVar[int] = 5

    def __init__(
        self,
        *,
        root: Path,
        public_url_path: str,
        timeout_seconds: float,
        max_bytes: int,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._root = root.resolve()
        self._public_url_path = public_url_path.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._owns_http_client = http_client is None
        self._resolve_dns = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )

    async def copy_from_provider(
        self,
        *,
        source_url: str,
        itinerary_id: UUID,
        expected_content_type: str | None,
    ) -> StoredMedia:
        try:
            data, response_content_type = await self._download(source_url)
        except MediaStorageError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise MediaStorageError(
                code="IMAGE_DOWNLOAD_UNAVAILABLE",
                message="The generated journal image could not be downloaded yet.",
                retryable=True,
            ) from exc
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
            raise MediaStorageError(
                code="IMAGE_DOWNLOAD_UNAVAILABLE",
                message="The generated journal image could not be downloaded.",
                retryable=retryable,
            ) from exc

        detected_content_type = self._detect_content_type(data)
        declared_content_type = (
            response_content_type if response_content_type in self._EXTENSIONS else None
        )
        expected_type = expected_content_type if expected_content_type in self._EXTENSIONS else None
        if (
            detected_content_type is None
            or (
                declared_content_type is not None and declared_content_type != detected_content_type
            )
            or (
                declared_content_type is None
                and expected_type is not None
                and expected_type != detected_content_type
            )
        ):
            raise MediaStorageError(
                code="IMAGE_DOWNLOAD_INVALID_CONTENT",
                message="The generated journal image had an unsupported format.",
                retryable=False,
            )

        content_type = detected_content_type
        extension = self._EXTENSIONS[content_type]
        storage_key = f"{itinerary_id}/journal{extension}"
        destination = (self._root / storage_key).resolve()
        if not destination.is_relative_to(self._root):
            raise MediaStorageError(
                code="IMAGE_STORAGE_INVALID_PATH",
                message="The generated journal image could not be stored.",
                retryable=False,
            )
        try:
            await asyncio.to_thread(self._write_atomically, destination, bytes(data))
        except OSError as exc:
            raise MediaStorageError(
                code="IMAGE_STORAGE_UNAVAILABLE",
                message="The generated journal image could not be stored.",
                retryable=True,
            ) from exc
        return StoredMedia(
            storage_key=storage_key,
            public_url=f"{self._public_url_path}/{quote(storage_key, safe='/')}",
            content_type=content_type,
            byte_count=len(data),
        )

    async def _download(self, source_url: str) -> tuple[bytes, str]:
        current_url = source_url
        for redirect_count in range(self._MAX_REDIRECTS + 1):
            await self._validate_remote_url(current_url)
            async with self._http_client.stream(
                "GET",
                current_url,
                follow_redirects=False,
            ) as response:
                if response.status_code in self._REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if location is None or redirect_count == self._MAX_REDIRECTS:
                        raise MediaStorageError(
                            code="IMAGE_DOWNLOAD_INVALID_URL",
                            message="The generated journal image URL was invalid.",
                            retryable=False,
                        )
                    current_url = urljoin(str(response.url), location)
                    continue

                response.raise_for_status()
                await self._validate_remote_url(str(response.url))
                declared_size = response.headers.get("content-length")
                try:
                    parsed_size = int(declared_size) if declared_size is not None else None
                except ValueError:
                    parsed_size = None
                if parsed_size is not None and parsed_size > self._max_bytes:
                    raise MediaStorageError(
                        code="IMAGE_DOWNLOAD_TOO_LARGE",
                        message="The generated journal image was too large to store.",
                        retryable=False,
                    )
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self._max_bytes:
                        raise MediaStorageError(
                            code="IMAGE_DOWNLOAD_TOO_LARGE",
                            message="The generated journal image was too large to store.",
                            retryable=False,
                        )
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                return bytes(data), content_type.lower().strip()

        raise MediaStorageError(
            code="IMAGE_DOWNLOAD_INVALID_URL",
            message="The generated journal image URL was invalid.",
            retryable=False,
        )

    async def _validate_remote_url(self, value: str) -> None:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except (UnicodeError, ValueError) as exc:
            raise self._invalid_url_error() from exc
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise self._invalid_url_error()

        hostname = hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            raise self._invalid_url_error()

        try:
            literal_address = ipaddress.ip_address(hostname)
        except ValueError:
            literal_address = None
        if literal_address is not None:
            if not literal_address.is_global:
                raise self._invalid_url_error()
            return

        if not self._resolve_dns:
            return
        try:
            async with asyncio.timeout(self._timeout_seconds):
                addresses = await asyncio.to_thread(self._resolve_addresses, hostname)
        except (TimeoutError, OSError) as exc:
            raise MediaStorageError(
                code="IMAGE_DOWNLOAD_UNAVAILABLE",
                message="The generated journal image could not be downloaded yet.",
                retryable=True,
            ) from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise self._invalid_url_error()

    @staticmethod
    def _resolve_addresses(hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        return {ipaddress.ip_address(answer[4][0]) for answer in answers}

    @staticmethod
    def _invalid_url_error() -> MediaStorageError:
        return MediaStorageError(
            code="IMAGE_DOWNLOAD_INVALID_URL",
            message="The generated journal image URL was invalid.",
            retryable=False,
        )

    @staticmethod
    def _detect_content_type(data: bytes | bytearray) -> str | None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        if (
            len(data) >= 12
            and data[4:8] == b"ftyp"
            and (data[8:12] in {b"avif", b"avis"} or b"avif" in data[12:32])
        ):
            return "image/avif"
        return None

    @staticmethod
    def _write_atomically(destination: Path, data: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "LocalMediaStore":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
