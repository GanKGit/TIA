from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.agents.base import ValidationAgent
from app.models.validation import ScenarioRequest


class MarketOrderCheckAgent(ValidationAgent):
    """Validate C001: client market orders are converted to limit orders before exchange."""

    agent_name = "market-order-check-agent"

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
            "11": "C001-MKT-AAPL-001",
            "55": "AAPL",
            "54": "1",
            "38": "100",
            "40": "1",
        },
        "expected_exchange_slices": [
            {"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
        ],
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
        exchange_orders = _exchange_orders(metrics)
        expected_slices = dataset["expected_exchange_slices"]

        no_market_order_leaked = metrics.get("no_market_orders_to_exchange")
        if no_market_order_leaked is None:
            no_market_order_leaked = bool(exchange_orders) and all(_tag(order, "40", "order_type") != "1" for order in exchange_orders)

        limit_order_matches_expected = metrics.get("limit_order_matches_expected")
        if limit_order_matches_expected is None:
            limit_order_matches_expected = _limit_orders_match_expected(exchange_orders, expected_slices)

        market_order_received = metrics.get("market_order_received")
        if market_order_received is None:
            client_order = metrics.get("client_order", dataset["client_order"])
            market_order_received = _tag(client_order, "40", "order_type") == "1"

        passed = all(
            [
                bool(market_order_received),
                bool(no_market_order_leaked),
                bool(limit_order_matches_expected),
            ]
        )
        observed_behavior = json.dumps(
            {
                "dataset": dataset,
                "metrics": metrics,
                "derived_checks": {
                    "market_order_received": bool(market_order_received),
                    "no_market_order_leaked": bool(no_market_order_leaked),
                    "limit_order_matches_expected": bool(limit_order_matches_expected),
                },
            },
            sort_keys=True,
        )
        return self.result(
            control,
            observation,
            passed,
            observed_behavior,
            "MARKET_ORDER_CONVERTED_TO_LIMIT",
            "MARKET_ORDER_SENT_OR_UNSLICED",
            "Convert client market orders into limit orders and never send tag 40=1 to exchange.",
        )


def _exchange_orders(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    orders = (
        metrics.get("exchange_orders")
        or metrics.get("outbound_exchange_orders")
        or metrics.get("exchange_messages")
        or []
    )
    return [order for order in orders if isinstance(order, dict)]


def _tag(order: dict[str, Any], fix_tag: str, alias: str) -> str:
    value = order.get(fix_tag, order.get(alias, ""))
    return str(value)


def _limit_orders_match_expected(
    exchange_orders: list[dict[str, Any]],
    expected_slices: list[dict[str, str]],
) -> bool:
    if len(exchange_orders) != len(expected_slices):
        return False
    for order, expected in zip(exchange_orders, expected_slices):
        if _tag(order, "55", "symbol") != expected["55"]:
            return False
        if _tag(order, "54", "side") != expected["54"]:
            return False
        if _tag(order, "38", "quantity") != expected["38"]:
            return False
        if _tag(order, "40", "order_type") != expected["40"]:
            return False
        price = _format_price(_tag(order, "44", "price"))
        if price is None or price != expected["44"]:
            return False
    return True


def _format_price(value: str) -> str | None:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None
