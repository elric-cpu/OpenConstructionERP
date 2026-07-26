from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import Settings
from app.core.storage_adapters.base import validate_object_key


class S3ObjectStorage:
    def __init__(
        self,
        bucket: str,
        client: Any,
        server_side_encryption: str | None = None,
        signing_client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.client = client
        self.server_side_encryption = server_side_encryption
        self.signing_client = signing_client or client

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3ObjectStorage":
        client = cls._client(settings, settings.s3_endpoint_url)
        signing_client = (
            cls._client(settings, settings.s3_public_endpoint_url)
            if settings.s3_public_endpoint_url
            else client
        )
        return cls(
            settings.s3_bucket or "",
            client,
            settings.s3_server_side_encryption,
            signing_client,
        )

    @staticmethod
    def _client(settings: Settings, endpoint_url: str | None) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.s3_addressing_style},
            ),
        )

    def put_immutable(
        self, key: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        request: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": validate_object_key(key),
            "Body": content,
            "ContentType": content_type,
            "IfNoneMatch": "*",
        }
        if self.server_side_encryption:
            request["ServerSideEncryption"] = self.server_side_encryption
        try:
            self.client.put_object(**request)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = exc.response.get("Error", {}).get("Code")
            if status == 412 or code in {"PreconditionFailed", "ConditionalRequestConflict"}:
                raise FileExistsError(key) from exc
            raise

    def get(self, key: str) -> bytes:
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=validate_object_key(key),
        )
        return response["Body"].read()

    def signed_get_url(self, key: str, expires_seconds: int) -> str:
        return self.signing_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": validate_object_key(key)},
            ExpiresIn=expires_seconds,
        )
