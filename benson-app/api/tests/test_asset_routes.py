from typing import Any

from fastapi.testclient import TestClient

from app.main import app


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def link_photo_asset_to_work_order(self, **values: Any) -> tuple[str, bool]:
        self.calls.append(values)
        return "asset-1", True


def test_photo_sync_maps_picker_asset_stage(monkeypatch: Any) -> None:
    fake = FakeStore()
    monkeypatch.setattr("app.asset_routes.store", lambda _settings: fake)
    response = TestClient(app).post(
        "/api/v1/assets/sync-google-photos",
        headers={"X-Request-ID": "request-1"},
        json={
            "work_order_id": "work-order-1",
            "assets": [
                {
                    "storage_key": "private/work-order-1/before.jpg",
                    "original_name": "before.jpg",
                    "content_type": "image/jpeg",
                    "size_bytes": 1024,
                    "sha256": "a" * 64,
                    "stage": "before",
                    "picker_media_item_id": "picker-1",
                    "latitude": 42.263,
                    "longitude": -118.675,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["assets"][0]["stage"] == "before"
    assert fake.calls[0]["asset_role"] == "before"
    assert fake.calls[0]["metadata"]["picker_media_item_id"] == "picker-1"


def test_photo_sync_rejects_unknown_stage(monkeypatch: Any) -> None:
    monkeypatch.setattr("app.asset_routes.store", lambda _settings: FakeStore())
    response = TestClient(app).post(
        "/api/v1/assets/sync-google-photos",
        json={
            "work_order_id": "work-order-1",
            "assets": [
                {
                    "storage_key": "private/work-order-1/photo.jpg",
                    "original_name": "photo.jpg",
                    "content_type": "image/jpeg",
                    "size_bytes": 1024,
                    "sha256": "a" * 64,
                    "stage": "unclassified",
                }
            ],
        },
    )
    assert response.status_code == 422
