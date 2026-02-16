from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json

from usagedash.config import Config
from usagedash.models import UsageSnapshot
from usagedash.providers import ClaudeAdapter, CodexAdapter, GeminiAdapter


def build_snapshot(cfg: Config) -> UsageSnapshot:
    providers = []

    if cfg.providers["codex"].enabled:
        providers.append(CodexAdapter().collect(cfg.providers["codex"]))
    if cfg.providers["claude"].enabled:
        providers.append(ClaudeAdapter().collect(cfg.providers["claude"]))
    if cfg.providers["gemini"].enabled:
        providers.append(GeminiAdapter().collect(cfg.providers["gemini"]))

    return UsageSnapshot(generated_at=datetime.now(timezone.utc).replace(tzinfo=None), providers=providers)


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"not serializable: {type(obj)!r}")


def snapshot_to_json(snapshot: UsageSnapshot) -> str:
    return json.dumps(asdict(snapshot), default=_json_default, indent=2)


def write_snapshot_files(cfg: Config, snapshot: UsageSnapshot) -> None:
    body = snapshot_to_json(snapshot)

    state_file = Path(cfg.general.state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(body)

    mirror = Path(cfg.general.windows_state_path)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(body)


def read_snapshot(path: str | Path) -> UsageSnapshot:
    raw = json.loads(Path(path).read_text())
    providers = []
    from usagedash.models import ProviderSnapshot, ProviderName, StatusKind, SourceKind

    for item in raw["providers"]:
        providers.append(
            ProviderSnapshot(
                provider=ProviderName(item["provider"]),
                status=StatusKind(item["status"]),
                session_used_pct=item.get("session_used_pct"),
                session_reset_at=datetime.fromisoformat(item["session_reset_at"]) if item.get("session_reset_at") else None,
                weekly_used_pct=item.get("weekly_used_pct"),
                weekly_reset_at=datetime.fromisoformat(item["weekly_reset_at"]) if item.get("weekly_reset_at") else None,
                source=SourceKind(item["source"]),
                messages=item.get("messages", []),
                details=item.get("details", {}),
                updated_at=datetime.fromisoformat(item["updated_at"]),
            )
        )

    return UsageSnapshot(generated_at=datetime.fromisoformat(raw["generated_at"]), providers=providers)
