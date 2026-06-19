from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class DuplicateOrderAgent(ValidationAgent):
    """Validate CTRL-002: duplicate ClOrdID submissions are rejected on the client channel."""

    agent_name = "duplicate-order-agent"

    default_dataset = {
        "symbol": "AAPL",
        "market_data": {
            "symbol": "AAPL",
            "bid": 174.95,
            "bid_size": 100,
            "ask": 175.00,
            "ask_size": 100,
            "asks": [[175.00, 100]],
        },
        "client_order": {
            "8": "FIX.4.4",
            "35": "D",
            "49": "CLIENT1",
            "56": "ENGINE",
            "11": "C002-DUP-AAPL-001",
            "55": "AAPL",
            "54": "1",
            "38": "100",
            "40": "2",
            "44": "175.00",
        },
        "expected_reject_text": "Duplicate Order ID",
    }

    async def validate(self, control, context):
        snapshot = await self.trading_system.get_snapshot(context.system_id)
        parameters = dict(control.parameters)
        parameters.setdefault("dataset", self.default_dataset)
        request = ScenarioRequest(
            scenario_name=control.scenario_name,
            parameters=parameters,
            correlation_id=str(uuid4()),
            dry_run=context.dry_run,
        )
        observation = await self.trading_system.run_scenario(context.system_id, request)
        return self.evaluate(control, snapshot, observation)

    def evaluate(self, control, snapshot, observation):
        metrics = observation.metrics
        dataset = {**self.default_dataset, **dict(control.parameters.get("dataset", {}))}
        first_response = metrics.get("first_client_response", {})
        second_response = metrics.get("second_client_response", {})
        expected_reject_text = str(dataset.get("expected_reject_text", "Duplicate Order ID"))

        orders_accepted = metrics.get("orders_accepted")
        if orders_accepted is None:
            orders_accepted = sum(
                1
                for response in (first_response, second_response)
                if _is_client_accepted(response)
            )

        duplicate_rejected = metrics.get("duplicate_rejected")
        if duplicate_rejected is None:
            duplicate_rejected = _is_client_rejected(second_response) and _reject_text_matches(
                second_response,
                expected_reject_text,
            )

        client_reject_sent = metrics.get("client_reject_sent")
        if client_reject_sent is None:
            client_reject_sent = bool(duplicate_rejected)

        first_order_accepted = _is_client_accepted(first_response)
        passed = (
            bool(first_order_accepted)
            and int(orders_accepted) == 1
            and bool(duplicate_rejected)
            and bool(client_reject_sent)
        )
        observed_behavior = json.dumps(
            {
                "dataset": dataset,
                "metrics": metrics,
                "derived_checks": {
                    "first_order_accepted": bool(first_order_accepted),
                    "orders_accepted": int(orders_accepted),
                    "duplicate_rejected": bool(duplicate_rejected),
                    "client_reject_sent": bool(client_reject_sent),
                },
            },
            sort_keys=True,
        )
        return self.result(
            control,
            observation,
            passed,
            observed_behavior,
            "DUPLICATE_REJECTED",
            "DUPLICATE_ACCEPTED",
            "Enable idempotency and duplicate-order rejection before exchange submission.",
        )


def _is_client_accepted(response: dict[str, Any]) -> bool:
    if not isinstance(response, dict) or not response:
        return False
    order_status = str(response.get("39", ""))
    execution_type = str(response.get("150", ""))
    if order_status == "8" or execution_type == "8":
        return False
    return order_status == "0" or execution_type == "0"


def _is_client_rejected(response: dict[str, Any]) -> bool:
    if not isinstance(response, dict) or not response:
        return False
    order_status = str(response.get("39", ""))
    execution_type = str(response.get("150", ""))
    return order_status == "8" or execution_type == "8"


def _reject_text_matches(response: dict[str, Any], expected_text: str) -> bool:
    if not expected_text:
        return True
    return expected_text in str(response.get("58", ""))
