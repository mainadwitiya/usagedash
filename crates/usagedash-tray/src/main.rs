use anyhow::Result;
use std::thread;
use std::time::Duration;
use tracing::warn;
use usagedash_core::models::UsageSnapshot;
use usagedash_core::snapshot::read_snapshot;

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter("info")
        .without_time()
        .init();

    let path = state_path();

    #[cfg(windows)]
    {
        return windows_tray_loop(path);
    }

    #[cfg(not(windows))]
    {
        warn!(
            "usagedash-tray is intended for Windows; polling snapshot in console mode from {}",
            path.display()
        );
        loop {
            match read_snapshot(&path) {
                Ok(snapshot) => println!("{}", summarize(&snapshot)),
                Err(e) => warn!("failed reading snapshot: {e}"),
            }
            thread::sleep(Duration::from_secs(15));
        }
    }
}

fn state_path() -> std::path::PathBuf {
    std::env::var("USAGEDASH_STATE_PATH")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| {
            std::path::PathBuf::from(r"C:\Users\Public\AppData\Local\UsageDash\latest.json")
        })
}

fn summarize(snapshot: &UsageSnapshot) -> String {
    let mut parts = Vec::new();
    for p in &snapshot.providers {
        let session = p
            .session_limit_percent_used
            .map(|v| format!("S:{:.0}%", v))
            .unwrap_or_else(|| "S:-".to_string());
        let weekly = p
            .weekly_limit_percent_used
            .map(|v| format!("W:{:.0}%", v))
            .unwrap_or_else(|| "W:-".to_string());
        parts.push(format!("{:?} {} {}", p.provider, session, weekly));
    }
    parts.join(" | ")
}

#[cfg(windows)]
fn windows_tray_loop(path: std::path::PathBuf) -> Result<()> {
    use tray_item::TrayItem;

    let mut tray = TrayItem::new("UsageDash", "icon-name")?;
    tray.add_label("Starting...")?;
    tray.add_menu_item("Quit", || std::process::exit(0))?;

    loop {
        if let Ok(snapshot) = read_snapshot(&path) {
            let label = summarize(&snapshot);
            let _ = tray.set_tooltip(&label);
        }
        thread::sleep(Duration::from_secs(15));
    }
}
