"""Pure data contracts shared by the recovery index and Tool layer."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class IndexDocument:
    case_id: str
    source_incident_ids: tuple[int, ...]
    origin: str
    signature: str
    service: str | None
    text: str
    passed_count: int = 1
    failed_count: int = 0
    parent_case_id: str | None = None
    section: str = "case"


@dataclass(frozen=True)
class SearchHit:
    citation_id: str
    case_id: str
    source_incident_ids: tuple[int, ...]
    origin: str
    signature: str
    service: str | None
    excerpt: str
    score: float
    passed_count: int
    failed_count: int
    section: str = "case"
    parent_case_id: str | None = None


@dataclass(frozen=True)
class SearchResult:
    status: Literal["success", "no_data", "error"]
    hits: list[SearchHit] = field(default_factory=list)
    corpus_version: str | None = None
    degraded: bool = False
    stale: bool = False
    error: str | None = None
