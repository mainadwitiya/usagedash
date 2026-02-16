from pathlib import Path

from usagedash.config import ProviderConfig
from usagedash.providers.codex import CodexAdapter


def test_codex_parser_reads_percentages(tmp_path: Path) -> None:
    sample = Path("tests/fixtures/codex_history_sample.jsonl").read_text()
    path = tmp_path / "history.jsonl"
    path.write_text(sample)

    adapter = CodexAdapter(history_path=path)
    snap = adapter.collect(ProviderConfig())

    assert snap.session_used_pct is not None
    assert snap.weekly_used_pct is not None
