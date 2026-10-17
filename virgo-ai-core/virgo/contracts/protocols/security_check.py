"""Protocol for bounded local security checks."""

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from virgo.contracts.models.security import SecurityCategory, SecurityFinding


class SecurityCheckProtocol(Protocol):
    check_id: str
    category: SecurityCategory
    description: str

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> Iterable[SecurityFinding]: ...


class VulnerabilityIntelligenceProviderProtocol(Protocol):
    """Optional verified vulnerability data source; never implied by manifests."""

    provider_name: str

    def is_available(self) -> bool: ...
