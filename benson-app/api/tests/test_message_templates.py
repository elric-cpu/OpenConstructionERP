from app.message_templates import client_lead_message


def test_residential_message_sets_business_hour_expectation_and_photo_reply() -> None:
    message = client_lead_message(
        {"name": "Morgan Builder", "customer_type": "homeowner", "urgency": "standard"}
    )

    assert message.audience == "residential"
    assert message.priority == "normal"
    assert "two business hours" in message.body
    assert "reply with project photos" in message.body


def test_federal_message_uses_transactional_routing_language() -> None:
    message = client_lead_message(
        {
            "name": "Procurement Officer",
            "customer_type": "government_procurement_officer",
            "urgency": "standard",
        }
    )

    assert message.audience == "federal"
    assert "federal-contracting review queue" in message.body
    assert "two business hours" not in message.body


def test_emergency_message_prioritizes_immediate_safety() -> None:
    message = client_lead_message(
        {
            "name": "Emergency Caller",
            "customer_type": "homeowner",
            "urgency": "emergency",
        }
    )

    assert message.audience == "emergency"
    assert message.priority == "high"
    assert "call 911" in message.body
    assert "when it is safe" in message.body
