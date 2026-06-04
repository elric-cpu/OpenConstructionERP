"""Contracts module domain events.

Most contract lifecycle events are published inline from the service via
``event_bus.publish_detached`` (signed / amended / claim.submitted / etc.).
This module centralises the event-name constants that the Gap I progress
bridge introduces so subscribers and tests reference one canonical string
instead of a magic literal.

Event reference
───────────────
``contracts.claim.populated``
    Emitted after a draft / submitted progress claim has its line breakdown
    rebuilt from the latest progress observations and committed
    (``commit_preview_to_claim``). Payload::

        {
            "claim_id": str,
            "contract_id": str,
            "claim_number": str,
            "line_count": int,        # number of claim lines written
            "gross": str,             # Decimal-as-string, claim currency
            "retention": str,
            "net_due": str,
            "currency": str,
            "actor": str | None,
        }

    Finance / dashboard subscribers use it to refresh a claim's billed-to-date
    once it has been auto-populated from the field, without re-querying the
    whole contract. The event is informational only: it does NOT post to the
    cost spine (the certified-claim → actual posting is owned by Gap B/E and
    fires on ``contracts.claim.certified``).
"""

from __future__ import annotations

#: Emitted when a claim's lines are (re)built from progress observations.
CLAIM_POPULATED = "contracts.claim.populated"

__all__ = ["CLAIM_POPULATED"]
