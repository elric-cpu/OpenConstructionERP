from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, settings
from app.core.storage_adapters.gcs import GoogleCloudObjectStorage
from app.core.storage_adapters.local import LocalObjectStorage
from app.core.storage_adapters.s3 import S3ObjectStorage


class ObjectStorage(Protocol):
    def put_immutable(
        self, key: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> None: ...

    def get(self, key: str) -> bytes: ...

    def signed_get_url(self, key: str, expires_seconds: int) -> str | None: ...


def build_object_storage(config: Settings) -> ObjectStorage:
    if config.storage_backend == "local":
        return LocalObjectStorage(config.local_storage_root)
    if config.storage_backend == "s3":
        return S3ObjectStorage.from_settings(config)
    if config.storage_backend == "gcs":
        return GoogleCloudObjectStorage.from_settings(config)
    raise RuntimeError(f"Storage backend {config.storage_backend!r} is not configured")


@lru_cache
def get_object_storage() -> ObjectStorage:
    return build_object_storage(settings)
