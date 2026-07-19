"""Path selection for the test session's embedded PostgreSQL cluster."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def make_embedded_pg_data_dir() -> Path:
    """Create test data under GitHub's Windows-native temporary root when available."""
    runner_temp = os.environ.get("RUNNER_TEMP", "").strip()
    temp_root = runner_temp if sys.platform == "win32" and runner_temp else None
    return Path(tempfile.mkdtemp(prefix="oe-tests-pg-", dir=temp_root))
