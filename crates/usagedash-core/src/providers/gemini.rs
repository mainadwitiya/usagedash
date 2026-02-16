use crate::config::ProviderConfig;
use crate::models::Provider;
use crate::providers::{PartialUsage, ProviderAdapter, merge_partial_with_manual};
use anyhow::Result;

pub struct GeminiAdapter;

impl ProviderAdapter for GeminiAdapter {
    fn provider(&self) -> Provider {
        Provider::Gemini
    }

    fn collect(&self, cfg: &ProviderConfig) -> Result<crate::models::ProviderStatus> {
        let partial = PartialUsage {
            messages: vec!["gemini adapter is a stub in v1; configure manual values".to_string()],
            ..Default::default()
        };
        Ok(merge_partial_with_manual(self.provider(), Some(partial), &cfg.manual))
    }
}
