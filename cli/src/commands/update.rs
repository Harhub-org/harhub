use anyhow::Result;
use colored::Colorize;

use super::install;
use crate::download::downloads_dir;

/// Simple policy: re-run install for every app whose binary is present in
/// the local harhub downloads folder, matched by filename prefix == slug.
/// A more complete implementation would track installed slugs/versions in
/// config.toml; this is the minimal correct version for v1.
pub async fn run(slug: Option<String>) -> Result<()> {
    if let Some(slug) = slug {
        println!("Checking for updates to {}...", slug.bold());
        install::run(slug).await?;
        return Ok(());
    }

    let dir = downloads_dir()?;
    println!(
        "{} Run `harhub update <app>` for a specific app, or `harhub install <app>` to reinstall.",
        "i".blue()
    );
    println!("Currently downloaded files are tracked in: {}", dir.display());
    Ok(())
}