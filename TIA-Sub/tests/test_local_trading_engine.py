from __future__ import annotations

import asyncio
import json
import unittest

from AlgoEngine.local_engine import (
    FixValidationError,
    LocalTradingEngine,
    TradingPortConfig,
    build_fix_execution_report,
    parse_fix_message,
    parse_market_data,
    validate_fix_order,
)


class LocalTradingEngineTests(unittest.TestCase):
    def test_accepts_fix_44_order_message_types(self) -> None:
        for message_type in ["D", "F", "G"]:
            fields = parse_fix_message(f"8=FIX.4.4|35={message_type}|11=ORDER-1|10=000|")
            validate_fix_order(fields)

    def test_rejects_non_order_fix_messages(self) -> None:
        fields = parse_fix_message("8=FIX.4.4|35=8|11=ORDER-1|10=000|")

        with self.assertRaises(FixValidationError):
            validate_fix_order(fields)

    def test_builds_fix_execution_report_response(self) -> None:
        fields = parse_fix_message("8=FIX.4.4|35=D|49=CLIENT|56=ENGINE|11=ORDER-1|10=000|")

        response = build_fix_execution_report(fields, accepted=True, text="accepted")

        self.assertIn("8=FIX.4.4", response)
        self.assertIn("35=8", response)
        self.assertIn("11=ORDER-1", response)
        self.assertIn("39=0", response)

    def test_parses_json_and_key_value_market_data(self) -> None:
        json_payload = parse_market_data('{"symbol": "AAPL", "bid": 175.1, "ask": 175.2}\n')
        text_payload = parse_market_data("symbol=AAPL bid=175.1 ask=175.2 depth=2\n")

        self.assertEqual("AAPL", json_payload["symbol"])
        self.assertEqual(175.1, text_payload["bid"])
        self.assertEqual(2, text_payload["depth"])

    def test_admin_commands_control_engine_state(self) -> None:
        engine = LocalTradingEngine(TradingPortConfig())

        self.assertIn("running", engine._execute_admin_command("STATUS"))
        self.assertEqual("OK trading_halted=true", engine._execute_admin_command("HALT"))
        status = json.loads(engine._execute_admin_command("STATUS"))

        self.assertEqual("halted", status["status"])
        self.assertEqual("OK trading_halted=false", engine._execute_admin_command("RESUME"))

    def test_snapshot_exposes_configured_ports(self) -> None:
        config = TradingPortConfig(
            client_port=10001,
            exchange_port=10002,
            market_data_port=10003,
            admin_port=10004,
        )
        engine = LocalTradingEngine(config)

        snapshot = engine.snapshot()

        self.assertEqual(10001, snapshot.configuration["client_port"])
        self.assertEqual(10002, snapshot.configuration["exchange_port"])
        self.assertEqual(10003, snapshot.configuration["market_data_port"])
        self.assertEqual(10004, snapshot.configuration["admin_port"])
        self.assertIn("fix_4_4_order_entry", snapshot.capabilities)


class LocalTradingEngineParentChildControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_update_without_parent_before_exchange_routing(self) -> None:
        exchange_connections = 0

        async def handle_exchange(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal exchange_connections
            exchange_connections += 1
            writer.close()
            await writer.wait_closed()

        exchange = await asyncio.start_server(handle_exchange, "127.0.0.1", 0)
        exchange_port = exchange.sockets[0].getsockname()[1]
        engine = LocalTradingEngine(TradingPortConfig(exchange_port=exchange_port))
        try:
            response = await engine._process_fix_order(
                "8=FIX.4.4|35=G|49=CLIENT|56=ENGINE|11=ORD-2|55=AAPL|54=1|38=100|40=2|44=176.00|10=000|"
            )
        finally:
            exchange.close()
            await exchange.wait_closed()

        fields = parse_fix_message(response)
        self.assertEqual("8", fields["150"])
        self.assertEqual("8", fields["39"])
        self.assertIn("PARENT_CHILD_LINK_MISSING", fields["58"])
        self.assertEqual(0, exchange_connections)
        self.assertEqual(1, engine.state.rejected_orders)

    async def test_rejects_update_with_unknown_parent_before_exchange_routing(self) -> None:
        exchange_connections = 0

        async def handle_exchange(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal exchange_connections
            exchange_connections += 1
            writer.close()
            await writer.wait_closed()

        exchange = await asyncio.start_server(handle_exchange, "127.0.0.1", 0)
        exchange_port = exchange.sockets[0].getsockname()[1]
        engine = LocalTradingEngine(TradingPortConfig(exchange_port=exchange_port))
        try:
            response = await engine._process_fix_order(
                "8=FIX.4.4|35=G|49=CLIENT|56=ENGINE|11=ORD-2|41=ORD-UNKNOWN|55=AAPL|54=1|38=100|40=2|44=176.00|10=000|"
            )
        finally:
            exchange.close()
            await exchange.wait_closed()

        fields = parse_fix_message(response)
        self.assertEqual("8", fields["150"])
        self.assertIn("PARENT_CHILD_LINK_NOT_FOUND", fields["58"])
        self.assertEqual(0, exchange_connections)

    async def test_routes_update_when_parent_child_link_matches_known_order(self) -> None:
        async def handle_exchange(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            while raw_order := await reader.readline():
                order = parse_fix_message(raw_order.decode("utf-8"))
                writer.write(build_fix_execution_report(order, accepted=True, text="exchange accepted").encode("utf-8"))
                await writer.drain()
            writer.close()
            await writer.wait_closed()

        exchange = await asyncio.start_server(handle_exchange, "127.0.0.1", 0)
        exchange_port = exchange.sockets[0].getsockname()[1]
        engine = LocalTradingEngine(TradingPortConfig(exchange_port=exchange_port))
        try:
            new_response = await engine._process_fix_order(
                "8=FIX.4.4|35=D|49=CLIENT|56=ENGINE|11=ORD-1|55=AAPL|54=1|38=100|40=2|44=175.00|10=000|"
            )
            update_response = await engine._process_fix_order(
                "8=FIX.4.4|35=G|49=CLIENT|56=ENGINE|11=ORD-2|41=ORD-1|55=AAPL|54=1|38=100|40=2|44=176.00|10=000|"
            )
        finally:
            exchange.close()
            await exchange.wait_closed()

        self.assertEqual("0", parse_fix_message(new_response)["150"])
        self.assertEqual("0", parse_fix_message(update_response)["150"])
        self.assertIn("ORD-1", engine.state.known_order_ids)
        self.assertIn("ORD-2", engine.state.known_order_ids)
        self.assertEqual("ORD-1", engine.state.parent_child_links["ORD-2"])
        self.assertEqual(2, engine.state.forwarded_orders)


if __name__ == "__main__":
    unittest.main()
