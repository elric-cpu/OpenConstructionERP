# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests for the CPM engine's per-activity ``start_offset`` floor.

``app.core.cpm.calculate_cpm`` is the engine the schedule module's
``reschedule`` runs. A root activity has no predecessor, so before
``start_offset`` existed the forward pass floored its early_start at 0 (the
project origin) and its successors were scheduled from there, regardless of the
root's real manual start. On a project with more than one independent chain
that placed a later chain's successor BEFORE its own predecessor. These tests
pin the fix: a root's ``start_offset`` anchors it (and therefore its
successors) at its real start, while an omitted offset keeps the historical
origin-anchored behaviour.
"""

from __future__ import annotations

import pytest

from app.core.cpm import calculate_cpm


@pytest.mark.asyncio
async def test_missing_start_offset_defaults_to_origin() -> None:
    """No start_offset -> root anchored at the project origin (unchanged)."""
    activities = [{"id": "a", "duration": 3}, {"id": "b", "duration": 3}]
    relationships = [{"predecessor_id": "a", "successor_id": "b", "type": "FS", "lag": 0}]
    by_id = {r["id"]: r for r in await calculate_cpm(activities, relationships, project_start_date="2024-01-01")}
    assert by_id["a"]["early_start"] == 0
    assert by_id["b"]["early_start"] == by_id["a"]["early_finish"]


@pytest.mark.asyncio
async def test_root_start_offset_anchors_the_root() -> None:
    """A root's start_offset becomes its early_start (a 'start no earlier than' floor)."""
    activities = [{"id": "root", "duration": 5, "start_offset": 60}]
    by_id = {r["id"]: r for r in await calculate_cpm(activities, [], project_start_date="2024-01-01")}
    assert by_id["root"]["early_start"] == 60


@pytest.mark.asyncio
async def test_successor_of_a_late_root_is_never_scheduled_before_it() -> None:
    """The reported bug: an independent later chain's successor lands before its predecessor.

    Two independent FS chains share the project origin. Chain 2's root starts 60
    days in. Its successor must be scheduled after the root finishes, never at
    the origin (which is where the pre-fix engine put it, weeks before the root
    even starts).
    """
    activities = [
        {"id": "r1", "duration": 5, "start_offset": 0},
        {"id": "s1", "duration": 5, "start_offset": 0},
        {"id": "r2", "duration": 5, "start_offset": 60},
        {"id": "s2", "duration": 5, "start_offset": 0},
    ]
    relationships = [
        {"predecessor_id": "r1", "successor_id": "s1", "type": "FS", "lag": 0},
        {"predecessor_id": "r2", "successor_id": "s2", "type": "FS", "lag": 0},
    ]
    by_id = {r["id"]: r for r in await calculate_cpm(activities, relationships, project_start_date="2024-01-01")}
    # Root 2 is anchored at its own start, not the origin.
    assert by_id["r2"]["early_start"] == 60
    # Its successor starts at or after the root finishes - never before the root.
    assert by_id["s2"]["early_start"] >= by_id["r2"]["early_finish"]
    # And it is clearly NOT sitting at the origin like chain 1's successor.
    assert by_id["s2"]["early_start"] > by_id["s1"]["early_start"]


@pytest.mark.asyncio
async def test_successor_offset_does_not_pin_it_earlier_than_the_network() -> None:
    """A successor's own start_offset never overrides a later predecessor-driven date.

    reschedule only passes start_offset for roots, but the engine must stay safe
    even if a successor carries one: the max() against predecessor candidates
    means the network still wins when it pushes the successor later.
    """
    activities = [
        {"id": "p", "duration": 10, "start_offset": 0},
        # Successor floored at day 2, but its predecessor finishes well after.
        {"id": "q", "duration": 3, "start_offset": 2},
    ]
    relationships = [{"predecessor_id": "p", "successor_id": "q", "type": "FS", "lag": 0}]
    by_id = {r["id"]: r for r in await calculate_cpm(activities, relationships, project_start_date="2024-01-01")}
    # The network (predecessor finish) wins over the day-2 floor.
    assert by_id["q"]["early_start"] == by_id["p"]["early_finish"]
