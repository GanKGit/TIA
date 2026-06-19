from __future__ import annotations

import asyncio
import unittest

from AlgoEngine.client_simulator import ClientOrder, FixClientSimulator
from AlgoEngine.exchange_simulator import (
    ExchangeSimulator,
    ExchangeSimulatorConfig,
    build_exchange_report,
)
from AlgoEngine.local_engine import (
    LocalTradingEngine,
    TradingPortConfig,
    normalize_fix_message,
    parse_fix_message,
)


class ExchangeSimulatorTests(unittest.IsolatedAsyncioTestCase):
    def test_builds_fill_report_for_new_order(self) -> None:
        order = parse_fix_message(
            "8=FIX.4.4|35=D|49=ENGINE|56=SIM_EXCHANGE|11=ORD-1|55=AAPL|54=1|38=100|40=2|44=175.25|10=000|"
        )

        report = parse_fix_message(build_exchange_report(order))

        self.assertEqual("8", report["35"])
        self.assertEqual("2", report["150"])
        self.assertEqual("2", report["39"])
        self.assertEqual("ORD-1", report["11"])
        self.assertEqual("100", report["32"])
        self.assertEqual("175.25", report["31"])

    def test_builds_cancel_report_for_cancel_request(self) -> None:
        order = parse_fix_message(
            "8=FIX.4.4|35=F|49=ENGINE|56=SIM_EXCHANGE|11=CXL-1|41=ORD-1|55=AAPL|54=1|38=100|10=000|"
        )

        report = parse_fix_message(build_exchange_report(order))

        self.assertEqual("8", report["35"])
        self.assertEqual("4", report["150"])
        self.assertEqual("4", report["39"])
        self.assertEqual("CXL-1", report["11"])
        self.assertEqual("ORD-1", report["41"])

    async def test_exchange_receives_order_and_rests_on_book(self) -> None:
        exchange = ExchangeSimulator(ExchangeSimulatorConfig(port=0))
        await exchange.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", exchange.bound_port)
            order = parse_fix_message(
                "8=FIX.4.4|35=D|49=ENGINE|56=SIM_EXCHANGE|11=ORD-2|55=MSFT|54=2|38=50|40=2|44=410.00|10=000|"
            )
            writer.write((normalize_fix_message(order) + "\n").encode("utf-8"))
            await writer.drain()
            report = parse_fix_message((await reader.readline()).decode("utf-8"))
            writer.close()
            await writer.wait_closed()
        finally:
            await exchange.stop()

        self.assertEqual("ORD-2", report["11"])
        self.assertEqual("0", report["150"])
        self.assertEqual("0", report["39"])
        self.assertEqual(1, exchange.state.received_orders)
        self.assertEqual(1, exchange.state.resting_orders)

    async def test_crossing_orders_fill_incoming_and_resting_parties(self) -> None:
        exchange = ExchangeSimulator(ExchangeSimulatorConfig(port=0))
        await exchange.start()
        try:
            resting_reader, resting_writer = await asyncio.open_connection("127.0.0.1", exchange.bound_port)
            incoming_reader, incoming_writer = await asyncio.open_connection("127.0.0.1", exchange.bound_port)
            resting_order = parse_fix_message(
                "8=FIX.4.4|35=D|49=SELLER|56=SIM_EXCHANGE|11=AAPL-ASK-1|55=AAPL|54=2|38=100|40=2|44=175.00|10=000|"
            )
            incoming_order = parse_fix_message(
                "8=FIX.4.4|35=D|49=BUYER|56=SIM_EXCHANGE|11=AAPL-BUY-1|55=AAPL|54=1|38=100|40=2|44=175.05|10=000|"
            )

            resting_writer.write((normalize_fix_message(resting_order) + "\n").encode("utf-8"))
            await resting_writer.drain()
            resting_ack = parse_fix_message((await resting_reader.readline()).decode("utf-8"))

            incoming_writer.write((normalize_fix_message(incoming_order) + "\n").encode("utf-8"))
            await incoming_writer.drain()
            incoming_fill = parse_fix_message((await incoming_reader.readline()).decode("utf-8"))
            resting_fill = parse_fix_message((await resting_reader.readline()).decode("utf-8"))

            resting_writer.close()
            incoming_writer.close()
            await resting_writer.wait_closed()
            await incoming_writer.wait_closed()
        finally:
            await exchange.stop()

        self.assertEqual("0", resting_ack["150"])
        self.assertEqual("AAPL-BUY-1", incoming_fill["11"])
        self.assertEqual("AAPL-ASK-1", resting_fill["11"])
        self.assertEqual("2", incoming_fill["150"])
        self.assertEqual("2", resting_fill["150"])
        self.assertEqual("175.00", incoming_fill["31"])
        self.assertEqual("0", incoming_fill["151"])
        self.assertEqual(0, exchange.state.resting_orders)

    async def test_engine_forwards_exchange_fill_to_client(self) -> None:
        exchange = ExchangeSimulator(ExchangeSimulatorConfig(port=0))
        await exchange.start()
        resting_reader, resting_writer = await asyncio.open_connection("127.0.0.1", exchange.bound_port)
        resting_order = parse_fix_message(
            "8=FIX.4.4|35=D|49=SELLER|56=SIM_EXCHANGE|11=IBM-ASK-1|55=IBM|54=2|38=25|40=2|44=130.50|10=000|"
        )
        resting_writer.write((normalize_fix_message(resting_order) + "\n").encode("utf-8"))
        await resting_writer.drain()
        await resting_reader.readline()
        engine = LocalTradingEngine(
            TradingPortConfig(
                client_port=0,
                exchange_port=exchange.bound_port,
                market_data_port=0,
                admin_port=0,
            )
        )
        await engine.start()
        client_port = int(engine._servers[0].sockets[0].getsockname()[1])
        try:
            client = FixClientSimulator(port=client_port)
            response = await client.send_order(
                ClientOrder(order_id="ORD-FILL", symbol="IBM", quantity=25, price=130.5)
            )
            resting_fill = parse_fix_message((await resting_reader.readline()).decode("utf-8"))
        finally:
            await engine.stop()
            await exchange.stop()
            resting_writer.close()
            await resting_writer.wait_closed()

        self.assertEqual("8", response["35"])
        self.assertEqual("2", response["150"])
        self.assertEqual("2", response["39"])
        self.assertEqual("ORD-FILL", response["11"])
        self.assertEqual("25", response["32"])
        self.assertEqual("IBM-ASK-1", resting_fill["11"])
        self.assertEqual(2, exchange.state.received_orders)
        self.assertEqual(1, engine.state.forwarded_orders)


if __name__ == "__main__":
    unittest.main()
