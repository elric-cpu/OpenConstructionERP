from pathlib import Path

import pytest
from app.cli import read_admin_password


def test_read_admin_password_from_secret_file(tmp_path: Path) -> None:
    secret = tmp_path / "password"
    secret.write_text("a-secure-bootstrap-password\n", encoding="utf-8")

    assert read_admin_password(str(secret)) == "a-secure-bootstrap-password"


def test_read_admin_password_rejects_short_secret(tmp_path: Path) -> None:
    secret = tmp_path / "password"
    secret.write_text("too-short", encoding="utf-8")

    with pytest.raises(SystemExit, match="at least 12 characters"):
        read_admin_password(str(secret))
