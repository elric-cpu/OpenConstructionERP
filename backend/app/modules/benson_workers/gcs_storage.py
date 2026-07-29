"""Google Cloud Storage adapter for the Benson edition."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.storage import StorageBackend, _normalise_key

if TYPE_CHECKING:
    from app.config import Settings


def _is_not_found(exc: BaseException) -> bool:
    return getattr(exc, "code", None) == 404 or "404" in str(exc) or "NotFound" in type(exc).__name__


class GoogleCloudStorageBackend(StorageBackend):
    """Private GCS backend using Application Default Credentials."""

    def __init__(self, *, bucket: str, client: Any) -> None:
        if not bucket:
            raise ValueError("GCS storage requires OE_GCS_BUCKET")
        self._bucket_name = bucket
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> GoogleCloudStorageBackend:
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise ImportError(
                "GoogleCloudStorageBackend requires google-cloud-storage. "
                "Install it with: pip install 'openconstructionerp[gcs]'"
            ) from exc
        return cls(
            bucket=settings.gcs_bucket,
            client=storage.Client(project=settings.gcs_project or None),
        )

    def _bucket(self) -> Any:
        return self._client.bucket(self._bucket_name)

    def _blob(self, key: str) -> Any:
        return self._bucket().blob(_normalise_key(key))

    async def put(self, key: str, content: bytes) -> None:
        await asyncio.to_thread(self._blob(key).upload_from_string, content)

    async def put_stream(self, key: str, src_path: Path) -> None:
        await asyncio.to_thread(self._blob(key).upload_from_filename, str(src_path))

    async def get(self, key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._blob(key).download_as_bytes)
        except Exception as exc:  # noqa: BLE001 - provider hierarchy is optional
            if _is_not_found(exc):
                raise FileNotFoundError(f"No blob at key: {key}") from exc
            raise

    async def exists(self, key: str) -> bool:
        return bool(await asyncio.to_thread(self._blob(key).exists))

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._blob(key).delete)
        except Exception as exc:  # noqa: BLE001 - provider hierarchy is optional
            if not _is_not_found(exc):
                raise

    async def delete_prefix(self, prefix: str) -> int:
        normalised = _normalise_key(prefix) if prefix else ""

        def _delete() -> int:
            removed = 0
            for blob in self._client.list_blobs(self._bucket_name, prefix=normalised):
                blob.delete()
                removed += 1
            return removed

        return await asyncio.to_thread(_delete)

    async def size(self, key: str) -> int:
        blob = self._blob(key)
        try:
            await asyncio.to_thread(blob.reload)
        except Exception as exc:  # noqa: BLE001 - provider hierarchy is optional
            if _is_not_found(exc):
                raise FileNotFoundError(f"No blob at key: {key}") from exc
            raise
        return int(blob.size or 0)

    async def list_prefix(
        self,
        prefix: str,
        *,
        include_backcompat_roots: bool = False,
    ) -> list[tuple[str, int]]:
        _ = include_backcompat_roots
        normalised = _normalise_key(prefix) if prefix else ""

        def _list() -> list[tuple[str, int]]:
            return [
                (str(blob.name), int(blob.size or 0))
                for blob in self._client.list_blobs(self._bucket_name, prefix=normalised)
            ]

        return await asyncio.to_thread(_list)
