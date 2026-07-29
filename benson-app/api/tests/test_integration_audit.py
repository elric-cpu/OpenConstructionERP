import pytest

from app.integration_audit import integration_audit_record


def test_integration_audit_has_required_operational_fields() -> None:
    record = integration_audit_record(
        event="photo_asset.linked",
        calling_ip="203.0.113.10",
        request_id="request-123",
        latitude=43.5862,
        longitude=-118.4967,
        target_delta={"work_order_id": "work-order-1", "stage": "before"},
    )

    assert record["timestamp"].endswith("+00:00")
    assert record["calling_ip"] == "203.0.113.10"
    assert record["geo_coordinates"] == {
        "latitude": 43.5862,
        "longitude": -118.4967,
        "source": "client_supplied",
    }
    assert record["target_delta"]["stage"] == "before"


def test_integration_audit_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValueError, match="outside valid bounds"):
        integration_audit_record(
            event="photo_asset.linked",
            calling_ip="203.0.113.10",
            latitude=100,
            longitude=-118,
            target_delta={},
        )
