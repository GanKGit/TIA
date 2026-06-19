from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.validation import (
    EvidenceItem,
    ScenarioObservation,
    ScenarioRequest,
    TradingSystemSnapshot,
)
from app.trading.gateway import TradingSystemGateway


class DemoTradingSystemGateway(TradingSystemGateway):
    """Deterministic in-memory trading system used for demos and automated tests."""

    def __init__(self, behavior_overrides: dict[str, dict[str, Any]] | None = None) -> None:
        self._overrides = behavior_overrides or {}

    async def get_snapshot(self, system_id: str) -> TradingSystemSnapshot:
        return TradingSystemSnapshot(
            system_id=system_id,
            configuration={
                "duplicate_order_protection": True,
                "parent_child_enforcement": True,
                "bad_price_threshold_bps": 100,
                "max_evaluation_frequency_hz": 10,
                "kill_switch_enabled": True,
            },
            capabilities=[
                "order_hierarchy",
                "duplicate_detection",
                "kill_switch",
                "scenario_injection",
            ],
            health={"status": "healthy"},
        )

    async def execute_scenario(
        self,
        system_id: str,
        request: ScenarioRequest,
    ) -> ScenarioObservation:
        started = datetime.now(timezone.utc)
        defaults = self._default_behavior(request.scenario_name)
        behavior = {**defaults, **self._overrides.get(request.scenario_name, {})}
        event = EvidenceItem(
            evidence_type="scenario_observation",
            source=f"demo-trading-system:{system_id}",
            value=behavior,
            description=f"Observed response for {request.scenario_name}",
        )
        return ScenarioObservation(
            scenario_name=request.scenario_name,
            correlation_id=request.correlation_id,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            accepted=True,
            events=[event],
            metrics=behavior,
        )

    async def reset_scenario(self, system_id: str, correlation_id: str) -> None:
        return None

    @staticmethod
    def _default_behavior(scenario_name: str) -> dict[str, Any]:
        behaviors = {
            "parent_child": {
                "dataset": {
                    "parent_order": {"11": "PARENT-AAPL-001", "55": "AAPL", "38": "500"},
                    "child_update": {"11": "CHILD-AAPL-001", "41": "PARENT-AAPL-001", "38": "300"},
                    "invalid_child_update": {"11": "CHILD-AAPL-BAD", "41": "UNKNOWN-PARENT", "38": "700"},
                },
                "parent_order_id": "PARENT-AAPL-001",
                "child_parent_id": "PARENT-AAPL-001",
                "parent_response": {"11": "PARENT-AAPL-001", "39": "0", "150": "0", "58": "Accepted."},
                "child_response": {"11": "CHILD-AAPL-001", "39": "0", "150": "0", "58": "Parent link preserved."},
                "invalid_child_response": {"11": "CHILD-AAPL-BAD", "39": "8", "150": "8", "58": "PARENT_CHILD_LINK_NOT_FOUND"},
                "link_preserved": True,
                "child_update_accepted": True,
                "invalid_child_rejected": True,
                "rejected_excess_child_quantity": True,
            },
            "duplicate_order": {
                "client_order": {"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00", "11": "C002-DUP-AAPL-001"},
                "first_client_response": {"11": "C002-DUP-AAPL-001", "39": "0", "150": "0", "58": "Exchange Simulator accepted."},
                "second_client_response": {"11": "C002-DUP-AAPL-001", "39": "8", "150": "8", "58": "Duplicate Order ID"},
                "exchange_orders": [{"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00", "11": "C002-DUP-AAPL-001"}],
                "duplicate_rejected": True,
                "orders_accepted": 1,
                "client_reject_sent": True,
            },
            "market_order_check": {
                "client_order": {"55": "AAPL", "54": "1", "38": "100", "40": "1"},
                "exchange_orders": [{"55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"}],
                "market_order_received": True,
                "no_market_orders_to_exchange": True,
                "limit_order_matches_expected": True,
            },
            "bad_price_breach": {
                "market_data": {"symbol": "AAPL", "bid": 174.95, "ask": 175.05},
                "bad_order": {"11": "BADPX-AAPL-001", "55": "AAPL", "54": "1", "44": "210.00"},
                "bad_order_response": {"11": "BADPX-AAPL-001", "39": "8", "150": "8", "58": "BAD_PRICE_BREACH"},
                "exchange_orders": [],
                "breach_detected": True,
                "trading_halted": True,
                "bad_price_rejected": True,
                "no_bad_order_to_exchange": True,
            },
            "kill_switch": {
                "resting_order_response": {"11": "KILL-AAPL-REST", "39": "0", "150": "0"},
                "halt_ack": "OK trading_halted=true exchange_cancelled_orders=1",
                "post_halt_order_response": {"11": "KILL-AAPL-POST", "39": "8", "150": "8", "58": "Trading is halted by admin control."},
                "trading_halted": True,
                "new_orders_rejected": True,
                "cancel_signal_sent": True,
                "exchange_cancelled_orders": 1,
            },
            "max_evaluation_frequency": {
                "evaluation_timestamps_ms": [0, 100, 200, 300],
                "observed_hz": 10,
                "configured_max_hz": 10,
                "rate_limited": True,
            },
            "crossed_market": {
                "crossed_market_data": {"symbol": "AAPL", "bid": 176.00, "ask": 175.00},
                "engine_market_data": {"symbol": "AAPL", "bid": 175.00, "ask": 176.00, "crossed_market_uncrossed": True},
                "crossed_market_detected": True,
                "condition_detected": True,
                "market_data_uncrossed": True,
                "trading_restricted": True,
                "crossed_market_uncrossed_updates": 1,
            },
            "locked_market": {
                "locked_market_data": {"symbol": "AAPL", "bid": 175.00, "ask": 175.00},
                "locked_market_detected": True,
                "condition_detected": True,
                "trading_restricted": True,
                "orders_cancelled_or_held": True,
                "locked_market_cancelled_orders": 1,
                "pending_locked_market_orders": 1,
            },
            "one_sided_market": {
                "one_sided_market_data": {"symbol": "AAPL", "ask": 175.05},
                "client_order": {"11": "ONESIDE-AAPL-001", "55": "AAPL", "54": "1", "44": "175.00"},
                "client_response": {"11": "ONESIDE-AAPL-001", "39": "0", "150": "0", "58": "ONE_SIDED_MARKET_HELD"},
                "exchange_orders": [],
                "one_sided_market_detected": True,
                "condition_detected": True,
                "trading_restricted": True,
                "order_held": True,
                "pending_one_sided_orders": 1,
                "no_order_to_exchange": True,
            },
            "rapid_move_retrace": {"risk_limits_respected": True, "uncontrolled_orders": 0},
            "favorable_adverse_move": {"limits_applied_both_directions": True},
            "market_data_halt": {"trading_halted": True, "stale_data_detected": True},
            "exchange_reject": {"retry_bounded": True, "duplicate_created": False},
        }
        return behaviors.get(scenario_name, {"manual_review_required": True})

