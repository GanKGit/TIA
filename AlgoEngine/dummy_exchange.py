from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from AlgoEngine.local_engine import SOH, build_fix_execution_report, parse_fix_message


class DummyExchange:
    """TCP exchange stub that prints inbound engine messages and sends FIX acks."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9601,
        query_port: int = 9602,
        capture_log: str = "outputs/algoengine_dummy_exchange_messages.jsonl",
    ) -> None:
        self.host = host
        self.port = port
        self.query_port = query_port
        self.capture_log = Path(capture_log)
        self.received_messages = 0
        self._captured_messages: list[dict[str, Any]] = []
        self._server: asyncio.AbstractServer | None = None
        self._query_server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self.host, self.port)
        self._query_server = await asyncio.start_server(self._handle_query_connection, self.host, self.query_port)
        exchange_bound = self._server.sockets[0].getsockname()
        query_bound = self._query_server.sockets[0].getsockname()
        print(f"Exchange Simulator listening on {exchange_bound[0]}:{exchange_bound[1]}", flush=True)
        print(f"Exchange Simulator query API on {query_bound[0]}:{query_bound[1]}", flush=True)
        print(f"Exchange Simulator capture log: {self.capture_log}", flush=True)

    async def serve_forever(self) -> None:
        await self.start()
        if self._server is None or self._query_server is None:
            raise RuntimeError("Exchange Simulator servers were not started.")
        async with self._server, self._query_server:
            await asyncio.gather(
                self._server.serve_forever(),
                self._query_server.serve_forever(),
            )

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        print(f"Accepted connection from {peer}", flush=True)
        try:
            while raw_message := await reader.readline():
                self.received_messages += 1
                message = raw_message.decode("utf-8", errors="replace")
                fields = parse_fix_message(message)
                self._print_message(message, fields)
                self._capture_message(message, fields)
                writer.write(build_fix_execution_report(fields, accepted=True, text="Exchange Simulator accepted.").encode("utf-8"))
                await writer.drain()
        except Exception as exc:
            print(f"Connection error from {peer}: {exc}", flush=True)
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"Closed connection from {peer}", flush=True)

    async def _handle_query_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw_command = await reader.readline()
            command = raw_command.decode("utf-8", errors="replace").strip()
            response = self._build_query_response(command)
            writer.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as exc:
            error = {"error": str(exc), "messages": [], "total_received": self.received_messages}
            writer.write((json.dumps(error, sort_keys=True) + "\n").encode("utf-8"))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def _build_query_response(self, command: str) -> dict[str, Any]:
        if command == "GET STATUS":
            return {
                "total_received": self.received_messages,
                "captured": len(self._captured_messages),
            }
        if command.startswith("GET MESSAGES"):
            order_id = None
            since_sequence = 0
            for token in command.split()[2:]:
                if token.startswith("order_id="):
                    order_id = token.split("=", 1)[1]
                elif token.startswith("since_sequence="):
                    since_sequence = int(token.split("=", 1)[1])
            messages = [
                record
                for record in self._captured_messages
                if int(record["sequence"]) > since_sequence
            ]
            if order_id is not None:
                messages = [
                    record
                    for record in messages
                    if record.get("fields", {}).get("11") == order_id
                ]
            return {
                "messages": messages,
                "total_received": self.received_messages,
            }
        return {
            "error": "unsupported_command",
            "supported_commands": ["GET STATUS", "GET MESSAGES", "GET MESSAGES order_id=<id>", "GET MESSAGES since_sequence=<n>"],
            "messages": [],
            "total_received": self.received_messages,
        }

    def _print_message(self, raw_message: str, fields: dict[str, str]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        printable_fix = raw_message.strip().replace(SOH, "|")
        print(
            "\n".join(
                [
                    f"[{timestamp}] message #{self.received_messages}",
                    f"raw_fix={printable_fix}",
                    f"fields={json.dumps(fields, sort_keys=True)}",
                ]
            ),
            flush=True,
        )

    def _capture_message(self, raw_message: str, fields: dict[str, str]) -> None:
        record = {
            "sequence": self.received_messages,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "raw_fix": raw_message.strip().replace(SOH, "|"),
            "fields": fields,
        }
        self._captured_messages.append(record)
        self.capture_log.parent.mkdir(parents=True, exist_ok=True)
        with self.capture_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Exchange Simulator that prints AlgoEngine messages.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/interface to bind.")
    parser.add_argument("--port", type=int, default=9601, help="Port to listen on for local_engine connections.")
    parser.add_argument(
        "--query-port",
        type=int,
        default=int(os.getenv("DUMMY_EXCHANGE_QUERY_PORT", "9602")),
        help="Port where validators can query captured exchange messages.",
    )
    parser.add_argument(
        "--capture-log",
        default=os.getenv("DUMMY_EXCHANGE_CAPTURE_LOG", "outputs/algoengine_dummy_exchange_messages.jsonl"),
        help="JSONL file where received exchange messages are captured for debugging.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await DummyExchange(args.host, args.port, args.query_port, args.capture_log).serve_forever()


if __name__ == "__main__":
    asyncio.run(main())



