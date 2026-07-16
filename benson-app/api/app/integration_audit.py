import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def integration_audit_record(
    *,
    event: str,
    calling_ip: str,
    target_delta: dict[str, Any],
    request_id: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    coordinates = None
    if latitude is not None and longitude is not None:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Geo-coordinates are outside valid bounds")
        coordinates = {
            "latitude": latitude,
            "longitude": longitude,
            "source": "client_supplied",
        }
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "request_id": request_id[:200] or str(uuid4()),
        "calling_ip": calling_ip[:64],
        "geo_coordinates": coordinates,
        "target_delta": target_delta,
    }


def integration_audit_json(**values: Any) -> str:
    return json.dumps(
        integration_audit_record(**values),
        separators=(",", ":"),
        sort_keys=True,
    )
