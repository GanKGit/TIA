from __future__ import annotations

from app.investigation_agents.base import ENGINE_CONTROLS, MARKET_CONTROLS, ORDER_CONTROLS, PRESET_DESCRIPTIONS, InvestigationState
from app.models.investigation import InvestigationStep


class PlannerAgent:
    agent_name = "planner-agent"

    async def plan(self, state: InvestigationState) -> list[str]:
        preset = state.request.preset
        if preset == "pre_trade_risk_control_investigation":
            path = ["order", "engine", "regulatory", "critic", "synthesizer"]
            first_controls = ORDER_CONTROLS
        elif preset == "production_readiness":
            path = ["order", "engine", "market", "regulatory", "critic", "synthesizer"]
            first_controls = ORDER_CONTROLS + ENGINE_CONTROLS + MARKET_CONTROLS
        else:
            path = ["market", "order", "engine", "regulatory", "critic", "synthesizer"]
            first_controls = MARKET_CONTROLS

        state.add_step(
            InvestigationStep(
                agent_name=self.agent_name,
                action="Interpret investigation question and choose first evidence path.",
                decision=f"Preset '{preset}' selected. {PRESET_DESCRIPTIONS.get(preset, PRESET_DESCRIPTIONS['market_stress_incident'])}",
                selected_controls=first_controls,
                observations=[f"Question: {state.request.question}", f"Parameters: {state.request.parameters}"],
                next_step=path[0],
            )
        )
        return path




