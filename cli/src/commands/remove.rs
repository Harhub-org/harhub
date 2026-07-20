use anyhow::{Context, Result};
use colored::Colorize;

use crate::download::downloads_dir;

pub async fn run(file_name: String) -> Result<()> {
    let path = downloads_dir()?.join(&file_name);
    if !path.exists() {
        println!("{} {} not found in Harhub downloads.", "!".yellow(), file_name);
        return Ok(());
    }
    std::fs::remove_file(&path).context("failed to remove file")?;
    println!("{} removed {}", "✓".green(), file_name);
    Ok(())
}