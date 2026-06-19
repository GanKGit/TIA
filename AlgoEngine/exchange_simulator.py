from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from AlgoEngine.local_engine import build_fix_message, parse_fix_message


@dataclass(frozen=True)
class ExchangeSimulatorConfig:
    host: str = "127.0.0.1"
    port: int = 9601
    sender_comp_id: str = "SIM_EXCHANGE"
    default_fill_price: float | None = None


@dataclass
class ExchangeSimulatorState:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    received_orders: int = 0
    sent_reports: int = 0
    resting_orders: int = 0
    last_order: dict[str, str] = field(default_factory=dict)
    last_report: dict[str, str] = field(default_factory=dict)


@dataclass
class RestingOrder:
    fields: dict[str, str]
    remaining_quantity: int
    price: float
    sequence: int
    writer: asyncio.StreamWriter

    @property
    def order_id(self) -> str:
        return self.fields.get("11", "")

    @property
    def symbol(self) -> str:
        return self.fields.get("55", "")

    @property
    def side(self) -> str:
        return self.fields.get("54", "")


class ExchangeSimulator:
    """Local exchange simulator with a simple price-time order book."""

    def __init__(self, config: ExchangeSimulatorConfig | None = None) -> None:
        self.config = config or ExchangeSimulatorConfig()
        self.state = ExchangeSimulatorState()
        self._server: asyncio.AbstractServer | None = None
        self._stop_event: asyncio.Event | None = None
        self._books: dict[str, dict[str, list[RestingOrder]]] = {}
        self._sequence = 0

    async def start(self) -> None:
        self._stop_event = asyncio.Event()
        self._server = await asyncio.start_server(
            self._handle_engine_connection,
            self.config.host,
            self.config.port,
        )

    async def serve_forever(self) -> None:
        await self.start()
        try:
            if self._stop_event is None:
                raise RuntimeError("Exchange simulator stop event was not initialized.")
            await self._stop_event.wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            return self.config.port
        return int(self._server.sockets[0].getsockname()[1])

    def status(self) -> dict[str, Any]:
        return {
            "status": "running" if self._server else "stopped",
            "host": self.config.host,
            "port": self.bound_port,
            "started_at": self.state.started_at.isoformat(),
            "received_orders": self.state.received_orders,
            "sent_reports": self.state.sent_reports,
            "resting_orders": self.state.resting_orders,
            "books": self.book_snapshot(),
            "last_order": self.state.last_order,
            "last_report": self.state.last_report,
        }

    def book_snapshot(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        snapshot: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for symbol, book in self._books.items():
            snapshot[symbol] = {
                "bids": [_snapshot_order(order) for order in book["bids"]],
                "asks": [_snapshot_order(order) for order in book["asks"]],
            }
        return snapshot

    async def _handle_engine_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while raw_order := await reader.readline():
                order = parse_fix_message(raw_order.decode("utf-8", errors="replace"))
                if _is_status_query(order):
                    writer.write((json.dumps(self.status(), sort_keys=True) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue
                self.state.received_orders += 1
                self.state.last_order = order
                reports = await self.process_order(order, writer)
                for report in reports:
                    await self._send_report(writer, report)
        finally:
            writer.close()
            await writer.wait_closed()

    async def process_order(
        self,
        order: dict[str, str],
        writer: asyncio.StreamWriter,
    ) -> list[str]:
        if order.get("35") == "K":
            return await self._cancel_all_orders(order)
        if order.get("35") == "F":
            return await self._cancel_order(order, writer)

        incoming = self._to_resting_order(order, writer)
        reports = await self._match_order(incoming)
        if incoming.remaining_quantity > 0:
            self._add_to_book(incoming)
            reports.append(_build_accepted_report(incoming, self.config))
        self._refresh_resting_count()
        return reports

    async def _match_order(self, incoming: RestingOrder) -> list[str]:
        reports: list[str] = []
        contra_side = "asks" if incoming.side == "1" else "bids"
        contra_orders = self._book(incoming.symbol)[contra_side]

        while incoming.remaining_quantity > 0 and contra_orders:
            resting = contra_orders[0]
            if not _prices_cross(incoming, resting):
                break

            fill_quantity = min(incoming.remaining_quantity, resting.remaining_quantity)
            fill_price = self.config.default_fill_price or resting.price
            incoming.remaining_quantity -= fill_quantity
            resting.remaining_quantity -= fill_quantity

            reports.append(
                _build_fill_report_for_order(
                    incoming,
                    self.config,
                    fill_quantity,
                    fill_price,
                    "Matched by simulated exchange.",
                )
            )
            await self._send_report(
                resting.writer,
                _build_fill_report_for_order(
                    resting,
                    self.config,
                    fill_quantity,
                    fill_price,
                    "Resting order matched by simulated exchange.",
                ),
            )

            if resting.remaining_quantity <= 0:
                contra_orders.pop(0)

        return reports

    async def _cancel_all_orders(self, request: dict[str, str]) -> list[str]:
        cancelled = 0
        for book in self._books.values():
            for side in ["bids", "asks"]:
                while book[side]:
                    order = book[side].pop(0)
                    cancelled += 1
                    await self._send_report(
                        order.writer,
                        _build_kill_cancel_report_for_order(order, self.config),
                    )
        self._refresh_resting_count()
        return [_build_cancel_all_ack(request, self.config, cancelled)]

    async def _cancel_order(
        self,
        cancel: dict[str, str],
        writer: asyncio.StreamWriter,
    ) -> list[str]:
        order_id = cancel.get("41") or cancel.get("11", "")
        canceled = self._remove_order(order_id)
        if canceled is None:
            return [_build_reject_report(cancel, self.config, f"Order not found: {order_id}")]

        cancel_report = _build_cancel_report_for_order(canceled, cancel, self.config)
        await self._send_report(canceled.writer, cancel_report)
        self._refresh_resting_count()
        return [cancel_report]

    async def _send_report(self, writer: asyncio.StreamWriter, report: str) -> None:
        try:
            writer.write(report.encode("utf-8"))
            await writer.drain()
            self.state.sent_reports += 1
            self.state.last_report = parse_fix_message(report)
        except (ConnectionError, RuntimeError):
            return

    def _to_resting_order(self, order: dict[str, str], writer: asyncio.StreamWriter) -> RestingOrder:
        self._sequence += 1
        return RestingOrder(
            fields=order,
            remaining_quantity=_quantity(order),
            price=_price(order),
            sequence=self._sequence,
            writer=writer,
        )

    def _add_to_book(self, order: RestingOrder) -> None:
        side = "bids" if order.side == "1" else "asks"
        orders = self._book(order.symbol)[side]
        orders.append(order)
        if side == "bids":
            orders.sort(key=lambda item: (-item.price, item.sequence))
        else:
            orders.sort(key=lambda item: (item.price, item.sequence))
        self._refresh_resting_count()

    def _remove_order(self, order_id: str) -> RestingOrder | None:
        for book in self._books.values():
            for side in ["bids", "asks"]:
                for index, order in enumerate(book[side]):
                    if order.order_id == order_id:
                        return book[side].pop(index)
        return None

    def _book(self, symbol: str) -> dict[str, list[RestingOrder]]:
        return self._books.setdefault(symbol, {"bids": [], "asks": []})

    def _refresh_resting_count(self) -> None:
        self.state.resting_orders = sum(
            len(book["bids"]) + len(book["asks"])
            for book in self._books.values()
        )


def build_exchange_report(order: dict[str, str], config: ExchangeSimulatorConfig | None = None) -> str:
    """Compatibility helper that builds a single immediate report for a FIX order."""
    config = config or ExchangeSimulatorConfig()
    if order.get("35") == "F":
        return _build_cancel_report_for_fields(order, config)
    return _build_fill_report_for_fields(order, config)


def _build_accepted_report(order: RestingOrder, config: ExchangeSimulatorConfig) -> str:
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": order.fields.get("49", "ENGINE"),
        "11": order.order_id,
        "17": f"ACK-{uuid4().hex[:12].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "0",
        "150": "0",
        "55": order.symbol,
        "54": order.side,
        "14": "0",
        "151": str(order.remaining_quantity),
        "58": "Accepted and resting on simulated exchange book.",
    }
    return build_fix_message(body_fields)


def _build_fill_report_for_order(
    order: RestingOrder,
    config: ExchangeSimulatorConfig,
    fill_quantity: int,
    fill_price: float,
    text: str,
) -> str:
    status = "2" if order.remaining_quantity == 0 else "1"
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": order.fields.get("49", "ENGINE"),
        "11": order.order_id,
        "17": f"FILL-{uuid4().hex[:12].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": status,
        "150": "2",
        "55": order.symbol,
        "54": order.side,
        "14": str(_quantity(order.fields) - order.remaining_quantity),
        "32": str(fill_quantity),
        "31": f"{fill_price:.2f}",
        "151": str(order.remaining_quantity),
        "58": text,
    }
    if order.fields.get("41"):
        body_fields["41"] = order.fields["41"]
    return build_fix_message(body_fields)


def _build_cancel_report_for_order(
    canceled: RestingOrder,
    cancel: dict[str, str],
    config: ExchangeSimulatorConfig,
) -> str:
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": cancel.get("49", "ENGINE"),
        "11": cancel.get("11", "UNKNOWN"),
        "41": canceled.order_id,
        "17": f"CXL-{uuid4().hex[:12].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "4",
        "150": "4",
        "55": canceled.symbol,
        "54": canceled.side,
        "14": "0",
        "151": "0",
        "58": "Canceled by simulated exchange.",
    }
    return build_fix_message({tag: value for tag, value in body_fields.items() if value})


def _build_kill_cancel_report_for_order(
    canceled: RestingOrder,
    config: ExchangeSimulatorConfig,
) -> str:
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": canceled.fields.get("49", "ENGINE"),
        "11": canceled.order_id,
        "17": f"KILL-CXL-{uuid4().hex[:8].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "4",
        "150": "4",
        "55": canceled.symbol,
        "54": canceled.side,
        "14": "0",
        "151": "0",
        "58": "Canceled by AlgoEngine kill switch.",
    }
    return build_fix_message(body_fields)


def _build_cancel_all_ack(
    request: dict[str, str],
    config: ExchangeSimulatorConfig,
    cancelled: int,
) -> str:
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": request.get("49", "ENGINE"),
        "11": request.get("11", "KILL"),
        "17": f"KILL-ACK-{uuid4().hex[:8].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "0",
        "150": "0",
        "911": str(cancelled),
        "58": f"Kill switch cancel-all completed; cancelled {cancelled} resting orders.",
    }
    return build_fix_message(body_fields)


def _build_reject_report(order: dict[str, str], config: ExchangeSimulatorConfig, text: str) -> str:
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": order.get("49", "ENGINE"),
        "11": order.get("11", "UNKNOWN"),
        "17": f"REJ-{uuid4().hex[:12].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "8",
        "150": "8",
        "58": text,
    }
    return build_fix_message(body_fields)


def _build_fill_report_for_fields(order: dict[str, str], config: ExchangeSimulatorConfig) -> str:
    quantity = order.get("38", "0")
    fill_price = config.default_fill_price or _price(order)
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": order.get("49", "ENGINE"),
        "11": order.get("11", "UNKNOWN"),
        "17": f"FILL-{uuid4().hex[:12].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "2",
        "150": "2",
        "55": order.get("55", ""),
        "54": order.get("54", ""),
        "14": quantity,
        "32": quantity,
        "31": f"{fill_price:.2f}",
        "151": "0",
        "58": "Filled by simulated exchange.",
    }
    if order.get("41"):
        body_fields["41"] = order["41"]
    return build_fix_message(body_fields)


def _build_cancel_report_for_fields(order: dict[str, str], config: ExchangeSimulatorConfig) -> str:
    body_fields = {
        "35": "8",
        "49": config.sender_comp_id,
        "56": order.get("49", "ENGINE"),
        "11": order.get("11", "UNKNOWN"),
        "41": order.get("41", ""),
        "17": f"CXL-{uuid4().hex[:12].upper()}",
        "37": f"EXCH-{uuid4().hex[:12].upper()}",
        "39": "4",
        "150": "4",
        "55": order.get("55", ""),
        "54": order.get("54", ""),
        "14": "0",
        "151": "0",
        "58": "Canceled by simulated exchange.",
    }
    return build_fix_message({tag: value for tag, value in body_fields.items() if value})


def _prices_cross(incoming: RestingOrder, resting: RestingOrder) -> bool:
    if incoming.side == "1":
        return incoming.price >= resting.price
    return incoming.price <= resting.price


def _quantity(order: dict[str, str]) -> int:
    return int(float(order.get("38") or "0"))


def _price(order: dict[str, str]) -> float:
    try:
        return float(order.get("44") or "0")
    except ValueError:
        return 0.0


def _snapshot_order(order: RestingOrder) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "side": order.side,
        "price": order.price,
        "remaining_quantity": order.remaining_quantity,
        "sequence": order.sequence,
    }


def _is_status_query(order: dict[str, str]) -> bool:
    return order.get("35") == "U100" and order.get("9000", "").upper() == "STATUS"


async def run_server(args: argparse.Namespace) -> None:
    simulator = ExchangeSimulator(
        ExchangeSimulatorConfig(
            host=args.host,
            port=args.port,
            sender_comp_id=args.sender,
            default_fill_price=args.fill_price,
        )
    )
    print(f"Starting exchange simulator {args.host}:{args.port}")
    print(json.dumps(simulator.status(), sort_keys=True))
    await simulator.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AlgoEngine local exchange simulator.")
    parser.add_argument("--host", default="127.0.0.1", help="Exchange simulator host.")
    parser.add_argument("--port", type=int, default=9601, help="Exchange simulator port.")
    parser.add_argument("--sender", default="SIM_EXCHANGE", help="Exchange SenderCompID, FIX tag 49.")
    parser.add_argument("--fill-price", type=float, default=None, help="Override fill price for all fills.")
    return parser.parse_args()


def main() -> None:
    asyncio.run(run_server(parse_args()))


if __name__ == "__main__":
    main()

