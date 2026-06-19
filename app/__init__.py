"""TIA Trade Investigative Agents application and API factory."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.models.investigation import InvestigationRequest
from app.services.compliance_pipeline import CompliancePlatform
from app.services.investigation_service import AgenticInvestigationService, DEMO_INVESTIGATION_CASES


class ValidationRequest(BaseModel):
    system_id: str
    knowledge_version: Optional[str] = None
    dry_run: bool = True


def create_api_app():
    from fastapi import FastAPI

    api = FastAPI(title="TIA - Trade Investigative Agents", version="0.1.0")
    platform = CompliancePlatform()

    @api.on_event("startup")
    async def initialize_platform() -> None:
        await platform.initialize()

    @api.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @api.get("/agents")
    async def agents() -> dict:
        return {"count": len(platform.agent_registry.names()), "agents": platform.agent_registry.names()}

    @api.get("/knowledge/current")
    async def current_knowledge() -> dict:
        knowledge = await platform.knowledge_base.current()
        return knowledge.model_dump(mode="json")

    @api.get("/knowledge/versions")
    async def knowledge_versions() -> dict:
        versions = await platform.knowledge_base.list_versions()
        return {"count": len(versions), "versions": [item.model_dump(mode="json") for item in versions]}


    @api.get("/investigations/cases")
    async def investigation_cases() -> dict:
        return {"count": len(DEMO_INVESTIGATION_CASES), "cases": DEMO_INVESTIGATION_CASES}

    @api.post("/investigations")
    async def investigate(request: InvestigationRequest) -> dict:
        finding = await AgenticInvestigationService(platform).investigate(request)
        return finding.model_dump(mode="json")
    @api.post("/validations")
    async def validate(request: ValidationRequest) -> dict:
        result = await platform.validator.validate_system(
            system_id=request.system_id,
            knowledge_version=request.knowledge_version,
            dry_run=request.dry_run,
        )
        payload = result.model_dump(mode="json")
        payload["overall_status"] = result.overall_status.value
        return payload

    return api


