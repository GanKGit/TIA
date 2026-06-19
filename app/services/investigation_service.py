from __future__ import annotations

from app.investigation_agents import (
    DecisionSynthesizerAgent,
    EngineControlAgent,
    EvidenceCriticAgent,
    MarketInvestigationAgent,
    OrderInvestigationAgent,
    PlannerAgent,
    RegulatoryMappingAgent,
)
from app.investigation_agents.base import InvestigationState, InvestigationToolbox, PRESET_DESCRIPTIONS
from app.models.investigation import InvestigationFinding, InvestigationRequest
from app.services.compliance_pipeline import CompliancePlatform


DEMO_INVESTIGATION_CASES = {
    "market_stress_incident": {
        "name": "Market Data Stress Investigation",
        "question": "AAPL experienced abnormal trading behavior during crossed, locked, or one-sided market data stress. Determine whether trading protections handled the condition correctly.",
        "data_preparation": [
            "Inject market data states that represent crossed, locked, and one-sided market conditions.",
            "Toggle market protection behavior to demonstrate both PASS and FAIL outcomes.",
            "Query AlgoEngine admin status and Exchange Simulator captures as supporting evidence when using the active stack.",
        ],
    },
    "pre_trade_risk_control_investigation": {
        "name": "Pre-Trade Risk Control Investigation",
        "question": "AAPL showed pre-trade risk signals such as duplicate submissions, parent-child order behavior, market-order routing, or bad-price risk. Determine whether controls blocked unsafe behavior before market exposure.",
        "data_preparation": [
            "Submit duplicate client order ids, parent/child order relationships, market order, and bad-price order datasets.",
            "Toggle duplicate and bad-price behavior to demonstrate both PASS and FAIL outcomes.",
            "Use Exchange Simulator capture to prove what the engine actually routed outward when using the active stack.",
        ],
    },
}
class AgenticInvestigationService:
    """Agentic layer that uses deterministic validation agents as auditable tools."""

    def __init__(self, platform: CompliancePlatform) -> None:
        self.platform = platform
        self.toolbox = InvestigationToolbox(platform)
        self.planner = PlannerAgent()
        self.market = MarketInvestigationAgent()
        self.order = OrderInvestigationAgent()
        self.engine = EngineControlAgent()
        self.regulatory = RegulatoryMappingAgent()
        self.critic = EvidenceCriticAgent()
        self.synthesizer = DecisionSynthesizerAgent()

    @staticmethod
    def demo_cases() -> dict:
        return DEMO_INVESTIGATION_CASES

    async def investigate(self, request: InvestigationRequest) -> InvestigationFinding:
        state = InvestigationState(request=request)
        path = await self.planner.plan(state)
        for stage in path:
            if stage == "market":
                await self.market.run(state, self.toolbox)
            elif stage == "order":
                await self.order.run(state, self.toolbox)
            elif stage == "engine":
                await self.engine.run(state, self.toolbox)
            elif stage == "regulatory":
                await self.regulatory.run(state, self.toolbox)
            elif stage == "critic":
                await self.critic.run(state)
            elif stage == "synthesizer":
                return await self.synthesizer.run(state)
        return await self.synthesizer.run(state)


def investigation_case_options() -> list[tuple[str, str]]:
    return [(key, value["name"]) for key, value in DEMO_INVESTIGATION_CASES.items()]




