from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from app.models.validation import (
    ComplianceControl,
    ScenarioObservation,
    ScenarioRequest,
    TradingSystemSnapshot,
    ValidationContext,
    ValidationResult,
    ValidationStatus,
)
from app.trading.service import TradingSystemService


class ValidationAgent(ABC):
    agent_name: str

    def __init__(self, trading_system: TradingSystemService) -> None:
        self.trading_system = trading_system

    async def validate(
        self,
        control: ComplianceControl,
        context: ValidationContext,
    ) -> ValidationResult:
        snapshot = await self.trading_system.get_snapshot(context.system_id)
        request = ScenarioRequest(
            scenario_name=control.scenario_name,
            parameters=control.parameters,
            correlation_id=str(uuid4()),
            dry_run=context.dry_run,
        )
        observation = await self.trading_system.run_scenario(context.system_id, request)
        return self.evaluate(control, snapshot, observation)

    @abstractmethod
    def evaluate(
        self,
        control: ComplianceControl,
        snapshot: TradingSystemSnapshot,
        observation: ScenarioObservation,
    ) -> ValidationResult:
        raise NotImplementedError

    def result(
        self,
        control: ComplianceControl,
        observation: ScenarioObservation,
        passed: bool | None,
        observed_behavior: str,
        pass_code: str,
        fail_code: str,
        remediation: str,
    ) -> ValidationResult:
        if passed is True:
            status = ValidationStatus.PASS
            reason_codes = [pass_code]
            remediation_actions: list[str] = []
            confidence = 0.96
        elif passed is False:
            status = ValidationStatus.FAIL
            reason_codes = [fail_code]
            remediation_actions = [remediation]
            confidence = 0.96
        else:
            status = ValidationStatus.REVIEW
            reason_codes = ["INSUFFICIENT_EVIDENCE"]
            remediation_actions = ["Collect complete scenario evidence and rerun validation."]
            confidence = 0.55

        return ValidationResult(
            control_id=control.control_id,
            control_name=control.name,
            agent_name=self.agent_name,
            status=status,
            expected_behavior=control.expected_behavior,
            observed_behavior=observed_behavior,
            evidence=observation.events,
            reason_codes=reason_codes,
            citations=control.citations,
            remediation=remediation_actions,
            confidence=confidence,
        )

