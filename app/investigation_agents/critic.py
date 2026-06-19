from __future__ import annotations

import json

from app.investigation_agents.base import InvestigationState
from app.models.investigation import InvestigationStep
from app.models.validation import ValidationStatus


class EvidenceCriticAgent:
    agent_name = "evidence-critic-agent"

    async def run(self, state: InvestigationState) -> None:
        contradictions: list[str] = []
        observations: list[str] = []
        for result in state.ordered_results:
            observations.append(f"Reviewing {result.control_id}: {result.status.value}")
            if result.control_id == "CTRL-005":
                try:
                    payload = json.loads(result.observed_behavior)
                    derived = payload.get("derived_checks", {})
                    observed = float(derived.get("observed_hz"))
                    configured = float(derived.get("configured_max_hz"))
                    if result.status == ValidationStatus.FAIL and observed <= configured:
                        contradictions.append(
                            "CTRL-005 failed even though observed_hz is within configured_max_hz. Recheck rate-limit rule."
                        )
                except (TypeError, ValueError, json.JSONDecodeError):
                    contradictions.append("CTRL-005 evidence could not be parsed for independent challenge.")
            if result.status == ValidationStatus.REVIEW and not result.evidence:
                contradictions.append(f"{result.control_id} is review and has no supporting evidence payload.")
        state.contradictions = contradictions
        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Challenge the validation evidence for contradictions, missing proof, and unsupported failures.",
                decision="Evidence challenge found issues that require human review." if contradictions else "No blocking evidence contradictions found.",
                selected_controls=[item.control_id for item in state.ordered_results],
                observations=observations + contradictions,
                next_step="decision-synthesizer-agent",
            )
        )
