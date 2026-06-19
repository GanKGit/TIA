from __future__ import annotations

import json
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class ParentChildAgent(ValidationAgent):
    agent_name = "parent-child-agent"

    default_dataset = {
        "market_data": {"symbol": "AAPL", "bid": 174.95, "ask": 175.05},
        "parent_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "PARENT-AAPL-001", "55": "AAPL", "54": "1", "38": "500", "40": "2", "44": "175.00"},
        "child_update": {"8": "FIX.4.4", "35": "G", "49": "CLIENT1", "56": "ENGINE", "11": "CHILD-AAPL-001", "41": "PARENT-AAPL-001", "55": "AAPL", "54": "1", "38": "300", "40": "2", "44": "175.00"},
        "invalid_child_update": {"8": "FIX.4.4", "35": "G", "49": "CLIENT1", "56": "ENGINE", "11": "CHILD-AAPL-BAD", "41": "UNKNOWN-PARENT", "55": "AAPL", "54": "1", "38": "700", "40": "2", "44": "175.00"},
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
        parent_accepted = _accepted(metrics.get("parent_response", {})) or bool(metrics.get("parent_accepted"))
        child_accepted = _accepted(metrics.get("child_response", {})) or bool(metrics.get("child_update_accepted"))
        invalid_child_rejected = _rejected(metrics.get("invalid_child_response", {})) or bool(metrics.get("invalid_child_rejected")) or bool(metrics.get("rejected_excess_child_quantity"))
        link_preserved = bool(metrics.get("link_preserved")) or str(metrics.get("child_parent_id", "")) == str(metrics.get("parent_order_id", ""))
        passed = parent_accepted and child_accepted and invalid_child_rejected and link_preserved
        observed = json.dumps({"metrics": metrics, "derived_checks": {"parent_accepted": parent_accepted, "child_accepted": child_accepted, "invalid_child_rejected": invalid_child_rejected, "link_preserved": link_preserved}}, sort_keys=True)
        return self.result(control, observation, passed, observed, "PARENT_CHILD_ENFORCED", "PARENT_CHILD_BREACH", "Enforce parent linkage and aggregate child quantity limits.")


def _accepted(response):
    return isinstance(response, dict) and str(response.get("39", "")) == "0" and str(response.get("150", "")) == "0"


def _rejected(response):
    return isinstance(response, dict) and (str(response.get("39", "")) == "8" or str(response.get("150", "")) == "8")
