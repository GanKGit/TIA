from __future__ import annotations

import asyncio
import unittest

from AlgoEngine.client_simulator import (
    ClientOrder,
    ClientSimulatorListener,
    FixClientSimulator,
    build_order_message,
    order_from_command,
    summarize_execution_report,
)
from AlgoEngine.local_engine import build_fix_execution_report, parse_fix_message


class ClientSimulatorTests(unittest.IsolatedAsyncioTestCase):
    def test_builds_new_order_single(self) -> None:
        message = build_order_message(
            ClientOrder(
                order_id="ORD-1",
                symbol="MSFT",
                side="2",
                quantity=50,
                price=415.5,
            )
        )
        fields = parse_fix_message(message)

        self.assertEqual("FIX.4.4", fields["8"])
        self.assertEqual("D", fields["35"])
        self.assertEqual("ORD-1", fields["11"])
        self.assertEqual("MSFT", fields["55"])
        self.assertEqual("2", fields["54"])
        self.assertEqual("50", fields["38"])
        self.assertEqual("415.50", fields["44"])

    def test_builds_cancel_replace_with_original_order_id(self) -> None:
        message = build_order_message(
            ClientOrder(
                message_type="G",
                order_id="ORD-2",
                original_order_id="ORD-1",
            )
        )
        fields = parse_fix_message(message)

        self.assertEqual("G", fields["35"])
        self.assertEqual("ORD-2", fields["11"])
        self.assertEqual("ORD-1", fields["41"])

    def test_builds_order_from_nc_command(self) -> None:
        order = order_from_command(
            "SELL order-id=ORD-SELL symbol=MSFT quantity=50 price=410.25"
        )

        self.assertEqual("D", order.message_type)
        self.assertEqual("ORD-SELL", order.order_id)
        self.assertEqual("MSFT", order.symbol)
        self.assertEqual("2", order.side)
        self.assertEqual(50, order.quantity)
        self.assertEqual(410.25, order.price)

    def test_builds_cancel_from_nc_command(self) -> None:
        order = order_from_command(
            "CANCEL order-id=CXL-1 original-order-id=ORD-1 symbol=AAPL side=1"
        )

        self.assertEqual("F", order.message_type)
        self.assertEqual("CXL-1", order.order_id)
        self.assertEqual("ORD-1", order.original_order_id)

    async def test_sends_order_and_receives_execution_report(self) -> None:
        async def handle_order(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            raw_order = await reader.readline()
            fields = parse_fix_message(raw_order.decode("utf-8"))
            writer.write(build_fix_execution_report(fields, accepted=True, text="dummy accepted").encode("utf-8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle_order, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            simulator = FixClientSimulator(port=port)
            response = await simulator.send_order(ClientOrder(order_id="ORD-ROUNDTRIP"))
        finally:
            server.close()
            await server.wait_closed()

        self.assertEqual("8", response["35"])
        self.assertEqual("ORD-ROUNDTRIP", response["11"])
        self.assertEqual("0", response["39"])
        self.assertIn("dummy accepted", summarize_execution_report(response))

    async def test_listener_accepts_nc_command_and_returns_report(self) -> None:
        async def handle_order(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            raw_order = await reader.readline()
            fields = parse_fix_message(raw_order.decode("utf-8"))
            writer.write(build_fix_execution_report(fields, accepted=True, text="listener accepted").encode("utf-8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        engine = await asyncio.start_server(handle_order, "127.0.0.1", 0)
        engine_port = engine.sockets[0].getsockname()[1]
        listener = ClientSimulatorListener(listen_port=0, engine_port=engine_port)
        await listener.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", listener.bound_port)
            banner = await reader.readline()
            writer.write(b"NEW order-id=ORD-NC symbol=AAPL side=1 quantity=10 price=101.25\n")
            await writer.drain()
            report = (await reader.readline()).decode("utf-8")
            summary = (await reader.readline()).decode("utf-8")
            writer.write(b"QUIT\n")
            await writer.drain()
            await reader.readline()
            writer.close()
            await writer.wait_closed()
        finally:
            await listener.stop()
            engine.close()
            await engine.wait_closed()

        self.assertIn("client simulator ready", banner.decode("utf-8"))
        self.assertIn("11=ORD-NC", report)
        self.assertIn("listener accepted", summary)


if __name__ == "__main__":
    unittest.main()
