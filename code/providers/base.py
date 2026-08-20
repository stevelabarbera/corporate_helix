from __future__ import annotations
from typing import Protocol
from models import ProviderResult

class CorporateDataProvider(Protocol):
    name: str
    def discover(self, query: str) -> ProviderResult:
        ...
