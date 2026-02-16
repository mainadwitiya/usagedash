use crate::models::UsageSnapshot;
use anyhow::Result;
use std::fs;
use std::path::Path;

pub fn write_snapshot(path: &Path, snapshot: &UsageSnapshot) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let body = serde_json::to_string_pretty(snapshot)?;
    fs::write(path, body)?;
    Ok(())
}

pub fn mirror_snapshot_to(path: &Path, snapshot: &UsageSnapshot) -> Result<()> {
    write_snapshot(path, snapshot)
}

pub fn read_snapshot(path: &Path) -> Result<UsageSnapshot> {
    let raw = fs::read_to_string(path)?;
    let snapshot = serde_json::from_str::<UsageSnapshot>(&raw)?;
    Ok(snapshot)
}
