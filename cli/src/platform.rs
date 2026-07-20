//! Detects the current runtime platform/arch so `harhub install` can pick
//! the right asset automatically, and classifies which asset kinds are
//! "installable" vs "download-only" per Harhub CLI policy.

use std::env::consts::{ARCH, OS};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AssetKind {
    Apk,
    Exe,
    Linux,
    AppImage,
    Deb,
    Rpm,
    Jar,
    Zip,
    TarGz,
    Plugin,
    Library,
    Unknown,
}

impl AssetKind {
    pub fn from_platform_str(s: &str) -> Self {
        match s {
            "android" => AssetKind::Apk,
            "windows" => AssetKind::Exe,
            "linux" => AssetKind::Linux,
            "appimage" => AssetKind::AppImage,
            "deb" => AssetKind::Deb,
            "rpm" => AssetKind::Rpm,
            "jar" => AssetKind::Jar,
            "zip" => AssetKind::Zip,
            "targz" => AssetKind::TarGz,
            "plugin" => AssetKind::Plugin,
            "library" => AssetKind::Library,
            _ => AssetKind::Unknown,
        }
    }

    /// Per user policy: .apk and .exe are ALWAYS download-only, never
    /// auto-installed, regardless of the host platform. Everything else
    /// that is inherently executable/installable on Linux gets the full
    /// install treatment.
    pub fn is_installable(&self) -> bool {
        matches!(
            self,
            AssetKind::Linux | AssetKind::AppImage | AssetKind::Deb
                | AssetKind::Rpm | AssetKind::Jar
        )
    }

    pub fn label(&self) -> &'static str {
        match self {
            AssetKind::Apk => "Android APK",
            AssetKind::Exe => "Windows EXE",
            AssetKind::Linux => "Linux binary",
            AssetKind::AppImage => "AppImage",
            AssetKind::Deb => "Debian package",
            AssetKind::Rpm => "RPM package",
            AssetKind::Jar => "Java JAR",
            AssetKind::Zip => "ZIP archive",
            AssetKind::TarGz => "TAR.GZ archive",
            AssetKind::Plugin => "Plugin",
            AssetKind::Library => "Library",
            AssetKind::Unknown => "Unknown",
        }
    }
}

/// Returns the ordered list of platform strings (as used in the `assets`
/// table) that are acceptable matches for the current host, best match
/// first. Termux on Android reports OS "android" but behaves like Linux
/// for binary execution purposes, so it prefers "linux" assets over "android".
pub fn host_platform_preference() -> Vec<&'static str> {
    match OS {
        "linux" => vec!["linux", "appimage", "deb", "rpm", "jar", "zip", "targz"],
        "android" => vec!["linux", "jar", "zip", "targz", "android"],
        "macos" => vec!["macos", "jar", "zip", "targz"],
        "windows" => vec!["windows", "jar", "zip", "targz"],
        _ => vec!["jar", "zip", "targz"],
    }
}

pub fn host_arch() -> &'static str {
    match ARCH {
        "aarch64" => "arm64-v8a",
        "arm" => "armeabi-v7a",
        "x86_64" => "x86_64",
        "x86" => "x86",
        _ => "unknown",
    }
}