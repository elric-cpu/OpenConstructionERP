from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

_SERVER_PREFIXES = ("api/", "docs", "health/", "metrics", "openapi.json", "redoc")


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code != 404 or path.startswith(_SERVER_PREFIXES):
            return response
        return await super().get_response("index.html", scope)


def mount_spa(app: FastAPI, web_dist_path: str | None) -> None:
    if not web_dist_path:
        return
    root = Path(web_dist_path)
    if not root.is_dir():
        raise RuntimeError(f"WEB_DIST_PATH does not exist: {root}")
    app.mount("/", SpaStaticFiles(directory=root, html=True), name="web")
