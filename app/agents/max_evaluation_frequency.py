from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class MaxEvaluationFrequencyAgent(ValidationAgent):
    agent_name = "max-evaluation-frequency-agent"

    default_dataset = {
        "configured_max_hz": 10,
        "evaluation_timestamps_ms": [0, 100, 200, 300],
    }

    async def validate(self, control, context):
        snapshot = await self.trading_system.get_snapshot(context.system_id)
        parameters = dict(control.parameters)
        parameters.setdefault("dataset", self.default_dataset)
        request = ScenarioRequest(scenario_name=control.scenario_name, parameters=parameters, correlation_id=str(uuid4()), dry_run=context.dry_run)
        observation = await self.trading_system.run_scenario(context.system_id, request)
        return self.evaluate(control, snapshot, observation)

    def evaluate(self, control, snapshot, observation):
        metrics = observation.metrics
        configured = float(metrics.get("configured_max_hz", control.parameters.get("max_hz", 10)))
        observed = metrics.get("observed_hz")
        if observed is None:
            observed = _observed_hz(metrics.get("evaluation_timestamps_ms", []))
        rate_limited = metrics.get("rate_limited")
        within_limit = observed is not None and configured >= 0 and float(observed) <= configured
        if rate_limited is None:
            rate_limited = within_limit
        passed = within_limit or bool(rate_limited)
        observed_behavior = json.dumps({"metrics": metrics, "derived_checks": {"observed_hz": observed, "configured_max_hz": configured, "rate_limited": bool(rate_limited), "within_limit": within_limit}}, sort_keys=True)
        return self.result(control, observation, passed, observed_behavior, "EVALUATION_RATE_WITHIN_LIMIT", "EVALUATION_RATE_EXCEEDED", "Throttle evaluation frequency to the approved maximum.")


def _observed_hz(timestamps_ms):
    if not isinstance(timestamps_ms, list) or len(timestamps_ms) < 2:
        return None
    duration_ms = float(max(timestamps_ms) - min(timestamps_ms))
    if duration_ms <= 0:
        return None
    return round((len(timestamps_ms) - 1) * 1000.0 / duration_ms, 3)

