"""Unit tests for the backup restore ownership remap (DB-free).

A backup is one user's own data. On restore into another account (typically on
another machine) every field that held the exporter's user id must be repointed
to the restoring user, and the ``users`` table must be skipped entirely.
"""

from __future__ import annotations

from app.modules.backup.service import RESTORE_SKIP_KEYS, remap_owner_refs


def test_remap_repoints_every_matching_field() -> None:
    old, new = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    record = {
        "id": "project-1",
        "owner_id": old,
        "created_by": old,
        "uploaded_by": old,
        "name": "Tower",
        "quantity": 5,
        "parent_id": None,
    }
    out = remap_owner_refs(record, old, new)

    # Every field that held the exporter's id now points at the restorer...
    assert out["owner_id"] == new
    assert out["created_by"] == new
    assert out["uploaded_by"] == new
    # ...and nothing else is touched.
    assert out["id"] == "project-1"
    assert out["name"] == "Tower"
    assert out["quantity"] == 5
    assert out["parent_id"] is None


def test_remap_is_a_noop_when_owner_is_unchanged_or_unknown() -> None:
    record = {"owner_id": "aaaa"}
    # Same owner: nothing to do.
    assert remap_owner_refs(record, "aaaa", "aaaa") == record
    # No exporter id on the manifest: leave the record as-is.
    assert remap_owner_refs(record, "", "bbbb") == record


def test_remap_does_not_mutate_the_input() -> None:
    old, new = "aaaa", "bbbb"
    record = {"owner_id": old}
    remap_owner_refs(record, old, new)
    assert record["owner_id"] == old


def test_users_table_is_never_restored() -> None:
    assert "users" in RESTORE_SKIP_KEYS
