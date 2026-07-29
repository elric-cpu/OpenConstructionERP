from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.config import Settings
from app.core.storage import build_storage_backend
from app.modules.benson_workers.gcs_storage import GoogleCloudStorageBackend


class MissingBlobError(Exception):
    code = 404


@dataclass
class FakeBlob:
    name: str
    objects: dict[str, bytes]

    @property
    def size(self) -> int | None:
        value = self.objects.get(self.name)
        return len(value) if value is not None else None

    def upload_from_string(self, content: bytes) -> None:
        self.objects[self.name] = content

    def download_as_bytes(self) -> bytes:
        if self.name not in self.objects:
            raise MissingBlobError(self.name)
        return self.objects[self.name]

    def exists(self) -> bool:
        return self.name in self.objects

    def delete(self) -> None:
        if self.name not in self.objects:
            raise MissingBlobError(self.name)
        del self.objects[self.name]

    def reload(self) -> None:
        if self.name not in self.objects:
            raise MissingBlobError(self.name)


class FakeBucket:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(name, self.objects)


class FakeClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def bucket(self, _name: str) -> FakeBucket:
        return FakeBucket(self.objects)

    def list_blobs(self, _name: str, *, prefix: str):
        return [FakeBlob(name, self.objects) for name in sorted(self.objects) if name.startswith(prefix)]


@pytest.mark.asyncio
async def test_gcs_backend_round_trip_and_prefix_delete() -> None:
    backend = GoogleCloudStorageBackend(bucket="private", client=FakeClient())

    await backend.put("documents/one.pdf", b"one")
    await backend.put("documents/two.pdf", b"two")
    await backend.put("other/three.pdf", b"three")

    assert await backend.get("documents/one.pdf") == b"one"
    assert await backend.exists("documents/two.pdf") is True
    assert await backend.size("documents/two.pdf") == 3
    assert await backend.list_prefix("documents") == [
        ("documents/one.pdf", 3),
        ("documents/two.pdf", 3),
    ]
    assert await backend.delete_prefix("documents") == 2
    assert await backend.exists("documents/one.pdf") is False
    assert await backend.get("other/three.pdf") == b"three"


@pytest.mark.asyncio
async def test_gcs_backend_maps_missing_objects() -> None:
    backend = GoogleCloudStorageBackend(bucket="private", client=FakeClient())

    with pytest.raises(FileNotFoundError):
        await backend.get("missing.pdf")
    with pytest.raises(FileNotFoundError):
        await backend.size("missing.pdf")
    await backend.delete("missing.pdf")


def test_storage_factory_selects_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = GoogleCloudStorageBackend(bucket="private", client=FakeClient())
    monkeypatch.setattr(GoogleCloudStorageBackend, "from_settings", lambda _settings: expected)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://oe:oe@localhost:5432/test",
        database_sync_url="postgresql+psycopg2://oe:oe@localhost:5432/test",
        storage_backend="gcs",
        gcs_bucket="private",
    )

    assert build_storage_backend(settings) is expected
