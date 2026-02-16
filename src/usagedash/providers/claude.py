from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import math
from statistics import quantiles

from usagedash.config import ProviderConfig
from usagedash.models import ProviderName, ProviderSnapshot
from usagedash.providers.base import PartialUsage, ProviderAdapter, merge_usage

DEFAULT_SESSION_TOKEN_LIMIT = 300_000.0
DEFAULT_WEEKLY_TOKEN_LIMIT = 3_000_000.0


class ClaudeAdapter(ProviderAdapter):
    name = ProviderName.CLAUDE

    def __init__(self, stats_path: Path | None = None, projects_path: Path | None = None) -> None:
        self.stats_path = stats_path or Path.home() / ".claude/stats-cache.json"
        self.projects_path = projects_path or Path.home() / ".claude/projects"

    def collect(self, cfg: ProviderConfig) -> ProviderSnapshot:
        partial = self._parse()
        return merge_usage(self.name, partial, cfg)

    def _parse(self) -> PartialUsage:
        if not self.stats_path.exists():
            return PartialUsage(messages=[f"missing {self.stats_path}"])

        data = json.loads(self.stats_path.read_text(errors="ignore"))
        session_used = _pick_float(data, [
            ("limits", "session", "percent_used"),
            ("session", "percent_used"),
            ("session_percent_used",),
        ])
        weekly_used = _pick_float(data, [
            ("limits", "weekly", "percent_used"),
            ("weekly", "percent_used"),
            ("weekly_percent_used",),
        ])

        session_reset = _pick_dt(data, [
            ("limits", "session", "reset_at"),
            ("session", "reset_at"),
            ("session_reset_at",),
        ])
        weekly_reset = _pick_dt(data, [
            ("limits", "weekly", "reset_at"),
            ("weekly", "reset_at"),
            ("weekly_reset_at",),
        ])

        messages: list[str] = []
        details: dict[str, object] | None = None

        # Always attempt project-log analysis — it provides richer metrics
        # (burn rate, P90 limits, model distribution) than stats-cache alone.
        project_partial = self._parse_from_projects()
        if project_partial.details:
            details = project_partial.details
        messages.extend(project_partial.messages or [])

        # Prefer project-log percentages when available (they're derived from
        # actual token counts against P90 limits). Fall back to stats-cache.
        if project_partial.session_used_pct is not None:
            session_used = project_partial.session_used_pct
        if project_partial.weekly_used_pct is not None:
            weekly_used = project_partial.weekly_used_pct
        session_reset = project_partial.session_reset_at or session_reset
        weekly_reset = project_partial.weekly_reset_at or weekly_reset

        if session_used is None and weekly_used is None:
            messages.append("unable to infer Claude usage from stats-cache.json or project logs")

        return PartialUsage(
            session_used_pct=session_used,
            session_reset_at=session_reset,
            weekly_used_pct=weekly_used,
            weekly_reset_at=weekly_reset,
            details=details,
            messages=messages,
        )

    def _parse_from_projects(self) -> PartialUsage:
        if not self.projects_path.exists():
            return PartialUsage(messages=[f"missing {self.projects_path}"])

        now = datetime.now()
        five_hours_ago = now - timedelta(hours=5)
        seven_days_ago = now - timedelta(days=7)

        current_entries: list[tuple[datetime, float, str]] = []
        historical_entries: list[tuple[datetime, float, str]] = []
        weekly_tokens = 0.0

        # Consider top-level session files (exclude subagents) and pick the
        # most active one in the last 5h as "current session".
        candidates = [
            p for p in self.projects_path.rglob("*.jsonl")
            if "/subagents/" not in str(p).replace("\\", "/")
        ]
        if not candidates:
            return PartialUsage(messages=["no Claude session files found in ~/.claude/projects"])

        seen_ids: set[str] = set()
        per_file_entries: dict[Path, list[tuple[datetime, float, str]]] = {p: [] for p in candidates}

        for jsonl_path in candidates:
            try:
                with jsonl_path.open("r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if "\"usage\"" not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = _parse_ts(obj.get("timestamp"))
                        if ts is None:
                            continue
                        if not _is_primary_assistant_usage_entry(obj):
                            continue
                        msg = obj.get("message") or {}
                        usage = msg.get("usage") or {}
                        entry_id = _entry_identity(obj)
                        if not entry_id or entry_id in seen_ids:
                            continue
                        seen_ids.add(entry_id)

                        tokens = _usage_total_tokens(usage)
                        if tokens <= 0:
                            continue
                        model = msg.get("model", "unknown")
                        historical_entries.append((ts, tokens, model))
                        per_file_entries[jsonl_path].append((ts, tokens, model))
                        if ts >= seven_days_ago:
                            weekly_tokens += tokens
            except OSError:
                continue

        if not historical_entries:
            return PartialUsage(messages=["no usage tokens found in project logs"])

        historical_entries.sort(key=lambda x: x[0])
        session_file = _pick_active_session_file(per_file_entries, five_hours_ago)
        current_entries = [
            e for e in per_file_entries.get(session_file, [])
            if e[0] >= five_hours_ago
        ]
        session_tokens = sum(e[1] for e in current_entries)
        session_messages = len(current_entries)

        sessions: list[tuple[datetime, float, int]] = []
        i = 0
        while i < len(historical_entries):
            start = historical_entries[i][0]
            end = start + timedelta(hours=5)
            token_total = 0.0
            msg_total = 0
            while i < len(historical_entries) and historical_entries[i][0] <= end:
                token_total += historical_entries[i][1]
                msg_total += 1
                i += 1
            sessions.append((start, token_total, msg_total))

        token_series = [s[1] for s in sessions]
        msg_series = [float(s[2]) for s in sessions]
        token_limit_p90 = _p90(token_series) or DEFAULT_SESSION_TOKEN_LIMIT
        message_limit_p90 = _p90(msg_series) or 200.0

        current_start = current_entries[0][0] if current_entries else now
        session_reset_at = current_start + timedelta(hours=5)
        elapsed_minutes = max(1.0, (now - current_start).total_seconds() / 60.0)
        burn_rate = session_tokens / elapsed_minutes if session_tokens > 0 else 0.0
        remaining_tokens = max(0.0, token_limit_p90 - session_tokens)
        predicted_runout = (
            now + timedelta(minutes=(remaining_tokens / burn_rate))
            if burn_rate > 0 and remaining_tokens > 0
            else None
        )

        weekly_limit_est = token_limit_p90 * (7.0 * 24.0 / 5.0)
        weekly_pct = (weekly_tokens / weekly_limit_est * 100.0) if weekly_limit_est > 0 else 0.0
        session_pct = (session_tokens / token_limit_p90 * 100.0) if token_limit_p90 > 0 else 0.0
        message_pct = (session_messages / message_limit_p90 * 100.0) if message_limit_p90 > 0 else 0.0

        model_tokens: dict[str, float] = {}
        for _, toks, model in current_entries:
            model_tokens[model] = model_tokens.get(model, 0.0) + toks
        model_distribution = {
            k: round((v / session_tokens * 100.0), 1) for k, v in model_tokens.items()
        } if session_tokens > 0 else {}

        details: dict[str, object] = {
            "dynamic_limits": {
                "session_tokens": int(session_tokens),
                "session_messages": session_messages,
                "weekly_tokens": int(weekly_tokens),
                "token_limit_p90": int(token_limit_p90),
                "message_limit_p90": int(message_limit_p90),
                "token_usage_pct": round(session_pct, 1),
                "message_usage_pct": round(message_pct, 1),
                "burn_rate_tokens_per_min": round(burn_rate, 1),
                "predicted_tokens_runout_at": predicted_runout.isoformat() if predicted_runout else None,
                "session_reset_at": session_reset_at.isoformat(),
                "model_distribution": model_distribution,
            }
        }

        messages = [f"derived Claude metrics from current session file: {session_file.name}"]
        if session_tokens <= 0 and weekly_tokens <= 0:
            messages.append("no usage tokens found in project logs")
            return PartialUsage(messages=messages)

        return PartialUsage(
            session_used_pct=session_pct,
            session_reset_at=session_reset_at,
            weekly_used_pct=weekly_pct,
            weekly_reset_at=now + timedelta(days=7),
            details=details,
            messages=messages,
        )


def _pick(data: dict, path: tuple[str, ...]):
    cur = data
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _pick_float(data: dict, candidates: list[tuple[str, ...]]) -> float | None:
    for path in candidates:
        v = _pick(data, path)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _pick_dt(data: dict, candidates: list[tuple[str, ...]]) -> datetime | None:
    for path in candidates:
        v = _pick(data, path)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
    return None


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _usage_total_tokens(usage: dict) -> float:
    if not isinstance(usage, dict):
        return 0.0
    # Monitor-style session usage should use direct input+output token traffic,
    # excluding cache read/creation tokens that can inflate numbers massively.
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    total = 0.0
    if isinstance(inp, (int, float)):
        total += float(inp)
    if isinstance(out, (int, float)):
        total += float(out)
    return total


def _is_primary_assistant_usage_entry(obj: dict) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("type") != "assistant":
        return False
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return False
    if msg.get("role") != "assistant":
        return False
    return isinstance(msg.get("usage"), dict)


def _entry_identity(obj: dict) -> str | None:
    rid = obj.get("requestId") or obj.get("request_id")
    mid = (obj.get("message") or {}).get("id")
    uid = obj.get("uuid")
    if rid and mid:
        return f"{rid}:{mid}"
    if rid and uid:
        return f"{rid}:{uid}"
    if mid:
        return str(mid)
    if uid:
        return str(uid)
    return None


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    try:
        return quantiles(values, n=10, method="inclusive")[8]
    except Exception:
        # Fallback percentile estimator if statistics backend fails.
        s = sorted(values)
        idx = min(len(s) - 1, max(0, math.ceil(0.9 * len(s)) - 1))
        return s[idx]


def _pick_active_session_file(
    per_file_entries: dict[Path, list[tuple[datetime, float, str]]],
    five_hours_ago: datetime,
) -> Path:
    best_path: Path | None = None
    best_score: tuple[float, datetime] | None = None
    for path, entries in per_file_entries.items():
        recent = [e for e in entries if e[0] >= five_hours_ago]
        recent_tokens = sum(e[1] for e in recent)
        latest_ts = max((e[0] for e in entries), default=datetime.min)
        score = (recent_tokens, latest_ts)
        if best_score is None or score > best_score:
            best_score = score
            best_path = path

    if best_path is None:
        # Should not happen, but keep a deterministic fallback.
        return max(per_file_entries.keys(), key=lambda p: p.stat().st_mtime)
    return best_path
