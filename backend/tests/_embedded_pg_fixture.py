"""Path selection for the test session's embedded PostgreSQL cluster."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path


def make_embedded_pg_data_dir() -> Path:
    """Choose an isolated test data path with Windows-compatible ACL inheritance."""
    if sys.platform == "win32":
        # Python 3.12.4+ gives mkdtemp() directories a restrictive Windows ACL.
        # The bundled initdb cannot traverse that parent reliably and reports a
        # misleading "File exists" error. Leave the unique path absent so
        # embedded_pg.boot() creates it with normal inherited ACLs instead.
        temp_root = os.environ.get("RUNNER_TEMP", "").strip() or tempfile.gettempdir()
        return Path(temp_root) / f"oe-tests-pg-{uuid.uuid4().hex}"
    return Path(tempfile.mkdtemp(prefix="oe-tests-pg-"))
