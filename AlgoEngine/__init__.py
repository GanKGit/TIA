"""Local TCP trading engine for compliance validation demos."""

__all__ = [
    "ClientOrder",
    "ClientSimulatorListener",
    "ExchangeSimulator",
    "ExchangeSimulatorConfig",
    "FixClientSimulator",
    "LocalTradingEngine",
    "TradingPortConfig",
]


def __getattr__(name: str):
    if name in {"ClientOrder", "ClientSimulatorListener", "FixClientSimulator"}:
        from AlgoEngine import client_simulator

        return getattr(client_simulator, name)
    if name in {"ExchangeSimulator", "ExchangeSimulatorConfig"}:
        from AlgoEngine import exchange_simulator

        return getattr(exchange_simulator, name)
    if name in {"LocalTradingEngine", "TradingPortConfig"}:
        from AlgoEngine import local_engine

        return getattr(local_engine, name)
    raise AttributeError(f"module 'AlgoEngine' has no attribute {name!r}")
