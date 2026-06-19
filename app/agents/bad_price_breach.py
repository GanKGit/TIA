from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class BadPriceBreachAgent(ValidationAgent):
    agent_name = "bad-price-breach-agent"

    default_dataset = {
        "market_data": {"symbol": "AAPL", "bid": 174.95, "ask": 175.05},
        "bad_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "BADPX-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "210.00"},
        "threshold_bps": 100,
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
        response = metrics.get("bad_order_response", {})
        rejected = _rejected(response) or bool(metrics.get("bad_price_rejected"))
        no_exchange_leak = metrics.get("no_bad_order_to_exchange")
        if no_exchange_leak is None:
            exchange_orders = metrics.get("exchange_orders", []) or []
            bad_order_id = str((metrics.get("bad_order") or {}).get("11", ""))
            no_exchange_leak = not any(str(order.get("11", "")) == bad_order_id for order in exchange_orders if isinstance(order, dict))
        passed = bool(metrics.get("breach_detected")) and bool(metrics.get("trading_halted")) and bool(rejected) and bool(no_exchange_leak)
        observed = json.dumps({"metrics": metrics, "derived_checks": {"bad_price_rejected": bool(rejected), "no_bad_order_to_exchange": bool(no_exchange_leak)}}, sort_keys=True)
        return self.result(control, observation, passed, observed, "BAD_PRICE_HALTED", "BAD_PRICE_NOT_HALTED", "Halt order generation when the configured bad-price threshold is breached.")


def _rejected(response):
    return isinstance(response, dict) and (str(response.get("39", "")) == "8" or str(response.get("150", "")) == "8")
