use anyhow::Result;
use colored::Colorize;

use crate::api::ApiClient;

pub async fn run(query: Option<String>) -> Result<()> {
    let client = ApiClient::new(None, None);
    let apps = client.search_apps(query.as_deref()).await?;

    if apps.is_empty() {
        println!("No apps found.");
        return Ok(());
    }

    for app in apps {
        let tagline = app.tagline.unwrap_or_default();
        println!(
            "{}  {}  {}",
            app.slug.bold().cyan(),
            tagline.dimmed(),
            format!("↓ {}", app.download_count).dimmed()
        );
    }

    Ok(())
}
