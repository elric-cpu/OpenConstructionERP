from pathlib import Path

from app.core.storage_adapters.base import validate_object_key


class LocalObjectStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / validate_object_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put_immutable(
        self, key: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            target.write(content)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def signed_get_url(self, key: str, expires_seconds: int) -> None:
        self._path(key)
        del expires_seconds
        return None
