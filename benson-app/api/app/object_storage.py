import base64
import hashlib
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from google.cloud import storage as gcs  # type: ignore[import-untyped]
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, UnidentifiedImageError

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
    settings: Settings,
    *,
    lead_id: str,
    original_name: str,
    content_type: str,
    content: bytes,
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


def sanitize_field_photo(content: bytes) -> tuple[bytes, str, str]:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            image_format = image.format
            if image_format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Field photos must be JPEG, PNG, or WebP")
            if image.width * image.height > 40_000_000:
                raise ValueError("Field photo dimensions exceed the safe limit")
            output = BytesIO()
            if image_format == "JPEG":
                image.convert("RGB").save(
                    output, format="JPEG", quality=90, optimize=True
                )
                content_type, suffix = "image/jpeg", ".jpg"
            elif image_format == "PNG":
                image.save(output, format="PNG", optimize=True)
                content_type, suffix = "image/png", ".png"
            else:
                image.save(output, format="WEBP", quality=90, method=4)
                content_type, suffix = "image/webp", ".webp"
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("Field photo could not be decoded") from error
    return output.getvalue(), content_type, suffix


def store_field_photo(
    settings: Settings,
    *,
    report_id: str,
    content: bytes,
    suffix: str,
    content_type: str,
) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    object_name = f"field-records/{report_id}/{uuid4().hex}{suffix}"
    if settings.upload_bucket:
        blob = gcs.Client().bucket(settings.upload_bucket).blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{settings.upload_bucket}/{object_name}", digest
    root = settings.upload_storage_path.resolve()
    destination = (root / object_name).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Unsafe field photo path")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.write_bytes(content)
    destination.chmod(0o600)
    return str(destination), digest


def store_change_order_evidence(
    settings: Settings,
    *,
    change_order_id: str,
    original_name: str,
    content: bytes,
    content_type: str,
) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(original_name).suffix.lower()[:10]
    object_name = f"change-orders/{change_order_id}/{uuid4().hex}{suffix}"
    if settings.upload_bucket:
        blob = gcs.Client().bucket(settings.upload_bucket).blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{settings.upload_bucket}/{object_name}", digest
    root = settings.upload_storage_path.resolve()
    destination = (root / object_name).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Unsafe change order evidence path")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.write_bytes(content)
    destination.chmod(0o600)
    return str(destination), digest


def delete_upload(settings: Settings, storage_key: str) -> None:
    if storage_key.startswith("gs://"):
        prefix = f"gs://{settings.upload_bucket}/"
        if not settings.upload_bucket or not storage_key.startswith(prefix):
            raise ValueError("Upload object does not belong to the configured bucket")
        gcs.Client().bucket(settings.upload_bucket).blob(
            storage_key.removeprefix(prefix)
        ).delete()
        return
    root = settings.upload_storage_path.resolve()
    destination = Path(storage_key).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Unsafe upload path")
    destination.unlink(missing_ok=True)


def read_upload(settings: Settings, storage_key: str) -> bytes:
    if storage_key.startswith("gs://"):
        prefix = f"gs://{settings.upload_bucket}/"
        if not settings.upload_bucket or not storage_key.startswith(prefix):
            raise ValueError("Upload object does not belong to the configured bucket")
        return bytes(
            gcs.Client()
            .bucket(settings.upload_bucket)
            .blob(storage_key.removeprefix(prefix))
            .download_as_bytes()
        )
    root = settings.upload_storage_path.resolve()
    source = Path(storage_key).resolve()
    if not source.is_relative_to(root):
        raise ValueError("Unsafe upload path")
    return source.read_bytes()


def store_employee_document(
    settings: Settings,
    *,
    employee_id: str,
    task_id: str,
    version: int,
    data_classification: str,
    original_name: str,
    content_type: str,
    content: bytes,
) -> tuple[str, str, str, str]:
    key = settings.employee_document_key_bytes()
    nonce = os.urandom(12)
    digest = hashlib.sha256(content).hexdigest()
    aad = f"{employee_id}:{task_id}:{version}:{data_classification}".encode()
    encrypted = AESGCM(key).encrypt(nonce, content, aad)
    suffix = Path(original_name).suffix.lower()[:10]
    object_name = (
        f"employees/{employee_id}/{data_classification}/{task_id}/v{version}/"
        f"{uuid4().hex}{suffix}.enc"
    )
    if settings.upload_bucket:
        bucket = gcs.Client().bucket(settings.upload_bucket)
        bucket.blob(object_name).upload_from_string(
            encrypted, content_type="application/octet-stream"
        )
        storage_key = f"gs://{settings.upload_bucket}/{object_name}"
    else:
        root = settings.upload_storage_path.resolve()
        destination = (root / object_name).resolve()
        if not destination.is_relative_to(root):
            raise ValueError("Unsafe employee document path")
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(encrypted)
        destination.chmod(0o600)
        storage_key = str(destination)
    return (
        storage_key,
        digest,
        base64.b64encode(nonce).decode(),
        settings.employee_document_key_version,
    )


def read_employee_document(
    settings: Settings,
    *,
    storage_key: str,
    employee_id: str,
    task_id: str,
    version: int,
    data_classification: str,
    nonce_base64: str,
    key_version: str,
) -> bytes:
    if key_version != settings.employee_document_key_version:
        raise ValueError("Employee document key version is unavailable")
    encrypted = read_upload(settings, storage_key)
    nonce = base64.b64decode(nonce_base64, validate=True)
    aad = f"{employee_id}:{task_id}:{version}:{data_classification}".encode()
    return AESGCM(settings.employee_document_key_bytes()).decrypt(nonce, encrypted, aad)
