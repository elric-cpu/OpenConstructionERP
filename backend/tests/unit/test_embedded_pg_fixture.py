"""Regression tests for embedded-PostgreSQL test data path selection."""

from __future__ import annotations

import uuid

from tests import _embedded_pg_fixture


def test_windows_ci_uses_runner_temp(monkeypatch, tmp_path) -> None:
    fixed_id = uuid.UUID(int=1)

    def fail_mkdtemp(*_args, **_kwargs):
        raise AssertionError("Windows must leave the data path for boot() to create")

    monkeypatch.setattr(_embedded_pg_fixture.sys, "platform", "win32")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(_embedded_pg_fixture.tempfile, "mkdtemp", fail_mkdtemp)
    monkeypatch.setattr(_embedded_pg_fixture.uuid, "uuid4", lambda: fixed_id)

    result = _embedded_pg_fixture.make_embedded_pg_data_dir()

    assert result == tmp_path / f"oe-tests-pg-{fixed_id.hex}"
    assert not result.exists()


def test_non_windows_keeps_platform_temp(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    def fake_mkdtemp(*, prefix, dir=None):
        calls.update(prefix=prefix, dir=dir)
        return str(tmp_path / "oe-tests-pg-default")

    monkeypatch.setattr(_embedded_pg_fixture.sys, "platform", "linux")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(_embedded_pg_fixture.tempfile, "mkdtemp", fake_mkdtemp)

    result = _embedded_pg_fixture.make_embedded_pg_data_dir()

    assert result == tmp_path / "oe-tests-pg-default"
    assert calls == {"prefix": "oe-tests-pg-", "dir": None}
