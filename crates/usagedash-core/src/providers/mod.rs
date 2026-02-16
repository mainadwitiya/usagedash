use crate::config::{ManualProviderFields, ProviderConfig};
use crate::models::{DataSource, Provider, ProviderStatus, ProviderStatusKind};
use anyhow::Result;
use chrono::Utc;

pub mod claude;
pub mod codex;
pub mod gemini;

pub trait ProviderAdapter {
    fn provider(&self) -> Provider;
    fn collect(&self, cfg: &ProviderConfig) -> Result<ProviderStatus>;
}

#[derive(Debug, Clone, Default)]
pub struct PartialUsage {
    pub session_limit_percent_used: Option<f32>,
    pub session_resets_at: Option<chrono::DateTime<Utc>>,
    pub weekly_limit_percent_used: Option<f32>,
    pub weekly_resets_at: Option<chrono::DateTime<Utc>>,
    pub messages: Vec<String>,
}

pub fn merge_partial_with_manual(
    provider: Provider,
    partial: Option<PartialUsage>,
    manual: &ManualProviderFields,
) -> ProviderStatus {
    let now = Utc::now();
    let mut messages = Vec::new();

    let parsed = partial.unwrap_or_default();
    messages.extend(parsed.messages.clone());

    let session_used = parsed
        .session_limit_percent_used
        .or(manual.session_limit_percent_used);
    let session_reset = parsed.session_resets_at.or(manual.session_resets_at);
    let weekly_used = parsed
        .weekly_limit_percent_used
        .or(manual.weekly_limit_percent_used);
    let weekly_reset = parsed.weekly_resets_at.or(manual.weekly_resets_at);

    let parsed_any = parsed.session_limit_percent_used.is_some()
        || parsed.session_resets_at.is_some()
        || parsed.weekly_limit_percent_used.is_some()
        || parsed.weekly_resets_at.is_some();

    let manual_any = manual.session_limit_percent_used.is_some()
        || manual.session_resets_at.is_some()
        || manual.weekly_limit_percent_used.is_some()
        || manual.weekly_resets_at.is_some();

    let source = match (parsed_any, manual_any) {
        (true, true) => DataSource::Mixed,
        (true, false) => DataSource::Parsed,
        (false, true) => DataSource::Manual,
        (false, false) => DataSource::Manual,
    };

    let status = if session_used.is_some() || weekly_used.is_some() {
        if session_reset.is_some() || weekly_reset.is_some() {
            ProviderStatusKind::Ok
        } else {
            messages.push("missing reset timestamps; populated usage only".to_string());
            ProviderStatusKind::Partial
        }
    } else if parsed_any || manual_any {
        ProviderStatusKind::Partial
    } else {
        messages.push("no usage metrics detected; set manual values in config".to_string());
        ProviderStatusKind::Error
    };

    ProviderStatus {
        provider,
        status,
        session_limit_percent_used: session_used,
        session_resets_at: session_reset,
        weekly_limit_percent_used: weekly_used,
        weekly_resets_at: weekly_reset,
        source,
        last_updated_at: now,
        messages,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    #[test]
    fn merge_prefers_parsed_when_available() {
        let parsed = PartialUsage {
            session_limit_percent_used: Some(45.0),
            ..Default::default()
        };
        let manual = ManualProviderFields {
            session_limit_percent_used: Some(10.0),
            ..Default::default()
        };

        let out = merge_partial_with_manual(Provider::Codex, Some(parsed), &manual);
        assert_eq!(out.session_limit_percent_used, Some(45.0));
        assert!(matches!(out.source, DataSource::Mixed));
    }

    #[test]
    fn merge_uses_manual_when_parsed_missing() {
        let manual = ManualProviderFields {
            session_limit_percent_used: Some(12.5),
            weekly_limit_percent_used: Some(77.0),
            ..Default::default()
        };

        let out = merge_partial_with_manual(Provider::Claude, None, &manual);
        assert_eq!(out.session_limit_percent_used, Some(12.5));
        assert_eq!(out.weekly_limit_percent_used, Some(77.0));
        assert!(matches!(out.source, DataSource::Manual));
    }

    #[test]
    fn merge_marks_error_when_no_data() {
        let out = merge_partial_with_manual(Provider::Gemini, None, &ManualProviderFields::default());
        assert!(matches!(out.status, ProviderStatusKind::Error));
        assert!(!out.messages.is_empty());
    }

    #[test]
    fn merge_reports_ok_when_usage_and_reset_present() {
        let parsed = PartialUsage {
            session_limit_percent_used: Some(30.0),
            session_resets_at: Some(Utc::now()),
            ..Default::default()
        };
        let out = merge_partial_with_manual(Provider::Codex, Some(parsed), &ManualProviderFields::default());
        assert!(matches!(out.status, ProviderStatusKind::Ok));
    }
}
