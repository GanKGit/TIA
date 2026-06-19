from __future__ import annotations

import asyncio
from collections import defaultdict

from app.models.validation import ScenarioObservation, ScenarioRequest, TradingSystemSnapshot
from app.trading.gateway import TradingSystemGateway


class TradingSystemService:
    """The only service validation agents use to communicate with a trading system."""

    def __init__(self, gateway: TradingSystemGateway, timeout_seconds: float = 30.0) -> None:
        self._gateway = gateway
        self._timeout_seconds = timeout_seconds
        self._system_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def get_snapshot(self, system_id: str) -> TradingSystemSnapshot:
        return await asyncio.wait_for(
            self._gateway.get_snapshot(system_id),
            timeout=self._timeout_seconds,
        )

    async def run_scenario(
        self,
        system_id: str,
        request: ScenarioRequest,
    ) -> ScenarioObservation:
        async with self._system_locks[system_id]:
            try:
                return await asyncio.wait_for(
                    self._gateway.execute_scenario(system_id, request),
                    timeout=self._timeout_seconds,
                )
            finally:
                await self._gateway.reset_scenario(system_id, request.correlation_id)

