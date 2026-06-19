from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import json
import ssl
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.models.validation import ScenarioObservation, ScenarioRequest, TradingSystemSnapshot
from app.trading.gateway import TradingSystemGateway


class HttpTradingSystemGateway(TradingSystemGateway):
    """Connects the unified trading service to a trading-system HTTP port."""

    def __init__(
        self,
        host: str,
        port: int,
        protocol: str = "http",
        api_token: str | None = None,
        verify_tls: bool = True,
        request_timeout_seconds: float = 25.0,
        snapshot_path: str = "/systems/{system_id}/snapshot",
        scenario_path: str = "/systems/{system_id}/scenarios",
        reset_path: str = "/systems/{system_id}/scenarios/{correlation_id}/reset",
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("Trading-system port must be between 1 and 65535.")
        if protocol not in {"http", "https"}:
            raise ValueError("Trading-system protocol must be http or https.")

        self.base_url = f"{protocol}://{host}:{port}"
        self.snapshot_path = snapshot_path
        self.scenario_path = scenario_path
        self.reset_path = reset_path
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"
        self.request_timeout_seconds = request_timeout_seconds
        self.ssl_context = None if verify_tls else ssl._create_unverified_context()

    async def get_snapshot(self, system_id: str) -> TradingSystemSnapshot:
        payload = await self._request_json("GET", self._path(self.snapshot_path, system_id))
        payload.setdefault("system_id", system_id)
        return TradingSystemSnapshot.model_validate(payload)

    async def execute_scenario(
        self,
        system_id: str,
        request: ScenarioRequest,
    ) -> ScenarioObservation:
        payload = await self._request_json(
            "POST",
            self._path(self.scenario_path, system_id),
            request.model_dump(mode="json"),
        )
        now = datetime.now(timezone.utc).isoformat()
        payload.setdefault("scenario_name", request.scenario_name)
        payload.setdefault("correlation_id", request.correlation_id)
        payload.setdefault("started_at", now)
        payload.setdefault("completed_at", now)
        return ScenarioObservation.model_validate(payload)

    async def reset_scenario(self, system_id: str, correlation_id: str) -> None:
        await self._request_json(
            "POST",
            self._path(self.reset_path, system_id, correlation_id),
            {"correlation_id": correlation_id},
            allow_empty=True,
        )

    async def close(self) -> None:
        return None

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_json_sync, method, path, payload, allow_empty)

    def _request_json_sync(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        allow_empty: bool,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url=f"{self.base_url}{path}",
            data=body,
            headers=self.headers,
            method=method,
        )
        with urlopen(
            request,
            timeout=self.request_timeout_seconds,
            context=self.ssl_context,
        ) as response:
            content = response.read()
        if not content and allow_empty:
            return {}
        return json.loads(content.decode("utf-8"))

    @staticmethod
    def _encode(value: str) -> str:
        return quote(value, safe="")

    def _path(self, template: str, system_id: str, correlation_id: str = "") -> str:
        return template.format(
            system_id=self._encode(system_id),
            correlation_id=self._encode(correlation_id),
        )
