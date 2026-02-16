use crate::config::{ProviderConfig, home_dir};
use crate::models::Provider;
use crate::providers::{PartialUsage, ProviderAdapter, merge_partial_with_manual};
use anyhow::Result;
use serde_json::Value;
use std::fs;

pub struct ClaudeAdapter;

impl ProviderAdapter for ClaudeAdapter {
    fn provider(&self) -> Provider {
        Provider::Claude
    }

    fn collect(&self, cfg: &ProviderConfig) -> Result<crate::models::ProviderStatus> {
        let parsed = parse_claude_usage().ok();
        Ok(merge_partial_with_manual(self.provider(), parsed, &cfg.manual))
    }
}

fn parse_claude_usage() -> Result<PartialUsage> {
    let mut partial = PartialUsage::default();
    let stats_path = home_dir().join(".claude/stats-cache.json");
    if !stats_path.exists() {
        partial.messages.push(format!("missing {}", stats_path.display()));
        return Ok(partial);
    }

    let raw = fs::read_to_string(&stats_path)?;
    let value = serde_json::from_str::<Value>(&raw)?;

    // Claude local format varies by version; we probe commonly observed shapes.
    if let Some(pct) = value
        .pointer("/limits/session/percent_used")
        .and_then(|v| v.as_f64())
    {
        partial.session_limit_percent_used = Some(pct as f32);
    }

    if let Some(pct) = value
        .pointer("/limits/weekly/percent_used")
        .and_then(|v| v.as_f64())
    {
        partial.weekly_limit_percent_used = Some(pct as f32);
    }

    if partial.session_limit_percent_used.is_none() && partial.weekly_limit_percent_used.is_none() {
        partial.messages.push(
            "could not infer usage values from .claude/stats-cache.json; use provider.claude.manual.*"
                .to_string(),
        );
    }

    Ok(partial)
}
