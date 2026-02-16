use chrono::{DateTime, Local, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Provider {
    Codex,
    Claude,
    Gemini,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderStatusKind {
    Ok,
    Partial,
    Error,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DataSource {
    Parsed,
    Manual,
    Mixed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderStatus {
    pub provider: Provider,
    pub status: ProviderStatusKind,
    pub session_limit_percent_used: Option<f32>,
    pub session_resets_at: Option<DateTime<Utc>>,
    pub weekly_limit_percent_used: Option<f32>,
    pub weekly_resets_at: Option<DateTime<Utc>>,
    pub source: DataSource,
    pub last_updated_at: DateTime<Utc>,
    pub messages: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageSnapshot {
    pub generated_at: DateTime<Utc>,
    pub providers: Vec<ProviderStatus>,
}

impl ProviderStatus {
    pub fn session_reset_local(&self) -> Option<DateTime<Local>> {
        self.session_resets_at.map(|ts| ts.with_timezone(&Local))
    }

    pub fn weekly_reset_local(&self) -> Option<DateTime<Local>> {
        self.weekly_resets_at.map(|ts| ts.with_timezone(&Local))
    }
}
