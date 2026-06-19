from __future__ import annotations

from app.investigation_agents.base import ORDER_CONTROLS, InvestigationState, InvestigationToolbox, result_counts, summarize_results
from app.models.investigation import InvestigationStep


class OrderInvestigationAgent:
    agent_name = "order-investigation-agent"

    async def run(self, state: InvestigationState, toolbox: InvestigationToolbox) -> None:
        results = await toolbox.run_controls(ORDER_CONTROLS, state.request)
        for result in results:
            state.results[result.control_id] = result
        counts = result_counts(results)
        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Run order-behavior controls for hierarchy, duplicates, bad price, and market-order conversion.",
                decision="Order controls found a breach; engine controls must be checked before final decision." if counts["fail"] else "Order controls did not show an unresolved breach; continue to engine controls for readiness evidence.",
                selected_controls=ORDER_CONTROLS,
                observations=summarize_results(results),
                next_step="engine-control-agent",
            )
        )
