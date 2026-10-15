"""Common data model shared by all source collectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Candidate:
    """One report of an object from one source."""

    name: str
    ra: float  # degrees, J2000
    dec: float  # degrees, J2000
    source: str
    url: str = ""
    mag: float | None = None
    band: str = ""
    mag_kind: str = ""  # "discovery", "latest" or ""
    disc_date: datetime | None = None
    obj_type: str = ""  # e.g. "nova candidate", "SN Ia", "transient"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["disc_date"] = self.disc_date.isoformat() if self.disc_date else None
        return d


@dataclass
class SourceResult:
    """What a collector returns, including its health for the digest."""

    source: str
    candidates: list[Candidate] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)  # non-positional news (ATel)
    ok: bool = True
    error: str = ""
    fetched: int = 0
