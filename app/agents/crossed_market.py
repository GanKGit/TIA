from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class CrossedMarketAgent(ValidationAgent):
    agent_name = "crossed-market-agent"

    default_dataset = {"crossed_market_data": {"symbol": "AAPL", "bid": 176.00, "ask": 175.00, "bid_size": 100, "ask_size": 100}}

    async def validate(self, control, context):
        snapshot = await self.trading_system.get_snapshot(context.system_id)
        parameters = dict(control.parameters)
        parameters.setdefault("dataset", self.default_dataset)
        request = ScenarioRequest(scenario_name=control.scenario_name, parameters=parameters, correlation_id=str(uuid4()), dry_run=context.dry_run)
        observation = await self.trading_system.run_scenario(context.system_id, request)
        return self.evaluate(control, snapshot, observation)

    def evaluate(self, control, snapshot, observation):
        metrics = observation.metrics
        detected = bool(metrics.get("condition_detected")) or bool(metrics.get("crossed_market_detected"))
        restricted = bool(metrics.get("trading_restricted")) or bool(metrics.get("market_data_uncrossed")) or int(metrics.get("crossed_market_uncrossed_updates", 0) or 0) > 0
        passed = detected and restricted
        observed = json.dumps({"metrics": metrics, "derived_checks": {"crossed_market_detected": detected, "trading_restricted": restricted}}, sort_keys=True)
        return self.result(control, observation, passed, observed, "CROSSED_MARKET_RESTRICTED", "CROSSED_MARKET_UNCONTROLLED", "Detect crossed markets and restrict unsafe trading behavior.")
