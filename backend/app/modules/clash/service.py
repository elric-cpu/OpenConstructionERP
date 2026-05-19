# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Clash detection engine + run lifecycle.

Three-phase, mathematically-exact narrow phase over **real triangle
meshes** (faces → vertices) supplied by
:class:`app.modules.clash.geometry.ClashGeometryProvider`:

1. **Broad phase** — uniform spatial hash (grid) over per-element world
   AABBs so only elements sharing a cell are pair-tested: O(n) buckets
   instead of O(n²). When real GLB geometry is available the AABBs come
   from the actual mesh extents; otherwise we fall back to the canonical
   ``oe_bim_element.bounding_box`` (DDC cad2data) so a model with no GLB
   still produces a (coarser, bbox-grade) result.
2. **Mid phase** — Oriented-Bounding-Box Separating Axis Theorem
   (15 candidate axes: 3+3 face normals + 9 edge cross products). A pure
   quick reject that culls the vast majority of AABB candidates before
   the expensive triangle test, with zero false negatives.
3. **Narrow phase** — pure-numpy, fully-vectorised **Möller (1997)
   triangle–triangle intersection** between the two elements' real
   triangles. A pair is a HARD clash iff at least one triangle pair
   actually intersects *and* the geometry-derived penetration estimate
   exceeds ``run.tolerance_m``; a CLEARANCE clash iff it is not hard and
   the *real measured* minimum surface-to-surface distance is within
   ``run.clearance_m`` (vectorised point-to-triangle, both directions).

Reference for the triangle test:
    Tomas Möller, "A Fast Triangle-Triangle Intersection Test",
    Journal of Graphics Tools, 2(2):25-30, 1997. The interval-overlap
    formulation on the line of intersection of the two triangle planes
    is used; coplanar pairs fall back to the 2-D edge/containment test
    of the same paper.

No IfcOpenShell, no native IFC — geometry is GLB triangles produced by
the DDC pipeline, or the canonical bbox fallback (the architecture guide §3).
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from itertools import combinations

import numpy as np
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bcf.schemas import PerspectiveCamera, TopicCreate, Vec3, ViewpointCreate
from app.modules.bcf.service import BCFService
from app.modules.clash.models import ClashResult, ClashRun
from app.modules.clash.repository import ClashRepository
from app.modules.clash.schemas import (
    CLASH_STATUSES,
    OPEN_STATUSES,
    ClashBCFExportRequest,
    ClashRunCreate,
)

try:  # The geometry loader is a sibling module; tolerate its absence.
    from app.modules.clash.geometry import ClashGeometryProvider, ElementGeom
except Exception:  # noqa: BLE001 — fall back to a structural stub for tests
    ClashGeometryProvider = None  # type: ignore[assignment,misc]
    ElementGeom = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Safety rails: a single sync run will not chew unbounded CPU/RAM.
_MAX_ELEMENTS = 60_000
_MAX_PAIRS = 3_000_000
_MAX_RESULTS = 25_000
# Bounding the cells an element can occupy stops one floor-sized slab from
# being inserted into tens of thousands of buckets.
_MAX_CELLS_PER_ELEMENT = 512
# Triangle budget per element. Above this the mesh is deterministically
# decimated to the largest-area triangles so a single pathological mesh
# (a tessellated dome, a re-bar cage) cannot blow the per-pair runtime.
_MAX_TRIS_PER_ELEMENT = 4000
# Numeric epsilon for the Möller plane / interval tests (metres scale).
_EPS = 1e-9

# Sentinel for "caller did not pass a precomputed value" — distinct from
# ``None`` which legitimately means "this element has no usable mesh".
_UNSET: object = object()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_bbox(bb: object) -> tuple[float, float, float, float, float, float] | None:
    """‌⁠‍Normalise either bbox dialect to ``(minx,miny,minz,maxx,maxy,maxz)``.

    The DDC pipeline writes the flat ``min_x..max_z`` form per element;
    some legacy paths use the nested ``{"min":{x,y,z},"max":{x,y,z}}``
    model-level shape. Anything malformed / zero-volume → ``None``.
    """
    if not isinstance(bb, dict):
        return None
    try:
        if "min_x" in bb:
            mn = (float(bb["min_x"]), float(bb["min_y"]), float(bb["min_z"]))
            mx = (float(bb["max_x"]), float(bb["max_y"]), float(bb["max_z"]))
        elif "min" in bb and "max" in bb:
            lo, hi = bb["min"], bb["max"]
            mn = (float(lo["x"]), float(lo["y"]), float(lo["z"]))
            mx = (float(hi["x"]), float(hi["y"]), float(hi["z"]))
        else:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    # Reject NaN/Inf and degenerate (non-positive volume) boxes.
    vals = (*mn, *mx)
    if any(not math.isfinite(v) for v in vals):
        return None
    if mx[0] <= mn[0] or mx[1] <= mn[1] or mx[2] <= mn[2]:
        return None
    return (mn[0], mn[1], mn[2], mx[0], mx[1], mx[2])


def _discipline_of(element: object) -> str:
    """‌⁠‍Resolve an element's coordination discipline.

    Prefer the persisted ``discipline`` column (the DDC pipeline already
    classifies on import); otherwise reuse bim_hub's keyword classifier on
    the element type so this module never re-implements the taxonomy.
    """
    d = (getattr(element, "discipline", None) or "").strip()
    if d:
        return d.capitalize()
    try:
        from app.modules.bim_hub.ifc_processor import _classify_discipline

        return _classify_discipline(getattr(element, "element_type", "") or "").capitalize()
    except Exception:  # noqa: BLE001 — classification is best-effort
        return "Unassigned"


def _type_of(element: object) -> str:
    """Element's category / family-type (the indexed ``element_type``)."""
    return (getattr(element, "element_type", None) or "").strip()


def _in_set(etype: str, disc: str, spec: dict | None) -> bool:
    """True iff an element belongs to a Navisworks-style selection set.

    ``spec`` is ``{"element_types": [...], "disciplines": [...]}``. The
    two lists are a *union*: every chip the user adds widens the set, so
    an element matches when its ``element_type`` is listed **or** its
    discipline is listed. An empty / missing spec matches nothing (the
    run-create guard already rejects empty sets for this mode).
    """
    if not spec:
        return False
    ets = spec.get("element_types") or []
    discs = spec.get("disciplines") or []
    return (etype in ets) or (disc in discs)


# ── Mesh helpers ───────────────────────────────────────────────────────────


def _triangles(geom: object) -> np.ndarray | None:
    """Resolve a geometry's triangle soup as an ``(T,3,3)`` float64 array.

    ``faces`` index into ``vertices``. Degenerate / empty meshes (no
    vertices, no faces, all-collinear triangles) return ``None`` so the
    caller treats the element as non-clashable rather than crashing.
    Meshes above :data:`_MAX_TRIS_PER_ELEMENT` are deterministically
    decimated to their largest-area triangles (stable sort, no RNG).
    """
    verts = getattr(geom, "vertices", None)
    faces = getattr(geom, "faces", None)
    if verts is None or faces is None:
        return None
    v = np.asarray(verts, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    if v.ndim != 2 or v.shape[0] < 3 or v.shape[1] != 3:
        return None
    if f.ndim != 2 or f.shape[0] < 1 or f.shape[1] != 3:
        return None
    if not np.isfinite(v).all():
        return None
    # Drop out-of-range indices defensively.
    in_range = (f >= 0).all(axis=1) & (f < v.shape[0]).all(axis=1)
    f = f[in_range]
    if f.shape[0] == 0:
        return None
    tris = v[f]  # (T,3,3)

    # Discard zero-area (degenerate / collinear) triangles — they cannot
    # bound a volume and break the Möller plane test.
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    cross = np.cross(e1, e2)
    area2 = np.einsum("ij,ij->i", cross, cross)  # 4·area²
    keep = area2 > (_EPS * _EPS)
    tris = tris[keep]
    if tris.shape[0] == 0:
        return None

    if tris.shape[0] > _MAX_TRIS_PER_ELEMENT:
        a2 = area2[keep]
        # Largest-area-first, stable so equal-area ties keep input order →
        # the decimation is fully deterministic across runs/platforms.
        order = np.argsort(-a2, kind="stable")[:_MAX_TRIS_PER_ELEMENT]
        order = np.sort(order)
        tris = tris[order]
    return tris


def _obb(geom: object) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """``(center(3,), axes(3,3) unit rows, half(3,))`` or ``None``."""
    c = getattr(geom, "obb_center", None)
    ax = getattr(geom, "obb_axes", None)
    hf = getattr(geom, "obb_half", None)
    if c is None or ax is None or hf is None:
        return None
    c = np.asarray(c, dtype=np.float64).reshape(3)
    ax = np.asarray(ax, dtype=np.float64).reshape(3, 3)
    hf = np.asarray(hf, dtype=np.float64).reshape(3)
    if not (np.isfinite(c).all() and np.isfinite(ax).all() and np.isfinite(hf).all()):
        return None
    return c, ax, hf


def _obb_sat_overlap(
    a: tuple[np.ndarray, np.ndarray, np.ndarray],
    b: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> bool:
    """OBB–OBB Separating Axis Theorem (15 axes) — True iff *not* separated.

    Classic Gottschalk SAT: 3 A-face axes, 3 B-face axes, 9 edge×edge
    cross products. A small epsilon is added to the cross-product test to
    absorb the near-parallel-edge degeneracy. This is a conservative
    quick *reject* — a False guarantees disjoint OBBs (and therefore
    disjoint meshes); a True only means "cannot rule out".
    """
    ca, ax_a, ha = a
    cb, ax_b, hb = b
    t = cb - ca
    # R[i,j] = A_i · B_j ; project the centre offset into A's frame.
    r = ax_a @ ax_b.T
    abs_r = np.abs(r) + 1e-12
    t_a = ax_a @ t

    # 3 axes — faces of A.
    for i in range(3):
        ra = ha[i]
        rb = hb[0] * abs_r[i, 0] + hb[1] * abs_r[i, 1] + hb[2] * abs_r[i, 2]
        if abs(t_a[i]) > ra + rb:
            return False
    # 3 axes — faces of B.
    t_b = ax_b @ t
    for j in range(3):
        ra = ha[0] * abs_r[0, j] + ha[1] * abs_r[1, j] + ha[2] * abs_r[2, j]
        rb = hb[j]
        if abs(t_b[j]) > ra + rb:
            return False
    # 9 axes — edge cross products A_i × B_j.
    for i in range(3):
        i1, i2 = (i + 1) % 3, (i + 2) % 3
        for j in range(3):
            j1, j2 = (j + 1) % 3, (j + 2) % 3
            ra = ha[i1] * abs_r[i2, j] + ha[i2] * abs_r[i1, j]
            rb = hb[j1] * abs_r[i, j2] + hb[j2] * abs_r[i, j1]
            sep = abs(t_a[i2] * r[i1, j] - t_a[i1] * r[i2, j])
            if sep > ra + rb:
                return False
    return True


# ── Möller (1997) triangle–triangle intersection (vectorised) ──────────────


def _coplanar_tri_tri(t1: np.ndarray, t2: np.ndarray, normal: np.ndarray) -> bool:
    """Coplanar fallback: project to 2-D, test edge crossings + containment.

    Möller §"Coplanar triangles": project both triangles onto the axis
    plane where the shared normal is largest, then run the 2-D
    edge-vs-edge intersection plus point-in-triangle containment.
    """
    ax = int(np.argmax(np.abs(normal)))
    i0, i1 = [(1, 2), (0, 2), (0, 1)][ax]
    p1 = t1[:, [i0, i1]]
    p2 = t2[:, [i0, i1]]

    def _seg_cross(a, b, c, d) -> bool:
        def _o(u, v, w):
            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])

        d1, d2 = _o(c, d, a), _o(c, d, b)
        d3, d4 = _o(a, b, c), _o(a, b, d)
        if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
            return True
        return False

    for ia in range(3):
        a, b = p1[ia], p1[(ia + 1) % 3]
        for ib in range(3):
            c, d = p2[ib], p2[(ib + 1) % 3]
            if _seg_cross(a, b, c, d):
                return True

    def _inside(pt, tri) -> bool:
        d = tri - pt
        s = (
            d[0, 0] * d[1, 1] - d[0, 1] * d[1, 0],
            d[1, 0] * d[2, 1] - d[1, 1] * d[2, 0],
            d[2, 0] * d[0, 1] - d[2, 1] * d[0, 0],
        )
        return (s[0] >= 0 and s[1] >= 0 and s[2] >= 0) or (
            s[0] <= 0 and s[1] <= 0 and s[2] <= 0
        )

    return _inside(p1[0], p2) or _inside(p2[0], p1)


def _tri_tri_intersect_mask(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Vectorised Möller (1997): ``(len(A), len(B))`` boolean intersect mask.

    For every (a, b) triangle pair this computes the canonical Möller
    test: signed distances of each triangle's vertices to the *other*
    triangle's plane (early reject if all same-sign & non-zero), then the
    overlap of the two intervals carved on the line L = plane1 ∩ plane2.
    Coplanar pairs are routed to :func:`_coplanar_tri_tri`.

    Broadcasting shape convention: A → axis 0 (i), B → axis 1 (j).

    The signed point–plane distances are **normalised** (divided by the
    triangle normal's magnitude) so the near-zero snap below is a true
    Euclidean ~1 nm tolerance, scale-consistent across triangle sizes. A
    raw Möller ``n·v + d`` is scaled by ``|n|``; for a small / thin
    (sliver) triangle ``|n|`` is tiny, so an *absolute* epsilon on the
    raw value behaves like a huge geometric tolerance and two surfaces
    several micrometres apart get mis-snapped onto the plane → falsely
    flagged coplanar → a phantom clash. Normalising removes that
    false-positive class and makes the result independent of triangle
    scale and of floating-point summation order (deterministic across
    numpy builds / platforms). ``_interval_overlap`` consumes only
    per-triangle distance *ratios*, so this per-triangle rescale leaves
    the interval test bit-identical — it changes only the (now correct)
    sign / coplanar / reject decision.

    An exact per-triangle AABB prefilter runs first: two triangles whose
    axis-aligned boxes are disjoint provably cannot intersect, so the
    (normalised) Möller test would reject them anyway. Only the
    AABB-overlapping candidate pairs therefore have their signed
    distances / interval test computed — this avoids materialising the
    dense ``(na, nb, 3)`` distance tensors for the (usually vast)
    majority of non-overlapping pairs, cutting the dominant cost and
    bounding peak memory, while remaining consistent with the normalised
    plane test (both use the same ~1 nm geometric scale).
    """
    na, nb = A.shape[0], B.shape[0]
    out = np.zeros((na, nb), dtype=bool)
    if na == 0 or nb == 0:
        return out

    # --- Per-triangle plane (cheap, O(na)+O(nb)).
    n1 = np.cross(A[:, 1] - A[:, 0], A[:, 2] - A[:, 0])  # (na,3)
    d1 = -np.einsum("ij,ij->i", n1, A[:, 0])  # (na,)
    n2 = np.cross(B[:, 1] - B[:, 0], B[:, 2] - B[:, 0])  # (nb,3)
    d2 = -np.einsum("ij,ij->i", n2, B[:, 0])  # (nb,)

    # --- Exact AABB prefilter → candidate (a,b) index pairs only.
    a_lo = A.min(axis=1)  # (na,3)
    a_hi = A.max(axis=1)
    b_lo = B.min(axis=1)  # (nb,3)
    b_hi = B.max(axis=1)
    overlap = (
        (a_lo[:, None, 0] <= b_hi[None, :, 0] + _EPS)
        & (b_lo[None, :, 0] <= a_hi[:, None, 0] + _EPS)
        & (a_lo[:, None, 1] <= b_hi[None, :, 1] + _EPS)
        & (b_lo[None, :, 1] <= a_hi[:, None, 1] + _EPS)
        & (a_lo[:, None, 2] <= b_hi[None, :, 2] + _EPS)
        & (b_lo[None, :, 2] <= a_hi[:, None, 2] + _EPS)
    )
    ai, bj = np.where(overlap)
    if ai.size == 0:
        return out

    # --- Signed distances on the candidate pairs only → (P,3) each.
    a_c = A[ai]  # (P,3,3)
    b_c = B[bj]
    n1c = n1[ai]
    n2c = n2[bj]
    # Per-triangle inverse normal magnitude → true Euclidean point-plane
    # distance. ``_triangles`` discards zero-area triangles (area² > _EPS²)
    # so |n| ≥ _EPS > 0 and the reciprocal is finite.
    inv1c = 1.0 / np.sqrt(np.einsum("pk,pk->p", n1c, n1c))  # (P,)
    inv2c = 1.0 / np.sqrt(np.einsum("pk,pk->p", n2c, n2c))  # (P,)
    # B's 3 verts vs A's plane; A's 3 verts vs B's plane (normalised).
    dB = (np.einsum("pk,pvk->pv", n1c, b_c) + d1[ai][:, None]) * inv1c[:, None]
    dB = np.where(np.abs(dB) < _EPS, 0.0, dB)
    sB = np.sign(dB)
    same_B = (sB[:, 0] == sB[:, 1]) & (sB[:, 1] == sB[:, 2]) & (sB[:, 0] != 0)
    dA = (np.einsum("pk,pvk->pv", n2c, a_c) + d2[bj][:, None]) * inv2c[:, None]
    dA = np.where(np.abs(dA) < _EPS, 0.0, dA)
    sA = np.sign(dA)
    same_A = (sA[:, 0] == sA[:, 1]) & (sA[:, 1] == sA[:, 2]) & (sA[:, 0] != 0)

    # Trivial reject: one triangle wholly on one side of the other's plane.
    cand = ~(same_B | same_A)
    coplanar = (np.abs(dB).sum(axis=-1) < _EPS) & (np.abs(dA).sum(axis=-1) < _EPS)

    m_int = cand & ~coplanar
    if m_int.any():
        out[ai[m_int], bj[m_int]] = _interval_overlap(
            a_c[m_int], b_c[m_int], n1c[m_int], n2c[m_int],
            dA[m_int], dB[m_int],
        )

    # Coplanar pairs (rare) handled with the 2-D fallback, one at a time.
    for p in np.where(cand & coplanar)[0].tolist():
        if _coplanar_tri_tri(a_c[p], b_c[p], n1c[p]):
            out[ai[p], bj[p]] = True
    return out


def _interval_overlap(
    A: np.ndarray,
    B: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
    distA: np.ndarray,
    distB: np.ndarray,
) -> np.ndarray:
    """Möller interval test on L = plane(A) ∩ plane(B).

    Direction of L is ``n1 × n2``. Each triangle's three vertices
    projected onto L yield a parameter; the two vertices on the *same*
    side of the other plane are interpolated with the lone vertex to give
    the scalar interval the triangle carves on L. The triangles intersect
    iff those two 1-D intervals overlap. Fully vectorised over the P
    surviving pairs.
    """
    d = np.cross(n1, n2)  # line direction, (P,3)
    ax = np.argmax(np.abs(d), axis=1)  # dominant component → projection axis

    # Per pair p, take the ax[p]-th coordinate of each of the 3 vertices.
    # A,B are (P,3verts,3coords); take_along_axis on the coord axis → (P,3).
    sel = ax[:, None, None]  # (P,1,1)
    pA = np.take_along_axis(A, sel, axis=2)[:, :, 0]  # (P,3)
    pB = np.take_along_axis(B, sel, axis=2)[:, :, 0]  # (P,3)

    def _interval(p: np.ndarray, dist: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # The vertex whose sign differs from the other two is the "lone"
        # one; choose its index per-pair, then interpolate the two
        # crossing points along the triangle edges meeting it.
        s = np.sign(dist)
        s = np.where(dist == 0.0, 0.0, s)
        # The "lone" vertex is the one whose sign differs from the other
        # two (Möller). Fully vectorised: default 0; if s0==s1 the odd one
        # out is vertex 2; else if s0==s2 it is vertex 1; else vertex 0.
        lone = np.where(
            s[:, 0] == s[:, 1], 2, np.where(s[:, 0] == s[:, 2], 1, 0)
        ).astype(np.int64)
        idx = np.arange(p.shape[0])
        o = lone
        a1 = (o + 1) % 3
        a2 = (o + 2) % 3
        po, pa1, pa2 = p[idx, o], p[idx, a1], p[idx, a2]
        do, da1, da2 = dist[idx, o], dist[idx, a1], dist[idx, a2]
        # Two crossing points: edge (o→a1) and edge (o→a2).
        denom1 = do - da1
        denom2 = do - da2
        denom1 = np.where(np.abs(denom1) < _EPS, _EPS, denom1)
        denom2 = np.where(np.abs(denom2) < _EPS, _EPS, denom2)
        t1 = po + (pa1 - po) * (do / denom1)
        t2 = po + (pa2 - po) * (do / denom2)
        lo = np.minimum(t1, t2)
        hi = np.maximum(t1, t2)
        return lo, hi

    loA, hiA = _interval(pA, distA)
    loB, hiB = _interval(pB, distB)
    # Closed-interval overlap (touching counts as intersecting at this
    # stage; the penetration-depth gate downstream removes mere touches).
    return (loA <= hiB + _EPS) & (loB <= hiA + _EPS)


# ── Vectorised point ↔ triangle distance (clearance phase) ─────────────────


def _point_tri_dist2(pts: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Squared distance from each point in ``pts`` (P,3) to triangle ``tri``.

    Ericson, *Real-Time Collision Detection* §5.1.5 closest-point-on-
    triangle via Voronoi regions, vectorised over the P query points.
    """
    a, b, c = tri[0], tri[1], tri[2]
    ab = b - a
    ac = c - a
    ap = pts - a  # (P,3)

    d1 = ap @ ab
    d2 = ap @ ac
    bp = pts - b
    d3 = bp @ ab
    d4 = bp @ ac
    cp = pts - c
    d5 = cp @ ab
    d6 = cp @ ac

    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4

    closest = np.empty_like(pts)

    # Region A
    m = (d1 <= 0) & (d2 <= 0)
    closest[m] = a
    done = m.copy()
    # Region B
    m = (~done) & (d3 >= 0) & (d4 <= d3)
    closest[m] = b
    done |= m
    # Region C
    m = (~done) & (d6 >= 0) & (d5 <= d6)
    closest[m] = c
    done |= m
    # Edge AB
    m = (~done) & (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    if m.any():
        denom = d1[m] - d3[m]
        v = np.where(np.abs(denom) < _EPS, 0.0, d1[m] / np.where(denom == 0, _EPS, denom))
        closest[m] = a + v[:, None] * ab
    done |= m
    # Edge AC
    m = (~done) & (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    if m.any():
        denom = d2[m] - d6[m]
        v = np.where(np.abs(denom) < _EPS, 0.0, d2[m] / np.where(denom == 0, _EPS, denom))
        closest[m] = a + v[:, None] * ac
    done |= m
    # Edge BC
    m = (~done) & (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    if m.any():
        denom = (d4[m] - d3[m]) + (d5[m] - d6[m])
        w = np.where(np.abs(denom) < _EPS, 0.0, (d4[m] - d3[m]) / np.where(denom == 0, _EPS, denom))
        closest[m] = b + w[:, None] * (c - b)
    done |= m
    # Interior (barycentric)
    m = ~done
    if m.any():
        denom = va[m] + vb[m] + vc[m]
        denom = np.where(np.abs(denom) < _EPS, _EPS, denom)
        v = vb[m] / denom
        w = vc[m] / denom
        closest[m] = a + ab * v[:, None] + ac * w[:, None]

    diff = pts - closest
    return np.einsum("ij,ij->i", diff, diff)


def _min_mesh_distance(
    A: np.ndarray, B: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    """Real minimum surface gap between two triangle meshes (sampled).

    Symmetric: every vertex of A is tested against every triangle of B
    and vice-versa, returning the smallest distance plus the closest
    point pair (for the clash centroid). This is a *measured* surface
    gap — not a bounding-box gap — so a clearance result reflects the
    true free space between the two solids.
    """
    vA = A.reshape(-1, 3)
    vB = B.reshape(-1, 3)
    best = math.inf
    pa = np.zeros(3)
    pb = np.zeros(3)

    for tri in B:
        d2 = _point_tri_dist2(vA, tri)
        k = int(np.argmin(d2))
        if d2[k] < best:
            best = float(d2[k])
            pa = vA[k]
            # Recover closest point on this tri for the centroid.
            pb = _closest_on_tri(vA[k], tri)
    for tri in A:
        d2 = _point_tri_dist2(vB, tri)
        k = int(np.argmin(d2))
        if d2[k] < best:
            best = float(d2[k])
            pb = vB[k]
            pa = _closest_on_tri(vB[k], tri)
    return math.sqrt(max(best, 0.0)), pa, pb


def _closest_on_tri(p: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Single closest point on ``tri`` to ``p`` (scalar wrapper)."""
    out = np.empty((1, 3))
    pp = p.reshape(1, 3)
    # Reuse the vectorised routine's geometry by reconstructing closest.
    a, b, c = tri[0], tri[1], tri[2]
    ab, ac, ap = b - a, c - a, (pp - a)[0]
    d1, d2 = ap @ ab, ap @ ac
    if d1 <= 0 and d2 <= 0:
        return a
    bp = (pp - b)[0]
    d3, d4 = bp @ ab, bp @ ac
    if d3 >= 0 and d4 <= d3:
        return b
    cp = (pp - c)[0]
    d5, d6 = cp @ ab, cp @ ac
    if d6 >= 0 and d5 <= d6:
        return c
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3) if abs(d1 - d3) > _EPS else 0.0
        return a + v * ab
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        v = d2 / (d2 - d6) if abs(d2 - d6) > _EPS else 0.0
        return a + v * ac
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        den = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / den if abs(den) > _EPS else 0.0
        return b + w * (c - b)
    den = va + vb + vc
    den = den if abs(den) > _EPS else _EPS
    v, w = vb / den, vc / den
    out[0] = a + ab * v + ac * w
    return out[0]


def _penetration_depth(
    A: np.ndarray, B: np.ndarray, mask: np.ndarray
) -> tuple[float, np.ndarray]:
    """Honest penetration estimate from the *actually intersecting* tris.

    Collect the vertices of every triangle pair flagged intersecting,
    take the overlap extent of the two intersecting-vertex point sets
    along each world axis, and return the **minimum** axis overlap (the
    shallowest direction you'd have to separate the solids — the same
    "tightest axis" semantics the bbox engine used, but now derived from
    real intersecting geometry rather than whole-element AABBs). The
    second value is the centroid of those intersecting vertices.

    This is an approximation (axis-aligned, vertex-set based), documented
    as such: it is conservative and monotone in true penetration, which
    is exactly what the ``tolerance_m`` gate needs.
    """
    ai, bj = np.where(mask)
    if ai.size == 0:
        return 0.0, np.zeros(3)
    pa = A[ai].reshape(-1, 3)
    pb = B[bj].reshape(-1, 3)
    lo = np.maximum(pa.min(axis=0), pb.min(axis=0))
    hi = np.minimum(pa.max(axis=0), pb.max(axis=0))
    # Per-axis overlap of the two intersecting-vertex point sets, clamped
    # at 0 (a negative means the sets are disjoint on that axis — no
    # penetration contribution there). The penetration depth is the
    # *minimum* axis overlap: the shallowest direction along which the
    # solids would have to be separated. For a coincident-face touch the
    # separating axis has ~0 overlap → pen ≈ 0 → correctly below
    # tolerance, so a slab-on-wall cosmetic contact is NOT a hard clash,
    # while a real interpenetration yields the true tightest-axis depth.
    overlap = np.clip(hi - lo, 0.0, None)
    pen = float(overlap.min())
    centroid = np.vstack([pa, pb]).mean(axis=0)
    return pen, centroid


class ClashService:
    """Stateless clash orchestration over one project's BIM models."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ClashRepository(session)

    # ── Run lifecycle ──────────────────────────────────────────────────

    async def create_run(
        self, project_id: uuid.UUID, data: ClashRunCreate, user_id: str
    ) -> ClashRun:
        """Persist + execute a clash run synchronously, return it complete."""
        models = await self.repo.models_for_project(project_id)
        valid_ids = {m.id for m in models}
        requested = [mid for mid in data.model_ids if mid in valid_ids]
        if not requested:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="None of the requested models belong to this project",
            )
        if data.mode not in (
            "cross_discipline", "all", "selected", "selection_sets"
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown clash mode '{data.mode}'",
            )
        set_a = set_b = None
        if data.mode == "selection_sets":
            if (
                data.set_a is None
                or data.set_b is None
                or data.set_a.is_empty
                or data.set_b.is_empty
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="selection_sets mode requires a non-empty "
                    "Set A and Set B (pick at least one type or "
                    "discipline for each).",
                )
            set_a = data.set_a.model_dump()
            set_b = data.set_b.model_dump()

        name = (data.name or "").strip() or (
            f"Clash run {_now():%Y-%m-%d %H:%M}"
        )
        run = ClashRun(
            project_id=project_id,
            name=name,
            model_ids=[str(m) for m in requested],
            tolerance_m=data.tolerance_m,
            clearance_m=data.clearance_m,
            mode=data.mode,
            discipline_filter=data.discipline_filter,
            set_a=set_a,
            set_b=set_b,
            status="running",
            created_by=str(user_id),
            summary={},
        )
        self.repo.add_run(run)
        await self.session.flush()

        try:
            geoms = await self._load_geometry(requested)
            elements = await self.repo.elements_with_geometry(requested)
            results = self._detect(run, elements, geoms)
            self.repo.add_results(results)
            run.element_count = len(elements)
            run.total_clashes = len(results)
            run.summary = _build_summary(results)
            run.status = "completed"
            run.completed_at = _now()
        except Exception as exc:  # noqa: BLE001 — surface, don't 500 the run
            logger.exception("Clash run %s failed", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"[:2000]
            run.completed_at = _now()
        await self.session.flush()
        return run

    async def _load_geometry(
        self, model_ids: list[uuid.UUID]
    ) -> dict[str, object]:
        """Best-effort load of real GLB triangle meshes per element.

        Returns ``{element_id: ElementGeom}``. If the geometry provider
        is unavailable (sibling module not yet present) or a model has no
        GLB, the dict is simply missing those elements and the broad
        phase transparently falls back to the canonical bbox.
        """
        if ClashGeometryProvider is None:
            return {}
        merged: dict[str, object] = {}
        provider = ClashGeometryProvider()
        for mid in model_ids:
            try:
                part = await provider.load(self.session, mid)
            except Exception:  # noqa: BLE001 — degrade to bbox for this model
                logger.exception("Geometry load failed for model %s", mid)
                continue
            if part:
                merged.update(part)
        return merged

    async def list_runs(self, project_id: uuid.UUID) -> list[ClashRun]:
        return await self.repo.list_runs(project_id)

    async def get_run(
        self, project_id: uuid.UUID, run_id: uuid.UUID
    ) -> ClashRun:
        run = await self.repo.get_run(project_id, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Clash run not found"
            )
        return run

    async def delete_run(
        self, project_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        run = await self.get_run(project_id, run_id)
        await self.repo.delete_run(run)

    # ── Engine ─────────────────────────────────────────────────────────

    def _detect(
        self,
        run: ClashRun,
        elements: list[object],
        geoms: dict[str, object] | None = None,
    ) -> list[ClashResult]:
        """Broad (grid) → mid (OBB-SAT) → narrow (Möller tri-tri) pipeline."""
        geoms = geoms or {}

        # Per-element record: (element, aabb, discipline, ElementGeom|None).
        # Deterministic ordering: stable_id then element_id, no RNG.
        ordered = sorted(
            elements[:_MAX_ELEMENTS],
            key=lambda e: (
                str(getattr(e, "stable_id", "") or ""),
                str(getattr(e, "id", "") or ""),
            ),
        )

        boxes: list[
            tuple[object, tuple[float, float, float, float, float, float], str, object]
        ] = []
        for el in ordered:
            g = geoms.get(str(getattr(el, "id", "")))
            aabb = None
            if g is not None:
                ga = getattr(g, "aabb", None)
                if ga is not None and len(ga) == 6 and all(math.isfinite(v) for v in ga):
                    if ga[3] > ga[0] and ga[4] > ga[1] and ga[5] > ga[2]:
                        aabb = (
                            float(ga[0]), float(ga[1]), float(ga[2]),
                            float(ga[3]), float(ga[4]), float(ga[5]),
                        )
            if aabb is None:
                aabb = _norm_bbox(getattr(el, "bounding_box", None))
            if aabb is None:
                continue
            boxes.append((el, aabb, _discipline_of(el), g))
        if len(boxes) < 2:
            return []

        # One-time per-run mesh extraction. ``_triangles`` / ``_obb`` are
        # pure deterministic functions of an element's mesh, but in a
        # dense single-model run one element participates in dozens of
        # candidate pairs — extracting per pair re-ran the whole triangle
        # soup (index, cross-product, area filter, stable-sort decimation)
        # O(pairs) times. Doing it once per element here makes it O(n)
        # with byte-identical output (pure memoisation — the narrow-phase
        # maths is untouched), which is the bulk of the runtime win.
        tri_by_idx: list[object] = [
            (_triangles(g) if g is not None else None) for _, _, _, g in boxes
        ]
        obb_by_idx: list[object] = [
            (_obb(g) if g is not None else None) for _, _, _, g in boxes
        ]

        # Cell size = 60th-percentile element extent, clamped to a sane
        # band so neither tiny bolts nor whole storeys distort the grid.
        extents = sorted(
            max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) for _, bb, _, _ in boxes
        )
        cell = extents[int(len(extents) * 0.6)]
        cell = min(max(cell, 0.5), 10.0)

        grid: dict[tuple[int, int, int], list[int]] = {}
        for idx, (_, bb, _, _) in enumerate(boxes):
            x0, y0, z0 = (int(math.floor(bb[i] / cell)) for i in (0, 1, 2))
            x1, y1, z1 = (int(math.floor(bb[i] / cell)) for i in (3, 4, 5))
            span = (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1)
            if span > _MAX_CELLS_PER_ELEMENT:
                cx = (x0 + x1) // 2
                cy = (y0 + y1) // 2
                cz = (z0 + z1) // 2
                grid.setdefault((cx, cy, cz), []).append(idx)
                continue
            for gx in range(x0, x1 + 1):
                for gy in range(y0, y1 + 1):
                    for gz in range(z0, z1 + 1):
                        grid.setdefault((gx, gy, gz), []).append(idx)

        dfilter: set[frozenset[str]] | None = None
        if run.mode == "selected" and run.discipline_filter:
            dfilter = {
                frozenset((str(a), str(b))) for a, b in run.discipline_filter
            }
        # Navisworks-style selection sets: only A×B cross pairs survive.
        sel_a = run.set_a if run.mode == "selection_sets" else None
        sel_b = run.set_b if run.mode == "selection_sets" else None

        seen: set[tuple[int, int]] = set()
        results: list[ClashResult] = []
        pairs_tested = 0
        tol = float(run.tolerance_m)
        clr = float(run.clearance_m)

        for bucket in grid.values():
            if len(bucket) < 2:
                continue
            for i, j in combinations(sorted(bucket), 2):
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                pairs_tested += 1
                if pairs_tested > _MAX_PAIRS:
                    logger.warning(
                        "Clash run %s hit the %d-pair cap", run.id, _MAX_PAIRS
                    )
                    return results
                ea, ba, da, ga = boxes[key[0]]
                eb, bb_, db, gb = boxes[key[1]]
                if ea.id == eb.id:  # type: ignore[attr-defined]
                    continue
                # Discipline gating.
                if run.mode == "cross_discipline" and da == db:
                    continue
                if dfilter is not None and frozenset((da, db)) not in dfilter:
                    continue
                # Selection-set gating — keep iff one element is in Set A
                # and the other is in Set B (strictly cross, e.g.
                # walls × pipes; never wall × wall).
                if sel_a is not None:
                    ta_ = _type_of(ea)
                    tb_ = _type_of(eb)
                    if not (
                        (_in_set(ta_, da, sel_a) and _in_set(tb_, db, sel_b))
                        or (_in_set(ta_, da, sel_b) and _in_set(tb_, db, sel_a))
                    ):
                        continue

                row = self._test_pair(
                    run, ea, ba, da, ga, eb, bb_, db, gb, tol, clr,
                    triA=tri_by_idx[key[0]], triB=tri_by_idx[key[1]],
                    oa=obb_by_idx[key[0]], ob=obb_by_idx[key[1]],
                )
                if row is not None:
                    results.append(row)
                    if len(results) >= _MAX_RESULTS:
                        logger.warning(
                            "Clash run %s hit the %d-result cap",
                            run.id, _MAX_RESULTS,
                        )
                        return results
        return results

    @staticmethod
    def _aabb_overlap(
        ba: tuple[float, float, float, float, float, float],
        bb: tuple[float, float, float, float, float, float],
    ) -> bool:
        return (
            ba[0] <= bb[3]
            and bb[0] <= ba[3]
            and ba[1] <= bb[4]
            and bb[1] <= ba[4]
            and ba[2] <= bb[5]
            and bb[2] <= ba[5]
        )

    @classmethod
    def _test_pair(
        cls,
        run: ClashRun,
        ea: object,
        ba: tuple[float, float, float, float, float, float],
        da: str,
        ga: object,
        eb: object,
        bb: tuple[float, float, float, float, float, float],
        db: str,
        gb: object,
        tol: float,
        clr: float,
        triA: object = _UNSET,
        triB: object = _UNSET,
        oa: object = _UNSET,
        ob: object = _UNSET,
    ) -> ClashResult | None:
        """Mid + narrow phase: classify one element pair, or ``None``.

        Falls back to the legacy exact-AABB classification when *either*
        element lacks a real mesh (bbox-only model) — preserving the old
        behaviour for un-tessellated data while giving mesh-grade
        precision wherever GLB geometry exists.

        ``triA``/``triB``/``oa``/``ob`` may be passed pre-extracted by the
        caller. :func:`_triangles` / :func:`_obb` are pure deterministic
        functions of the element mesh, and a single element participates
        in many candidate pairs, so :meth:`_detect` extracts each once and
        threads the cached value here. When a value is left ``_UNSET``
        (e.g. the unit tests that call this method directly) it is
        extracted here exactly as before — the result is byte-identical
        either way; only redundant recomputation is removed.
        """
        if triA is _UNSET:
            triA = _triangles(ga) if ga is not None else None
        if triB is _UNSET:
            triB = _triangles(gb) if gb is not None else None

        if triA is None or triB is None:
            return cls._test_pair_bbox(
                run, ea, ba, da, eb, bb, db, tol, clr, ga, gb
            )

        # Broad AABB re-check (grid buckets are conservative).
        if not cls._aabb_overlap(ba, bb):
            if clr <= 0:
                return None

        # Mid phase: OBB-SAT quick reject (zero false negatives).
        if oa is _UNSET:
            oa = _obb(ga) if ga is not None else None
        if ob is _UNSET:
            ob = _obb(gb) if gb is not None else None
        sat_separated = False
        if oa is not None and ob is not None:
            if not _obb_sat_overlap(oa, ob):
                sat_separated = True

        clash_type = ""
        penetration = 0.0
        distance = 0.0
        cx = cy = cz = 0.0

        if not sat_separated:
            mask = _tri_tri_intersect_mask(triA, triB)
            if mask.any():
                pen, centroid = _penetration_depth(triA, triB, mask)
                if pen > tol:
                    clash_type = "hard"
                    penetration = pen
                    cx, cy, cz = (
                        float(centroid[0]),
                        float(centroid[1]),
                        float(centroid[2]),
                    )

        if not clash_type and clr > 0:
            dist, pa, pb = _min_mesh_distance(triA, triB)
            if 1e-9 < dist <= clr:
                clash_type = "clearance"
                distance = dist
                mid = (np.asarray(pa) + np.asarray(pb)) / 2.0
                cx, cy, cz = float(mid[0]), float(mid[1]), float(mid[2])

        if not clash_type:
            return None

        return cls._row(
            run, ea, da, eb, db, clash_type, penetration, distance,
            cx, cy, cz, ga, gb,
        )

    @classmethod
    def _test_pair_bbox(
        cls,
        run: ClashRun,
        ea: object,
        ba: tuple[float, float, float, float, float, float],
        da: str,
        eb: object,
        bb: tuple[float, float, float, float, float, float],
        db: str,
        tol: float,
        clr: float,
        ga: object = None,
        gb: object = None,
    ) -> ClashResult | None:
        """Legacy exact-AABB classification (no-GLB fallback path)."""
        ox = min(ba[3], bb[3]) - max(ba[0], bb[0])
        oy = min(ba[4], bb[4]) - max(ba[1], bb[1])
        oz = min(ba[5], bb[5]) - max(ba[2], bb[2])

        clash_type = ""
        penetration = 0.0
        distance = 0.0
        if ox > 0 and oy > 0 and oz > 0:
            penetration = min(ox, oy, oz)
            if penetration <= tol:
                return None
            clash_type = "hard"
            cx = (max(ba[0], bb[0]) + min(ba[3], bb[3])) / 2
            cy = (max(ba[1], bb[1]) + min(ba[4], bb[4])) / 2
            cz = (max(ba[2], bb[2]) + min(ba[5], bb[5])) / 2
        elif clr > 0:
            sx = max(ba[0] - bb[3], bb[0] - ba[3], 0.0)
            sy = max(ba[1] - bb[4], bb[1] - ba[4], 0.0)
            sz = max(ba[2] - bb[5], bb[2] - ba[5], 0.0)
            distance = math.sqrt(sx * sx + sy * sy + sz * sz)
            if distance <= 1e-9 or distance > clr:
                return None
            clash_type = "clearance"
            cx = ((ba[0] + ba[3]) / 2 + (bb[0] + bb[3]) / 2) / 2
            cy = ((ba[1] + ba[4]) / 2 + (bb[1] + bb[4]) / 2) / 2
            cz = ((ba[2] + ba[5]) / 2 + (bb[2] + bb[5]) / 2) / 2
        else:
            return None

        return cls._row(
            run, ea, da, eb, db, clash_type, penetration, distance,
            cx, cy, cz, ga, gb,
        )

    @staticmethod
    def _storey_of(geom: object) -> int | None:
        """Resolve an element's storey index from its ElementGeom.

        The geometry loader clusters a level index from real geometry Z
        onto ``ElementGeom.storey``. Absent (no GLB / loader did not set
        it / older loader) → ``None`` so the row + level matrix degrade
        gracefully without ever crashing.
        """
        if geom is None:
            return None
        s = getattr(geom, "storey", None)
        if s is None:
            return None
        try:
            return int(s)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _row(
        cls,
        run: ClashRun,
        ea: object,
        da: str,
        eb: object,
        db: str,
        clash_type: str,
        penetration: float,
        distance: float,
        cx: float,
        cy: float,
        cz: float,
        ga: object = None,
        gb: object = None,
    ) -> ClashResult:
        """Build a :class:`ClashResult` row (single construction point)."""
        return ClashResult(
            run_id=run.id,
            a_element_id=ea.id,  # type: ignore[attr-defined]
            b_element_id=eb.id,  # type: ignore[attr-defined]
            a_stable_id=str(getattr(ea, "stable_id", "") or ""),
            b_stable_id=str(getattr(eb, "stable_id", "") or ""),
            a_name=(getattr(ea, "name", None) or getattr(ea, "element_type", "") or "")[:500],
            b_name=(getattr(eb, "name", None) or getattr(eb, "element_type", "") or "")[:500],
            a_discipline=da[:64] or "Unassigned",
            b_discipline=db[:64] or "Unassigned",
            a_element_type=(getattr(ea, "element_type", "") or "")[:100],
            b_element_type=(getattr(eb, "element_type", "") or "")[:100],
            a_model_id=ea.model_id,  # type: ignore[attr-defined]
            b_model_id=eb.model_id,  # type: ignore[attr-defined]
            a_storey=cls._storey_of(ga),
            b_storey=cls._storey_of(gb),
            clash_type=clash_type,
            penetration_m=round(penetration, 4),
            distance_m=round(distance, 4),
            cx=round(cx, 4),
            cy=round(cy, 4),
            cz=round(cz, 4),
            status="new",
        )

    # ── Result triage ──────────────────────────────────────────────────

    async def update_result(
        self,
        project_id: uuid.UUID,
        run_id: uuid.UUID,
        result_id: uuid.UUID,
        *,
        new_status: str | None,
        assigned_to: str | None,
    ) -> ClashResult:
        run = await self.get_run(project_id, run_id)
        result = await self.repo.get_result(run_id, result_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Clash not found"
            )
        if new_status is not None:
            if new_status not in CLASH_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid clash status '{new_status}'",
                )
            result.status = new_status
        if assigned_to is not None:
            result.assigned_to = assigned_to or None
        await self.session.flush()
        # Refresh the cached status counts so the dashboard KPI stays true.
        rows, _ = await self.repo.list_results(run_id, limit=_MAX_RESULTS)
        run.summary = _build_summary(list(rows))
        await self.session.flush()
        return result

    async def list_results(self, run_id: uuid.UUID, **kw: object):
        return await self.repo.list_results(run_id, **kw)  # type: ignore[arg-type]

    # ── BCF export ─────────────────────────────────────────────────────

    async def export_bcf(
        self,
        project_id: uuid.UUID,
        run_id: uuid.UUID,
        data: ClashBCFExportRequest,
        author: str,
        user_id: str,
    ) -> tuple[int, int]:
        """Mirror selected clashes into native BCF topics. (exported, skipped)."""
        run = await self.get_run(project_id, run_id)
        selection = await self.repo.results_for_export(run_id, data.result_ids)
        bcf = BCFService(self.session)
        exported = 0
        skipped = 0
        for r in selection:
            if r.bcf_topic_guid:
                skipped += 1
                continue
            priority = "High" if r.clash_type == "hard" else "Normal"
            desc = (
                f"{r.clash_type.capitalize()} clash · "
                f"{r.a_discipline} ↔ {r.b_discipline}\n"
                f"A: {r.a_name} ({r.a_stable_id})\n"
                f"B: {r.b_name} ({r.b_stable_id})\n"
                f"Penetration: {r.penetration_m} m · "
                f"Clearance gap: {r.distance_m} m\n"
                f"Location: ({r.cx}, {r.cy}, {r.cz})\n"
                f"Source: clash run '{run.name}'"
            )
            topic = await bcf.create_topic(
                project_id,
                TopicCreate(
                    title=f"Clash: {r.a_name} × {r.b_name}"[:500],
                    description=desc,
                    topic_type="Clash",
                    topic_status="Open",
                    priority=priority,
                    labels=[r.clash_type, r.a_discipline, r.b_discipline],
                    bim_model_id=str(r.a_model_id),
                ),
                author=author,
                user_id=str(user_id),
            )
            # Camera pulled back along +XYZ looking at the clash centroid.
            eye = Vec3(x=r.cx + 8.0, y=r.cy - 8.0, z=r.cz + 8.0)
            look = Vec3(x=-1.0, y=1.0, z=-1.0)
            await bcf.add_viewpoint(
                project_id,
                topic.id,
                ViewpointCreate(
                    perspective_camera=PerspectiveCamera(
                        camera_view_point=eye,
                        camera_direction=look,
                        camera_up_vector=Vec3(x=0.0, y=0.0, z=1.0),
                        field_of_view=60.0,
                    ),
                    element_stable_ids=[r.a_stable_id, r.b_stable_id],
                ),
                str(user_id),
            )
            r.bcf_topic_guid = topic.guid
            exported += 1
        await self.session.flush()
        return exported, skipped


def _build_summary(results: list[ClashResult]) -> dict:
    """Aggregate results into the cached dashboard payload.

    Produces two coordination grids with the *identical* cell shape so
    the frontend renders them with one component:

    * ``matrix`` — discipline×discipline (string keys). Correct for true
      multi-discipline federated uploads. Untouched by the storey work.
    * ``level_matrix`` — storey×storey (integer keys). The meaningful
      view for the common single-discipline intra-model run, where the
      discipline matrix collapses to a useless 1×1. Built only from
      result rows whose *both* storeys are known (non-NULL); a clash with
      an unknown storey is still counted in every other aggregate.

    ``storeys`` is the sorted distinct set of storey indices appearing in
    the level matrix (its row/column axis).
    """
    disciplines: set[str] = set()
    cell: dict[tuple[str, str], dict[str, int]] = {}
    storeys: set[int] = set()
    level_cell: dict[tuple[int, int], dict[str, int]] = {}
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in results:
        a, b = sorted((r.a_discipline or "Unassigned", r.b_discipline or "Unassigned"))
        disciplines.add(a)
        disciplines.add(b)
        c = cell.setdefault((a, b), {"count": 0, "open_count": 0})
        c["count"] += 1
        is_open = r.status in OPEN_STATUSES
        if is_open:
            c["open_count"] += 1
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_type[r.clash_type] = by_type.get(r.clash_type, 0) + 1

        # Level matrix: only when both storeys resolved (NULL = unknown).
        sa_ = getattr(r, "a_storey", None)
        sb_ = getattr(r, "b_storey", None)
        if sa_ is not None and sb_ is not None:
            la, lb = (int(sa_), int(sb_)) if int(sa_) <= int(sb_) else (
                int(sb_), int(sa_)
            )
            storeys.add(la)
            storeys.add(lb)
            lc = level_cell.setdefault((la, lb), {"count": 0, "open_count": 0})
            lc["count"] += 1
            if is_open:
                lc["open_count"] += 1

    matrix = [
        {"a": a, "b": b, "count": v["count"], "open_count": v["open_count"]}
        for (a, b), v in sorted(cell.items())
    ]
    level_matrix = [
        {"a": a, "b": b, "count": v["count"], "open_count": v["open_count"]}
        for (a, b), v in sorted(level_cell.items())
    ]
    return {
        "disciplines": sorted(disciplines),
        "matrix": matrix,
        "storeys": sorted(storeys),
        "level_matrix": level_matrix,
        "by_status": by_status,
        "by_type": by_type,
    }
