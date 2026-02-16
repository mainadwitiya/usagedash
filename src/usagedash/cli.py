from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict
from pathlib import Path

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from usagedash.app import run_dashboard
from usagedash.config import CONFIG_PATH, load_config, save_config, set_config_value
from usagedash.snapshot import build_snapshot, snapshot_to_json, write_snapshot_files
from usagedash.tray import run_tray


def _bar_color(pct: float) -> str:
    if pct >= 80.0:
        return "red"
    if pct >= 50.0:
        return "yellow"
    return "green"


def _cli_bar(value: float | None, width: int = 30) -> Text:
    if value is None:
        return Text("── no data ──", style="dim")
    shown = max(0.0, value)
    bar_pct = min(100.0, shown)
    filled = int(round((bar_pct / 100.0) * width))
    empty = width - filled
    color = _bar_color(shown)
    bar = Text()
    bar.append("━" * filled, style=f"bold {color}")
    bar.append("╌" * empty, style="bright_black")
    bar.append(f"  {shown:5.1f}%", style=f"bold {color}")
    return bar


def _fmt_num(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.0f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _fmt_rate(value) -> str:
    if value is None or value == 0:
        return "-"
    if isinstance(value, (int, float)) and value >= 1000:
        return f"{value:,.0f} tok/min"
    return f"{value:.1f} tok/min"


def _fmt_reset(dt) -> str:
    if dt is None:
        return "-"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
    return dt.strftime("%b %d  %H:%M")


def _fmt_runout(runout_iso: str | None) -> Text:
    if not runout_iso:
        return Text("-", style="dim")
    try:
        runout = datetime.fromisoformat(runout_iso)
    except (ValueError, TypeError):
        return Text(runout_iso, style="dim")
    remaining = runout - datetime.now()
    total_seconds = remaining.total_seconds()
    if total_seconds <= 0:
        return Text("EXHAUSTED", style="bold red")
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if hours > 0:
        time_str = f"{hours}h {minutes}m remaining"
    else:
        time_str = f"{minutes}m remaining"
    color = "red" if total_seconds < 1800 else "yellow" if total_seconds < 7200 else "green"
    return Text(time_str, style=color)


def _model_name(raw: str) -> str:
    parts = raw.split("-")
    if parts and parts[0] in ("claude", "gpt", "o", "gemini"):
        parts = parts[1:]
    if parts and len(parts[-1]) == 8 and parts[-1].isdigit():
        parts = parts[:-1]
    if not parts:
        return raw
    name_parts = [p for p in parts if not p.isdigit()]
    ver_parts = [p for p in parts if p.isdigit()]
    name = "-".join(name_parts) if name_parts else "-".join(parts)
    ver = ".".join(ver_parts) if ver_parts else ""
    return f"{name} {ver}".strip() if ver else name


def _render_panel(provider) -> Panel:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column("label", no_wrap=True, style="bold bright_white", ratio=1)
    table.add_column("value", ratio=4)

    # ── Status ──
    status_color = {"ok": "green", "partial": "yellow", "error": "red"}.get(provider.status.value, "white")
    status_text = Text()
    status_text.append(f"● {provider.status.value.upper()}", style=f"bold {status_color}")
    status_text.append(f"    source: {provider.source.value}", style="dim")
    table.add_row("Status", status_text)

    # ── Session ──
    table.add_row("", Text())
    table.add_row(Text("Session", style="bold cyan"), _cli_bar(provider.session_used_pct))
    table.add_row(Text("  resets", style="dim"), Text(_fmt_reset(provider.session_reset_at), style="bright_white"))

    # ── Weekly ──
    table.add_row("", Text())
    table.add_row(Text("Weekly", style="bold magenta"), _cli_bar(provider.weekly_used_pct))
    table.add_row(Text("  resets", style="dim"), Text(_fmt_reset(provider.weekly_reset_at), style="bright_white"))

    # ── Claude details ──
    dyn = (provider.details or {}).get("dynamic_limits", {})
    if isinstance(dyn, dict) and dyn and provider.provider.value == "claude":
        table.add_row("", Text())
        table.add_row(
            Text("Tokens", style="bold blue"),
            Text(f"{_fmt_num(dyn.get('session_tokens'))} / {_fmt_num(dyn.get('token_limit_p90'))}  (P90 limit)", style="bright_white"),
        )
        table.add_row(
            Text("Messages", style="bold blue"),
            Text(f"{_fmt_num(dyn.get('session_messages'))} / {_fmt_num(dyn.get('message_limit_p90'))}  (P90 limit)", style="bright_white"),
        )
        table.add_row(
            Text("Burn rate", style="bold blue"),
            Text(_fmt_rate(dyn.get("burn_rate_tokens_per_min")), style="bright_white"),
        )
        table.add_row(Text("Runout", style="bold blue"), _fmt_runout(dyn.get("predicted_tokens_runout_at")))

        model_dist = dyn.get("model_distribution", {})
        if isinstance(model_dist, dict) and model_dist:
            models_text = Text()
            for i, (k, v) in enumerate(model_dist.items()):
                if i > 0:
                    models_text.append("  ", style="dim")
                models_text.append(f"{_model_name(k)}", style="bold cyan")
                models_text.append(f" {v}%", style="bright_white")
            table.add_row(Text("Models", style="bold blue"), models_text)

    # ── Notes ──
    if provider.messages:
        table.add_row("", Text())
        notes = " | ".join(provider.messages)
        table.add_row(Text("Notes", style="dim"), Text(notes, style="dim italic"))

    border = {"ok": "#2be38f", "partial": "#f2c94c", "error": "#ff5e6c"}.get(provider.status.value, "#7184d6")
    return Panel(
        table,
        title=f"[bold bright_white] {provider.provider.value.upper()} [/]",
        subtitle=f"[dim]updated {provider.updated_at.strftime('%H:%M:%S')}[/]" if provider.updated_at else None,
        border_style=border,
        padding=(1, 2),
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="usagedash")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("dashboard")

    panel = sub.add_parser("panel")
    panel.add_argument("--provider", choices=["all", "codex", "claude", "gemini"], default="all")

    snap_cmd = sub.add_parser("snapshot")
    snap_cmd.add_argument("--format", choices=["json"], default="json")

    sub.add_parser("health")

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_cmd")
    config_sub.add_parser("show")
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")

    tray = sub.add_parser("tray")
    tray_sub = tray.add_subparsers(dest="tray_cmd")
    tray_sub.add_parser("run")

    args = parser.parse_args()
    cfg = load_config()

    cmd = args.cmd or "dashboard"
    console = Console()

    if cmd == "dashboard":
        run_dashboard(cfg)
        return

    if cmd == "panel":
        snapshot = build_snapshot(cfg)
        write_snapshot_files(cfg, snapshot)
        providers = snapshot.providers
        if args.provider != "all":
            providers = [p for p in providers if p.provider.value == args.provider]
        for p in providers:
            console.print(_render_panel(p))
        return

    if cmd == "snapshot":
        snapshot = build_snapshot(cfg)
        write_snapshot_files(cfg, snapshot)
        print(snapshot_to_json(snapshot))
        return

    if cmd == "health":
        checks = {
            "config": str(CONFIG_PATH),
            "codex_history": str(Path.home() / ".codex/history.jsonl"),
            "claude_stats": str(Path.home() / ".claude/stats-cache.json"),
            "state_file": cfg.general.state_file,
            "windows_mirror": cfg.general.windows_state_path,
            "platform": platform.platform(),
        }
        print(json.dumps(checks, indent=2))
        return

    if cmd == "config":
        if args.config_cmd == "show":
            print(json.dumps(asdict(cfg), indent=2, default=str))
            return
        if args.config_cmd == "set":
            set_config_value(cfg, args.key, args.value)
            save_config(cfg)
            print(f"updated {args.key}")
            return
        parser.error("config requires show or set")

    if cmd == "tray":
        if args.tray_cmd != "run":
            parser.error("tray requires run")
        run_tray()
        return

    parser.error("unknown command")


if __name__ == "__main__":
    main()
