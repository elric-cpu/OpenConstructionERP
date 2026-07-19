"""Regression tests for embedded-PostgreSQL test data path selection."""

from __future__ import annotations

from tests import _embedded_pg_fixture


def test_windows_ci_uses_runner_temp(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    def fake_mkdtemp(*, prefix, dir=None):
        calls.update(prefix=prefix, dir=dir)
        return str(tmp_path / "oe-tests-pg-fixed")

    monkeypatch.setattr(_embedded_pg_fixture.sys, "platform", "win32")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(_embedded_pg_fixture.tempfile, "mkdtemp", fake_mkdtemp)

    result = _embedded_pg_fixture.make_embedded_pg_data_dir()

    assert result == tmp_path / "oe-tests-pg-fixed"
    assert calls == {"prefix": "oe-tests-pg-", "dir": str(tmp_path)}


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
