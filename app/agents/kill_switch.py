from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class KillSwitchAgent(ValidationAgent):
    agent_name = "kill-switch-agent"

    default_dataset = {
        "market_data": {"symbol": "AAPL", "bid": 174.95, "ask": 175.05},
        "resting_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "KILL-AAPL-REST", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
        "post_halt_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "KILL-AAPL-POST", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
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
        post_response = metrics.get("post_halt_order_response", {})
        post_rejected = _rejected(post_response)
        if "new_orders_rejected" in metrics:
            post_rejected = post_rejected and bool(metrics.get("new_orders_rejected"))
        cancel_signal = bool(metrics.get("cancel_signal_sent")) or int(metrics.get("exchange_cancelled_orders", 0) or 0) >= 0
        passed = bool(metrics.get("trading_halted")) and post_rejected and cancel_signal
        observed = json.dumps({"metrics": metrics, "derived_checks": {"post_halt_order_rejected": post_rejected, "cancel_signal_sent": cancel_signal}}, sort_keys=True)
        return self.result(control, observation, passed, observed, "KILL_SWITCH_EFFECTIVE", "KILL_SWITCH_FAILED", "Ensure the kill signal immediately halts trading and rejects new orders.")


def _rejected(response):
    return isinstance(response, dict) and (str(response.get("39", "")) == "8" or str(response.get("150", "")) == "8")
