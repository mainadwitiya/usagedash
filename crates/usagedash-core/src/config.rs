use crate::models::Provider;
use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneralConfig {
    pub refresh_seconds: u64,
    pub timezone: String,
    pub state_file: PathBuf,
    pub windows_state_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ManualProviderFields {
    pub session_limit_percent_used: Option<f32>,
    pub session_resets_at: Option<DateTime<Utc>>,
    pub weekly_limit_percent_used: Option<f32>,
    pub weekly_resets_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    pub enabled: bool,
    pub parser_mode: String,
    pub manual: ManualProviderFields,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrayConfig {
    pub enabled: bool,
    pub autostart: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub general: GeneralConfig,
    pub tray: TrayConfig,
    pub codex: ProviderConfig,
    pub claude: ProviderConfig,
    pub gemini: ProviderConfig,
}

impl Default for Config {
    fn default() -> Self {
        let home = home_dir();
        let state = home.join(".local/state/usagedash/latest.json");
        let windows_state = PathBuf::from("/mnt/c/Users/Public/AppData/Local/UsageDash/latest.json");
        Self {
            general: GeneralConfig {
                refresh_seconds: 15,
                timezone: "local".to_string(),
                state_file: state,
                windows_state_path: Some(windows_state),
            },
            tray: TrayConfig {
                enabled: true,
                autostart: false,
            },
            codex: ProviderConfig {
                enabled: true,
                parser_mode: "hybrid".to_string(),
                manual: ManualProviderFields::default(),
            },
            claude: ProviderConfig {
                enabled: true,
                parser_mode: "hybrid".to_string(),
                manual: ManualProviderFields::default(),
            },
            gemini: ProviderConfig {
                enabled: false,
                parser_mode: "manual".to_string(),
                manual: ManualProviderFields::default(),
            },
        }
    }
}

impl Config {
    pub fn from_default_path() -> Result<Self> {
        let path = default_config_path();
        if !path.exists() {
            let cfg = Self::default();
            cfg.write_default(&path)?;
            return Ok(cfg);
        }
        Self::from_path(&path)
    }

    pub fn from_path(path: &Path) -> Result<Self> {
        let raw = fs::read_to_string(path)
            .with_context(|| format!("failed reading config at {}", path.display()))?;
        let cfg = toml::from_str::<Config>(&raw)
            .with_context(|| format!("failed parsing TOML config at {}", path.display()))?;
        Ok(cfg)
    }

    pub fn write_default(&self, path: &Path) -> Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let text = toml::to_string_pretty(self)?;
        fs::write(path, text)?;
        Ok(())
    }

    pub fn provider_config(&self, provider: Provider) -> &ProviderConfig {
        match provider {
            Provider::Codex => &self.codex,
            Provider::Claude => &self.claude,
            Provider::Gemini => &self.gemini,
        }
    }

    pub fn provider_config_mut(&mut self, provider: Provider) -> &mut ProviderConfig {
        match provider {
            Provider::Codex => &mut self.codex,
            Provider::Claude => &mut self.claude,
            Provider::Gemini => &mut self.gemini,
        }
    }
}

pub fn default_config_path() -> PathBuf {
    home_dir().join(".config/usagedash/config.toml")
}

pub fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}
