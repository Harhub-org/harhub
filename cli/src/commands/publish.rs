use anyhow::{bail, Context, Result};
use colored::Colorize;
use sha2::{Digest, Sha256};
use std::io::Read;
use std::path::PathBuf;

use crate::api::{ApiClient, PublishAssetInput, PublishRequest};
use crate::config::Config;

pub struct PublishArgs {
    pub file: PathBuf,
    pub repo_owner: String,
    pub repo_name: String,
    pub app_slug: String,
    pub app_name: String,
    pub version: String,
    pub platform: String,
    pub arch: String,
    pub visibility: String,
}

pub async fn run(args: PublishArgs) -> Result<()> {
    let config = Config::load()?;
    let token = config
        .access_token
        .context("not logged in — run `harhub login` first")?;

    if !args.file.exists() {
        bail!("file not found: {}", args.file.display());
    }

    println!("Hashing {}...", args.file.display());
    let mut file = std::fs::File::open(&args.file)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 1 << 20];
    let mut size_bytes: u64 = 0;
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
        size_bytes += read as u64;
    }
    let sha256 = format!("{:x}", hasher.finalize());
    let file_name = args
        .file
        .file_name()
        .context("invalid file name")?
        .to_string_lossy()
        .to_string();

    let asset = if args.visibility == "proprietary" {
        // Proprietary binaries need a pre-signed upload URL from the
        // backend before the CLI can PUT the file to Storage. That
        // endpoint (create-upload-url) is a follow-up Edge Function, not
        // yet wired here — for now this path uploads via a service
        // endpoint the developer configures locally.
        bail!(
            "proprietary publish from the CLI requires the create-upload-url \
             endpoint (not yet available) — use the GitHub Action for \
             proprietary releases in the meantime."
        );
    } else {
        PublishAssetInput {
            file_name: file_name.clone(),
            platform: args.platform.clone(),
            arch: args.arch.clone(),
            size_bytes,
            sha256,
            storage_path: None,
            public_url: Some(format!(
                "https://github.com/{}/{}/releases/download/{}/{}",
                args.repo_owner, args.repo_name, args.version, file_name
            )),
        }
    };

    let request = PublishRequest {
        repo_owner: args.repo_owner,
        repo_name: args.repo_name,
        app_slug: args.app_slug,
        app_name: args.app_name,
        version: args.version,
        visibility: args.visibility,
        assets: vec![asset],
    };

    let api = ApiClient::new(None, None);
    let url = api.functions_url("publish-release", "");
    let http = reqwest::Client::new();
    let resp = http
        .post(url)
        .bearer_auth(token)
        .json(&request)
        .send()
        .await?;

    if !resp.status().is_success() {
        bail!("publish failed: {}", resp.text().await?);
    }

    println!("{} published {} {}", "✓".green(), file_name, "successfully".dimmed());
    Ok(())
}