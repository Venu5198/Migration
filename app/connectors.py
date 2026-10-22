from abc import ABC, abstractmethod
from typing import Any


class TargetConnector(ABC):
    writes_enabled = False

    @abstractmethod
    async def test_connection(self) -> dict[str, Any]: ...

    async def validate(self, records: list[dict]) -> list[dict]:
        return []

    async def write(self, records: list[dict]) -> None:
        raise PermissionError(
            "Target writes are disabled until an approved connector is configured."
        )


class MockConnector(TargetConnector):
    async def test_connection(self) -> dict[str, Any]:
        return {"connected": True, "kind": "mock", "writes_enabled": False}
