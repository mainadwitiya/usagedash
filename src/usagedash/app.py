from __future__ import annotations

from datetime import datetime
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, TabbedContent, TabPane

from usagedash.config import Config
from usagedash.models import ProviderName
from usagedash.snapshot import build_snapshot, write_snapshot_files
from usagedash.ui.theme import APP_CSS
from usagedash.ui.widgets import ProviderCard


class UsageDashApp(App):
    CSS = APP_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "show_all", "All"),
        Binding("2", "show_codex", "Codex"),
        Binding("3", "show_claude", "Claude"),
    ]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self._all_cards: dict[str, ProviderCard] = {}
        self._tab_cards: dict[str, ProviderCard] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("ALL", id="all"):
                with VerticalScroll():
                    self._all_cards["codex"] = ProviderCard("Codex", id="all-codex")
                    self._all_cards["claude"] = ProviderCard("Claude", id="all-claude")
                    self._all_cards["gemini"] = ProviderCard("Gemini", id="all-gemini")
                    yield self._all_cards["codex"]
                    yield self._all_cards["claude"]
                    yield self._all_cards["gemini"]

            with TabPane("CODEX", id="codex"):
                with VerticalScroll():
                    self._tab_cards["codex"] = ProviderCard("Codex", id="tab-codex")
                    yield self._tab_cards["codex"]

            with TabPane("CLAUDE", id="claude"):
                with VerticalScroll():
                    self._tab_cards["claude"] = ProviderCard("Claude", id="tab-claude")
                    yield self._tab_cards["claude"]

        yield Footer()

    def on_mount(self) -> None:
        self.refresh_dashboard()
        self.set_interval(max(1, self.cfg.general.refresh_seconds), self.refresh_dashboard)

    def action_refresh(self) -> None:
        self.refresh_dashboard()

    def action_show_all(self) -> None:
        self.query_one(TabbedContent).active = "all"

    def action_show_codex(self) -> None:
        self.query_one(TabbedContent).active = "codex"

    def action_show_claude(self) -> None:
        self.query_one(TabbedContent).active = "claude"

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self) -> None:
        # Keep key-driven navigation smooth; no extra action needed.
        return

    def refresh_dashboard(self) -> None:
        snapshot = build_snapshot(self.cfg)
        write_snapshot_files(self.cfg, snapshot)

        seen = {p.provider.value: p for p in snapshot.providers}
        for name, card in self._all_cards.items():
            if name in seen:
                card.render_provider(seen[name])
            else:
                from usagedash.models import ProviderSnapshot, StatusKind, SourceKind

                card.render_provider(
                    ProviderSnapshot(
                        provider=ProviderName(name),
                        status=StatusKind.ERROR,
                        source=SourceKind.MANUAL,
                        messages=["provider disabled"],
                        updated_at=datetime.utcnow(),
                    )
                )

        for name, card in self._tab_cards.items():
            if name in seen:
                card.render_provider(seen[name])


def run_dashboard(cfg: Config) -> None:
    app = UsageDashApp(cfg)
    app.run()
