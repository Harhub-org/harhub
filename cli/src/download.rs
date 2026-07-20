//! Streaming download + SHA256 verification + platform-aware post-install.

use anyhow::{bail, Context, Result};
use colored::Colorize;
use futures_util::StreamExt;
use indicatif::{ProgressBar, ProgressStyle};
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::platform::AssetKind;

pub fn downloads_dir() -> Result<PathBuf> {
    let mut dir = dirs::download_dir()
        .or_else(dirs::home_dir)
        .context("could not resolve a downloads directory")?;
    dir.push("harhub");
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}

pub async fn download_and_verify(
    client: &reqwest::Client,
    url: &str,
    file_name: &str,
    expected_sha256: &str,
) -> Result<PathBuf> {
    let dest_dir = downloads_dir()?;
    let dest_path = dest_dir.join(file_name);

    let response = client.get(url).send().await?;
    if !response.status().is_success() {
        bail!("download failed with status {}", response.status());
    }

    let total_size = response.content_length().unwrap_or(0);
    let progress = ProgressBar::new(total_size);
    progress.set_style(
        ProgressStyle::with_template(
            "  {spinner:.cyan}  [{bar:30.cyan/blue}] {bytes}/{total_bytes} ({eta})",
        )?
        .progress_chars("=>-"),
    );

    let mut file = std::fs::File::create(&dest_path)?;
    let mut hasher = Sha256::new();
    let mut stream = response.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        file.write_all(&chunk)?;
        hasher.update(&chunk);
        progress.inc(chunk.len() as u64);
    }
    progress.finish_and_clear();

    let actual_hash = format!("{:x}", hasher.finalize());
    if actual_hash.to_lowercase() != expected_sha256.to_lowercase() {
        std::fs::remove_file(&dest_path).ok();
        bail!(
            "SHA256 mismatch — expected {}, got {}. File removed for safety.",
            expected_sha256,
            actual_hash
        );
    }

    println!("  {} verified (sha256 match)", "✓".green());
    Ok(dest_path)
}

/// Runs the install step appropriate for the asset kind. Only called for
/// kinds where `AssetKind::is_installable()` is true — .apk and .exe never
/// reach this function; they are download-only by policy.
pub fn install_binary(path: &Path, kind: AssetKind) -> Result<()> {
    match kind {
        AssetKind::Linux | AssetKind::AppImage => {
            let mut perms = std::fs::metadata(path)?.permissions();
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                perms.set_mode(perms.mode() | 0o111);
            }
            std::fs::set_permissions(path, perms)?;
            println!("  {} marked executable: {}", "✓".green(), path.display());
        }
        AssetKind::Deb => {
            println!(
                "  {} installing via dpkg (may prompt for sudo)...",
                "→".cyan()
            );
            let status = Command::new("sudo")
                .arg("dpkg")
                .arg("-i")
                .arg(path)
                .status();
            match status {
                Ok(s) if s.success() => println!("  {} installed via dpkg", "✓".green()),
                _ => println!(
                    "  {} dpkg install failed or unavailable — binary saved at {}",
                    "!".yellow(),
                    path.display()
                ),
            }
        }
        AssetKind::Rpm => {
            println!(
                "  {} installing via rpm (may prompt for sudo)...",
                "→".cyan()
            );
            let status = Command::new("sudo").arg("rpm").arg("-i").arg(path).status();
            match status {
                Ok(s) if s.success() => println!("  {} installed via rpm", "✓".green()),
                _ => println!(
                    "  {} rpm install failed or unavailable — binary saved at {}",
                    "!".yellow(),
                    path.display()
                ),
            }
        }
        AssetKind::Jar => {
            println!(
                "  {} JAR downloaded — run with: java -jar {}",
                "✓".green(),
                path.display()
            );
        }
        _ => {
            println!("  {} downloaded to {}", "✓".green(), path.display());
        }
    }
    Ok(())
}
