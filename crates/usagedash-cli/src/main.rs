use anyhow::{Context, Result, bail};
use chrono::Local;
use clap::{Parser, Subcommand};
use comfy_table::{Cell, ContentArrangement, Table};
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;
use usagedash_core::config::{Config, default_config_path};
use usagedash_core::models::{Provider, ProviderStatus, UsageSnapshot};
use usagedash_core::providers::ProviderAdapter;
use usagedash_core::providers::claude::ClaudeAdapter;
use usagedash_core::providers::codex::CodexAdapter;
use usagedash_core::providers::gemini::GeminiAdapter;
use usagedash_core::snapshot::{mirror_snapshot_to, write_snapshot};

#[derive(Parser)]
#[command(name = "usagedash")]
#[command(about = "WSL-first AI usage dashboard")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Status,
    Watch {
        #[arg(long)]
        interval: Option<u64>,
    },
    Export {
        #[arg(long, default_value = "json")]
        format: String,
    },
    Config {
        #[command(subcommand)]
        command: ConfigCommands,
    },
    Doctor,
    SelfUpdate,
}

#[derive(Subcommand)]
enum ConfigCommands {
    Set { key: String, value: String },
}

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter("info")
        .without_time()
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Status => {
            let cfg = Config::from_default_path()?;
            let snapshot = collect_snapshot(&cfg)?;
            persist_snapshot(&cfg, &snapshot)?;
            render_table(&snapshot);
        }
        Commands::Watch { interval } => {
            let cfg = Config::from_default_path()?;
            let sleep_s = interval.unwrap_or(cfg.general.refresh_seconds).max(1);
            loop {
                let snapshot = collect_snapshot(&cfg)?;
                persist_snapshot(&cfg, &snapshot)?;
                clear_screen()?;
                render_table(&snapshot);
                thread::sleep(Duration::from_secs(sleep_s));
            }
        }
        Commands::Export { format } => {
            if format != "json" {
                bail!("unsupported format: {}; only json is supported in v1", format);
            }
            let cfg = Config::from_default_path()?;
            let snapshot = collect_snapshot(&cfg)?;
            persist_snapshot(&cfg, &snapshot)?;
            println!("{}", serde_json::to_string_pretty(&snapshot)?);
        }
        Commands::Config { command } => match command {
            ConfigCommands::Set { key, value } => config_set(&key, &value)?,
        },
        Commands::Doctor => doctor()?,
        Commands::SelfUpdate => {
            eprintln!(
                "self-update is not wired to release downloads yet; use scripts/install.sh for now"
            );
        }
    }

    Ok(())
}

fn collect_snapshot(cfg: &Config) -> Result<UsageSnapshot> {
    let mut providers = Vec::new();

    if cfg.codex.enabled {
        providers.push(CodexAdapter.collect(&cfg.codex)?);
    }
    if cfg.claude.enabled {
        providers.push(ClaudeAdapter.collect(&cfg.claude)?);
    }
    if cfg.gemini.enabled {
        providers.push(GeminiAdapter.collect(&cfg.gemini)?);
    }

    Ok(UsageSnapshot {
        generated_at: chrono::Utc::now(),
        providers,
    })
}

fn persist_snapshot(cfg: &Config, snapshot: &UsageSnapshot) -> Result<()> {
    write_snapshot(&cfg.general.state_file, snapshot)?;
    if let Some(path) = &cfg.general.windows_state_path {
        mirror_snapshot_to(path, snapshot)?;
    }
    Ok(())
}

fn render_table(snapshot: &UsageSnapshot) {
    let mut table = Table::new();
    table
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            "Provider",
            "Status",
            "Session Used%",
            "Session Reset",
            "Weekly Used%",
            "Weekly Reset",
            "Source",
            "Messages",
        ]);

    for p in &snapshot.providers {
        table.add_row(vec![
            Cell::new(format!("{:?}", p.provider).to_lowercase()),
            Cell::new(format!("{:?}", p.status).to_lowercase()),
            Cell::new(opt_pct(p.session_limit_percent_used)),
            Cell::new(opt_dt(p.session_reset_local())),
            Cell::new(opt_pct(p.weekly_limit_percent_used)),
            Cell::new(opt_dt(p.weekly_reset_local())),
            Cell::new(format!("{:?}", p.source).to_lowercase()),
            Cell::new(p.messages.join(" | ")),
        ]);
    }

    println!(
        "Usage snapshot generated at {}",
        snapshot.generated_at.with_timezone(&Local).format("%Y-%m-%d %H:%M:%S")
    );
    println!("{}", table);
}

fn opt_pct(v: Option<f32>) -> String {
    v.map(|p| format!("{:.1}", p)).unwrap_or_else(|| "-".to_string())
}

fn opt_dt(v: Option<chrono::DateTime<Local>>) -> String {
    v.map(|d| d.format("%Y-%m-%d %H:%M").to_string())
        .unwrap_or_else(|| "-".to_string())
}

fn clear_screen() -> Result<()> {
    print!("\x1B[2J\x1B[1;1H");
    std::io::stdout().flush()?;
    Ok(())
}

fn config_set(key: &str, value: &str) -> Result<()> {
    let path = default_config_path();
    let mut cfg = Config::from_default_path()?;

    match key {
        "general.refresh_seconds" => {
            cfg.general.refresh_seconds = value
                .parse::<u64>()
                .context("general.refresh_seconds must be an integer")?;
        }
        "general.windows_state_path" => {
            cfg.general.windows_state_path = Some(PathBuf::from(value));
        }
        "provider.codex.manual.session_limit_percent_used" => {
            cfg.codex.manual.session_limit_percent_used = Some(value.parse::<f32>()?);
        }
        "provider.codex.manual.weekly_limit_percent_used" => {
            cfg.codex.manual.weekly_limit_percent_used = Some(value.parse::<f32>()?);
        }
        "provider.claude.manual.session_limit_percent_used" => {
            cfg.claude.manual.session_limit_percent_used = Some(value.parse::<f32>()?);
        }
        "provider.claude.manual.weekly_limit_percent_used" => {
            cfg.claude.manual.weekly_limit_percent_used = Some(value.parse::<f32>()?);
        }
        _ => bail!("unsupported key: {key}"),
    }

    cfg.write_default(&path)?;
    println!("updated {}", path.display());
    Ok(())
}

fn doctor() -> Result<()> {
    let cfg_path = default_config_path();
    let cfg = Config::from_default_path()?;

    let codex_file = home(".codex/history.jsonl");
    let claude_file = home(".claude/stats-cache.json");

    println!("Config: {}", cfg_path.display());
    println!("State file: {}", cfg.general.state_file.display());
    println!(
        "Codex source: {} ({})",
        codex_file.display(),
        exists_str(&codex_file)
    );
    println!(
        "Claude source: {} ({})",
        claude_file.display(),
        exists_str(&claude_file)
    );

    if let Some(path) = cfg.general.windows_state_path {
        println!("Windows mirror: {}", path.display());
    }

    Ok(())
}

fn exists_str(path: &PathBuf) -> &'static str {
    if fs::metadata(path).is_ok() {
        "ok"
    } else {
        "missing"
    }
}

fn home(suffix: &str) -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(suffix)
}

#[allow(dead_code)]
fn _provider_name(p: ProviderStatus) -> Provider {
    p.provider
}
