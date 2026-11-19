"""Finding model shared by audit, verify, convert and install."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

SEVERITIES = ("error", "warning", "info")
_RANK = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    target: str = ""
    path: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def rank(severity: str) -> int:
    return _RANK.get(severity, 99)


def sort_findings(findings: List[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda item: (rank(item.severity), item.code, item.path))


def count(findings: List[Finding]) -> Dict[str, int]:
    return {
        "error": sum(1 for item in findings if item.severity == "error"),
        "warning": sum(1 for item in findings if item.severity == "warning"),
        "info": sum(1 for item in findings if item.severity == "info"),
    }
