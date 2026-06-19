from __future__ import annotations

from datetime import datetime, timezone
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from typing import Any

from pydantic import BaseModel, Field


class ValidationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"


class EvidenceItem(BaseModel):
    evidence_type: str
    source: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    value: Any
    description: str = ""


class ComplianceControl(BaseModel):
    control_id: str
    name: str
    description: str
    expected_behavior: str
    validation_agent: str
    scenario_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    effective_version: str = "mvp-1"
    source_obligation_ids: list[str] = Field(default_factory=list)


class ScenarioRequest(BaseModel):
    scenario_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    dry_run: bool = True


class ScenarioObservation(BaseModel):
    scenario_name: str
    correlation_id: str
    started_at: datetime
    completed_at: datetime
    accepted: bool = True
    events: list[EvidenceItem] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class TradingSystemSnapshot(BaseModel):
    system_id: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    configuration: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)


class ValidationContext(BaseModel):
    system_id: str
    knowledge_version: str
    requested_by: str = "compliance-validator"
    dry_run: bool = True


class ValidationResult(BaseModel):
    control_id: str
    control_name: str
    agent_name: str
    status: ValidationStatus
    expected_behavior: str
    observed_behavior: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ValidationRun(BaseModel):
    run_id: str
    system_id: str
    knowledge_version: str
    started_at: datetime
    completed_at: datetime
    results: list[ValidationResult]

    @property
    def overall_status(self) -> ValidationStatus:
        statuses = {result.status for result in self.results}
        if ValidationStatus.FAIL in statuses:
            return ValidationStatus.FAIL
        if ValidationStatus.REVIEW in statuses:
            return ValidationStatus.REVIEW
        return ValidationStatus.PASS
