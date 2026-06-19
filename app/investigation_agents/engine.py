from __future__ import annotations

from app.investigation_agents.base import ENGINE_CONTROLS, InvestigationState, InvestigationToolbox, result_counts, summarize_results
from app.models.investigation import InvestigationStep


class EngineControlAgent:
    agent_name = "engine-control-agent"

    async def run(self, state: InvestigationState, toolbox: InvestigationToolbox) -> None:
        results = await toolbox.run_controls(ENGINE_CONTROLS, state.request)
        for result in results:
            state.results[result.control_id] = result
        counts = result_counts(results)
        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Run emergency and rate-control checks: kill switch and maximum evaluation frequency.",
                decision="Engine protection failure detected; final decision must consider compliance breach." if counts["fail"] else "Engine protection controls passed; proceed to regulatory mapping.",
                selected_controls=ENGINE_CONTROLS,
                observations=summarize_results(results),
                next_step="regulatory-mapping-agent",
            )
        )
