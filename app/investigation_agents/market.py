from __future__ import annotations

from app.investigation_agents.base import MARKET_CONTROLS, InvestigationState, InvestigationToolbox, result_counts, summarize_results
from app.models.investigation import InvestigationStep


class MarketInvestigationAgent:
    agent_name = "market-investigation-agent"

    async def run(self, state: InvestigationState, toolbox: InvestigationToolbox) -> None:
        results = await toolbox.run_controls(MARKET_CONTROLS, state.request)
        for result in results:
            state.results[result.control_id] = result
        counts = result_counts(results)
        stressed = counts["fail"] > 0 or counts["review"] > 0
        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Run market data stress controls against crossed, locked, and one-sided market conditions.",
                decision="Market evidence indicates stress or uncertainty; branch to order and engine protections." if stressed else "Market controls passed; continue to order and engine controls to confirm protections remain healthy.",
                selected_controls=MARKET_CONTROLS,
                observations=summarize_results(results),
                next_step="order-investigation-agent",
            )
        )

