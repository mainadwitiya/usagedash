from __future__ import annotations

from usagedash.config import ProviderConfig
from usagedash.models import ProviderName, ProviderSnapshot
from usagedash.providers.base import PartialUsage, ProviderAdapter, merge_usage


class GeminiAdapter(ProviderAdapter):
    name = ProviderName.GEMINI

    def collect(self, cfg: ProviderConfig) -> ProviderSnapshot:
        partial = PartialUsage(messages=["Gemini parser is not implemented in v2; use manual fields"])
        return merge_usage(self.name, partial, cfg)
