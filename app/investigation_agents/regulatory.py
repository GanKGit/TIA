from __future__ import annotations

from app.investigation_agents.base import InvestigationState, InvestigationToolbox
from app.models.investigation import InvestigationStep


class RegulatoryMappingAgent:
    agent_name = "regulatory-mapping-agent"

    async def run(self, state: InvestigationState, toolbox: InvestigationToolbox) -> None:
        controls = await toolbox.current_controls(state.request.knowledge_version)
        control_by_id = {control.control_id: control for control in controls}
        mapping: dict[str, list[str]] = {}
        observations: list[str] = []
        for result in state.ordered_results:
            control = control_by_id.get(result.control_id)
            citations = list(result.citations or (control.citations if control else []))
            mapping[result.control_id] = citations
            observations.append(f"{result.control_id}: {len(citations)} citation(s), status={result.status.value}")
        state.regulatory_mapping = mapping
        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Map executed controls back to the active knowledge base and citations.",
                decision="Regulatory context attached to every executed validation result.",
                selected_controls=list(mapping),
                observations=observations,
                next_step="evidence-critic-agent",
            )
        )
