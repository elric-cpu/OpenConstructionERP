import base64
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.main import app
from app.storage import operations_store


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path) -> Iterator[Settings]:
    settings = Settings(
        environment="test",
        employee_document_encryption_key=base64.b64encode(b"t" * 32).decode(),
        database_url="sqlite+pysqlite:///:memory:",
        database_path=tmp_path / "operations.sqlite3",
        upload_storage_path=tmp_path / "uploads",
        ddc_registry_path=Path(__file__).resolve().parents[2]
        / "skills"
        / "registry.json",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    test_store = operations_store(settings.resolved_database_url())
    test_store.initialize_schema()
    yield settings
    app.dependency_overrides.clear()
    test_store.engine.dispose()
    operations_store.cache_clear()
