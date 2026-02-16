from pathlib import Path

from usagedash.config import ProviderConfig
from usagedash.providers.codex import CodexAdapter


def test_codex_parser_reads_percentages(tmp_path: Path) -> None:
    sample = Path("tests/fixtures/codex_history_sample.jsonl").read_text()
    path = tmp_path / "history.jsonl"
    path.write_text(sample)

    # Use empty sessions_path so it falls back to history regex parsing.
    empty_sessions = tmp_path / "sessions"
    empty_sessions.mkdir()

    adapter = CodexAdapter(history_path=path, sessions_path=empty_sessions)
    snap = adapter.collect(ProviderConfig())

    assert snap.session_used_pct is not None
    assert snap.weekly_used_pct is not None
