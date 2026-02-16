from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from usagedash.config import ProviderConfig
from usagedash.models import ProviderName, ProviderSnapshot
from usagedash.providers.base import PartialUsage, ProviderAdapter, merge_usage

FIVE_HOUR_RE = re.compile(r"5h limit:\s*\[[^\]]*\]\s*([0-9]{1,3})% left \(resets ([0-9]{2}:[0-9]{2})\)")
WEEKLY_RE = re.compile(r"Weekly limit:\s*\[[^\]]*\]\s*([0-9]{1,3})% left \(resets ([0-9]{2}:[0-9]{2}) on ([0-9]{1,2} [A-Za-z]{3})\)")


class CodexAdapter(ProviderAdapter):
    name = ProviderName.CODEX

    def __init__(self, history_path: Path | None = None) -> None:
        self.history_path = history_path or Path.home() / ".codex/history.jsonl"

    def collect(self, cfg: ProviderConfig) -> ProviderSnapshot:
        partial = self._parse()
        return merge_usage(self.name, partial, cfg)

    def _parse(self) -> PartialUsage:
        if not self.history_path.exists():
            return PartialUsage(messages=[f"missing {self.history_path}"])

        lines = self.history_path.read_text(errors="ignore").splitlines()[-300:]
        lines.reverse()

        session_used = None
        session_reset = None
        weekly_used = None
        weekly_reset = None
        messages: list[str] = []

        for line in lines:
            if session_used is None:
                m = FIVE_HOUR_RE.search(line)
                if m:
                    left = float(m.group(1))
                    session_used = max(0.0, 100.0 - left)
                    session_reset = datetime.combine(datetime.now().date(), datetime.strptime(m.group(2), "%H:%M").time())

            if weekly_used is None:
                m = WEEKLY_RE.search(line)
                if m:
                    left = float(m.group(1))
                    weekly_used = max(0.0, 100.0 - left)
                    dt_str = f"{m.group(3)} {datetime.now().year} {m.group(2)}"
                    weekly_reset = datetime.strptime(dt_str, "%d %b %Y %H:%M")

            if session_used is not None and weekly_used is not None:
                break

        if session_used is None and weekly_used is None:
            messages.append("unable to parse Codex usage, fallback to manual config")

        return PartialUsage(
            session_used_pct=session_used,
            session_reset_at=session_reset,
            weekly_used_pct=weekly_used,
            weekly_reset_at=weekly_reset,
            messages=messages,
        )
