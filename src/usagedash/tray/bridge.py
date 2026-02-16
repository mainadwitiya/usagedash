from __future__ import annotations

from pathlib import Path

from usagedash.snapshot import read_snapshot


def summary_line(state_file: str) -> str:
    path = Path(state_file)
    if not path.exists():
        return "UsageDash: snapshot missing"

    snap = read_snapshot(path)
    parts: list[str] = []
    for p in snap.providers:
        s = f"{p.provider.value}:S{_fmt(p.session_used_pct)} W{_fmt(p.weekly_used_pct)}"
        parts.append(s)
    return " | ".join(parts) if parts else "UsageDash: no providers"


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}%"
