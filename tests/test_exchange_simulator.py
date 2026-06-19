from __future__ import annotations

import asyncio
import json
import unittest

from AlgoEngine.exchange_simulator import ExchangeSimulator, ExchangeSimulatorConfig


class ExchangeSimulatorStatusTests(unittest.TestCase):
    def test_status_query_returns_current_book_snapshot(self) -> None:
        async def scenario() -> dict:
            simulator = ExchangeSimulator(ExchangeSimulatorConfig(port=0))
            await simulator.start()
            port = simulator.bound_port
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(
                    b"8=FIX.4.4|35=D|49=ENGINE|56=SIM_EXCHANGE|11=AAPL-BID-1|"
                    b"55=AAPL|54=1|38=100|40=2|44=175.00|10=000|\n"
                )
                await writer.drain()
                await asyncio.sleep(0.05)
                writer.close()
                await writer.wait_closed()

                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(b"8=FIX.4.4|35=U100|49=UI|56=SIM_EXCHANGE|9000=STATUS|10=000|\n")
                await writer.drain()
                payload = await reader.readline()
                writer.close()
                await writer.wait_closed()
                return json.loads(payload.decode("utf-8"))
            finally:
                await simulator.stop()

        snapshot = asyncio.run(scenario())

        self.assertEqual(snapshot["status"], "running")
        self.assertEqual(snapshot["resting_orders"], 1)
        self.assertEqual(snapshot["books"]["AAPL"]["bids"][0]["order_id"], "AAPL-BID-1")


if __name__ == "__main__":
    unittest.main()
