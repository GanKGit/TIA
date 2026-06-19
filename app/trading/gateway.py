from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.validation import ScenarioObservation, ScenarioRequest, TradingSystemSnapshot


class TradingSystemGateway(ABC):
    """Adapter contract implemented once per trading platform or test harness."""

    @abstractmethod
    async def get_snapshot(self, system_id: str) -> TradingSystemSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def execute_scenario(
        self,
        system_id: str,
        request: ScenarioRequest,
    ) -> ScenarioObservation:
        raise NotImplementedError

    @abstractmethod
    async def reset_scenario(self, system_id: str, correlation_id: str) -> None:
        raise NotImplementedError

