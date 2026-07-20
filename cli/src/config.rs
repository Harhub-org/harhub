//! Local CLI config stored as TOML at ~/.config/harhub/config.toml
//! (per user preference: TOML over JSON for config files).

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize, Default)]
pub struct Config {
    pub supabase_url: Option<String>,
    pub supabase_anon_key: Option<String>,
    pub access_token: Option<String>,
    pub refresh_token: Option<String>,
}

fn config_path() -> Result<PathBuf> {
    let mut dir = dirs::config_dir().context("could not resolve config directory")?;
    dir.push("harhub");
    std::fs::create_dir_all(&dir)?;
    dir.push("config.toml");
    Ok(dir)
}

impl Config {
    pub fn load() -> Result<Self> {
        let path = config_path()?;
        if !path.exists() {
            return Ok(Config::default());
        }
        let content = std::fs::read_to_string(&path)?;
        Ok(toml::from_str(&content)?)
    }

    pub fn save(&self) -> Result<()> {
        let path = config_path()?;
        let content = toml::to_string_pretty(self)?;
        std::fs::write(path, content)?;
        Ok(())
    }

    pub fn is_logged_in(&self) -> bool {
        self.access_token.is_some()
    }
}
