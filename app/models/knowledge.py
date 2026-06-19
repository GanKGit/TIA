from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from app.models.validation import ComplianceControl


class KnowledgeBaseVersion(BaseModel):
    version: str
    source_name: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    controls: list[ComplianceControl]
    obligation_ids: list[str] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)


class KnowledgeUpdateResult(BaseModel):
    previous_version: Optional[str]
    published_version: KnowledgeBaseVersion
    affected_control_ids: list[str]
    revalidation_required: bool

