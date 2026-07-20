//! Thin HTTP client over Supabase PostgREST + Edge Functions for the CLI.

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};

const DEFAULT_SUPABASE_URL: &str = "https://harhub-project.supabase.co";
const DEFAULT_ANON_KEY: &str = "public-anon-key-placeholder";

#[derive(Debug, Deserialize, Clone)]
pub struct App {
    pub id: String,
    pub slug: String,
    pub name: String,
    pub tagline: Option<String>,
    pub visibility: String,
    pub download_count: i64,
}

#[derive(Debug, Deserialize, Clone)]
pub struct Release {
    pub id: String,
    pub version: String,
    pub is_latest: bool,
    pub published_at: String,
}

#[derive(Debug, Deserialize, Clone)]
pub struct Asset {
    pub id: String,
    pub file_name: String,
    pub platform: String,
    pub arch: String,
    pub size_bytes: i64,
    pub sha256: String,
    pub public_url: Option<String>,
}

pub struct ApiClient {
    http: reqwest::Client,
    base_url: String,
    anon_key: String,
}

impl ApiClient {
    pub fn new(base_url: Option<String>, anon_key: Option<String>) -> Self {
        Self {
            http: reqwest::Client::new(),
            base_url: base_url.unwrap_or_else(|| DEFAULT_SUPABASE_URL.to_string()),
            anon_key: anon_key.unwrap_or_else(|| DEFAULT_ANON_KEY.to_string()),
        }
    }

    pub fn functions_url(&self, name: &str, query: &str) -> String {
        format!("{}/functions/v1/{}?{}", self.base_url, name, query)
    }

    pub async fn search_apps(&self, query: Option<&str>) -> Result<Vec<App>> {
        let mut url = format!(
            "{}/rest/v1/apps?select=id,slug,name,tagline,visibility,download_count&status=eq.published&order=download_count.desc&limit=20",
            self.base_url
        );
        if let Some(q) = query {
            url.push_str(&format!("&name=ilike.*{}*", urlencoding::encode(q)));
        }

        let resp = self
            .http
            .get(&url)
            .header("apikey", &self.anon_key)
            .send()
            .await
            .context("failed to reach Harhub registry")?;

        if !resp.status().is_success() {
            bail!("Harhub registry returned {}", resp.status());
        }

        Ok(resp.json::<Vec<App>>().await?)
    }

    pub async fn get_app(&self, slug: &str) -> Result<App> {
        let url = format!("{}/rest/v1/apps?slug=eq.{}&select=*", self.base_url, slug);
        let apps: Vec<App> = self
            .http
            .get(&url)
            .header("apikey", &self.anon_key)
            .send()
            .await?
            .json()
            .await?;

        apps.into_iter()
            .next()
            .with_context(|| format!("app '{}' not found on Harhub", slug))
    }

    pub async fn get_latest_release(&self, app_id: &str) -> Result<Release> {
        let url = format!(
            "{}/rest/v1/releases?app_id=eq.{}&is_latest=eq.true&limit=1",
            self.base_url, app_id
        );
        let releases: Vec<Release> = self
            .http
            .get(&url)
            .header("apikey", &self.anon_key)
            .send()
            .await?
            .json()
            .await?;

        releases
            .into_iter()
            .next()
            .context("no published release found for this app")
    }

    pub async fn get_assets(&self, release_id: &str) -> Result<Vec<Asset>> {
        let url = format!(
            "{}/rest/v1/assets?release_id=eq.{}",
            self.base_url, release_id
        );
        Ok(self
            .http
            .get(&url)
            .header("apikey", &self.anon_key)
            .send()
            .await?
            .json()
            .await?)
    }

    /// Resolves the actual download URL for an asset — direct for public
    /// apps, or the sign-download endpoint for proprietary ones.
    pub fn resolve_download_url(&self, app_slug: &str, asset: &Asset) -> String {
        asset
            .public_url
            .clone()
            .unwrap_or_else(|| self.functions_url("sign-download", &format!("app={}&file={}", app_slug, asset.file_name)))
    }

    pub async fn sign_in(&self, email: &str, password: &str) -> Result<LoginResponse> {
        let url = format!("{}/auth/v1/token?grant_type=password", self.base_url);
        let resp = self
            .http
            .post(&url)
            .header("apikey", &self.anon_key)
            .json(&serde_json::json!({ "email": email, "password": password }))
            .send()
            .await?;

        if !resp.status().is_success() {
            bail!("login failed: {}", resp.status());
        }

        Ok(resp.json::<LoginResponse>().await?)
    }
}

#[derive(Debug, Deserialize)]
pub struct LoginResponse {
    pub access_token: String,
    pub refresh_token: String,
}

#[derive(Debug, Serialize)]
pub struct PublishAssetInput {
    pub file_name: String,
    pub platform: String,
    pub arch: String,
    pub size_bytes: u64,
    pub sha256: String,
    pub storage_path: Option<String>,
    pub public_url: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct PublishRequest {
    pub repo_owner: String,
    pub repo_name: String,
    pub app_slug: String,
    pub app_name: String,
    pub version: String,
    pub visibility: String,
    pub assets: Vec<PublishAssetInput>,
}