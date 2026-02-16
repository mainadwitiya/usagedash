from __future__ import annotations

from datetime import datetime

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from usagedash.models import ProviderSnapshot


def _bar_color(pct: float) -> str:
    if pct >= 80.0:
        return "red"
    if pct >= 50.0:
        return "yellow"
    return "green"


def _bar(value: float | None, width: int = 30) -> Text:
    if value is None:
        return Text("  ── no data ──", style="dim")
    shown = max(0.0, value)
    bar_pct = min(100.0, shown)
    filled = int(round((bar_pct / 100.0) * width))
    empty = width - filled
    color = _bar_color(shown)

    bar = Text()
    bar.append("  ")
    bar.append("━" * filled, style=f"bold {color}")
    bar.append("╌" * empty, style="bright_black")
    bar.append(f"  {shown:5.1f}%", style=f"bold {color}")
    return bar


def _fmt_num(value: int | float | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.0f}"
    return f"{value:,}"


def _fmt_rate(value: float | None) -> str:
    if value is None or value == 0:
        return "-"
    if value >= 1000:
        return f"{value:,.0f} tok/min"
    return f"{value:.1f} tok/min"


def _fmt_time_remaining(runout_iso: str | None) -> Text:
    if not runout_iso:
        return Text("  -", style="dim")
    try:
        runout = datetime.fromisoformat(runout_iso)
    except (ValueError, TypeError):
        return Text(f"  {runout_iso}", style="dim")
    remaining = runout - datetime.now()
    total_seconds = remaining.total_seconds()
    if total_seconds <= 0:
        return Text("  EXHAUSTED", style="bold red")
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if hours > 0:
        txt = f"  {hours}h {minutes}m remaining"
    else:
        txt = f"  {minutes}m remaining"
    color = "red" if total_seconds < 1800 else "yellow" if total_seconds < 7200 else "green"
    return Text(txt, style=color)


def _fmt_reset(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%b %d  %H:%M")


def _model_name(raw: str) -> str:
    """Extract a clean model name from various vendor naming schemes.

    claude-sonnet-4-5-20250514 -> sonnet 4.5
    claude-3-5-sonnet-20241022 -> sonnet 3.5
    claude-opus-4-6             -> opus 4.6
    gpt-4o-mini                 -> 4o-mini
    """
    parts = raw.split("-")
    # Strip vendor prefix
    if parts and parts[0] in ("claude", "gpt", "o", "gemini"):
        parts = parts[1:]
    # Strip date suffix (YYYYMMDD)
    if parts and len(parts[-1]) == 8 and parts[-1].isdigit():
        parts = parts[:-1]
    if not parts:
        return raw
    # Old Claude scheme: 3-5-sonnet → find the name part, collect version digits
    # New Claude scheme: sonnet-4-5 → name is first, version digits follow
    name_parts = [p for p in parts if not p.isdigit()]
    ver_parts = [p for p in parts if p.isdigit()]
    name = "-".join(name_parts) if name_parts else "-".join(parts)
    ver = ".".join(ver_parts) if ver_parts else ""
    return f"{name} {ver}".strip() if ver else name


class ProviderCard(Static):
    def __init__(self, title: str, **kwargs):
        super().__init__(**kwargs)
        self.title = title

    def render_provider(self, snap: ProviderSnapshot) -> None:
        status_color = {
            "ok": "green",
            "partial": "yellow",
            "error": "red",
        }.get(snap.status.value, "white")

        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("label", ratio=1, no_wrap=True, style="bold bright_white")
        table.add_column("value", ratio=4)

        # ── Status row ──
        status_text = Text()
        status_text.append(f"  ● {snap.status.value.upper()}", style=f"bold {status_color}")
        status_text.append(f"    source: {snap.source.value}", style="dim")
        table.add_row("Status", status_text)

        # ── Session usage ──
        table.add_row("", Text())
        session_label = Text("Session", style="bold cyan")
        table.add_row(session_label, _bar(snap.session_used_pct))
        table.add_row(
            Text("  resets", style="dim"),
            Text(f"  {_fmt_reset(snap.session_reset_at)}", style="bright_white"),
        )

        # ── Weekly usage ──
        table.add_row("", Text())
        weekly_label = Text("Weekly", style="bold magenta")
        table.add_row(weekly_label, _bar(snap.weekly_used_pct))
        table.add_row(
            Text("  resets", style="dim"),
            Text(f"  {_fmt_reset(snap.weekly_reset_at)}", style="bright_white"),
        )

        # ── Claude dynamic details ──
        dyn = (snap.details or {}).get("dynamic_limits", {})
        if isinstance(dyn, dict) and dyn and snap.provider.value == "claude":
            table.add_row("", Text())
            table.add_row(
                Text("Tokens", style="bold blue"),
                Text(f"  {_fmt_num(dyn.get('session_tokens'))} / {_fmt_num(dyn.get('token_limit_p90'))}  (P90 limit)", style="bright_white"),
            )
            table.add_row(
                Text("Messages", style="bold blue"),
                Text(f"  {_fmt_num(dyn.get('session_messages'))} / {_fmt_num(dyn.get('message_limit_p90'))}  (P90 limit)", style="bright_white"),
            )
            table.add_row(
                Text("Burn rate", style="bold blue"),
                Text(f"  {_fmt_rate(dyn.get('burn_rate_tokens_per_min'))}", style="bright_white"),
            )
            table.add_row(
                Text("Runout", style="bold blue"),
                _fmt_time_remaining(dyn.get("predicted_tokens_runout_at")),
            )

            model_dist = dyn.get("model_distribution", {})
            if isinstance(model_dist, dict) and model_dist:
                models_text = Text("  ")
                for i, (k, v) in enumerate(model_dist.items()):
                    if i > 0:
                        models_text.append("  ", style="dim")
                    models_text.append(f"{_model_name(k)}", style="bold cyan")
                    models_text.append(f" {v}%", style="bright_white")
                table.add_row(Text("Models", style="bold blue"), models_text)

        # ── Notes ──
        if snap.messages:
            table.add_row("", Text())
            notes = " | ".join(snap.messages)
            table.add_row(Text("Notes", style="dim"), Text(f"  {notes}", style="dim italic"))

        border = {"ok": "#2be38f", "partial": "#f2c94c", "error": "#ff5e6c"}.get(snap.status.value, "#7184d6")
        self.update(Panel(
            table,
            title=f"[bold bright_white] {self.title.upper()} [/]",
            subtitle=f"[dim]updated {snap.updated_at.strftime('%H:%M:%S')}[/]" if snap.updated_at else None,
            border_style=border,
            padding=(1, 2),
        ))
