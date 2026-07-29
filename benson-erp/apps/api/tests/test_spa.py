from pathlib import Path

from app.core.spa import mount_spa
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_spa_serves_direct_browser_routes_without_masking_api_404(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Benson ERP</h1>", encoding="utf-8")
    app = FastAPI()
    mount_spa(app, str(tmp_path))
    client = TestClient(app)

    assert client.get("/login").text == "<h1>Benson ERP</h1>"
    assert client.get("/activate").text == "<h1>Benson ERP</h1>"
    assert client.get("/api/v1/missing").status_code == 404
