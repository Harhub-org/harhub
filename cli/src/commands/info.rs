use anyhow::Result;
use colored::Colorize;

use crate::api::ApiClient;

pub async fn run(slug: String) -> Result<()> {
    let client = ApiClient::new(None, None);
    let app = client.get_app(&slug).await?;
    let release = client.get_latest_release(&app.id).await?;
    let assets = client.get_assets(&release.id).await?;

    println!("{}", app.name.bold());
    if let Some(tagline) = &app.tagline {
        println!("{}", tagline.dimmed());
    }
    println!();
    println!("Latest version : {}", release.version.green());
    println!("Visibility     : {}", app.visibility);
    println!("Downloads      : {}", app.download_count);
    println!();
    println!("Available assets:");
    for asset in assets {
        let size_mb = asset.size_bytes as f64 / (1024.0 * 1024.0);
        println!(
            "  - {} ({}, {}, {:.1} MB)",
            asset.file_name.cyan(),
            asset.platform,
            asset.arch,
            size_mb
        );
    }

    Ok(())
}