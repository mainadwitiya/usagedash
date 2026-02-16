from usagedash.config import ProviderConfig
from usagedash.models import ProviderName, SourceKind, StatusKind
from usagedash.providers.base import PartialUsage, merge_usage


def test_merge_prefers_parsed_when_present() -> None:
    cfg = ProviderConfig()
    cfg.manual.session_used_pct = 1.0
    out = merge_usage(ProviderName.CODEX, PartialUsage(session_used_pct=50.0), cfg)
    assert out.session_used_pct == 50.0
    assert out.source == SourceKind.MIXED


def test_merge_error_when_no_data() -> None:
    cfg = ProviderConfig()
    out = merge_usage(ProviderName.CLAUDE, PartialUsage(), cfg)
    assert out.status == StatusKind.ERROR
    assert out.messages
