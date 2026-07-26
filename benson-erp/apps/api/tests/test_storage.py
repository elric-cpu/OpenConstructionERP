from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from app.core.config import Settings
from app.core.storage import build_object_storage
from app.core.storage_adapters.base import validate_object_key
from app.core.storage_adapters.gcs import GoogleCloudObjectStorage
from app.core.storage_adapters.local import LocalObjectStorage
from app.core.storage_adapters.s3 import S3ObjectStorage
from botocore.exceptions import ClientError
from google.api_core.exceptions import PreconditionFailed


def test_local_storage_is_create_only_and_rejects_traversal(tmp_path: Path) -> None:
    storage = LocalObjectStorage(str(tmp_path))
    storage.put_immutable("tenants/one/proposal.pdf", b"first", "application/pdf")

    assert storage.get("tenants/one/proposal.pdf") == b"first"
    assert storage.signed_get_url("tenants/one/proposal.pdf", 300) is None
    with pytest.raises(FileExistsError):
        storage.put_immutable("tenants/one/proposal.pdf", b"replacement")
    for invalid in ("../secret", "/absolute", r"tenants\one\file", "tenants//file"):
        with pytest.raises(ValueError):
            validate_object_key(invalid)


def test_factory_builds_local_storage(tmp_path: Path) -> None:
    config = Settings(local_storage_root=str(tmp_path))

    assert isinstance(build_object_storage(config), LocalObjectStorage)


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.last_put: dict[str, Any] = {}
        self.signed_requests = 0

    def put_object(self, **request: Any) -> None:
        self.last_put = request
        identity = (request["Bucket"], request["Key"])
        if identity in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "PreconditionFailed"},
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        self.objects[identity] = request["Body"]

    def get_object(self, **request: Any) -> dict[str, BytesIO]:
        return {"Body": BytesIO(self.objects[(request["Bucket"], request["Key"])])}

    def generate_presigned_url(
        self, operation: str, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        self.signed_requests += 1
        return f"https://objects.example/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"


def test_s3_storage_uses_conditional_create_encryption_and_signed_urls() -> None:
    client = FakeS3Client()
    signing_client = FakeS3Client()
    storage = S3ObjectStorage("erp-private", client, "AES256", signing_client)
    key = "tenants/one/proposal.pdf"

    storage.put_immutable(key, b"proposal", "application/pdf")

    assert client.last_put["IfNoneMatch"] == "*"
    assert client.last_put["ServerSideEncryption"] == "AES256"
    assert storage.get(key) == b"proposal"
    assert storage.signed_get_url(key, 120).endswith("?ttl=120")
    assert client.signed_requests == 0
    assert signing_client.signed_requests == 1
    with pytest.raises(FileExistsError):
        storage.put_immutable(key, b"replacement")


class FakeBlob:
    def __init__(self) -> None:
        self.content: bytes | None = None
        self.upload: dict[str, Any] = {}

    def upload_from_string(self, content: bytes, **options: Any) -> None:
        if self.content is not None:
            raise PreconditionFailed("already exists")
        self.content = content
        self.upload = options

    def download_as_bytes(self) -> bytes:
        assert self.content is not None
        return self.content

    def generate_signed_url(self, **options: Any) -> str:
        return f"https://storage.googleapis.test/object?method={options['method']}"


class FakeGcsBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, key: str) -> FakeBlob:
        return self.blobs.setdefault(key, FakeBlob())


class FakeGcsClient:
    def __init__(self) -> None:
        self.value = FakeGcsBucket()

    def bucket(self, name: str) -> FakeGcsBucket:
        assert name == "erp-private"
        return self.value


def test_gcs_storage_uses_generation_precondition_and_signed_urls() -> None:
    storage = GoogleCloudObjectStorage("erp-private", FakeGcsClient())
    key = "tenants/one/proposal.pdf"

    storage.put_immutable(key, b"proposal", "application/pdf")

    blob = storage.client.value.blobs[key]
    assert blob.upload == {"content_type": "application/pdf", "if_generation_match": 0}
    assert storage.get(key) == b"proposal"
    assert storage.signed_get_url(key, 120).startswith("https://storage.googleapis.test/")
    with pytest.raises(FileExistsError):
        storage.put_immutable(key, b"replacement")
