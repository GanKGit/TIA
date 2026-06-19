from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class LockedMarketAgent(ValidationAgent):
    agent_name = "locked-market-agent"

    default_dataset = {
        "normal_market_data": {"symbol": "AAPL", "bid": 174.95, "ask": 175.05},
        "locked_market_data": {"symbol": "AAPL", "bid": 175.00, "ask": 175.00},
        "resting_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "LOCK-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
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
        detected = bool(metrics.get("condition_detected")) or bool(metrics.get("locked_market_detected")) or bool(metrics.get("locked_market_active"))
        restricted = bool(metrics.get("trading_restricted")) or bool(metrics.get("orders_cancelled_or_held")) or int(metrics.get("locked_market_cancelled_orders", 0) or 0) > 0 or int(metrics.get("pending_locked_market_orders", 0) or 0) > 0
        passed = detected and restricted
        observed = json.dumps({"metrics": metrics, "derived_checks": {"locked_market_detected": detected, "trading_restricted": restricted}}, sort_keys=True)
        return self.result(control, observation, passed, observed, "LOCKED_MARKET_RESTRICTED", "LOCKED_MARKET_UNCONTROLLED", "Apply the approved restriction when bid and ask prices are locked.")
