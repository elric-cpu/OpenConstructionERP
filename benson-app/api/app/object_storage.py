import hashlib
from pathlib import Path
from uuid import uuid4

from google.cloud import storage as gcs  # type: ignore[import-untyped]

from .config import Settings


def detect_upload_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def store_upload(
    settings: Settings, *, lead_id: str, original_name: str, content_type: str, content: bytes
) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(original_name).suffix.lower()[:10]
    object_name = f"leads/{lead_id}/{uuid4().hex}{suffix}"
    if settings.upload_bucket:
        bucket = gcs.Client().bucket(settings.upload_bucket)
        blob = bucket.blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{settings.upload_bucket}/{object_name}", digest
    root = settings.upload_storage_path.resolve()
    destination = (root / object_name).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Unsafe upload path")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.write_bytes(content)
    destination.chmod(0o600)
    return str(destination), digest


def delete_upload(settings: Settings, storage_key: str) -> None:
    if storage_key.startswith("gs://"):
        prefix = f"gs://{settings.upload_bucket}/"
        if not settings.upload_bucket or not storage_key.startswith(prefix):
            raise ValueError("Upload object does not belong to the configured bucket")
        gcs.Client().bucket(settings.upload_bucket).blob(storage_key.removeprefix(prefix)).delete()
        return
    root = settings.upload_storage_path.resolve()
    destination = Path(storage_key).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Unsafe upload path")
    destination.unlink(missing_ok=True)
