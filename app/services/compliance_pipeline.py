from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.registry import ValidationAgentRegistry
from app.knowledge.repository import KnowledgeBaseRepository
from app.models.validation import ComplianceControl, ValidationContext, ValidationResult, ValidationRun, ValidationStatus
from app.services.knowledge_update_service import KnowledgeUpdateService
from app.trading.factory import gateway_from_environment
from app.trading.gateway import TradingSystemGateway
from app.trading.service import TradingSystemService


class TradingComplianceValidationService:
    def __init__(self, knowledge_base: KnowledgeBaseRepository, agent_registry: ValidationAgentRegistry) -> None:
        self.knowledge_base = knowledge_base
        self.agent_registry = agent_registry

    async def validate_system(
        self,
        system_id: str,
        knowledge_version: str | None = None,
        dry_run: bool = True,
    ) -> ValidationRun:
        started = datetime.now(timezone.utc)
        knowledge = await self.knowledge_base.get(knowledge_version) if knowledge_version else await self.knowledge_base.current()
        context = ValidationContext(system_id=system_id, knowledge_version=knowledge.version, dry_run=dry_run)
        results = await asyncio.gather(*(self._run_control(control, context) for control in knowledge.controls))
        return ValidationRun(
            run_id=str(uuid4()),
            system_id=system_id,
            knowledge_version=knowledge.version,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            results=list(results),
        )

    async def _run_control(self, control: ComplianceControl, context: ValidationContext) -> ValidationResult:
        agent = self.agent_registry.get(control.validation_agent)
        if agent is None:
            return self._review(
                control,
                "VALIDATION_AGENT_NOT_AVAILABLE",
                "No specialist validation agent is registered for this control.",
                f"Implement and register {control.validation_agent} before activation.",
                1.0,
            )
        try:
            return await agent.validate(control, context)
        except Exception as exc:
            return self._review(
                control,
                "VALIDATION_EXECUTION_ERROR",
                f"Validation execution failed: {exc}",
                "Resolve the trading-system or evidence error and rerun validation.",
                0.4,
                agent.agent_name,
            )

    @staticmethod
    def _review(control, code, observed, remediation, confidence, agent_name=None) -> ValidationResult:
        return ValidationResult(
            control_id=control.control_id,
            control_name=control.name,
            agent_name=agent_name or control.validation_agent,
            status=ValidationStatus.REVIEW,
            expected_behavior=control.expected_behavior,
            observed_behavior=observed,
            reason_codes=[code],
            citations=control.citations,
            remediation=[remediation],
            confidence=confidence,
        )


class CompliancePlatform:
    """Composition root for the TIA validation and investigation runtime."""

    def __init__(self, gateway: TradingSystemGateway | None = None) -> None:
        self.knowledge_base = KnowledgeBaseRepository()
        self.trading_system = TradingSystemService(gateway or gateway_from_environment())
        self.agent_registry = ValidationAgentRegistry(self.trading_system)
        self.knowledge_updater = KnowledgeUpdateService(self.knowledge_base)
        self.validator = TradingComplianceValidationService(self.knowledge_base, self.agent_registry)

    async def initialize(self) -> None:
        try:
            await self.knowledge_base.current()
        except LookupError:
            await self.knowledge_updater.publish_initial_mvp()


async def run_trading_validation(
    system_id: str = "demo-trading-system",
    gateway: TradingSystemGateway | None = None,
) -> ValidationRun:
    platform = CompliancePlatform(gateway)
    await platform.initialize()
    return await platform.validator.validate_system(system_id)