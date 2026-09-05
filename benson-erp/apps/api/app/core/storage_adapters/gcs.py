from datetime import timedelta
from typing import Any

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage  # type: ignore[import-untyped]

from app.core.config import Settings
from app.core.storage_adapters.base import validate_object_key


class GoogleCloudObjectStorage:
    def __init__(self, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "GoogleCloudObjectStorage":
        return cls(
            settings.gcs_bucket or "",
            storage.Client(project=settings.gcs_project or None),
        )

    def _blob(self, key: str) -> Any:
        return self.client.bucket(self.bucket).blob(validate_object_key(key))

    def put_immutable(
        self, key: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        try:
            self._blob(key).upload_from_string(
                content,
                content_type=content_type,
                if_generation_match=0,
            )
        except PreconditionFailed as exc:
            raise FileExistsError(key) from exc

    def get(self, key: str) -> bytes:
        return self._blob(key).download_as_bytes()

    def signed_get_url(self, key: str, expires_seconds: int) -> str:
        return self._blob(key).generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_seconds),
            method="GET",
        )
