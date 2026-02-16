use anyhow::Result;
use clap::Parser;

#[derive(Parser)]
struct Args {
    #[arg(long, default_value = "false")]
    with_tray: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    println!(
        "Installer helper placeholder. with_tray={}, use scripts/install.sh for bootstrap in v1.",
        args.with_tray
    );
    Ok(())
}
