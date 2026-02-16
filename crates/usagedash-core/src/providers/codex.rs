use crate::config::{ProviderConfig, home_dir};
use crate::models::Provider;
use crate::providers::{PartialUsage, ProviderAdapter, merge_partial_with_manual};
use anyhow::Result;
use chrono::{Datelike, Local, NaiveDateTime, NaiveTime, TimeZone, Utc};
use regex::Regex;
use std::fs;
use std::path::PathBuf;

pub struct CodexAdapter;

impl ProviderAdapter for CodexAdapter {
    fn provider(&self) -> Provider {
        Provider::Codex
    }

    fn collect(&self, cfg: &ProviderConfig) -> Result<crate::models::ProviderStatus> {
        let parsed = parse_codex_usage().ok();
        Ok(merge_partial_with_manual(self.provider(), parsed, &cfg.manual))
    }
}

fn parse_codex_usage() -> Result<PartialUsage> {
    let history_path = home_dir().join(".codex/history.jsonl");
    if !history_path.exists() {
        return Ok(PartialUsage {
            messages: vec![format!("missing {}", history_path.display())],
            ..Default::default()
        });
    }

    let raw = fs::read_to_string(&history_path)?;
    let lines: Vec<&str> = raw.lines().rev().take(300).collect();

    let five_hour = Regex::new(r"5h limit:\s*\[[^\]]*\]\s*([0-9]{1,3})% left \(resets ([0-9]{2}:[0-9]{2})\)")?;
    let weekly = Regex::new(
        r"Weekly limit:\s*\[[^\]]*\]\s*([0-9]{1,3})% left \(resets ([0-9]{2}:[0-9]{2}) on ([0-9]{1,2} [A-Za-z]{3})\)",
    )?;

    let mut out = PartialUsage::default();

    for line in &lines {
        if out.session_limit_percent_used.is_none() {
            if let Some(caps) = five_hour.captures(line) {
            let left = caps.get(1).and_then(|m| m.as_str().parse::<f32>().ok());
            let reset_time = caps.get(2).map(|m| m.as_str().to_string());
            if let Some(l) = left {
                out.session_limit_percent_used = Some((100.0 - l).max(0.0));
            }
                if let Some(ts) = reset_time {
                    if let Some(dt) = parse_today_time(&ts) {
                        out.session_resets_at = Some(dt.with_timezone(&Utc));
                    }
                }
            }
        }

        if out.weekly_limit_percent_used.is_none() {
            if let Some(caps) = weekly.captures(line) {
            let left = caps.get(1).and_then(|m| m.as_str().parse::<f32>().ok());
            let time = caps.get(2).map(|m| m.as_str().to_string());
            let day_month = caps.get(3).map(|m| m.as_str().to_string());

            if let Some(l) = left {
                out.weekly_limit_percent_used = Some((100.0 - l).max(0.0));
            }
                if let (Some(t), Some(dm)) = (time, day_month) {
                    if let Some(dt) = parse_day_month_time(&dm, &t) {
                        out.weekly_resets_at = Some(dt.with_timezone(&Utc));
                    }
                }
            }
        }

        if out.session_limit_percent_used.is_some() && out.weekly_limit_percent_used.is_some() {
            break;
        }
    }

    if out.session_limit_percent_used.is_none() && out.weekly_limit_percent_used.is_none() {
        out.messages.push(
            "could not parse codex usage from history; set provider.codex.manual.* values"
                .to_string(),
        );
    }

    Ok(out)
}

fn parse_today_time(hhmm: &str) -> Option<chrono::DateTime<Local>> {
    let today = Local::now().date_naive();
    let t = NaiveTime::parse_from_str(hhmm, "%H:%M").ok()?;
    let naive = NaiveDateTime::new(today, t);
    Local.from_local_datetime(&naive).single()
}

fn parse_day_month_time(day_month: &str, hhmm: &str) -> Option<chrono::DateTime<Local>> {
    let year = Local::now().year();
    let fmt = format!("{} {} {}", day_month, year, hhmm);
    let naive = chrono::NaiveDateTime::parse_from_str(&fmt, "%d %b %Y %H:%M").ok()?;
    Local.from_local_datetime(&naive).single()
}

#[allow(dead_code)]
fn default_source_path() -> PathBuf {
    home_dir().join(".codex/history.jsonl")
}
