from __future__ import annotations

from app.models.knowledge import KnowledgeBaseVersion


class KnowledgeBaseRepository:
    """In-memory MVP repository; replace with a durable database/vector store adapter."""

    def __init__(self) -> None:
        self._versions: dict[str, KnowledgeBaseVersion] = {}
        self._current_version: str | None = None

    async def publish(self, version: KnowledgeBaseVersion) -> None:
        self._versions[version.version] = version
        self._current_version = version.version

    async def current(self) -> KnowledgeBaseVersion:
        if self._current_version is None:
            raise LookupError("No compliance knowledge version has been published.")
        return self._versions[self._current_version]

    async def get(self, version: str) -> KnowledgeBaseVersion:
        try:
            return self._versions[version]
        except KeyError as exc:
            raise LookupError(f"Unknown compliance knowledge version: {version}") from exc

    async def list_versions(self) -> list[KnowledgeBaseVersion]:
        return list(self._versions.values())

