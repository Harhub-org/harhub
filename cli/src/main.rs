use clap::{Parser, Subcommand};

mod api;
mod commands;
mod config;
mod download;
mod platform;

#[derive(Parser)]
#[command(
    name = "harhub",
    version,
    about = "Harhub — the app download registry for your GitHub repos"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Search for apps on Harhub
    Search { query: Option<String> },
    /// Show details about an app
    Info { slug: String },
    /// Download (and install, where applicable) an app's latest release
    Install { slug: String },
    /// Re-check and reinstall an app to its latest version
    Update { slug: Option<String> },
    /// Remove a previously downloaded file
    Remove { file_name: String },
    /// Log in to your Harhub developer account
    Login,
    /// Publish a public release asset
    Publish {
        #[arg(long)]
        file: std::path::PathBuf,
        #[arg(long)]
        repo_owner: String,
        #[arg(long)]
        repo_name: String,
        #[arg(long)]
        app_slug: String,
        #[arg(long)]
        app_name: String,
        #[arg(long)]
        version: String,
        #[arg(long)]
        platform: String,
        #[arg(long, default_value = "unknown")]
        arch: String,
        #[arg(long, default_value = "public")]
        visibility: String,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Search { query } => commands::search::run(query).await,
        Commands::Info { slug } => commands::info::run(slug).await,
        Commands::Install { slug } => commands::install::run(slug).await,
        Commands::Update { slug } => commands::update::run(slug).await,
        Commands::Remove { file_name } => commands::remove::run(file_name).await,
        Commands::Login => commands::login::run().await,
        Commands::Publish {
            file,
            repo_owner,
            repo_name,
            app_slug,
            app_name,
            version,
            platform,
            arch,
            visibility,
        } => {
            commands::publish::run(commands::publish::PublishArgs {
                file,
                repo_owner,
                repo_name,
                app_slug,
                app_name,
                version,
                platform,
                arch,
                visibility,
            })
            .await
        }
    }
}
