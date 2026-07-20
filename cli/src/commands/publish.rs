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

async fn request_upload_url(
    api: &ApiClient,
    token: &str,
    app_slug: &str,
    file_name: &str,
) -> Result<crate::api::UploadUrlResponse> {
    api.create_upload_url(token, app_slug, file_name).await
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
    let api_check = ApiClient::new(None, None);
    let check_url = api_check.functions_url("check-slug", &format!("slug={}", args.app_slug));
    let resp: serde_json::Value = reqwest::get(&check_url).await?.json().await?;
    if resp["available"] == false {
        println!("  {} slug '{}' is already taken by another app on Harhub — this will update your own app if you already own it.", "i".blue(), args.app_slug);
    }
    let sha256 = format!("{:x}", hasher.finalize());
    let file_name = args
        .file
        .file_name()
        .context("invalid file name")?
        .to_string_lossy()
        .to_string();

    let asset = if args.visibility == "proprietary" {
        let upload_info = request_upload_url(&api, &token, &args.app_slug, &file_name).await?;

        let http = reqwest::Client::new();
        let file_bytes = std::fs::read(&args.file)?;
        let put_resp = http
            .put(&upload_info.upload_url)
            .header("Content-Type", "application/octet-stream")
            .body(file_bytes)
            .send()
            .await?;
        if !put_resp.status().is_success() {
            bail!("upload failed: {}", put_resp.status());
        }

        PublishAssetInput {
            file_name: file_name.clone(),
            platform: args.platform.clone(),
            arch: args.arch.clone(),
            size_bytes,
            sha256,
            storage_path: Some(upload_info.storage_path),
            public_url: None,
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

    println!(
        "{} published {} {}",
        "✓".green(),
        file_name,
        "successfully".dimmed()
    );
    Ok(())
}
