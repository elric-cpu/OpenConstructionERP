"""Unit tests for restoring a backup's embedded files (DB-free).

Export can embed the binaries referenced by a row (documents, drawings, photos)
under ``files/<backup_key>/<storage-key>``. Restore writes them back so a
transferred backup keeps the files, not just the rows pointing at them.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.modules.backup.service import restore_backup_files


class _FakeBackend:
    """Records ``put`` calls instead of touching real storage."""

    def __init__(self) -> None:
        self.puts: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes) -> None:
        self.puts[key] = content


def _zip_with(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "openestimate"}))
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_restore_writes_embedded_blobs_under_their_storage_key() -> None:
    raw = _zip_with(
        {
            "files/documents/proj-1/plan.pdf": b"PDFBYTES",
            "files/documents/nested/dir/photo.jpg": b"JPGBYTES",
            "projects.json": b"[]",  # a data table, not a file: must be ignored
        }
    )
    backend = _FakeBackend()

    written, warnings = await restore_backup_files(raw, backend=backend)

    assert written == 2
    assert warnings == []
    # The storage key is the entry path minus the ``files/<backup_key>/`` prefix.
    assert backend.puts["proj-1/plan.pdf"] == b"PDFBYTES"
    assert backend.puts["nested/dir/photo.jpg"] == b"JPGBYTES"


@pytest.mark.asyncio
async def test_restore_reports_a_failed_write_as_a_warning_not_a_crash() -> None:
    class _FailBackend:
        async def put(self, key: str, content: bytes) -> None:
            raise OSError("disk full")

    raw = _zip_with({"files/documents/x.bin": b"DATA"})

    written, warnings = await restore_backup_files(raw, backend=_FailBackend())

    assert written == 0
    assert len(warnings) == 1
    assert "x.bin" in warnings[0]


@pytest.mark.asyncio
async def test_restore_is_a_noop_when_no_files_are_embedded() -> None:
    raw = _zip_with({"projects.json": b"[]"})
    backend = _FakeBackend()

    written, warnings = await restore_backup_files(raw, backend=backend)

    assert written == 0
    assert warnings == []
    assert backend.puts == {}
