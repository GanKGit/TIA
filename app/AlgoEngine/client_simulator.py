from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from AlgoEngine.local_engine import SOH, build_fix_message, parse_fix_message


@dataclass(frozen=True)
class ClientOrder:
    message_type: str = "D"
    order_id: str = ""
    symbol: str = "AAPL"
    side: str = "1"
    quantity: int = 100
    order_type: str = "2"
    price: float | None = 175.25
    original_order_id: str = ""
    sender_comp_id: str = "CLIENT1"
    target_comp_id: str = "ENGINE"

    def with_default_order_id(self) -> "ClientOrder":
        if self.order_id:
            return self
        return ClientOrder(
            message_type=self.message_type,
            order_id=f"ORD-{uuid4().hex[:8].upper()}",
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            order_type=self.order_type,
            price=self.price,
            original_order_id=self.original_order_id,
            sender_comp_id=self.sender_comp_id,
            target_comp_id=self.target_comp_id,
        )


class FixClientSimulator:
    """TCP client that sends FIX 4.4 orders and reads execution reports."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9500,
        read_timeout_seconds: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.read_timeout_seconds = read_timeout_seconds

    async def send_order(self, order: ClientOrder) -> dict[str, str]:
        responses = await self.send_orders([order])
        return responses[0]

    async def send_raw_message(self, message: str) -> dict[str, str]:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(_line(message).encode("utf-8"))
            await writer.drain()
            raw_response = await asyncio.wait_for(
                reader.readline(),
                timeout=self.read_timeout_seconds,
            )
            return parse_fix_message(raw_response.decode("utf-8", errors="replace"))
        finally:
            writer.close()
            await writer.wait_closed()

    async def send_orders(self, orders: Iterable[ClientOrder]) -> list[dict[str, str]]:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            responses: list[dict[str, str]] = []
            for order in orders:
                message = build_order_message(order)
                writer.write(message.encode("utf-8"))
                await writer.drain()
                raw_response = await asyncio.wait_for(
                    reader.readline(),
                    timeout=self.read_timeout_seconds,
                )
                responses.append(parse_fix_message(raw_response.decode("utf-8", errors="replace")))
            return responses
        finally:
            writer.close()
            await writer.wait_closed()


def build_order_message(order: ClientOrder) -> str:
    order = order.with_default_order_id()
    body_fields = {
        "35": order.message_type,
        "49": order.sender_comp_id,
        "56": order.target_comp_id,
        "34": "1",
        "52": datetime.now(timezone.utc).strftime("%Y%m%d-%H:%M:%S.%f")[:-3],
        "11": order.order_id,
        "55": order.symbol,
        "54": order.side,
        "38": str(order.quantity),
        "40": order.order_type,
    }
    if order.message_type in {"F", "G"} and order.original_order_id:
        body_fields["41"] = order.original_order_id
    if order.price is not None and order.order_type == "2":
        body_fields["44"] = f"{order.price:.2f}"
    return to_printable_fix(build_fix_message(body_fields))


def order_from_command(command: str) -> ClientOrder:
    fields = _parse_command_fields(command)
    message_type = fields.get("message-type") or fields.get("type") or fields.get("35") or "D"
    return ClientOrder(
        message_type=message_type.upper(),
        order_id=fields.get("order-id") or fields.get("order_id") or fields.get("11") or "",
        symbol=fields.get("symbol") or fields.get("55") or "AAPL",
        side=fields.get("side") or fields.get("54") or "1",
        quantity=int(fields.get("quantity") or fields.get("qty") or fields.get("38") or "100"),
        order_type=fields.get("order-type") or fields.get("ordtype") or fields.get("40") or "2",
        price=_optional_float(fields.get("price") or fields.get("44")),
        original_order_id=(
            fields.get("original-order-id")
            or fields.get("original_order_id")
            or fields.get("origclordid")
            or fields.get("41")
            or ""
        ),
        sender_comp_id=fields.get("sender") or fields.get("49") or "CLIENT1",
        target_comp_id=fields.get("target") or fields.get("56") or "ENGINE",
    )


def is_raw_fix(command: str) -> bool:
    normalized = command.strip().replace(SOH, "|")
    return normalized.startswith("8=FIX.4.4|") or ("35=" in normalized and "11=" in normalized)


def to_printable_fix(message: str) -> str:
    return message.replace(SOH, "|")


def summarize_execution_report(fields: dict[str, str]) -> str:
    status = fields.get("39", "?")
    execution_type = fields.get("150", "?")
    order_id = fields.get("11", "UNKNOWN")
    text = fields.get("58", "")
    return f"order_id={order_id} exec_type={execution_type} status={status} text={text}"


class ClientSimulatorListener:
    """nc-friendly TCP listener that submits typed orders to AlgoEngine."""

    def __init__(
        self,
        listen_host: str = "127.0.0.1",
        listen_port: int = 9890,
        engine_host: str = "127.0.0.1",
        engine_port: int = 9500,
        read_timeout_seconds: float = 5.0,
    ) -> None:
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.engine_client = FixClientSimulator(engine_host, engine_port, read_timeout_seconds)
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_connection,
            self.listen_host,
            self.listen_port,
        )

    async def serve_forever(self) -> None:
        await self.start()
        if self._server is None:
            raise RuntimeError("Client simulator listener failed to start.")
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            return self.listen_port
        return int(self._server.sockets[0].getsockname()[1])

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        writer.write(_listener_banner().encode("utf-8"))
        await writer.drain()
        try:
            while raw_command := await reader.readline():
                command = raw_command.decode("utf-8", errors="replace").strip()
                if not command:
                    continue
                if command.upper() in {"QUIT", "EXIT"}:
                    writer.write(b"BYE\n")
                    await writer.drain()
                    break
                if command.upper() == "HELP":
                    writer.write(_listener_help().encode("utf-8"))
                    await writer.drain()
                    continue

                try:
                    response = await self.submit_command(command)
                    writer.write((format_response(response) + "\n").encode("utf-8"))
                    writer.write((summarize_execution_report(response) + "\n").encode("utf-8"))
                except Exception as exc:
                    writer.write(f"ERROR {exc}\n".encode("utf-8"))
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def submit_command(self, command: str) -> dict[str, str]:
        if is_raw_fix(command):
            return await self.engine_client.send_raw_message(command)
        return await self.engine_client.send_order(order_from_command(command))


def format_response(fields: dict[str, str]) -> str:
    return to_printable_fix(SOH.join(f"{tag}={value}" for tag, value in fields.items()) + SOH)


async def run_once(args: argparse.Namespace) -> None:
    simulator = FixClientSimulator(args.host, args.port, args.timeout)
    orders = [
        ClientOrder(
            message_type=args.message_type,
            order_id=args.order_id if args.count == 1 else f"{args.order_id}-{index + 1}",
            symbol=args.symbol,
            side=args.side,
            quantity=args.quantity,
            order_type=args.order_type,
            price=args.price,
            original_order_id=args.original_order_id,
            sender_comp_id=args.sender,
            target_comp_id=args.target,
        )
        for index in range(args.count)
    ]
    responses = await simulator.send_orders(orders)
    for response in responses:
        print(format_response(response))
        print(summarize_execution_report(response))


async def run_listener(args: argparse.Namespace) -> None:
    listener = ClientSimulatorListener(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        engine_host=args.host,
        engine_port=args.port,
        read_timeout_seconds=args.timeout,
    )
    print(
        "Starting client simulator listener "
        f"listen={args.listen_host}:{args.listen_port} "
        f"engine={args.host}:{args.port}"
    )
    await listener.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send FIX 4.4 orders to AlgoEngine.")
    parser.add_argument("--host", default="127.0.0.1", help="Trading engine client host.")
    parser.add_argument("--port", type=int, default=9500, help="Trading engine client port.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Response read timeout in seconds.")
    parser.add_argument("--listen", action="store_true", help="Run as an nc-friendly order listener.")
    parser.add_argument("--listen-host", default="127.0.0.1", help="Client simulator listen host.")
    parser.add_argument("--listen-port", type=int, default=9890, help="Client simulator listen port.")
    parser.add_argument("--message-type", choices=["D", "F", "G"], default="D", help="FIX 35 value.")
    parser.add_argument("--order-id", default="ORD-1", help="Client order id, FIX tag 11.")
    parser.add_argument("--original-order-id", default="", help="Original client order id, FIX tag 41.")
    parser.add_argument("--symbol", default="AAPL", help="Symbol, FIX tag 55.")
    parser.add_argument("--side", choices=["1", "2"], default="1", help="Side: 1=buy, 2=sell.")
    parser.add_argument("--quantity", type=int, default=100, help="Order quantity, FIX tag 38.")
    parser.add_argument("--order-type", choices=["1", "2"], default="2", help="Order type: 1=market, 2=limit.")
    parser.add_argument("--price", type=float, default=175.25, help="Limit price, FIX tag 44.")
    parser.add_argument("--sender", default="CLIENT1", help="SenderCompID, FIX tag 49.")
    parser.add_argument("--target", default="ENGINE", help="TargetCompID, FIX tag 56.")
    parser.add_argument("--count", type=int, default=1, help="Number of orders to send.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.listen:
        asyncio.run(run_listener(args))
        return
    asyncio.run(run_once(args))


def _parse_command_fields(command: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    tokens = command.replace(",", " ").split()
    if tokens and "=" not in tokens[0]:
        first = tokens.pop(0).upper()
        aliases = {
            "NEW": "D",
            "BUY": "D",
            "SELL": "D",
            "CANCEL": "F",
            "REPLACE": "G",
            "AMEND": "G",
        }
        fields["message-type"] = aliases.get(first, first)
        if first == "SELL":
            fields["side"] = "2"
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"Invalid token '{token}'. Expected key=value.")
        key, value = token.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _optional_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _line(message: str) -> str:
    return message if message.endswith("\n") else message + "\n"


def _listener_banner() -> str:
    return (
        "AlgoEngine client simulator ready. Type HELP for examples, "
        "or QUIT to close this session.\n"
    )


def _listener_help() -> str:
    return (
        "Examples:\n"
        "NEW order-id=ORD-1 symbol=AAPL side=1 quantity=100 price=175.25\n"
        "SELL order-id=ORD-2 symbol=MSFT quantity=50 price=410.00\n"
        "CANCEL order-id=CXL-1 original-order-id=ORD-1 symbol=AAPL side=1\n"
        "REPLACE order-id=RPL-1 original-order-id=ORD-1 symbol=AAPL side=1 quantity=150 price=176.00\n"
        "Raw FIX is also accepted, e.g. 8=FIX.4.4|35=D|11=ORD-1|55=AAPL|54=1|38=100|40=2|44=175.25|10=000|\n"
    )


if __name__ == "__main__":
    main()

