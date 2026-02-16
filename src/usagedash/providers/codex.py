from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import re

from usagedash.config import ProviderConfig
from usagedash.models import ProviderName, ProviderSnapshot
from usagedash.providers.base import PartialUsage, ProviderAdapter, merge_usage

FIVE_HOUR_RE = re.compile(r"5h limit:\s*\[[^\]]*\]\s*([0-9]{1,3})% left \(resets ([0-9]{2}:[0-9]{2})\)")
WEEKLY_RE = re.compile(r"Weekly limit:\s*\[[^\]]*\]\s*([0-9]{1,3})% left \(resets ([0-9]{2}:[0-9]{2}) on ([0-9]{1,2} [A-Za-z]{3})\)")


class CodexAdapter(ProviderAdapter):
    name = ProviderName.CODEX

    def __init__(
        self,
        history_path: Path | None = None,
        sessions_path: Path | None = None,
    ) -> None:
        self.history_path = history_path or Path.home() / ".codex/history.jsonl"
        self.sessions_path = sessions_path or Path.home() / ".codex/sessions"

    def collect(self, cfg: ProviderConfig) -> ProviderSnapshot:
        partial = self._parse()
        return merge_usage(self.name, partial, cfg)

    def _parse(self) -> PartialUsage:
        # Try structured session files first (much richer data).
        session_partial = self._parse_from_sessions()
        if session_partial.session_used_pct is not None:
            return session_partial

        # Fall back to regex parsing of history.jsonl.
        return self._parse_from_history()

    def _parse_from_sessions(self) -> PartialUsage:
        if not self.sessions_path.exists():
            return PartialUsage(messages=["no Codex sessions directory found"])

        now = datetime.now()
        five_hours_ago = now - timedelta(hours=5)

        # Find recent session files (today + yesterday to cover edge cases).
        candidates: list[Path] = []
        for day_offset in range(2):
            day = now - timedelta(days=day_offset)
            day_dir = self.sessions_path / day.strftime("%Y/%m/%d")
            if day_dir.exists():
                candidates.extend(sorted(day_dir.glob("rollout-*.jsonl"), reverse=True))

        if not candidates:
            return PartialUsage(messages=["no recent Codex session files found"])

        # Read the most recent session file for rate_limits and token data.
        latest_rate_limits: dict | None = None
        latest_rl_ts: datetime | None = None
        session_tokens = 0
        session_messages = 0
        session_start: datetime | None = None
        model_name: str | None = None
        context_window: int | None = None

        for session_file in candidates:
            found_in_file = False
            try:
                with session_file.open("r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        ts_str = obj.get("timestamp")
                        ts = _parse_ts(ts_str)
                        event_type = obj.get("type", "")

                        # Extract session metadata.
                        if event_type == "session_meta":
                            payload = obj.get("payload", {})
                            meta_model = (payload.get("base_instructions") or {})
                            if not model_name:
                                model_name = payload.get("model") or None

                        # Extract rate limits and token usage from token_count events.
                        if event_type == "event_msg":
                            payload = obj.get("payload", {})
                            if payload.get("type") == "token_count":
                                info = payload.get("info") or {}
                                rl = payload.get("rate_limits") or info.get("rate_limits")
                                if rl and ts:
                                    if latest_rl_ts is None or ts >= latest_rl_ts:
                                        latest_rate_limits = rl
                                        latest_rl_ts = ts
                                        found_in_file = True

                                # Track context window.
                                cw = info.get("model_context_window")
                                if isinstance(cw, int) and cw > 0:
                                    context_window = cw

                                # Accumulate token usage from last_token_usage.
                                last_usage = info.get("last_token_usage", {})
                                if isinstance(last_usage, dict) and ts and ts >= five_hours_ago:
                                    inp = last_usage.get("input_tokens", 0)
                                    out = last_usage.get("output_tokens", 0)
                                    reasoning = last_usage.get("reasoning_output_tokens", 0)
                                    if isinstance(inp, (int, float)):
                                        session_tokens += int(inp)
                                    if isinstance(out, (int, float)):
                                        session_tokens += int(out)
                                    session_messages += 1
                                    if session_start is None or (ts and ts < session_start):
                                        session_start = ts

            except OSError:
                continue

            # If we found rate limits in the most recent file, use it.
            if found_in_file:
                break

        if latest_rate_limits is None:
            return PartialUsage(messages=["no rate limit data found in Codex session files"])

        # Parse structured rate limits.
        primary = latest_rate_limits.get("primary", {})
        secondary = latest_rate_limits.get("secondary", {})

        session_used = primary.get("used_percent")
        weekly_used = secondary.get("used_percent")

        session_reset = _unix_to_dt(primary.get("resets_at"))
        weekly_reset = _unix_to_dt(secondary.get("resets_at"))

        if isinstance(session_used, (int, float)):
            session_used = float(session_used)
        else:
            session_used = None
        if isinstance(weekly_used, (int, float)):
            weekly_used = float(weekly_used)
        else:
            weekly_used = None

        # Calculate burn rate.
        elapsed_minutes = max(1.0, (now - (session_start or now)).total_seconds() / 60.0) if session_start else 0.0
        burn_rate = session_tokens / elapsed_minutes if session_tokens > 0 and elapsed_minutes > 0 else 0.0

        # Build details.
        details: dict[str, object] = {
            "codex_limits": {
                "session_used_pct": session_used,
                "weekly_used_pct": weekly_used,
                "session_tokens": session_tokens,
                "session_messages": session_messages,
                "burn_rate_tokens_per_min": round(burn_rate, 1),
                "context_window": context_window,
                "model": model_name,
                "session_window_minutes": primary.get("window_minutes"),
                "weekly_window_minutes": secondary.get("window_minutes"),
            }
        }

        messages = [f"parsed from Codex session: {candidates[0].name}"]

        return PartialUsage(
            session_used_pct=session_used,
            session_reset_at=session_reset,
            weekly_used_pct=weekly_used,
            weekly_reset_at=weekly_reset,
            details=details,
            messages=messages,
        )

    def _parse_from_history(self) -> PartialUsage:
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
            messages.append("unable to parse Codex usage from sessions or history")

        return PartialUsage(
            session_used_pct=session_used,
            session_reset_at=session_reset,
            weekly_used_pct=weekly_used,
            weekly_reset_at=weekly_reset,
            messages=messages,
        )


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _unix_to_dt(value: int | float | None) -> datetime | None:
    if value is None or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value)
    except (OSError, ValueError):
        return None
