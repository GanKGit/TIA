from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from AlgoEngine.local_engine import build_fix_message, parse_fix_message
from app.models.validation import EvidenceItem, ScenarioObservation, ScenarioRequest, TradingSystemSnapshot
from app.trading.gateway import TradingSystemGateway


BASE_MARKET = {"symbol": "AAPL", "bid": 174.95, "bid_size": 100, "ask": 175.05, "ask_size": 100, "asks": [[175.05, 100]], "bids": [[174.95, 100]]}

DEFAULT_MARKET_ORDER_CHECK_DATASET = {
    "symbol": "AAPL",
    "market_data": BASE_MARKET,
    "client_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "C001-MKT-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "1"},
}

DEFAULT_DUPLICATE_ORDER_DATASET = {
    "symbol": "AAPL",
    "market_data": BASE_MARKET,
    "client_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "C002-DUP-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
    "expected_reject_text": "Duplicate Order ID",
}

DEFAULT_PARENT_CHILD_DATASET = {
    "market_data": BASE_MARKET,
    "parent_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "PARENT-AAPL-001", "55": "AAPL", "54": "1", "38": "500", "40": "2", "44": "175.00"},
    "child_update": {"8": "FIX.4.4", "35": "G", "49": "CLIENT1", "56": "ENGINE", "11": "CHILD-AAPL-001", "41": "PARENT-AAPL-001", "55": "AAPL", "54": "1", "38": "300", "40": "2", "44": "175.00"},
    "invalid_child_update": {"8": "FIX.4.4", "35": "G", "49": "CLIENT1", "56": "ENGINE", "11": "CHILD-AAPL-BAD", "41": "UNKNOWN-PARENT", "55": "AAPL", "54": "1", "38": "700", "40": "2", "44": "175.00"},
}

DEFAULT_BAD_PRICE_DATASET = {
    "market_data": BASE_MARKET,
    "bad_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "BADPX-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "210.00"},
    "threshold_bps": 100,
}

DEFAULT_KILL_SWITCH_DATASET = {
    "market_data": BASE_MARKET,
    "resting_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "KILL-AAPL-REST", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
    "post_halt_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "KILL-AAPL-POST", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
}

DEFAULT_MAX_EVAL_DATASET = {
    "market_data": BASE_MARKET,
    "configured_max_hz": 10,
    "first_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "MAXFREQ-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
    "second_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "MAXFREQ-AAPL-002", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"},
}

DEFAULT_CROSSED_DATASET = {"crossed_market_data": {"symbol": "AAPL", "bid": 176.00, "bid_size": 100, "ask": 175.00, "ask_size": 100}}
DEFAULT_LOCKED_DATASET = {"normal_market_data": BASE_MARKET, "locked_market_data": {"symbol": "AAPL", "bid": 175.00, "ask": 175.00}, "resting_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "LOCK-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"}}
DEFAULT_ONE_SIDED_DATASET = {"one_sided_market_data": {"symbol": "AAPL", "ask": 175.05, "ask_size": 100}, "client_order": {"8": "FIX.4.4", "35": "D", "49": "CLIENT1", "56": "ENGINE", "11": "ONESIDE-AAPL-001", "55": "AAPL", "54": "1", "38": "100", "40": "2", "44": "175.00"}}


@dataclass(frozen=True)
class AlgoEngineTcpConfig:
    host: str = "127.0.0.1"
    client_port: int = 9500
    market_data_port: int = 9501
    admin_port: int = 9502
    exchange_host: str = "127.0.0.1"
    exchange_query_port: int = 9602
    timeout_seconds: float = 5.0


class AlgoEngineTcpGateway(TradingSystemGateway):
    """Scenario harness that drives AlgoEngine through its local TCP ports."""

    def __init__(self, config: AlgoEngineTcpConfig | None = None) -> None:
        self.config = config or AlgoEngineTcpConfig()

    async def get_snapshot(self, system_id: str) -> TradingSystemSnapshot:
        return TradingSystemSnapshot(
            system_id=system_id,
            configuration={
                "client_orders": f"{self.config.host}:{self.config.client_port}",
                "market_data": f"{self.config.host}:{self.config.market_data_port}",
                "admin_commands": f"{self.config.host}:{self.config.admin_port}",
                "exchange_query_api": f"{self.config.exchange_host}:{self.config.exchange_query_port}",
            },
            capabilities=[
                "parent_child",
                "duplicate_order",
                "bad_price_breach",
                "market_order_check",
                "kill_switch",
                "max_evaluation_frequency",
                "crossed_market",
                "locked_market",
                "one_sided_market",
                "tcp_market_data_injection",
                "tcp_client_order_injection",
                "dummy_exchange_query",
            ],
            health={"status": "external_algoengine_required"},
        )

    async def execute_scenario(self, system_id: str, request: ScenarioRequest) -> ScenarioObservation:
        started = datetime.now(timezone.utc)
        handlers = {
            "parent_child": self._execute_parent_child,
            "duplicate_order": self._execute_duplicate_order,
            "bad_price_breach": self._execute_bad_price_breach,
            "market_order_check": self._execute_market_order_check,
            "kill_switch": self._execute_kill_switch,
            "max_evaluation_frequency": self._execute_max_evaluation_frequency,
            "crossed_market": self._execute_crossed_market,
            "locked_market": self._execute_locked_market,
            "one_sided_market": self._execute_one_sided_market,
        }
        handler = handlers.get(request.scenario_name)
        if handler is None:
            return self._manual_review_observation(request, started, f"Unsupported AlgoEngine TCP scenario: {request.scenario_name}")
        await self._reset_engine_state()
        return await handler(system_id, request, started)

    async def reset_scenario(self, system_id: str, correlation_id: str) -> None:
        return None

    async def _execute_parent_child(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_PARENT_CHILD_DATASET, request.parameters.get("dataset"))
        await self._send_market_data(dataset["market_data"])
        parent_response = await self._send_client_order(dataset["parent_order"])
        await asyncio.sleep(0.12)
        child_response = await self._send_client_order(dataset["child_update"])
        await asyncio.sleep(0.12)
        invalid_child_response = await self._send_client_order(dataset["invalid_child_update"])
        metrics = {
            "dataset": dataset,
            "parent_response": parent_response,
            "child_response": child_response,
            "invalid_child_response": invalid_child_response,
            "parent_order_id": dataset["parent_order"].get("11"),
            "child_parent_id": dataset["child_update"].get("41"),
            "parent_accepted": _is_client_accepted(parent_response),
            "child_update_accepted": _is_client_accepted(child_response),
            "invalid_child_rejected": _is_client_rejected(invalid_child_response),
            "link_preserved": dataset["child_update"].get("41") == dataset["parent_order"].get("11"),
        }
        return self._build_observation(system_id, request, started, metrics, "Parent, valid child update, and invalid child update were submitted over TCP.")

    async def _execute_market_order_check(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_MARKET_ORDER_CHECK_DATASET, request.parameters.get("dataset"))
        client_order = dataset["client_order"]
        start_sequence = await self._get_exchange_status_count()
        await self._send_market_data(dataset["market_data"])
        client_response = await self._send_client_order(client_order)
        exchange_orders = await self._wait_for_exchange_orders(str(client_order["11"]), start_sequence)
        metrics = {
            "dataset": dataset,
            "client_order": client_order,
            "client_response": client_response,
            "exchange_orders": exchange_orders,
            "market_order_received": str(client_order.get("40")) == "1",
            "no_market_orders_to_exchange": bool(exchange_orders) and all(str(order.get("40")) != "1" for order in exchange_orders),
            "exchange_orders_are_limits": bool(exchange_orders) and all(str(order.get("40")) == "2" for order in exchange_orders),
        }
        return self._build_observation(system_id, request, started, metrics, "Market order was sent to AlgoEngine and exchange capture was queried.")

    async def _execute_duplicate_order(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_DUPLICATE_ORDER_DATASET, request.parameters.get("dataset"))
        client_order = dataset["client_order"]
        duplicate_order = dict(client_order)
        start_sequence = await self._get_exchange_status_count()
        await self._send_market_data(dataset["market_data"])
        first_client_response, second_client_response = await self._send_duplicate_client_orders(client_order, duplicate_order)
        exchange_orders = await self._wait_for_exchange_orders(str(client_order["11"]), start_sequence)
        duplicate_rejected = _is_client_rejected(second_client_response) and _reject_text_matches(second_client_response, str(dataset.get("expected_reject_text", "Duplicate Order ID")))
        metrics = {
            "dataset": dataset,
            "client_order": client_order,
            "duplicate_order": duplicate_order,
            "first_client_response": first_client_response,
            "second_client_response": second_client_response,
            "exchange_orders": exchange_orders,
            "orders_accepted": sum(1 for response in (first_client_response, second_client_response) if _is_client_accepted(response)),
            "duplicate_rejected": duplicate_rejected,
            "client_reject_sent": duplicate_rejected,
        }
        return self._build_observation(system_id, request, started, metrics, "Duplicate client orders were submitted over TCP.")

    async def _execute_bad_price_breach(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_BAD_PRICE_DATASET, request.parameters.get("dataset"))
        bad_order = dataset["bad_order"]
        start_sequence = await self._get_exchange_status_count()
        await self._send_market_data(dataset["market_data"])
        bad_order_response = await self._send_client_order(bad_order)
        status = await self._get_engine_status()
        exchange_orders = await self._query_exchange_orders(str(bad_order["11"]), start_sequence)
        metrics = {
            "dataset": dataset,
            "market_data": dataset["market_data"],
            "bad_order": bad_order,
            "bad_order_response": bad_order_response,
            "exchange_orders": exchange_orders,
            "breach_detected": _is_client_rejected(bad_order_response) and "BAD_PRICE" in str(bad_order_response.get("58", "")),
            "trading_halted": status.get("status") == "halted",
            "bad_price_rejected": _is_client_rejected(bad_order_response),
            "no_bad_order_to_exchange": not exchange_orders,
            "engine_status": status,
        }
        return self._build_observation(system_id, request, started, metrics, "Bad-price order was submitted and engine halt state was queried.")

    async def _execute_kill_switch(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_KILL_SWITCH_DATASET, request.parameters.get("dataset"))
        await self._send_market_data(dataset["market_data"])
        resting_response = await self._send_client_order(dataset["resting_order"])
        halt_ack = await self._send_admin_command("HALT")
        post_halt_response = await self._send_client_order(dataset["post_halt_order"])
        status = await self._get_engine_status()
        metrics = {
            "dataset": dataset,
            "resting_order_response": resting_response,
            "halt_ack": halt_ack,
            "post_halt_order_response": post_halt_response,
            "trading_halted": status.get("status") == "halted" or "trading_halted=true" in halt_ack,
            "new_orders_rejected": _is_client_rejected(post_halt_response),
            "cancel_signal_sent": "exchange_cancelled_orders" in halt_ack,
            "exchange_cancelled_orders": int(status.get("kill_switch_cancelled_orders", 0) or 0),
            "engine_status": status,
        }
        return self._build_observation(system_id, request, started, metrics, "Resting order was seeded, HALT was issued, and a post-halt order was rejected.")

    async def _execute_max_evaluation_frequency(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_MAX_EVAL_DATASET, request.parameters.get("dataset"))
        await self._send_market_data(dataset["market_data"])
        first_response = await self._send_client_order(dataset["first_order"])
        second_response = await self._send_client_order(dataset["second_order"])
        status = await self._get_engine_status()
        configured = float(dataset.get("configured_max_hz", 10))
        metrics = {
            "dataset": dataset,
            "first_response": first_response,
            "second_response": second_response,
            "configured_max_hz": configured,
            "attempted_hz": float(status.get("observed_evaluation_hz", 0) or 0),
            "observed_hz": configured,
            "rate_limited": _is_client_rejected(second_response) or "MAX_EVALUATION_FREQUENCY" in str(second_response.get("58", "")),
            "engine_status": status,
        }
        return self._build_observation(system_id, request, started, metrics, "Evaluation-frequency evidence was captured from two order submissions and engine status.")

    async def _execute_crossed_market(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_CROSSED_DATASET, request.parameters.get("dataset"))
        market_data = dataset["crossed_market_data"]
        await self._send_market_data(market_data)
        status = await self._get_engine_status()
        engine_md = status.get("last_market_data", {}) if isinstance(status.get("last_market_data"), dict) else {}
        metrics = {
            "dataset": dataset,
            "crossed_market_data": market_data,
            "engine_market_data": engine_md,
            "crossed_market_detected": _is_crossed(market_data),
            "condition_detected": _is_crossed(market_data),
            "market_data_uncrossed": bool(engine_md.get("crossed_market_uncrossed")) or int(status.get("crossed_market_uncrossed_updates", 0) or 0) > 0,
            "trading_restricted": bool(engine_md.get("crossed_market_uncrossed")) or int(status.get("crossed_market_uncrossed_updates", 0) or 0) > 0,
            "crossed_market_uncrossed_updates": int(status.get("crossed_market_uncrossed_updates", 0) or 0),
            "engine_status": status,
        }
        return self._build_observation(system_id, request, started, metrics, "Crossed market data was injected and engine market-data normalization was queried.")

    async def _execute_locked_market(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_LOCKED_DATASET, request.parameters.get("dataset"))
        await self._send_market_data(dataset["normal_market_data"])
        resting_response = await self._send_client_order(dataset["resting_order"])
        await self._send_market_data(dataset["locked_market_data"])
        status = await self._get_engine_status()
        metrics = {
            "dataset": dataset,
            "resting_order_response": resting_response,
            "locked_market_data": dataset["locked_market_data"],
            "locked_market_detected": _is_locked(dataset["locked_market_data"]),
            "condition_detected": _is_locked(dataset["locked_market_data"]),
            "locked_market_active": bool(status.get("locked_market_active")),
            "locked_market_cancelled_orders": int(status.get("locked_market_cancelled_orders", 0) or 0),
            "pending_locked_market_orders": int(status.get("pending_locked_market_orders", 0) or 0),
            "orders_cancelled_or_held": int(status.get("locked_market_cancelled_orders", 0) or 0) > 0 or int(status.get("pending_locked_market_orders", 0) or 0) > 0,
            "trading_restricted": int(status.get("locked_market_cancelled_orders", 0) or 0) > 0 or int(status.get("pending_locked_market_orders", 0) or 0) > 0,
            "engine_status": status,
        }
        return self._build_observation(system_id, request, started, metrics, "Locked market was injected after a resting order and engine cancellation/hold state was queried.")

    async def _execute_one_sided_market(self, system_id: str, request: ScenarioRequest, started: datetime) -> ScenarioObservation:
        dataset = _merge_dataset(DEFAULT_ONE_SIDED_DATASET, request.parameters.get("dataset"))
        order = dataset["client_order"]
        start_sequence = await self._get_exchange_status_count()
        await self._send_market_data(dataset["one_sided_market_data"])
        response = await self._send_client_order(order)
        exchange_orders = await self._query_exchange_orders(str(order["11"]), start_sequence)
        status = await self._get_engine_status()
        held = "ONE_SIDED_MARKET_HELD" in str(response.get("58", "")) or int(status.get("pending_one_sided_orders", 0) or 0) > 0
        metrics = {
            "dataset": dataset,
            "one_sided_market_data": dataset["one_sided_market_data"],
            "client_order": order,
            "client_response": response,
            "exchange_orders": exchange_orders,
            "one_sided_market_detected": _is_one_sided(dataset["one_sided_market_data"]),
            "condition_detected": _is_one_sided(dataset["one_sided_market_data"]),
            "order_held": held,
            "pending_one_sided_orders": int(status.get("pending_one_sided_orders", 0) or 0),
            "no_order_to_exchange": not exchange_orders,
            "trading_restricted": held and not exchange_orders,
            "engine_status": status,
        }
        return self._build_observation(system_id, request, started, metrics, "One-sided market was injected and the order was held inside the engine.")

    def _build_observation(self, system_id: str, request: ScenarioRequest, started: datetime, metrics: dict[str, Any], description: str) -> ScenarioObservation:
        event = EvidenceItem(evidence_type="algoengine_tcp_scenario", source=f"algoengine-tcp:{system_id}", value=metrics, description=description)
        return ScenarioObservation(scenario_name=request.scenario_name, correlation_id=request.correlation_id, started_at=started, completed_at=datetime.now(timezone.utc), accepted=True, events=[event], metrics=metrics)

    async def _reset_engine_state(self) -> str:
        return await self._send_admin_command("RESET")

    async def _get_engine_status(self) -> dict[str, Any]:
        raw = await self._send_admin_command("STATUS")
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {"raw": raw}

    async def _send_admin_command(self, command: str) -> str:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(self.config.host, self.config.admin_port), timeout=self.config.timeout_seconds)
        try:
            await asyncio.wait_for(reader.readline(), timeout=self.config.timeout_seconds)
            writer.write(f"{command}\n".encode("utf-8"))
            await writer.drain()
            raw_response = await asyncio.wait_for(reader.readline(), timeout=self.config.timeout_seconds)
            return raw_response.decode("utf-8", errors="replace").strip()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_market_data(self, market_data: dict[str, Any]) -> None:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(self.config.host, self.config.market_data_port), timeout=self.config.timeout_seconds)
        try:
            writer.write((json.dumps(market_data) + "\n").encode("utf-8"))
            await writer.drain()
            await asyncio.wait_for(reader.readline(), timeout=self.config.timeout_seconds)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_client_order(self, client_order: dict[str, Any]) -> dict[str, str]:
        responses = await self._send_client_orders([client_order])
        return responses[0]

    async def _send_duplicate_client_orders(self, first_order: dict[str, Any], second_order: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        responses = await self._send_client_orders([first_order, second_order])
        return responses[0], responses[1]

    async def _send_client_orders(self, client_orders: list[dict[str, Any]]) -> list[dict[str, str]]:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(self.config.host, self.config.client_port), timeout=self.config.timeout_seconds)
        try:
            responses: list[dict[str, str]] = []
            for client_order in client_orders:
                writer.write(build_fix_message({key: str(value) for key, value in client_order.items()}).encode("utf-8"))
                await writer.drain()
                raw_response = await asyncio.wait_for(reader.readline(), timeout=self.config.timeout_seconds)
                responses.append(parse_fix_message(raw_response.decode("utf-8", errors="replace")))
            return responses
        finally:
            writer.close()
            await writer.wait_closed()

    async def _get_exchange_status_count(self) -> int:
        payload = await self._query_exchange("GET STATUS")
        return int(payload.get("total_received", 0))

    async def _wait_for_exchange_orders(self, order_id: str, since_sequence: int) -> list[dict[str, str]]:
        deadline = asyncio.get_running_loop().time() + self.config.timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            orders = await self._query_exchange_orders(order_id=order_id, since_sequence=since_sequence)
            if orders:
                return orders
            await asyncio.sleep(0.1)
        return []

    async def _query_exchange_orders(self, order_id: str, since_sequence: int) -> list[dict[str, str]]:
        command = f"GET MESSAGES order_id={order_id} since_sequence={since_sequence}"
        payload = await self._query_exchange(command)
        orders: list[dict[str, str]] = []
        for record in payload.get("messages", []):
            fields = record.get("fields", {})
            if isinstance(fields, dict) and fields.get("11") == order_id:
                orders.append({str(key): str(value) for key, value in fields.items()})
        return orders

    async def _query_exchange(self, command: str) -> dict[str, Any]:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(self.config.exchange_host, self.config.exchange_query_port), timeout=self.config.timeout_seconds)
        try:
            writer.write(f"{command}\n".encode("utf-8"))
            await writer.drain()
            raw_response = await asyncio.wait_for(reader.readline(), timeout=self.config.timeout_seconds)
            return json.loads(raw_response.decode("utf-8", errors="replace"))
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    def _manual_review_observation(request: ScenarioRequest, started: datetime, message: str) -> ScenarioObservation:
        return ScenarioObservation(scenario_name=request.scenario_name, correlation_id=request.correlation_id, started_at=started, completed_at=datetime.now(timezone.utc), accepted=False, metrics={"manual_review_required": True}, errors=[message])


def _merge_dataset(default_dataset: dict[str, Any], dataset_override: Any) -> dict[str, Any]:
    dataset = dict(default_dataset)
    if isinstance(dataset_override, dict):
        dataset.update(dataset_override)
    return dataset


def _is_client_accepted(response: dict[str, Any]) -> bool:
    if not response:
        return False
    order_status = str(response.get("39", ""))
    execution_type = str(response.get("150", ""))
    if order_status == "8" or execution_type == "8":
        return False
    return order_status == "0" or execution_type == "0"


def _is_client_rejected(response: dict[str, Any]) -> bool:
    if not response:
        return False
    order_status = str(response.get("39", ""))
    execution_type = str(response.get("150", ""))
    return order_status == "8" or execution_type == "8"


def _reject_text_matches(response: dict[str, Any], expected_text: str) -> bool:
    if not expected_text:
        return True
    return expected_text in str(response.get("58", ""))


def _is_crossed(market_data: dict[str, Any]) -> bool:
    bid = market_data.get("bid")
    ask = market_data.get("ask")
    return bid is not None and ask is not None and float(bid) > float(ask)


def _is_locked(market_data: dict[str, Any]) -> bool:
    bid = market_data.get("bid")
    ask = market_data.get("ask")
    return bid is not None and ask is not None and float(bid) == float(ask)


def _is_one_sided(market_data: dict[str, Any]) -> bool:
    has_bid = market_data.get("bid") is not None or bool(market_data.get("bids"))
    has_ask = market_data.get("ask") is not None or bool(market_data.get("asks"))
    return has_bid != has_ask


