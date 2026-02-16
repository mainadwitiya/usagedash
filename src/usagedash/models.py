from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ProviderName(str, Enum):
    CODEX = "codex"
    CLAUDE = "claude"
    GEMINI = "gemini"


class StatusKind(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


class SourceKind(str, Enum):
    PARSED = "parsed"
    MANUAL = "manual"
    MIXED = "mixed"


@dataclass
class ProviderSnapshot:
    provider: ProviderName
    status: StatusKind
    session_used_pct: float | None = None
    session_reset_at: datetime | None = None
    weekly_used_pct: float | None = None
    weekly_reset_at: datetime | None = None
    source: SourceKind = SourceKind.MANUAL
    messages: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UsageSnapshot:
    generated_at: datetime
    providers: list[ProviderSnapshot]
