from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.validation import ValidationResult, ValidationStatus


class InvestigationStatus(str):
    pass


class InvestigationRequest(BaseModel):
    system_id: str = "demo-trading-system"
    question: str = "AAPL experienced abnormal trading behavior during market stress. Determine whether this is a compliance breach or expected protection behavior."
    preset: str = "market_stress_incident"
    knowledge_version: str | None = None
    dry_run: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class InvestigationStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_name: str
    action: str
    decision: str
    selected_controls: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    next_step: str = ""
    status: str = "completed"


class InvestigationFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    system_id: str
    question: str
    preset: str
    started_at: datetime
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    final_status: ValidationStatus
    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0)
    human_review_required: bool
    root_cause: str
    evidence_summary: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    agent_trace: list[InvestigationStep] = Field(default_factory=list)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    regulatory_mapping: dict[str, Any] = Field(default_factory=dict)
    contradictions: list[str] = Field(default_factory=list)

    @property
    def failed_controls(self) -> list[str]:
        return [item.control_id for item in self.validation_results if item.status == ValidationStatus.FAIL]

    @property
    def review_controls(self) -> list[str]:
        return [item.control_id for item in self.validation_results if item.status == ValidationStatus.REVIEW]
