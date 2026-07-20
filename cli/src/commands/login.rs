use anyhow::Result;
use colored::Colorize;
use std::io::{self, Write};

use crate::api::ApiClient;
use crate::config::Config;

pub async fn run() -> Result<()> {
    print!("Email: ");
    io::stdout().flush()?;
    let mut email = String::new();
    io::stdin().read_line(&mut email)?;

    let password = rpassword::prompt_password("Password: ")?;

    let api = ApiClient::new(None, None);
    let login = api.sign_in(email.trim(), password.trim()).await?;

    let mut config = Config::load()?;
    config.access_token = Some(login.access_token);
    config.refresh_token = Some(login.refresh_token);
    config.save()?;

    println!("{} logged in successfully", "✓".green());
    Ok(())
}
