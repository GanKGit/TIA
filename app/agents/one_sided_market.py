from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class OneSidedMarketAgent(ValidationAgent):
    agent_name = "one-sided-market-agent"

    default_dataset = {
        "one_sided_market_data": {"symbol": "AAPL", "ask": 175.05, "ask_size": 100},
        "client_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "ONESIDE-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
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
        detected = bool(metrics.get("condition_detected")) or bool(metrics.get("one_sided_market_detected"))
        held = bool(metrics.get("order_held")) or int(metrics.get("pending_one_sided_orders", 0) or 0) > 0
        no_exchange_leak = metrics.get("no_order_to_exchange")
        if no_exchange_leak is None:
            no_exchange_leak = not bool(metrics.get("exchange_orders", []))
        passed = detected and held and bool(no_exchange_leak)
        observed = json.dumps({"metrics": metrics, "derived_checks": {"one_sided_market_detected": detected, "order_held": held, "no_order_to_exchange": bool(no_exchange_leak)}}, sort_keys=True)
        return self.result(control, observation, passed, observed, "ONE_SIDED_MARKET_RESTRICTED", "ONE_SIDED_MARKET_UNCONTROLLED", "Restrict trading when a valid two-sided market is unavailable.")
