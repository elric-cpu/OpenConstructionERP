# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Geo Hub API routes.

Mounted by the module loader at ``/api/v1/geo-hub/``. All routes are
RBAC-gated; the service layer additionally closes cross-tenant IDOR
holes by 404-ing project-mismatched accesses.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import CurrentUserPayload, RequirePermission, SessionDep
from app.modules.geo_hub.schemas import (
    CanonicalToTilesetRequest,
    DiaryPhotoPinResponse,
    GeoAnchorCreate,
    GeoAnchorResponse,
    GeoAnchorUpdate,
    GeoJSONImportRequest,
    GeoOverlayCreate,
    GeoOverlayResponse,
    GeoOverlayUpdate,
    HSEPinResponse,
    ImageryLayerCreate,
    ImageryLayerResponse,
    ImageryLayerUpdate,
    KMLImportRequest,
    MapConfigResponse,
    PunchlistPinResponse,
    TerrainSourceCreate,
    TerrainSourceResponse,
    TerrainSourceUpdate,
    TileGenerateRequest,
    TileJobResponse,
    TilesetCreate,
    TilesetResponse,
    TilesetUpdate,
    ViewpointCreate,
    ViewpointResponse,
    ViewpointUpdate,
)
from app.modules.geo_hub.service import GeoHubService

router = APIRouter()


def _svc(session: SessionDep) -> GeoHubService:
    return GeoHubService(session)


# ── Anchors ──────────────────────────────────────────────────────────────


@router.get("/anchors/", response_model=list[GeoAnchorResponse])
async def list_anchors(
    project_id: uuid.UUID = Query(...),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[GeoAnchorResponse]:
    await service._verify_project_owner(
        project_id, payload, not_found_detail="Project not found",
    )
    anchor = await service.get_anchor_for_project(project_id)
    if anchor is None:
        return []
    return [GeoAnchorResponse.model_validate(anchor)]


@router.post(
    "/anchors/", response_model=GeoAnchorResponse, status_code=201,
)
async def create_anchor(
    data: GeoAnchorCreate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> GeoAnchorResponse:
    obj = await service.create_anchor(data, payload=payload)
    return GeoAnchorResponse.model_validate(obj)


@router.get("/anchors/{anchor_id}", response_model=GeoAnchorResponse)
async def get_anchor(
    anchor_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> GeoAnchorResponse:
    obj = await service.get_anchor(anchor_id)
    await service._verify_project_owner(
        obj.project_id, payload, not_found_detail="Anchor not found",
    )
    return GeoAnchorResponse.model_validate(obj)


@router.patch("/anchors/{anchor_id}", response_model=GeoAnchorResponse)
async def update_anchor(
    anchor_id: uuid.UUID,
    data: GeoAnchorUpdate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> GeoAnchorResponse:
    obj = await service.update_anchor(anchor_id, data, payload=payload)
    return GeoAnchorResponse.model_validate(obj)


@router.delete("/anchors/{anchor_id}", status_code=204)
async def delete_anchor(
    anchor_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> Response:
    await service.delete_anchor(anchor_id, payload=payload)
    return Response(status_code=204)


# ── Tilesets ─────────────────────────────────────────────────────────────


@router.get("/tilesets/", response_model=list[TilesetResponse])
async def list_tilesets(
    project_id: uuid.UUID = Query(...),
    tileset_status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[TilesetResponse]:
    rows = await service.list_tilesets_for_project(
        project_id,
        payload=payload,
        offset=offset,
        limit=limit,
        tileset_status=tileset_status,
    )
    return [TilesetResponse.model_validate(r) for r in rows]


@router.post("/tilesets/", response_model=TilesetResponse, status_code=201)
async def create_tileset(
    data: TilesetCreate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> TilesetResponse:
    obj = await service.create_tileset(data, payload=payload)
    return TilesetResponse.model_validate(obj)


@router.get("/tilesets/{tileset_id}", response_model=TilesetResponse)
async def get_tileset(
    tileset_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> TilesetResponse:
    obj = await service.get_tileset(tileset_id)
    await service._verify_project_owner(
        obj.project_id, payload, not_found_detail="Tileset not found",
    )
    return TilesetResponse.model_validate(obj)


@router.patch("/tilesets/{tileset_id}", response_model=TilesetResponse)
async def update_tileset(
    tileset_id: uuid.UUID,
    data: TilesetUpdate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> TilesetResponse:
    obj = await service.update_tileset(tileset_id, data, payload=payload)
    return TilesetResponse.model_validate(obj)


@router.delete("/tilesets/{tileset_id}", status_code=204)
async def delete_tileset(
    tileset_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> Response:
    await service.delete_tileset(tileset_id, payload=payload)
    return Response(status_code=204)


# ── Tile-generation jobs ─────────────────────────────────────────────────


@router.post("/tilesets/generate/", response_model=TileJobResponse, status_code=202)
async def enqueue_tile_job(
    data: TileGenerateRequest,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.job_run")),
) -> TileJobResponse:
    job = await service.enqueue_tile_generation(data, payload=payload)
    return TileJobResponse.model_validate(job)


@router.post(
    "/jobs/{job_id}/cancel", response_model=TileJobResponse, status_code=200,
)
async def cancel_tile_job(
    job_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.job_run")),
) -> TileJobResponse:
    job = await service.cancel_tile_job(job_id, payload=payload)
    return TileJobResponse.model_validate(job)


@router.get("/jobs/{job_id}", response_model=TileJobResponse)
async def get_tile_job(
    job_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> TileJobResponse:
    job = await service.get_job(job_id)
    await service._verify_project_owner(
        job.project_id, payload, not_found_detail="Job not found",
    )
    return TileJobResponse.model_validate(job)


@router.get("/jobs/", response_model=list[TileJobResponse])
async def list_tile_jobs(
    project_id: uuid.UUID = Query(...),
    state: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[TileJobResponse]:
    jobs = await service.list_jobs_for_project(
        project_id,
        payload=payload,
        state=state,
        offset=offset,
        limit=limit,
    )
    return [TileJobResponse.model_validate(j) for j in jobs]


# ── Canonical -> 3D Tileset (one-shot packaging) ────────────────────────


@router.post(
    "/from-canonical/{cad_import_id}",
    response_model=TilesetResponse,
    status_code=200,
)
async def package_canonical_as_tileset(
    cad_import_id: uuid.UUID,
    data: CanonicalToTilesetRequest | None = None,
    development_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.job_run")),
) -> TilesetResponse:
    obj = await service.package_canonical_as_tileset(
        cad_import_id,
        development_id=development_id,
        project_id=project_id,
        request=data,
        payload=payload,
    )
    return TilesetResponse.model_validate(obj)


# ── Imagery layers ───────────────────────────────────────────────────────


@router.get("/imagery-layers/", response_model=list[ImageryLayerResponse])
async def list_imagery_layers(
    project_id: uuid.UUID = Query(...),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[ImageryLayerResponse]:
    rows = await service.list_imagery_for_project(project_id, payload=payload)
    return [ImageryLayerResponse.model_validate(r) for r in rows]


@router.post(
    "/imagery-layers/", response_model=ImageryLayerResponse, status_code=201,
)
async def create_imagery_layer(
    data: ImageryLayerCreate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> ImageryLayerResponse:
    obj = await service.create_imagery_layer(data, payload=payload)
    return ImageryLayerResponse.model_validate(obj)


@router.patch(
    "/imagery-layers/{layer_id}", response_model=ImageryLayerResponse,
)
async def update_imagery_layer(
    layer_id: uuid.UUID,
    data: ImageryLayerUpdate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> ImageryLayerResponse:
    obj = await service.update_imagery_layer(layer_id, data, payload=payload)
    return ImageryLayerResponse.model_validate(obj)


@router.delete("/imagery-layers/{layer_id}", status_code=204)
async def delete_imagery_layer(
    layer_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> Response:
    await service.delete_imagery_layer(layer_id, payload=payload)
    return Response(status_code=204)


# ── Terrain sources (system-wide) ────────────────────────────────────────


@router.get("/terrain-sources/", response_model=list[TerrainSourceResponse])
async def list_terrain_sources(
    service: GeoHubService = Depends(_svc),
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[TerrainSourceResponse]:
    rows = await service.list_terrain_sources()
    return [TerrainSourceResponse.model_validate(r) for r in rows]


@router.post(
    "/terrain-sources/", response_model=TerrainSourceResponse, status_code=201,
)
async def create_terrain_source(
    data: TerrainSourceCreate,
    service: GeoHubService = Depends(_svc),
    _perm: None = Depends(RequirePermission("geo_hub.admin")),
) -> TerrainSourceResponse:
    obj = await service.create_terrain_source(data)
    return TerrainSourceResponse.model_validate(obj)


@router.patch(
    "/terrain-sources/{src_id}", response_model=TerrainSourceResponse,
)
async def update_terrain_source(
    src_id: uuid.UUID,
    data: TerrainSourceUpdate,
    service: GeoHubService = Depends(_svc),
    _perm: None = Depends(RequirePermission("geo_hub.admin")),
) -> TerrainSourceResponse:
    obj = await service.update_terrain_source(src_id, data)
    return TerrainSourceResponse.model_validate(obj)


@router.delete("/terrain-sources/{src_id}", status_code=204)
async def delete_terrain_source(
    src_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    _perm: None = Depends(RequirePermission("geo_hub.admin")),
) -> Response:
    await service.delete_terrain_source(src_id)
    return Response(status_code=204)


# ── Viewpoints ───────────────────────────────────────────────────────────


@router.get("/viewpoints/", response_model=list[ViewpointResponse])
async def list_viewpoints(
    project_id: uuid.UUID = Query(...),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[ViewpointResponse]:
    rows = await service.list_viewpoints(project_id, payload=payload)
    return [ViewpointResponse.model_validate(r) for r in rows]


@router.post(
    "/viewpoints/", response_model=ViewpointResponse, status_code=201,
)
async def create_viewpoint(
    data: ViewpointCreate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> ViewpointResponse:
    obj = await service.save_viewpoint(data, payload=payload)
    return ViewpointResponse.model_validate(obj)


@router.patch("/viewpoints/{vp_id}", response_model=ViewpointResponse)
async def update_viewpoint(
    vp_id: uuid.UUID,
    data: ViewpointUpdate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> ViewpointResponse:
    obj = await service.update_viewpoint(vp_id, data, payload=payload)
    return ViewpointResponse.model_validate(obj)


@router.delete("/viewpoints/{vp_id}", status_code=204)
async def delete_viewpoint(
    vp_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> Response:
    await service.delete_viewpoint(vp_id, payload=payload)
    return Response(status_code=204)


# ── Overlays + GeoJSON / KML I/O ─────────────────────────────────────────


@router.get("/overlays/", response_model=list[GeoOverlayResponse])
async def list_overlays(
    project_id: uuid.UUID = Query(...),
    kind: str | None = Query(default=None),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[GeoOverlayResponse]:
    rows = await service.list_overlays(project_id, payload=payload, kind=kind)
    return [GeoOverlayResponse.model_validate(r) for r in rows]


@router.post(
    "/overlays/", response_model=GeoOverlayResponse, status_code=201,
)
async def create_overlay(
    data: GeoOverlayCreate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> GeoOverlayResponse:
    obj = await service.create_overlay(data, payload=payload)
    return GeoOverlayResponse.model_validate(obj)


@router.patch(
    "/overlays/{overlay_id}", response_model=GeoOverlayResponse,
)
async def update_overlay(
    overlay_id: uuid.UUID,
    data: GeoOverlayUpdate,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> GeoOverlayResponse:
    obj = await service.update_overlay(overlay_id, data, payload=payload)
    return GeoOverlayResponse.model_validate(obj)


@router.delete("/overlays/{overlay_id}", status_code=204)
async def delete_overlay(
    overlay_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> Response:
    await service.delete_overlay(overlay_id, payload=payload)
    return Response(status_code=204)


@router.post(
    "/overlays/import-geojson/",
    response_model=GeoOverlayResponse,
    status_code=201,
)
async def import_geojson(
    data: GeoJSONImportRequest,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> GeoOverlayResponse:
    obj = await service.import_geojson(data, payload=payload)
    return GeoOverlayResponse.model_validate(obj)


@router.post(
    "/overlays/import-kml/",
    response_model=GeoOverlayResponse,
    status_code=201,
)
async def import_kml(
    data: KMLImportRequest,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.write")),
) -> GeoOverlayResponse:
    obj = await service.import_kml(data, payload=payload)
    return GeoOverlayResponse.model_validate(obj)


@router.get("/overlays/export-geojson/", response_model=dict[str, Any])
async def export_geojson(
    project_id: uuid.UUID = Query(...),
    kind: str | None = Query(default=None),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> dict[str, Any]:
    return await service.export_geojson(project_id, payload=payload, kind=kind)


# ── Map config one-shot bundle ───────────────────────────────────────────


@router.get("/map-config/{project_id}", response_model=MapConfigResponse)
async def get_map_config(
    project_id: uuid.UUID,
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> MapConfigResponse:
    bundle = await service.map_config(project_id, payload=payload)
    return MapConfigResponse.model_validate(bundle)


# ── Cross-module geo pin layers ──────────────────────────────────────────


@router.get(
    "/projects/{project_id}/hse-pins",
    response_model=list[HSEPinResponse],
)
async def list_hse_pins(
    project_id: uuid.UUID,
    limit: int = Query(default=500, ge=1, le=2000),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[HSEPinResponse]:
    """Geo-pinned safety incidents for the project."""
    rows = await service.list_hse_pins(project_id, payload=payload, limit=limit)
    return [HSEPinResponse.model_validate(r) for r in rows]


@router.get(
    "/projects/{project_id}/punchlist-pins",
    response_model=list[PunchlistPinResponse],
)
async def list_punchlist_pins(
    project_id: uuid.UUID,
    limit: int = Query(default=500, ge=1, le=2000),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[PunchlistPinResponse]:
    """Geo-pinned punch list items for the project."""
    rows = await service.list_punchlist_pins(
        project_id, payload=payload, limit=limit,
    )
    return [PunchlistPinResponse.model_validate(r) for r in rows]


@router.get(
    "/projects/{project_id}/diary-photo-pins",
    response_model=list[DiaryPhotoPinResponse],
)
async def list_diary_photo_pins(
    project_id: uuid.UUID,
    limit: int = Query(default=500, ge=1, le=2000),
    service: GeoHubService = Depends(_svc),
    payload: CurrentUserPayload = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("geo_hub.read")),
) -> list[DiaryPhotoPinResponse]:
    """Geo-tagged Daily Diary photos for the project."""
    rows = await service.list_diary_photo_pins(
        project_id, payload=payload, limit=limit,
    )
    return [DiaryPhotoPinResponse.model_validate(r) for r in rows]


__all__ = ["router"]
