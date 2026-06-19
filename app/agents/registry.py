from __future__ import annotations

from app.agents import (
    BadPriceBreachAgent,
    CrossedMarketAgent,
    DuplicateOrderAgent,
    KillSwitchAgent,
    LockedMarketAgent,
    MarketOrderCheckAgent,
    MaxEvaluationFrequencyAgent,
    OneSidedMarketAgent,
    ParentChildAgent,
)
from app.agents.base import ValidationAgent
from app.trading.service import TradingSystemService


class ValidationAgentRegistry:
    def __init__(self, trading_system: TradingSystemService) -> None:
        agents = [
            ParentChildAgent(trading_system),
            DuplicateOrderAgent(trading_system),
            BadPriceBreachAgent(trading_system),
            MarketOrderCheckAgent(trading_system),
            KillSwitchAgent(trading_system),
            MaxEvaluationFrequencyAgent(trading_system),
            CrossedMarketAgent(trading_system),
            LockedMarketAgent(trading_system),
            OneSidedMarketAgent(trading_system),
        ]
        self._agents: dict[str, ValidationAgent] = {
            agent.agent_name: agent for agent in agents
        }

    def get(self, agent_name: str) -> ValidationAgent | None:
        return self._agents.get(agent_name)

    def names(self) -> list[str]:
        return sorted(self._agents)
