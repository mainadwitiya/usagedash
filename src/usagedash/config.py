from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import tomllib
import tomli_w


HOME = Path.home()
CONFIG_PATH = HOME / ".config/usagedash/config.toml"


@dataclass
class ManualFields:
    session_used_pct: float | None = None
    session_reset_at: datetime | None = None
    weekly_used_pct: float | None = None
    weekly_reset_at: datetime | None = None


@dataclass
class ProviderConfig:
    enabled: bool = True
    parser_mode: str = "hybrid"
    manual: ManualFields = field(default_factory=ManualFields)


@dataclass
class AppConfig:
    refresh_seconds: int = 2
    timezone: str = "local"
    state_file: str = str(HOME / ".local/state/usagedash/latest.json")
    windows_state_path: str = "/mnt/c/Users/Public/AppData/Local/UsageDash/latest.json"


@dataclass
class TrayConfig:
    enabled: bool = True
    poll_seconds: int = 15
    autostart: bool = True


@dataclass
class Config:
    general: AppConfig = field(default_factory=AppConfig)
    tray: TrayConfig = field(default_factory=TrayConfig)
    providers: dict[str, ProviderConfig] = field(
        default_factory=lambda: {
            "codex": ProviderConfig(enabled=True),
            "claude": ProviderConfig(enabled=True),
            "gemini": ProviderConfig(enabled=False, parser_mode="manual"),
        }
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _provider_from_dict(raw: dict) -> ProviderConfig:
    manual_raw = raw.get("manual", {})
    manual = ManualFields(
        session_used_pct=manual_raw.get("session_used_pct"),
        session_reset_at=_parse_dt(manual_raw.get("session_reset_at")),
        weekly_used_pct=manual_raw.get("weekly_used_pct"),
        weekly_reset_at=_parse_dt(manual_raw.get("weekly_reset_at")),
    )
    return ProviderConfig(enabled=raw.get("enabled", True), parser_mode=raw.get("parser_mode", "hybrid"), manual=manual)


def _provider_to_dict(cfg: ProviderConfig) -> dict:
    manual: dict[str, object] = {}
    if cfg.manual.session_used_pct is not None:
        manual["session_used_pct"] = cfg.manual.session_used_pct
    if cfg.manual.session_reset_at is not None:
        manual["session_reset_at"] = cfg.manual.session_reset_at.isoformat()
    if cfg.manual.weekly_used_pct is not None:
        manual["weekly_used_pct"] = cfg.manual.weekly_used_pct
    if cfg.manual.weekly_reset_at is not None:
        manual["weekly_reset_at"] = cfg.manual.weekly_reset_at.isoformat()

    return {
        "enabled": cfg.enabled,
        "parser_mode": cfg.parser_mode,
        "manual": manual,
    }


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        cfg = Config()
        save_config(cfg, path)
        return cfg

    raw = tomllib.loads(path.read_text())
    general_raw = raw.get("general", {})
    tray_raw = raw.get("tray", {})
    providers_raw = raw.get("providers", {})

    cfg = Config(
        general=AppConfig(
            refresh_seconds=int(general_raw.get("refresh_seconds", 2)),
            timezone=general_raw.get("timezone", "local"),
            state_file=general_raw.get("state_file", str(HOME / ".local/state/usagedash/latest.json")),
            windows_state_path=general_raw.get("windows_state_path", "/mnt/c/Users/Public/AppData/Local/UsageDash/latest.json"),
        ),
        tray=TrayConfig(
            enabled=bool(tray_raw.get("enabled", True)),
            poll_seconds=int(tray_raw.get("poll_seconds", 15)),
            autostart=bool(tray_raw.get("autostart", True)),
        ),
        providers={
            "codex": _provider_from_dict(providers_raw.get("codex", {})),
            "claude": _provider_from_dict(providers_raw.get("claude", {})),
            "gemini": _provider_from_dict(providers_raw.get("gemini", {"enabled": False, "parser_mode": "manual"})),
        },
    )
    return cfg


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "general": {
            "refresh_seconds": cfg.general.refresh_seconds,
            "timezone": cfg.general.timezone,
            "state_file": cfg.general.state_file,
            "windows_state_path": cfg.general.windows_state_path,
        },
        "tray": {
            "enabled": cfg.tray.enabled,
            "poll_seconds": cfg.tray.poll_seconds,
            "autostart": cfg.tray.autostart,
        },
        "providers": {name: _provider_to_dict(pc) for name, pc in cfg.providers.items()},
    }
    path.write_text(tomli_w.dumps(payload))


def set_config_value(cfg: Config, dotted_key: str, value: str) -> None:
    if dotted_key == "general.refresh_seconds":
        cfg.general.refresh_seconds = int(value)
        return
    if dotted_key == "general.windows_state_path":
        cfg.general.windows_state_path = value
        return

    keys = dotted_key.split(".")
    if len(keys) == 4 and keys[0] == "providers" and keys[2] == "manual":
        provider = keys[1]
        field_name = keys[3]
        if provider not in cfg.providers:
            raise ValueError(f"unknown provider: {provider}")
        manual = cfg.providers[provider].manual
        if field_name in {"session_used_pct", "weekly_used_pct"}:
            setattr(manual, field_name, float(value))
            return
        if field_name in {"session_reset_at", "weekly_reset_at"}:
            setattr(manual, field_name, datetime.fromisoformat(value))
            return
    raise ValueError(f"unsupported key: {dotted_key}")
