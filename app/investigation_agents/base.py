from __future__ import annotations

from copy import deepcopy

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from app.models.investigation import InvestigationRequest, InvestigationStep
from app.models.validation import ComplianceControl, ValidationContext, ValidationResult
from app.services.compliance_pipeline import CompliancePlatform


MARKET_CONTROLS = ["STRESS-001", "STRESS-002", "STRESS-003"]
ORDER_CONTROLS = ["CTRL-001", "CTRL-002", "CTRL-003", "CTRL-006"]
ENGINE_CONTROLS = ["CTRL-004", "CTRL-005"]
ALL_INVESTIGATION_CONTROLS = ORDER_CONTROLS + ENGINE_CONTROLS + MARKET_CONTROLS


PRESET_DESCRIPTIONS = {
    "market_stress_incident": "Market Data Stress Investigation that starts with market conditions, then branches into order protection and engine controls.",
    "pre_trade_risk_control_investigation": "Pre-Trade Risk Control Investigation that starts with duplicate, parent-child, market-order, and bad-price controls.",
    "production_readiness": "Production readiness investigation that runs every available MVP control and performs evidence sufficiency review.",
}

MARKET_DATA_STRESS_FAILURE_OVERRIDES = {
    "crossed_market": {
        "crossed_market_detected": True,
        "condition_detected": True,
        "market_data_uncrossed": False,
        "trading_restricted": False,
        "crossed_market_uncrossed_updates": 0,
    },
    "locked_market": {
        "locked_market_detected": True,
        "condition_detected": True,
        "trading_restricted": False,
        "orders_cancelled_or_held": False,
        "locked_market_cancelled_orders": 0,
        "pending_locked_market_orders": 0,
    },
    "one_sided_market": {
        "one_sided_market_detected": True,
        "condition_detected": True,
        "trading_restricted": False,
        "order_held": False,
        "exchange_orders": [{"11": "ONESIDE-AAPL-001", "55": "AAPL", "54": "1", "44": "175.00"}],
        "no_order_to_exchange": False,
    },
}


PRE_TRADE_RISK_FAILURE_OVERRIDES = {
    "duplicate_order": {
        "second_client_response": {"11": "C002-DUP-AAPL-001", "39": "0", "150": "0", "58": "Duplicate accepted unexpectedly."},
        "exchange_orders": [
            {"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00", "11": "C002-DUP-AAPL-001"},
            {"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00", "11": "C002-DUP-AAPL-001"},
        ],
        "duplicate_rejected": False,
        "orders_accepted": 2,
        "client_reject_sent": False,
    },
    "bad_price_breach": {
        "bad_order_response": {"11": "BADPX-AAPL-001", "39": "0", "150": "0", "58": "Bad price accepted unexpectedly."},
        "exchange_orders": [{"11": "BADPX-AAPL-001", "55": "AAPL", "54": "1", "44": "210.00"}],
        "breach_detected": False,
        "trading_halted": False,
        "bad_price_rejected": False,
        "no_bad_order_to_exchange": False,
    },
}

def behavior_overrides_for_request(request: InvestigationRequest) -> dict | None:
    overrides = {}
    parameters = request.parameters or {}

    if "market_protections_enabled" in parameters:
        if parameters.get("market_protections_enabled"):
            for key in ("crossed_market", "locked_market", "one_sided_market"):
                overrides.pop(key, None)
        else:
            overrides.update(deepcopy(MARKET_DATA_STRESS_FAILURE_OVERRIDES))

    if "duplicate_rejected" in parameters:
        if parameters.get("duplicate_rejected"):
            overrides.pop("duplicate_order", None)
        else:
            overrides["duplicate_order"] = _duplicate_failure_override(parameters)

    if "bad_price_blocked" in parameters:
        if parameters.get("bad_price_blocked"):
            overrides.pop("bad_price_breach", None)
        else:
            overrides["bad_price_breach"] = _bad_price_failure_override(parameters)

    return overrides or None


def _duplicate_failure_override(parameters: dict) -> dict:
    symbol = str(parameters.get("symbol") or "AAPL").upper()
    client_order_id = str(parameters.get("duplicate_client_order_id") or f"DUP-{symbol}-001")
    quantity = str(parameters.get("order_quantity") or 100)
    return {
        "second_client_response": {"11": client_order_id, "39": "0", "150": "0", "58": "Duplicate accepted unexpectedly."},
        "exchange_orders": [
            {"55": symbol, "54": "1", "38": quantity, "40": "2", "44": "175.00", "11": client_order_id},
            {"55": symbol, "54": "1", "38": quantity, "40": "2", "44": "175.00", "11": client_order_id},
        ],
        "duplicate_rejected": False,
        "orders_accepted": 2,
        "client_reject_sent": False,
    }


def _bad_price_failure_override(parameters: dict) -> dict:
    symbol = str(parameters.get("symbol") or "AAPL").upper()
    client_order_id = f"BADPX-{symbol}-001"
    bad_price = float(parameters.get("bad_price") or 210.00)
    return {
        "bad_order_response": {"11": client_order_id, "39": "0", "150": "0", "58": "Bad price accepted unexpectedly."},
        "exchange_orders": [{"11": client_order_id, "55": symbol, "54": "1", "44": f"{bad_price:.2f}"}],
        "breach_detected": False,
        "trading_halted": False,
        "bad_price_rejected": False,
        "no_bad_order_to_exchange": False,
    }
@dataclass
class InvestigationState:
    request: InvestigationRequest
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    steps: list[InvestigationStep] = field(default_factory=list)
    results: dict[str, ValidationResult] = field(default_factory=dict)
    regulatory_mapping: dict[str, list[str]] = field(default_factory=dict)
    contradictions: list[str] = field(default_factory=list)

    def add_step(self, step: InvestigationStep) -> None:
        self.steps.append(step)

    @property
    def ordered_results(self) -> list[ValidationResult]:
        return sorted(self.results.values(), key=lambda item: item.control_id)


class InvestigationToolbox:
    def __init__(self, platform: CompliancePlatform) -> None:
        self.platform = platform

    async def current_controls(self, knowledge_version: str | None = None) -> list[ComplianceControl]:
        knowledge = await self.platform.knowledge_base.get(knowledge_version) if knowledge_version else await self.platform.knowledge_base.current()
        return knowledge.controls

    async def run_controls(self, control_ids: Iterable[str], request: InvestigationRequest) -> list[ValidationResult]:
        from app.agents.registry import ValidationAgentRegistry
        from app.services.compliance_pipeline import TradingComplianceValidationService
        from app.trading.demo_gateway import DemoTradingSystemGateway
        from app.trading.service import TradingSystemService

        knowledge = await self.platform.knowledge_base.get(request.knowledge_version) if request.knowledge_version else await self.platform.knowledge_base.current()
        control_by_id = {control.control_id: control for control in knowledge.controls}
        context = ValidationContext(system_id=request.system_id, knowledge_version=knowledge.version, dry_run=request.dry_run, requested_by="agentic-investigator")

        validator = self.platform.validator
        anomaly_overrides = behavior_overrides_for_request(request)
        use_seeded_demo = (request.parameters or {}).get("evidence_source") == "demo"
        if anomaly_overrides or use_seeded_demo:
            trading_service = TradingSystemService(DemoTradingSystemGateway(behavior_overrides=anomaly_overrides))
            validator = TradingComplianceValidationService(self.platform.knowledge_base, ValidationAgentRegistry(trading_service))

        results: list[ValidationResult] = []
        for control_id in control_ids:
            control = control_by_id.get(control_id)
            if control is None:
                continue
            result = await validator._run_control(control, context)
            results.append(result)
        return results


def result_counts(results: Iterable[ValidationResult]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "review": 0}
    for result in results:
        counts[result.status.value] = counts.get(result.status.value, 0) + 1
    return counts


def summarize_results(results: Iterable[ValidationResult]) -> list[str]:
    return [f"{item.control_id} {item.control_name}: {item.status.value.upper()} ({', '.join(item.reason_codes)})" for item in results]




