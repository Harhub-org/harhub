use anyhow::{bail, Result};
use colored::Colorize;

use crate::api::ApiClient;
use crate::download::{download_and_verify, install_binary};
use crate::platform::{host_arch, host_platform_preference, AssetKind};

pub async fn run(slug: String) -> Result<()> {
    let api = ApiClient::new(None, None);
    let app = api.get_app(&slug).await?;
    let release = api.get_latest_release(&app.id).await?;
    let assets = api.get_assets(&release.id).await?;

    if assets.is_empty() {
        bail!("no assets available for '{}'", slug);
    }

    let preference = host_platform_preference();
    let arch = host_arch();

    // Pick the best match: platform preference order first, then prefer
    // matching arch within that platform.
    let chosen = preference.iter().find_map(|preferred_platform| {
        let mut candidates: Vec<_> = assets
            .iter()
            .filter(|a| a.platform == *preferred_platform)
            .collect();
        candidates.sort_by_key(|a| if a.arch == arch { 0 } else { 1 });
        candidates.into_iter().next()
    });

    let asset = match chosen {
        Some(a) => a,
        None => bail!(
            "no compatible asset found for this platform among: {}",
            assets
                .iter()
                .map(|a| a.platform.clone())
                .collect::<Vec<_>>()
                .join(", ")
        ),
    };

    let kind = AssetKind::from_platform_str(&asset.platform);

    println!(
        "Installing {} {} ({})",
        app.name.bold(),
        release.version.green(),
        asset.file_name.cyan()
    );

    if matches!(kind, AssetKind::Apk | AssetKind::Exe) {
        println!(
            "  {} {} files are download-only — no auto-install is performed.",
            "i".blue(),
            kind.label()
        );
    }

    let url = api.resolve_download_url(&app.slug, asset);
    let http = reqwest::Client::new();
    let path = download_and_verify(&http, &url, &asset.file_name, &asset.sha256).await?;

    if kind.is_installable() {
        install_binary(&path, kind)?;
    } else {
        println!("  {} saved to {}", "✓".green(), path.display());
    }

    Ok(())
}
