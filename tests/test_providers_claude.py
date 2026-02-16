from pathlib import Path

from usagedash.config import ProviderConfig
from usagedash.providers.claude import ClaudeAdapter


def test_claude_parser_reads_expected_fields(tmp_path: Path) -> None:
    sample = Path("tests/fixtures/claude_stats_sample.json").read_text()
    path = tmp_path / "stats-cache.json"
    path.write_text(sample)

    # Use an empty projects_path so project-log analysis finds nothing
    # and stats-cache values are used as fallback.
    empty_projects = tmp_path / "projects"
    empty_projects.mkdir()

    adapter = ClaudeAdapter(stats_path=path, projects_path=empty_projects)
    snap = adapter.collect(ProviderConfig())

    assert snap.session_used_pct == 34.5
    assert snap.weekly_used_pct == 58.0
