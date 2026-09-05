import uuid
from enum import StrEnum

from sqlalchemy import Enum, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class DocumentVisibility(StrEnum):
    INTERNAL = "INTERNAL"
    CLIENT = "CLIENT"


class Document(TenantRecord, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "storage_key"),
    )

    record_type: Mapped[str] = mapped_column(String(80), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    visibility: Mapped[DocumentVisibility] = mapped_column(
        Enum(DocumentVisibility), nullable=False
    )
