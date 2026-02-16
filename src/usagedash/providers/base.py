from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from usagedash.config import ProviderConfig
from usagedash.models import ProviderName, ProviderSnapshot, SourceKind, StatusKind


@dataclass
class PartialUsage:
    session_used_pct: float | None = None
    session_reset_at: datetime | None = None
    weekly_used_pct: float | None = None
    weekly_reset_at: datetime | None = None
    details: dict[str, object] | None = None
    messages: list[str] | None = None


class ProviderAdapter(ABC):
    name: ProviderName

    @abstractmethod
    def collect(self, cfg: ProviderConfig) -> ProviderSnapshot:
        raise NotImplementedError


def merge_usage(name: ProviderName, partial: PartialUsage | None, cfg: ProviderConfig) -> ProviderSnapshot:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    parsed = partial or PartialUsage(messages=[])
    messages = list(parsed.messages or [])

    session_used = parsed.session_used_pct if parsed.session_used_pct is not None else cfg.manual.session_used_pct
    session_reset = parsed.session_reset_at or cfg.manual.session_reset_at
    weekly_used = parsed.weekly_used_pct if parsed.weekly_used_pct is not None else cfg.manual.weekly_used_pct
    weekly_reset = parsed.weekly_reset_at or cfg.manual.weekly_reset_at

    parsed_any = any(
        v is not None for v in [parsed.session_used_pct, parsed.session_reset_at, parsed.weekly_used_pct, parsed.weekly_reset_at]
    )
    manual_any = any(
        v is not None for v in [cfg.manual.session_used_pct, cfg.manual.session_reset_at, cfg.manual.weekly_used_pct, cfg.manual.weekly_reset_at]
    )

    if parsed_any and manual_any:
        source = SourceKind.MIXED
    elif parsed_any:
        source = SourceKind.PARSED
    else:
        source = SourceKind.MANUAL

    if session_used is not None or weekly_used is not None:
        if session_reset is not None or weekly_reset is not None:
            status = StatusKind.OK
        else:
            status = StatusKind.PARTIAL
            messages.append("usage detected but reset timestamps missing")
    elif parsed_any or manual_any:
        status = StatusKind.PARTIAL
    else:
        status = StatusKind.ERROR
        messages.append("no usage metrics detected; configure providers.<name>.manual.*")

    return ProviderSnapshot(
        provider=name,
        status=status,
        session_used_pct=session_used,
        session_reset_at=session_reset,
        weekly_used_pct=weekly_used,
        weekly_reset_at=weekly_reset,
        source=source,
        messages=messages,
        details=parsed.details or {},
        updated_at=now,
    )
