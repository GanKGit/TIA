from __future__ import annotations

from datetime import datetime, timezone

from app.knowledge.control_catalog import initial_mvp_controls
from app.knowledge.repository import KnowledgeBaseRepository
from app.models.knowledge import KnowledgeBaseVersion, KnowledgeUpdateResult


class KnowledgeUpdateService:
    """Publishes the fixed TIA MVP control catalog into the in-memory repository."""

    def __init__(self, repository: KnowledgeBaseRepository) -> None:
        self.repository = repository

    async def publish_initial_mvp(self) -> KnowledgeUpdateResult:
        version = KnowledgeBaseVersion(
            version="tia-mvp-initial",
            source_name="TIA MVP Control Catalog",
            published_at=datetime.now(timezone.utc),
            controls=initial_mvp_controls(),
            change_summary=[
                "Published the fixed TIA MVP control catalog.",
                "The catalog is fixed for this TIA demo build.",
            ],
        )
        await self.repository.publish(version)
        return KnowledgeUpdateResult(
            previous_version=None,
            published_version=version,
            affected_control_ids=[control.control_id for control in version.controls],
            revalidation_required=False,
        )