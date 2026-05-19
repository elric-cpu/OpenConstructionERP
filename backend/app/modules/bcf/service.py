"""‌⁠‍BCF business logic.

Owns:
    * Topic / comment / viewpoint CRUD.
    * Snapshot binary persistence via the platform storage abstraction
      (:func:`app.core.storage.get_storage_backend`) — keys live under
      ``bcf/<project_id>/<topic_guid>/<viewpoint_guid>.png``, the same
      abstraction BIM geometry and takeoff PDFs use. We never invent a
      new on-disk path.
    * ``.bcfzip`` export (2.1 + 3.0) and idempotent import.

The service is stateless apart from the injected session; it commits
nothing — the request session dependency owns the transaction boundary.
"""

from __future__ import annotations

import base64
import binascii
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage_backend
from app.modules.bcf import bcf_xml
from app.modules.bcf.models import BCFComment, BCFTopic, BCFViewpoint
from app.modules.bcf.repository import BCFRepository
from app.modules.bcf.schemas import (
    BCFImportIssue,
    BCFImportReport,
    CommentCreate,
    TopicCreate,
    TopicUpdate,
    ViewpointCreate,
)

logger = logging.getLogger(__name__)


class BCFServiceError(Exception):
    """‌⁠‍Raised for caller-facing service errors (mapped to HTTP by router)."""


def _now() -> datetime:
    return datetime.now(UTC)


def _snapshot_key(project_id: uuid.UUID, topic_guid: str, vp_guid: str) -> str:
    """‌⁠‍Storage key for a viewpoint snapshot PNG.

    POSIX, no leading slash — matches ``app.core.storage`` key rules and
    the ``bim/<project>/...`` style used elsewhere.
    """
    return f"bcf/{project_id}/{topic_guid}/{vp_guid}.png"


class BCFService:
    """High-level BCF operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BCFRepository(session)

    # ── Topics ─────────────────────────────────────────────────────────

    async def list_topics(self, project_id: uuid.UUID) -> list[BCFTopic]:
        """List all topics for a project, newest first."""
        return await self.repo.list_topics(project_id)

    async def get_topic(
        self, project_id: uuid.UUID, topic_id: uuid.UUID
    ) -> BCFTopic:
        """Load one topic, asserting it belongs to ``project_id``."""
        topic = await self.repo.get_topic(topic_id)
        if topic is None or topic.project_id != project_id:
            raise BCFServiceError("Topic not found")
        return topic

    async def create_topic(
        self,
        project_id: uuid.UUID,
        data: TopicCreate,
        author: str,
        user_id: str,
    ) -> BCFTopic:
        """Create a new topic. ``author`` is the BCF CreationAuthor label."""
        now = _now()
        topic = BCFTopic(
            guid=str(uuid.uuid4()),
            project_id=project_id,
            bim_model_id=data.bim_model_id,
            title=data.title,
            description=data.description,
            topic_type=data.topic_type,
            topic_status=data.topic_status or "Open",
            priority=data.priority,
            stage=data.stage,
            assigned_to=data.assigned_to,
            due_date=data.due_date,
            labels=list(data.labels),
            reference_links=list(data.reference_links),
            creation_author=author,
            creation_date=now,
            modified_author=author,
            modified_date=now,
            created_by=user_id,
            metadata_={},
        )
        self.repo.add_topic(topic)
        await self.session.flush()
        logger.info("BCF topic %s created in project %s", topic.guid, project_id)
        # Re-fetch with relationships eager-loaded so the router can render
        # the (empty) comments/viewpoints collections without a lazy load
        # firing after the request session commits (MissingGreenlet).
        return await self.get_topic(project_id, topic.id)

    async def update_topic(
        self,
        project_id: uuid.UUID,
        topic_id: uuid.UUID,
        data: TopicUpdate,
        author: str,
    ) -> BCFTopic:
        """Patch a topic. Only fields explicitly set in ``data`` change."""
        topic = await self.get_topic(project_id, topic_id)
        patch = data.model_dump(exclude_unset=True)
        for field_name, value in patch.items():
            setattr(topic, field_name, value)
        topic.modified_author = author
        topic.modified_date = _now()
        await self.session.flush()
        return topic

    async def delete_topic(
        self, project_id: uuid.UUID, topic_id: uuid.UUID
    ) -> None:
        """Delete a topic plus its comments, viewpoints and snapshots."""
        topic = await self.get_topic(project_id, topic_id)
        await self._delete_snapshots_for_topic(topic)
        await self.repo.delete_topic(topic)
        await self.session.flush()

    # ── Comments ───────────────────────────────────────────────────────

    async def add_comment(
        self,
        project_id: uuid.UUID,
        topic_id: uuid.UUID,
        data: CommentCreate,
        author: str,
        user_id: str,
    ) -> BCFComment:
        """Append a comment to a topic."""
        topic = await self.get_topic(project_id, topic_id)
        if data.viewpoint_guid:
            vp = await self.repo.get_viewpoint_by_guid(
                topic.id, data.viewpoint_guid
            )
            if vp is None:
                raise BCFServiceError(
                    f"Viewpoint {data.viewpoint_guid} not found on this topic"
                )
        now = _now()
        comment = BCFComment(
            guid=str(uuid.uuid4()),
            topic_id=topic.id,
            comment_text=data.comment,
            author=author,
            date=now,
            modified_author=author,
            modified_date=now,
            viewpoint_guid=data.viewpoint_guid,
            created_by=user_id,
            metadata_={},
        )
        self.repo.add_comment(comment)
        topic.modified_author = author
        topic.modified_date = now
        await self.session.flush()
        return comment

    async def update_comment(
        self,
        project_id: uuid.UUID,
        topic_id: uuid.UUID,
        comment_id: uuid.UUID,
        new_text: str,
        author: str,
    ) -> BCFComment:
        """Edit a comment's text (records ModifiedAuthor/Date)."""
        topic = await self.get_topic(project_id, topic_id)
        comment = await self.repo.get_comment(comment_id)
        if comment is None or comment.topic_id != topic.id:
            raise BCFServiceError("Comment not found")
        comment.comment_text = new_text
        comment.modified_author = author
        comment.modified_date = _now()
        await self.session.flush()
        return comment

    async def delete_comment(
        self,
        project_id: uuid.UUID,
        topic_id: uuid.UUID,
        comment_id: uuid.UUID,
    ) -> None:
        """Delete a single comment."""
        topic = await self.get_topic(project_id, topic_id)
        comment = await self.repo.get_comment(comment_id)
        if comment is None or comment.topic_id != topic.id:
            raise BCFServiceError("Comment not found")
        await self.repo.delete_comment(comment)
        await self.session.flush()

    # ── Viewpoints ─────────────────────────────────────────────────────

    async def add_viewpoint(
        self,
        project_id: uuid.UUID,
        topic_id: uuid.UUID,
        data: ViewpointCreate,
        user_id: str,
    ) -> BCFViewpoint:
        """Attach a viewpoint (camera + components + optional PNG) to a topic."""
        topic = await self.get_topic(project_id, topic_id)
        vp_guid = str(uuid.uuid4())

        camera_type = ""
        camera: dict = {}
        fov: float | None = None
        v2w: float | None = None
        if data.perspective_camera is not None:
            camera_type = "perspective"
            camera = data.perspective_camera.model_dump(
                exclude={"field_of_view"}
            )
            fov = data.perspective_camera.field_of_view
        elif data.orthogonal_camera is not None:
            camera_type = "orthogonal"
            camera = data.orthogonal_camera.model_dump(
                exclude={"view_to_world_scale"}
            )
            v2w = data.orthogonal_camera.view_to_world_scale

        snapshot_key: str | None = None
        snapshot_type: str | None = None
        if data.snapshot_png_b64:
            raw = self._decode_png(data.snapshot_png_b64)
            snapshot_key = _snapshot_key(project_id, topic.guid, vp_guid)
            await get_storage_backend().put(snapshot_key, raw)
            snapshot_type = "png"

        viewpoint = BCFViewpoint(
            guid=vp_guid,
            topic_id=topic.id,
            vp_index=await self.repo.next_viewpoint_index(topic.id),
            camera_type=camera_type,
            camera=camera,
            components=data.components.model_dump(),
            element_stable_ids=list(data.element_stable_ids),
            field_of_view=fov,
            view_to_world_scale=v2w,
            snapshot_key=snapshot_key,
            snapshot_type=snapshot_type,
            created_by=user_id,
            metadata_={},
        )
        self.repo.add_viewpoint(viewpoint)
        await self.session.flush()
        return viewpoint

    async def get_snapshot(
        self,
        project_id: uuid.UUID,
        topic_id: uuid.UUID,
        viewpoint_guid: str,
    ) -> bytes:
        """Return a viewpoint's snapshot PNG bytes (raises if absent)."""
        topic = await self.get_topic(project_id, topic_id)
        vp = await self.repo.get_viewpoint_by_guid(topic.id, viewpoint_guid)
        if vp is None or not vp.snapshot_key:
            raise BCFServiceError("Snapshot not found")
        try:
            return await get_storage_backend().get(vp.snapshot_key)
        except FileNotFoundError as exc:
            raise BCFServiceError("Snapshot not found") from exc

    # ── Export ─────────────────────────────────────────────────────────

    async def export_bcfzip(
        self,
        project_id: uuid.UUID,
        project_name: str,
        version: str,
    ) -> tuple[bytes, int]:
        """Build a ``.bcfzip`` for the whole project.

        Returns ``(archive_bytes, topic_count)``.
        """
        if version not in bcf_xml.SUPPORTED_VERSIONS:
            raise BCFServiceError(
                f"Unsupported BCF version {version!r}; "
                f"expected one of {bcf_xml.SUPPORTED_VERSIONS}"
            )
        topics = await self.repo.list_topics(project_id)
        storage = get_storage_backend()
        dto_topics: list[bcf_xml.ParsedTopic] = []
        for t in topics:
            dto = bcf_xml.ParsedTopic(
                guid=t.guid,
                title=t.title,
                description=t.description,
                topic_type=t.topic_type,
                topic_status=t.topic_status,
                priority=t.priority,
                stage=t.stage,
                index=t.topic_index,
                assigned_to=t.assigned_to,
                due_date=t.due_date,
                labels=list(t.labels or []),
                reference_links=list(t.reference_links or []),
                creation_author=t.creation_author,
                creation_date=t.creation_date,
                modified_author=t.modified_author,
                modified_date=t.modified_date,
            )
            for c in t.comments:
                dto.comments.append(
                    bcf_xml.ParsedComment(
                        guid=c.guid,
                        comment=c.comment_text,
                        author=c.author,
                        date=c.date,
                        modified_author=c.modified_author,
                        modified_date=c.modified_date,
                        viewpoint_guid=c.viewpoint_guid,
                    )
                )
            for v in t.viewpoints:
                pv = bcf_xml.ParsedViewpoint(
                    guid=v.guid,
                    camera_type=v.camera_type or "",
                    camera=dict(v.camera or {}),
                    components=dict(v.components or {}),
                    lines=list(v.lines or []),
                    clipping_planes=list(v.clipping_planes or []),
                    field_of_view=v.field_of_view,
                    view_to_world_scale=v.view_to_world_scale,
                )
                if v.snapshot_key:
                    try:
                        pv.snapshot_bytes = await storage.get(v.snapshot_key)
                        pv.snapshot_filename = "snapshot.png"
                    except FileNotFoundError:
                        logger.warning(
                            "Snapshot blob missing for viewpoint %s (key=%s) "
                            "— exporting viewpoint without image",
                            v.guid,
                            v.snapshot_key,
                        )
                dto.viewpoints.append(pv)
            dto_topics.append(dto)

        archive = bcf_xml.build_bcfzip(
            version=version,
            project_id=str(project_id),
            project_name=project_name,
            topics=dto_topics,
        )
        return archive, len(dto_topics)

    # ── Import ─────────────────────────────────────────────────────────

    async def import_bcfzip(
        self,
        project_id: uuid.UUID,
        data: bytes,
        user_id: str,
        forced_version: str | None = None,
    ) -> BCFImportReport:
        """Import a ``.bcfzip`` into a project, idempotently.

        Topics/comments/viewpoints are matched by BCF GUID: an existing
        GUID is updated in place, a new GUID is inserted. A malformed
        archive yields an ``errors`` report — never a 500.
        """
        try:
            result = bcf_xml.parse_bcfzip(data, forced_version=forced_version)
        except bcf_xml.BCFParseError as exc:
            return BCFImportReport(
                status="errors",
                detected_version=None,
                issues=[
                    BCFImportIssue(
                        severity="error",
                        code="archive_invalid",
                        message=str(exc),
                    )
                ],
            )

        report = BCFImportReport(
            status="passed",
            detected_version=result.detected_version,
            issues=[
                BCFImportIssue(
                    severity=i.severity,
                    code=i.code,
                    message=i.message,
                    location=i.location,
                )
                for i in result.issues
            ],
        )
        if result.has_errors:
            report.status = "errors"
            return report

        storage = get_storage_backend()
        for pt in result.topics:
            if not pt.guid:
                report.issues.append(
                    BCFImportIssue(
                        severity="warning",
                        code="topic_no_guid",
                        message="Skipped a topic with no GUID",
                    )
                )
                continue

            existing = await self.repo.get_topic_by_guid(project_id, pt.guid)
            if existing is None:
                topic = BCFTopic(
                    guid=pt.guid,
                    project_id=project_id,
                    title=pt.title or "(untitled)",
                    description=pt.description,
                    topic_type=pt.topic_type,
                    topic_status=pt.topic_status or "Open",
                    priority=pt.priority,
                    stage=pt.stage,
                    topic_index=pt.index,
                    assigned_to=pt.assigned_to,
                    due_date=pt.due_date,
                    labels=list(pt.labels),
                    reference_links=list(pt.reference_links),
                    creation_author=pt.creation_author,
                    creation_date=pt.creation_date,
                    modified_author=pt.modified_author,
                    modified_date=pt.modified_date,
                    created_by=user_id,
                    metadata_={"imported": True},
                )
                self.repo.add_topic(topic)
                await self.session.flush()
                report.topics_imported += 1
            else:
                topic = existing
                topic.title = pt.title or topic.title
                topic.description = pt.description
                topic.topic_type = pt.topic_type
                topic.topic_status = pt.topic_status or topic.topic_status
                topic.priority = pt.priority
                topic.stage = pt.stage
                topic.topic_index = pt.index
                topic.assigned_to = pt.assigned_to
                topic.due_date = pt.due_date
                topic.labels = list(pt.labels)
                topic.reference_links = list(pt.reference_links)
                topic.modified_author = pt.modified_author
                topic.modified_date = pt.modified_date
                await self.session.flush()
                report.topics_updated += 1

            await self._upsert_comments(topic, pt, user_id, report)
            await self._upsert_viewpoints(
                project_id, topic, pt, user_id, storage, report
            )

        if any(i.severity == "error" for i in report.issues):
            report.status = "errors"
        elif any(i.severity == "warning" for i in report.issues):
            report.status = "warnings"
        return report

    # ── import helpers ─────────────────────────────────────────────────

    async def _upsert_comments(
        self,
        topic: BCFTopic,
        pt: bcf_xml.ParsedTopic,
        user_id: str,
        report: BCFImportReport,
    ) -> None:
        for pc in pt.comments:
            guid = pc.guid or str(uuid.uuid4())
            existing = await self.repo.get_comment_by_guid(topic.id, guid)
            if existing is None:
                self.repo.add_comment(
                    BCFComment(
                        guid=guid,
                        topic_id=topic.id,
                        comment_text=pc.comment,
                        author=pc.author,
                        date=pc.date,
                        modified_author=pc.modified_author,
                        modified_date=pc.modified_date,
                        viewpoint_guid=pc.viewpoint_guid,
                        created_by=user_id,
                        metadata_={"imported": True},
                    )
                )
                report.comments_imported += 1
            else:
                existing.comment_text = pc.comment
                existing.author = pc.author
                existing.date = pc.date
                existing.modified_author = pc.modified_author
                existing.modified_date = pc.modified_date
                existing.viewpoint_guid = pc.viewpoint_guid
        await self.session.flush()

    async def _upsert_viewpoints(
        self,
        project_id: uuid.UUID,
        topic: BCFTopic,
        pt: bcf_xml.ParsedTopic,
        user_id: str,
        storage: object,
        report: BCFImportReport,
    ) -> None:
        for pv in pt.viewpoints:
            guid = pv.guid or str(uuid.uuid4())
            snapshot_key: str | None = None
            snapshot_type: str | None = None
            if pv.snapshot_bytes:
                snapshot_key = _snapshot_key(project_id, topic.guid, guid)
                await get_storage_backend().put(
                    snapshot_key, pv.snapshot_bytes
                )
                snapshot_type = "png"

            existing = await self.repo.get_viewpoint_by_guid(topic.id, guid)
            if existing is None:
                self.repo.add_viewpoint(
                    BCFViewpoint(
                        guid=guid,
                        topic_id=topic.id,
                        vp_index=await self.repo.next_viewpoint_index(topic.id),
                        camera_type=pv.camera_type or "",
                        camera=dict(pv.camera or {}),
                        components=dict(pv.components or {}),
                        lines=list(pv.lines or []),
                        clipping_planes=list(pv.clipping_planes or []),
                        field_of_view=pv.field_of_view,
                        view_to_world_scale=pv.view_to_world_scale,
                        snapshot_key=snapshot_key,
                        snapshot_type=snapshot_type,
                        created_by=user_id,
                        metadata_={"imported": True},
                    )
                )
                report.viewpoints_imported += 1
            else:
                existing.camera_type = pv.camera_type or ""
                existing.camera = dict(pv.camera or {})
                existing.components = dict(pv.components or {})
                existing.lines = list(pv.lines or [])
                existing.clipping_planes = list(pv.clipping_planes or [])
                existing.field_of_view = pv.field_of_view
                existing.view_to_world_scale = pv.view_to_world_scale
                if snapshot_key:
                    existing.snapshot_key = snapshot_key
                    existing.snapshot_type = snapshot_type
        await self.session.flush()

    async def _delete_snapshots_for_topic(self, topic: BCFTopic) -> None:
        """Best-effort removal of a topic's snapshot blobs."""
        storage = get_storage_backend()
        for vp in topic.viewpoints:
            if vp.snapshot_key:
                try:
                    await storage.delete(vp.snapshot_key)
                except Exception:  # noqa: BLE001 — storage cleanup is best-effort
                    logger.warning(
                        "Failed to delete snapshot blob %s", vp.snapshot_key
                    )

    @staticmethod
    def _decode_png(b64: str) -> bytes:
        """Decode a base64 PNG, tolerating a ``data:image/png;base64,`` prefix."""
        payload = b64.strip()
        if payload.startswith("data:"):
            _, _, payload = payload.partition(",")
        try:
            raw = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise BCFServiceError("snapshot_png_b64 is not valid base64") from exc
        # PNG magic number — reject anything that is not a PNG so a
        # malicious payload can't be smuggled through the snapshot field.
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise BCFServiceError("snapshot_png_b64 is not a PNG image")
        return raw
