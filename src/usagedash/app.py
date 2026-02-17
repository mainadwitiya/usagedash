from __future__ import annotations

import time
from datetime import datetime

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from usagedash.cli import _render_panel
from usagedash.config import Config
from usagedash.snapshot import build_snapshot, write_snapshot_files


def _build_display(cfg: Config) -> Group:
    snapshot = build_snapshot(cfg)
    write_snapshot_files(cfg, snapshot)

    panels = [_render_panel(p) for p in snapshot.providers]

    now = datetime.now().strftime("%H:%M:%S")
    footer = Text()
    footer.append(f"  {now}", style="bold bright_white")
    footer.append(f"  |  refreshing every {cfg.general.refresh_seconds}s", style="dim")
    footer.append("  |  Ctrl+C to exit", style="dim")

    return Group(*panels, footer)


def run_dashboard(cfg: Config) -> None:
    console = Console()
    try:
        with Live(
            _build_display(cfg),
            console=console,
            refresh_per_second=1,
            screen=True,
        ) as live:
            while True:
                live.update(_build_display(cfg))
                time.sleep(max(1, cfg.general.refresh_seconds))
    except KeyboardInterrupt:
        pass
