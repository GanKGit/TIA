from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.asset import CorporateAsset
from app.models.impact import Priority, Severity
from app.models.obligation import Obligation

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


SEVERITY_RANK: dict[Severity, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

PRIORITY_RANK: dict[Priority, int] = {
    "P4": 1,
    "P3": 2,
    "P2": 3,
    "P1": 4,
}


@dataclass(frozen=True)
class RuleDecision:
    severity: Severity
    priority: Priority
    escalation_required: bool
    reason_codes: list[str]


def load_rules(path: Path | None = None) -> dict:
    if yaml is None:
        return {}
    rules_path = path or Path(__file__).with_name("compliance_rules.yaml")
    with rules_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def apply_rules(obligation: Obligation, assets: list[CorporateAsset]) -> RuleDecision:
    reason_codes: list[str] = []
    severity: Severity = "medium"
    priority: Priority = "P3"

    obligation_text = f"{obligation.obligation_text} {obligation.required_action}".lower()
    high_criticality_assets = [
        asset for asset in assets if asset.criticality.lower() in {"high", "critical"}
    ]
    vendor_assets = [asset for asset in assets if asset.vendor_dependency]

    if high_criticality_assets:
        severity, priority = _max_decision(severity, priority, "high", "P1")
        reason_codes.append("RULE_CRITICAL_BUSINESS_SERVICE")

    if vendor_assets:
        severity, priority = _max_decision(severity, priority, "high", "P1")
        reason_codes.append("RULE_VENDOR_DEPENDENCY")

    if any(
        token in obligation_text
        for token in ["technology", "system", "dependency", "resilience", "mapping", "service"]
    ):
        severity, priority = _max_decision(severity, priority, "medium", "P2")
        reason_codes.append("RULE_TECHNOLOGY_IMPACT")

    if obligation.evidence_required:
        severity, priority = _max_decision(severity, priority, "medium", "P2")
        reason_codes.append("RULE_EVIDENCE_REQUIRED")

    if not reason_codes:
        reason_codes.append("RULE_DEFAULT_REVIEW")

    escalation_required = severity in {"high", "critical"} or priority == "P1"
    return RuleDecision(
        severity=severity,
        priority=priority,
        escalation_required=escalation_required,
        reason_codes=sorted(set(reason_codes)),
    )


def _max_decision(
    current_severity: Severity,
    current_priority: Priority,
    candidate_severity: Severity,
    candidate_priority: Priority,
) -> tuple[Severity, Priority]:
    severity = (
        candidate_severity
        if SEVERITY_RANK[candidate_severity] > SEVERITY_RANK[current_severity]
        else current_severity
    )
    priority = (
        candidate_priority
        if PRIORITY_RANK[candidate_priority] > PRIORITY_RANK[current_priority]
        else current_priority
    )
    return severity, priority
