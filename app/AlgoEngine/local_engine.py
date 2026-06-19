from __future__ import annotations

import asyncio
import argparse
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

SOH = "\x01"


class ControlFlag:
    PARENT_CHILD = 1
    DUPLICATE_ORDER_ID = 2
    KILL_SWITCH = 4
    MARKET_ORDER_LIMIT_CONVERSION = 8
    ONE_SIDED_MARKET = 16
    LOCKED_MARKET = 32
    CROSSED_MARKET = 64
    BAD_PRICE_BREACH = 128
    MAX_EVALUATION_FREQUENCY = 256
    ALL = (
        PARENT_CHILD
        | DUPLICATE_ORDER_ID
        | KILL_SWITCH
        | MARKET_ORDER_LIMIT_CONVERSION
        | ONE_SIDED_MARKET
        | LOCKED_MARKET
        | CROSSED_MARKET
        | BAD_PRICE_BREACH
        | MAX_EVALUATION_FREQUENCY
    )


CONTROL_NAMES = {
    ControlFlag.PARENT_CHILD: "parent_child_update_validation",
    ControlFlag.DUPLICATE_ORDER_ID: "duplicate_order_id_validation",
    ControlFlag.KILL_SWITCH: "kill_switch",
    ControlFlag.MARKET_ORDER_LIMIT_CONVERSION: "market_order_limit_conversion",
    ControlFlag.ONE_SIDED_MARKET: "one_sided_market_control",
    ControlFlag.LOCKED_MARKET: "locked_market_control",
    ControlFlag.CROSSED_MARKET: "crossed_market_control",
    ControlFlag.BAD_PRICE_BREACH: "bad_price_breach",
    ControlFlag.MAX_EVALUATION_FREQUENCY: "max_evaluation_frequency",
}


@dataclass(frozen=True)
class TradingPortConfig:
    system_id: str = "local-trading-engine"
    host: str = "127.0.0.1"
    client_port: int = 9500
    exchange_host: str = "127.0.0.1"
    exchange_port: int = 9601
    market_data_port: int = 9501
    admin_port: int = 9502
    exchange_connect_timeout_seconds: float = 3.0
    controls: int = ControlFlag.ALL
    bad_price_threshold_bps: float = 100.0
    max_evaluation_frequency_hz: float = 10.0

    @classmethod
    def from_environment(cls) -> "TradingPortConfig":
        return cls(
            system_id=os.getenv("TRADING_ENGINE_SYSTEM_ID", "local-trading-engine"),
            host=os.getenv("TRADING_ENGINE_HOST", "127.0.0.1"),
            client_port=_port("TRADING_CLIENT_PORT", 9500),
            exchange_host=os.getenv("TRADING_EXCHANGE_HOST", "127.0.0.1"),
            exchange_port=_port("TRADING_EXCHANGE_PORT", 9601),
            market_data_port=_port("TRADING_MARKET_DATA_PORT", 9501),
            admin_port=_port("TRADING_ADMIN_PORT", 9502),
            exchange_connect_timeout_seconds=float(
                os.getenv("TRADING_EXCHANGE_CONNECT_TIMEOUT_SECONDS", "3.0")
            ),
            controls=int(os.getenv("TRADING_ENGINE_CONTROLS", str(ControlFlag.ALL))),
            bad_price_threshold_bps=float(os.getenv("TRADING_BAD_PRICE_THRESHOLD_BPS", "100")),
            max_evaluation_frequency_hz=float(os.getenv("TRADING_MAX_EVALUATION_FREQUENCY_HZ", "10")),
        )


@dataclass
class TradingEngineState:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trading_halted: bool = False
    accepted_orders: int = 0
    rejected_orders: int = 0
    forwarded_orders: int = 0
    exchange_forward_failures: int = 0
    kill_switch_cancelled_orders: int = 0
    market_data_updates: int = 0
    known_order_ids: set[str] = field(default_factory=set)
    parent_child_links: dict[str, str] = field(default_factory=dict)
    pending_one_sided_orders: list[dict[str, str]] = field(default_factory=list)
    active_exchange_orders: dict[str, dict[str, str]] = field(default_factory=dict)
    pending_locked_market_orders: list[dict[str, str]] = field(default_factory=list)
    locked_market_active: bool = False
    locked_market_cancelled_orders: int = 0
    crossed_market_uncrossed_updates: int = 0
    last_market_data: dict[str, Any] = field(default_factory=dict)
    last_order: dict[str, str] = field(default_factory=dict)
    last_exchange_error: str = ""
    last_evaluation_monotonic: float = 0.0
    observed_evaluation_hz: float = 0.0


@dataclass
class TradingSystemSnapshot:
    system_id: str
    configuration: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    health: dict[str, Any] = field(default_factory=dict)
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def model_dump(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "captured_at": self.captured_at.isoformat(),
            "configuration": self.configuration,
            "capabilities": self.capabilities,
            "health": self.health,
        }

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True)


class FixValidationError(ValueError):
    pass


class LocalTradingEngine:
    """Small asyncio TCP trading engine for local integration and compliance demos."""

    def __init__(self, config: TradingPortConfig | None = None) -> None:
        self.config = config or TradingPortConfig.from_environment()
        self.state = TradingEngineState()
        self._servers: list[asyncio.AbstractServer] = []
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        self._stop_event = asyncio.Event()
        self._servers = [
            await asyncio.start_server(
                self._handle_client_order_connection,
                self.config.host,
                self.config.client_port,
            ),
            await asyncio.start_server(
                self._handle_market_data_connection,
                self.config.host,
                self.config.market_data_port,
            ),
            await asyncio.start_server(
                self._handle_admin_connection,
                self.config.host,
                self.config.admin_port,
            ),
        ]

    async def serve_forever(self) -> None:
        await self.start()
        try:
            if self._stop_event is None:
                raise RuntimeError("Trading engine stop event was not initialized.")
            await self._stop_event.wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        for server in self._servers:
            server.close()
        await asyncio.gather(
            *(server.wait_closed() for server in self._servers),
            return_exceptions=True,
        )
        self._servers = []

    def snapshot(self) -> TradingSystemSnapshot:
        return TradingSystemSnapshot(
            system_id=self.config.system_id,
            configuration={
                "client_port": self.config.client_port,
                "exchange_host": self.config.exchange_host,
                "exchange_port": self.config.exchange_port,
                "market_data_port": self.config.market_data_port,
                "admin_port": self.config.admin_port,
                "fix_version": "FIX.4.4",
                "supported_order_msg_types": ["D", "F", "G"],
                "controls": self.config.controls,
                "enabled_controls": enabled_control_names(self.config.controls),
                "bad_price_threshold_bps": self.config.bad_price_threshold_bps,
                "max_evaluation_frequency_hz": self.config.max_evaluation_frequency_hz,
            },
            capabilities=[
                "fix_4_4_order_entry",
                "duplicate_order_id_validation",
                "parent_child_update_validation",
                "market_order_limit_conversion",
                "one_sided_market_control",
                "locked_market_control",
                "crossed_market_control",
                "bad_price_breach",
                "max_evaluation_frequency",
                "exchange_order_routing",
                "market_data_ingestion",
                "admin_control",
            ],
            health=self._status_payload(),
        )

    async def _handle_client_order_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while data := await reader.read(65536):
                for frame in _split_fix_frames(data.decode("utf-8", errors="replace")):
                    response = await self._process_fix_order(frame)
                    writer.write(response.encode("utf-8"))
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_fix_order(self, raw_message: str) -> str:
        try:
            fields = parse_fix_message(raw_message)
            validate_fix_order(fields)
            if control_enabled(self.config.controls, ControlFlag.DUPLICATE_ORDER_ID):
                self._validate_duplicate_order_id_control(fields)
            if control_enabled(self.config.controls, ControlFlag.PARENT_CHILD):
                self._validate_parent_child_control(fields)
            if control_enabled(self.config.controls, ControlFlag.KILL_SWITCH) and self.state.trading_halted:
                raise FixValidationError("Trading is halted by admin control.")
            if control_enabled(self.config.controls, ControlFlag.MAX_EVALUATION_FREQUENCY):
                self._validate_evaluation_frequency_control()
            if control_enabled(self.config.controls, ControlFlag.CROSSED_MARKET):
                self._uncross_latest_market_data()
            if control_enabled(self.config.controls, ControlFlag.MARKET_ORDER_LIMIT_CONVERSION):
                self._convert_market_order_to_limit(fields)
            if control_enabled(self.config.controls, ControlFlag.BAD_PRICE_BREACH):
                self._validate_bad_price_control(fields)
            if control_enabled(self.config.controls, ControlFlag.LOCKED_MARKET):
                pocketed_response = self._pocket_order_during_locked_market(fields)
                if pocketed_response:
                    return pocketed_response
            if control_enabled(self.config.controls, ControlFlag.ONE_SIDED_MARKET):
                held_response = self._hold_order_during_one_sided_market(fields)
                if held_response:
                    return held_response

            exchange_response = await self._forward_to_exchange(normalize_fix_message(fields))
            self.state.accepted_orders += 1
            self.state.last_order = fields
            if exchange_response:
                self.state.forwarded_orders += 1
                self._record_order_relationship(fields)
                self._record_exchange_order_state(fields, exchange_response)
                return exchange_response
            return build_fix_execution_report(
                fields,
                accepted=True,
                text="Order accepted; exchange unavailable.",
            )
        except FixValidationError as exc:
            self.state.rejected_orders += 1
            fallback = _best_effort_fix_fields(raw_message)
            return build_fix_execution_report(fallback, accepted=False, text=str(exc))

    async def _forward_to_exchange(self, message: str) -> str | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.exchange_host, self.config.exchange_port),
                timeout=self.config.exchange_connect_timeout_seconds,
            )
            writer.write((message + "\n").encode("utf-8"))
            await writer.drain()
            raw_response = await asyncio.wait_for(
                reader.readline(),
                timeout=self.config.exchange_connect_timeout_seconds,
            )
            writer.close()
            await writer.wait_closed()
            self.state.last_exchange_error = ""
            return raw_response.decode("utf-8", errors="replace")
        except Exception as exc:
            self.state.exchange_forward_failures += 1
            self.state.last_exchange_error = str(exc)
            return None

    async def _cancel_all_at_exchange(self) -> int:
        message = build_fix_message(
            {
                "35": "K",
                "49": "ENGINE",
                "56": "SIM_EXCHANGE",
                "11": f"KILL-{uuid4().hex[:8].upper()}",
                "58": "AlgoEngine kill switch cancel all.",
            }
        )
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.exchange_host, self.config.exchange_port),
                timeout=self.config.exchange_connect_timeout_seconds,
            )
            writer.write(message.encode("utf-8"))
            await writer.drain()
            raw_response = await asyncio.wait_for(
                reader.readline(),
                timeout=self.config.exchange_connect_timeout_seconds,
            )
            writer.close()
            await writer.wait_closed()
            response = parse_fix_message(raw_response.decode("utf-8", errors="replace"))
            self.state.last_exchange_error = ""
            return int(response.get("911", "0"))
        except Exception as exc:
            self.state.exchange_forward_failures += 1
            self.state.last_exchange_error = str(exc)
            return 0

    def _validate_parent_child_control(self, fields: dict[str, str]) -> None:
        message_type = fields.get("35")
        if message_type != "G":
            return

        order_id = fields.get("11", "")
        original_order_id = fields.get("41", "")
        if not original_order_id:
            raise FixValidationError(
                "PARENT_CHILD_LINK_MISSING: update order 35=G must include previous order id in tag 41."
            )
        if original_order_id not in self.state.known_order_ids:
            raise FixValidationError(
                f"PARENT_CHILD_LINK_NOT_FOUND: tag 41 '{original_order_id}' does not match a known prior tag 11."
            )
        if order_id == original_order_id:
            raise FixValidationError(
                "PARENT_CHILD_LINK_INVALID: update order tag 11 must be different from tag 41."
            )

    def _validate_duplicate_order_id_control(self, fields: dict[str, str]) -> None:
        order_id = fields.get("11", "")
        if order_id and order_id in self.state.known_order_ids:
            raise FixValidationError("Duplicate Order ID")

    def _validate_evaluation_frequency_control(self) -> None:
        now = time.monotonic()
        if self.state.last_evaluation_monotonic > 0:
            delta = now - self.state.last_evaluation_monotonic
            if delta > 0:
                self.state.observed_evaluation_hz = 1.0 / delta
                if self.state.observed_evaluation_hz > self.config.max_evaluation_frequency_hz:
                    raise FixValidationError("MAX_EVALUATION_FREQUENCY_EXCEEDED")
        self.state.last_evaluation_monotonic = now

    def _validate_bad_price_control(self, fields: dict[str, str]) -> None:
        if fields.get("35") not in {"D", "G"} or fields.get("40") != "2" or not fields.get("44"):
            return
        try:
            price = float(fields["44"])
        except ValueError:
            return
        threshold = self.config.bad_price_threshold_bps / 10000.0
        side = fields.get("54")
        ask = best_ask_price(self.state.last_market_data)
        bid = best_bid_price(self.state.last_market_data)
        breached = False
        if side == "1" and ask is not None:
            breached = price > ask * (1.0 + threshold)
        elif side == "2" and bid is not None:
            breached = price < bid * (1.0 - threshold)
        if breached:
            self.state.trading_halted = True
            raise FixValidationError("BAD_PRICE_BREACH")

    def _convert_market_order_to_limit(self, fields: dict[str, str]) -> None:
        if fields.get("40") != "1":
            return
        ask_price = best_ask_price(self.state.last_market_data)
        if ask_price is None:
            raise FixValidationError("Market order rejected: no ask price available")
        fields["40"] = "2"
        fields["44"] = f"{ask_price:.2f}"

    def _hold_order_during_one_sided_market(self, fields: dict[str, str]) -> str | None:
        if not should_hold_for_one_sided_market(fields, self.state.last_market_data):
            return None

        self.state.accepted_orders += 1
        self.state.last_order = dict(fields)
        self.state.pending_one_sided_orders.append(dict(fields))
        self._record_order_relationship(fields)
        return build_fix_execution_report(
            fields,
            accepted=True,
            text="ONE_SIDED_MARKET_HELD: order accepted and resting in engine.",
        )

    def _pocket_order_during_locked_market(self, fields: dict[str, str]) -> str | None:
        if is_locked_market(self.state.last_market_data):
            self.state.locked_market_active = True
        if not self.state.locked_market_active:
            return None
        if fields.get("35") not in {"D", "G"}:
            return None

        self.state.accepted_orders += 1
        self.state.last_order = dict(fields)
        self.state.pending_locked_market_orders.append(dict(fields))
        self._record_order_relationship(fields)
        return build_fix_execution_report(
            fields,
            accepted=True,
            text="LOCKED_MARKET_POCKETED: order accepted and held in engine.",
        )

    def _record_order_relationship(self, fields: dict[str, str]) -> None:
        order_id = fields.get("11", "")
        if not order_id:
            return
        self.state.known_order_ids.add(order_id)
        if fields.get("35") == "G" and fields.get("41"):
            self.state.parent_child_links[order_id] = fields["41"]

    def _record_exchange_order_state(self, fields: dict[str, str], raw_report: str) -> None:
        order_id = fields.get("11", "")
        if not order_id:
            return
        try:
            report = parse_fix_message(raw_report)
        except FixValidationError:
            return

        execution_type = report.get("150")
        order_status = report.get("39")
        if execution_type == "0" and order_status == "0":
            self.state.active_exchange_orders[order_id] = dict(fields)
        if execution_type in {"2", "4", "8"} or order_status in {"2", "4", "8"}:
            self.state.active_exchange_orders.pop(order_id, None)

    async def _handle_market_data_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while line := await reader.readline():
                payload = parse_market_data(line.decode("utf-8", errors="replace"))
                self.state.market_data_updates += 1
                if control_enabled(self.config.controls, ControlFlag.CROSSED_MARKET):
                    payload = self._uncross_market_data(payload)
                self.state.last_market_data = payload
                await self._handle_locked_market_data(payload)
                if not self.state.locked_market_active:
                    await self._release_one_sided_orders(payload)
                writer.write(b"OK\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_admin_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        writer.write(b"Admin commands: STATUS, SNAPSHOT, HALT, RESUME, RESET, STOP, HELP\n")
        await writer.drain()
        try:
            while line := await reader.readline():
                command = line.decode("utf-8", errors="replace").strip().upper()
                response = await self._execute_admin_command_async(command)
                writer.write((response + "\n").encode("utf-8"))
                await writer.drain()
                if command == "STOP":
                    if self._stop_event is not None:
                        self._stop_event.set()
                    break
        finally:
            writer.close()
            await writer.wait_closed()

    def _execute_admin_command(self, command: str) -> str:
        if command == "STATUS":
            return json.dumps(self._status_payload(), sort_keys=True)
        if command == "SNAPSHOT":
            return self.snapshot().model_dump_json()
        if command == "HALT":
            if not control_enabled(self.config.controls, ControlFlag.KILL_SWITCH):
                return "CONTROL_DISABLED kill_switch"
            self.state.trading_halted = True
            return "OK trading_halted=true"
        if command == "RESUME":
            self.state.trading_halted = False
            return "OK trading_halted=false"
        if command == "RESET":
            self.state = TradingEngineState()
            return "OK state_reset=true"
        if command == "STOP":
            return "OK stopping=true"
        if command == "HELP":
            return "STATUS, SNAPSHOT, HALT, RESUME, RESET, STOP, HELP"
        return "ERROR unknown_command"

    async def _execute_admin_command_async(self, command: str) -> str:
        if command != "HALT":
            return self._execute_admin_command(command)
        if not control_enabled(self.config.controls, ControlFlag.KILL_SWITCH):
            return "CONTROL_DISABLED kill_switch"

        self.state.trading_halted = True
        cancelled = await self._cancel_all_at_exchange()
        self.state.kill_switch_cancelled_orders += cancelled
        return f"OK trading_halted=true exchange_cancelled_orders={cancelled}"

    def _status_payload(self) -> dict[str, Any]:
        return {
            "status": "halted" if self.state.trading_halted else "running",
            "started_at": self.state.started_at.isoformat(),
            "accepted_orders": self.state.accepted_orders,
            "rejected_orders": self.state.rejected_orders,
            "forwarded_orders": self.state.forwarded_orders,
            "exchange_forward_failures": self.state.exchange_forward_failures,
            "kill_switch_cancelled_orders": self.state.kill_switch_cancelled_orders,
            "locked_market_active": self.state.locked_market_active,
            "locked_market_cancelled_orders": self.state.locked_market_cancelled_orders,
            "crossed_market_uncrossed_updates": self.state.crossed_market_uncrossed_updates,
            "market_data_updates": self.state.market_data_updates,
            "observed_evaluation_hz": self.state.observed_evaluation_hz,
            "pending_one_sided_orders": len(self.state.pending_one_sided_orders),
            "pending_locked_market_orders": len(self.state.pending_locked_market_orders),
            "active_exchange_orders": len(self.state.active_exchange_orders),
            "last_market_data": self.state.last_market_data,
            "last_exchange_error": self.state.last_exchange_error,
        }

    async def _release_one_sided_orders(self, market_data: dict[str, Any]) -> int:
        released = 0
        remaining: list[dict[str, str]] = []
        for order in self.state.pending_one_sided_orders:
            if not can_release_one_sided_order(order, market_data):
                remaining.append(order)
                continue

            exchange_response = await self._forward_to_exchange(normalize_fix_message(order))
            if exchange_response:
                self.state.forwarded_orders += 1
                self._record_exchange_order_state(order, exchange_response)
                released += 1
            else:
                remaining.append(order)

        self.state.pending_one_sided_orders = remaining
        return released

    async def _handle_locked_market_data(self, market_data: dict[str, Any]) -> int:
        if not control_enabled(self.config.controls, ControlFlag.LOCKED_MARKET):
            return 0

        locked = is_locked_market(market_data)
        if not locked:
            self.state.locked_market_active = False
            return 0

        self.state.locked_market_active = True
        if not self.state.active_exchange_orders:
            return 0

        self.state.pending_locked_market_orders.extend(
            dict(order) for order in self.state.active_exchange_orders.values()
        )
        self.state.active_exchange_orders.clear()
        cancelled = await self._cancel_all_at_exchange()
        self.state.locked_market_cancelled_orders += cancelled
        return cancelled

    def _uncross_latest_market_data(self) -> None:
        self.state.last_market_data = self._uncross_market_data(self.state.last_market_data)

    def _uncross_market_data(self, market_data: dict[str, Any]) -> dict[str, Any]:
        uncrossed = uncross_market_data(market_data)
        if uncrossed is not market_data:
            self.state.crossed_market_uncrossed_updates += 1
            self.state.locked_market_active = False
        return uncrossed


def parse_fix_message(raw_message: str) -> dict[str, str]:
    normalized = raw_message.strip().replace("|", SOH)
    fields: dict[str, str] = {}
    for token in normalized.split(SOH):
        if not token:
            continue
        if "=" not in token:
            raise FixValidationError(f"Invalid FIX field: {token}")
        tag, value = token.split("=", 1)
        fields[tag] = value
    if not fields:
        raise FixValidationError("Empty FIX message.")
    return fields


def validate_fix_order(fields: dict[str, str]) -> None:
    if fields.get("8") != "FIX.4.4":
        raise FixValidationError("Only FIX.4.4 messages are accepted.")
    if fields.get("35") not in {"D", "F", "G"}:
        raise FixValidationError(
            "Only NewOrderSingle(35=D), OrderCancelRequest(35=F), "
            "and OrderCancelReplaceRequest(35=G) are accepted."
        )
    if not fields.get("11"):
        raise FixValidationError("Client order id tag 11 is required.")


def normalize_fix_message(fields: dict[str, str]) -> str:
    ordered_tags = [
        "8",
        "9",
        "35",
        "49",
        "56",
        "34",
        "52",
        "11",
        "41",
        "55",
        "54",
        "38",
        "40",
        "44",
        "10",
    ]
    seen: set[str] = set()
    parts: list[str] = []
    for tag in ordered_tags:
        if tag in fields:
            parts.append(f"{tag}={fields[tag]}")
            seen.add(tag)
    for tag, value in fields.items():
        if tag not in seen:
            parts.append(f"{tag}={value}")
    return SOH.join(parts) + SOH


def build_fix_execution_report(fields: dict[str, str], accepted: bool, text: str) -> str:
    execution_type = "0" if accepted else "8"
    order_status = "0" if accepted else "8"
    body_fields = {
        "35": "8",
        "49": fields.get("56", "TRADING_ENGINE"),
        "56": fields.get("49", "CLIENT"),
        "11": fields.get("11", "UNKNOWN"),
        "17": f"EXEC-{datetime.now(timezone.utc).timestamp():.6f}",
        "39": order_status,
        "150": execution_type,
        "58": text,
    }
    return build_fix_message(body_fields)


def build_fix_message(body_fields: dict[str, str]) -> str:
    body = SOH.join(f"{tag}={value}" for tag, value in body_fields.items()) + SOH
    header = f"8=FIX.4.4{SOH}9={len(body.encode('utf-8'))}{SOH}"
    message_without_checksum = header + body
    checksum = sum(message_without_checksum.encode("utf-8")) % 256
    return f"{message_without_checksum}10={checksum:03d}{SOH}\n"


def parse_market_data(raw_line: str) -> dict[str, Any]:
    text = raw_line.strip()
    if not text:
        return {}
    if text.startswith("{"):
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Market data JSON must be an object.")
        return payload

    fields: dict[str, Any] = {}
    for token in text.replace(",", " ").split():
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = _coerce_market_data_value(value)
    return fields or {"raw": text}


def best_ask_price(market_data: dict[str, Any]) -> float | None:
    ask = market_data.get("ask")
    if ask is not None and ask != "":
        try:
            return float(ask)
        except (TypeError, ValueError):
            return None

    asks = market_data.get("asks")
    if isinstance(asks, list) and asks:
        first_ask = asks[0]
        if isinstance(first_ask, (list, tuple)) and first_ask:
            try:
                return float(first_ask[0])
            except (TypeError, ValueError):
                return None
        if isinstance(first_ask, dict):
            price = first_ask.get("price") or first_ask.get("ask")
            try:
                return float(price)
            except (TypeError, ValueError):
                return None
    return None


def best_bid_price(market_data: dict[str, Any]) -> float | None:
    bid = market_data.get("bid")
    if bid is not None and bid != "":
        try:
            return float(bid)
        except (TypeError, ValueError):
            return None

    bids = market_data.get("bids")
    if isinstance(bids, list) and bids:
        first_bid = bids[0]
        if isinstance(first_bid, (list, tuple)) and first_bid:
            try:
                return float(first_bid[0])
            except (TypeError, ValueError):
                return None
        if isinstance(first_bid, dict):
            price = first_bid.get("price") or first_bid.get("bid")
            try:
                return float(price)
            except (TypeError, ValueError):
                return None
    return None


def should_hold_for_one_sided_market(fields: dict[str, str], market_data: dict[str, Any]) -> bool:
    if fields.get("35") not in {"D", "G"}:
        return False
    if not _market_data_matches_order_symbol(fields, market_data):
        return False

    has_bid = best_bid_price(market_data) is not None
    has_ask = best_ask_price(market_data) is not None
    if has_bid == has_ask:
        return False

    side = fields.get("54")
    return (has_bid and side == "2") or (has_ask and side == "1")


def can_release_one_sided_order(fields: dict[str, str], market_data: dict[str, Any]) -> bool:
    if not _market_data_matches_order_symbol(fields, market_data):
        return False
    side = fields.get("54")
    return (side == "2" and best_ask_price(market_data) is not None) or (
        side == "1" and best_bid_price(market_data) is not None
    )


def is_locked_market(market_data: dict[str, Any]) -> bool:
    bid = best_bid_price(market_data)
    ask = best_ask_price(market_data)
    if bid is None or ask is None:
        return False
    return bid == ask


def is_crossed_market(market_data: dict[str, Any]) -> bool:
    bid = best_bid_price(market_data)
    ask = best_ask_price(market_data)
    if bid is None or ask is None:
        return False
    return bid > ask


def uncross_market_data(market_data: dict[str, Any]) -> dict[str, Any]:
    if not is_crossed_market(market_data):
        return market_data

    uncrossed = dict(market_data)
    bid = uncrossed.get("bid")
    ask = uncrossed.get("ask")
    if bid is not None and ask is not None:
        uncrossed["bid"], uncrossed["ask"] = ask, bid
        if "bid_size" in uncrossed or "ask_size" in uncrossed:
            uncrossed["bid_size"], uncrossed["ask_size"] = (
                uncrossed.get("ask_size"),
                uncrossed.get("bid_size"),
            )

    bids = uncrossed.get("bids")
    asks = uncrossed.get("asks")
    if isinstance(bids, list) and isinstance(asks, list) and bids and asks:
        uncrossed["bids"], uncrossed["asks"] = asks, bids

    uncrossed["crossed_market_uncrossed"] = True
    return uncrossed


def _market_data_matches_order_symbol(fields: dict[str, str], market_data: dict[str, Any]) -> bool:
    market_symbol = market_data.get("symbol")
    order_symbol = fields.get("55")
    return not market_symbol or not order_symbol or str(market_symbol) == order_symbol


def _coerce_market_data_value(value: str) -> Any:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _split_fix_frames(payload: str) -> list[str]:
    lines = [line for line in payload.replace("\r", "\n").split("\n") if line.strip()]
    if lines:
        return lines
    return [payload]


def _best_effort_fix_fields(raw_message: str) -> dict[str, str]:
    try:
        return parse_fix_message(raw_message)
    except FixValidationError:
        return {}


def _port(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535.")
    return value


def control_enabled(mask: int, flag: int) -> bool:
    return (mask & flag) == flag


def enabled_control_names(mask: int) -> list[str]:
    return [name for flag, name in CONTROL_NAMES.items() if control_enabled(mask, flag)]


def parse_args() -> argparse.Namespace:
    config = TradingPortConfig.from_environment()
    parser = argparse.ArgumentParser(description="Run AlgoEngine local trading engine.")
    parser.add_argument("--system-id", default=config.system_id, help="Trading engine system id.")
    parser.add_argument("--host", default=config.host, help="Engine listen host.")
    parser.add_argument("--client-port", type=int, default=config.client_port, help="FIX client order port.")
    parser.add_argument("--exchange-host", default=config.exchange_host, help="Exchange host; defaults to Exchange Simulator.")
    parser.add_argument("--exchange-port", type=int, default=config.exchange_port, help="Exchange port; defaults to Exchange Simulator port.")
    parser.add_argument("--market-data-port", type=int, default=config.market_data_port, help="Market data input port.")
    parser.add_argument("--admin-port", type=int, default=config.admin_port, help="Admin command port.")
    parser.add_argument(
        "--exchange-timeout",
        type=float,
        default=config.exchange_connect_timeout_seconds,
        help="Exchange connect/read timeout in seconds.",
    )
    parser.add_argument(
        "--controls",
        type=int,
        default=config.controls,
        help=(
            "Bitmask of enabled controls: "
            "1=parent-child, 2=duplicate order ID, 4=kill switch, "
            "8=market order to limit conversion, 16=one-sided market, "
            "32=locked market, 64=crossed market, 128=bad price breach, "
            "256=max evaluation frequency. Use 511 for all current controls."
        ),
    )
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> TradingPortConfig:
    return TradingPortConfig(
        system_id=args.system_id,
        host=args.host,
        client_port=args.client_port,
        exchange_host=args.exchange_host,
        exchange_port=args.exchange_port,
        market_data_port=args.market_data_port,
        admin_port=args.admin_port,
        exchange_connect_timeout_seconds=args.exchange_timeout,
        controls=args.controls,
        bad_price_threshold_bps=TradingPortConfig.from_environment().bad_price_threshold_bps,
        max_evaluation_frequency_hz=TradingPortConfig.from_environment().max_evaluation_frequency_hz,
    )


async def main() -> None:
    engine = LocalTradingEngine(config_from_args(parse_args()))
    print(
        "Starting local trading engine\n"
        f"  client_orders  = {engine.config.host}:{engine.config.client_port}\n"
        f"  exchange       = {engine.config.exchange_host}:{engine.config.exchange_port} (Exchange Simulator)\n"
        f"  market_data    = {engine.config.host}:{engine.config.market_data_port}\n"
        f"  admin_commands = {engine.config.host}:{engine.config.admin_port}\n"
        f"  controls       = {engine.config.controls}:"
        f"{','.join(enabled_control_names(engine.config.controls)) or 'none'}"
    )
    await engine.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())


