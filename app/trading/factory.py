from __future__ import annotations

import os

from app.trading.algo_engine_gateway import AlgoEngineTcpConfig, AlgoEngineTcpGateway
from app.trading.demo_gateway import DemoTradingSystemGateway
from app.trading.gateway import TradingSystemGateway
from app.trading.http_gateway import HttpTradingSystemGateway

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False


load_dotenv()


def gateway_from_environment() -> TradingSystemGateway:
    gateway_type = os.getenv("TRADING_SYSTEM_GATEWAY", "demo").strip().lower()
    if gateway_type == "demo":
        return DemoTradingSystemGateway()
    if gateway_type in {"algoengine", "algoengine_tcp", "tcp"}:
        return AlgoEngineTcpGateway(
            AlgoEngineTcpConfig(
                host=os.getenv("ALGOENGINE_HOST", "127.0.0.1"),
                client_port=int(os.getenv("ALGOENGINE_CLIENT_PORT", "9500")),
                market_data_port=int(os.getenv("ALGOENGINE_MARKET_DATA_PORT", "9501")),
                admin_port=int(os.getenv("ALGOENGINE_ADMIN_PORT", "9502")),
                exchange_host=os.getenv("DUMMY_EXCHANGE_HOST", os.getenv("ALGOENGINE_HOST", "127.0.0.1")),
                exchange_query_port=int(os.getenv("DUMMY_EXCHANGE_QUERY_PORT", "9602")),
                timeout_seconds=float(os.getenv("ALGOENGINE_SCENARIO_TIMEOUT_SECONDS", "5")),
            )
        )
    if gateway_type != "http":
        raise ValueError(f"Unsupported TRADING_SYSTEM_GATEWAY: {gateway_type}")

    return HttpTradingSystemGateway(
        host=os.getenv("TRADING_SYSTEM_HOST", "127.0.0.1"),
        port=int(os.getenv("TRADING_SYSTEM_PORT", "8080")),
        protocol=os.getenv("TRADING_SYSTEM_PROTOCOL", "http").lower(),
        api_token=os.getenv("TRADING_SYSTEM_API_TOKEN") or None,
        verify_tls=_as_bool(os.getenv("TRADING_SYSTEM_VERIFY_TLS", "true")),
        request_timeout_seconds=float(os.getenv("TRADING_SYSTEM_REQUEST_TIMEOUT_SECONDS", "25")),
        snapshot_path=os.getenv("TRADING_SYSTEM_SNAPSHOT_PATH", "/systems/{system_id}/snapshot"),
        scenario_path=os.getenv("TRADING_SYSTEM_SCENARIO_PATH", "/systems/{system_id}/scenarios"),
        reset_path=os.getenv(
            "TRADING_SYSTEM_RESET_PATH",
            "/systems/{system_id}/scenarios/{correlation_id}/reset",
        ),
    )


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

