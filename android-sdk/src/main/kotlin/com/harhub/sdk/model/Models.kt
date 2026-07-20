package com.harhub.sdk.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
enum class AppVisibility {
    @SerialName("public") PUBLIC,
    @SerialName("proprietary") PROPRIETARY,
}

@Serializable
enum class AssetPlatform {
    @SerialName("android") ANDROID,
    @SerialName("windows") WINDOWS,
    @SerialName("linux") LINUX,
    @SerialName("macos") MACOS,
    @SerialName("appimage") APPIMAGE,
    @SerialName("deb") DEB,
    @SerialName("rpm") RPM,
    @SerialName("zip") ZIP,
    @SerialName("targz") TARGZ,
    @SerialName("jar") JAR,
    @SerialName("plugin") PLUGIN,
    @SerialName("library") LIBRARY,
}

@Serializable
data class HarhubApp(
    val id: String,
    val slug: String,
    val name: String,
    val tagline: String? = null,
    val description: String? = null,
    @SerialName("repo_owner") val repoOwner: String,
    @SerialName("repo_name") val repoName: String,
    @SerialName("repo_url") val repoUrl: String,
    val visibility: AppVisibility,
    @SerialName("icon_url") val iconUrl: String? = null,
    @SerialName("banner_url") val bannerUrl: String? = null,
    @SerialName("star_count") val starCount: Long = 0,
    @SerialName("download_count") val downloadCount: Long = 0,
)

@Serializable
data class HarhubRelease(
    val id: String,
    @SerialName("app_id") val appId: String,
    val version: String,
    val changelog: String? = null,
    @SerialName("is_prerelease") val isPrerelease: Boolean = false,
    @SerialName("is_latest") val isLatest: Boolean = false,
    @SerialName("published_at") val publishedAt: String,
)

@Serializable
data class HarhubAsset(
    val id: String,
    @SerialName("release_id") val releaseId: String,
    @SerialName("file_name") val fileName: String,
    val platform: AssetPlatform,
    val arch: String,
    @SerialName("size_bytes") val sizeBytes: Long,
    val sha256: String,
    @SerialName("public_url") val publicUrl: String? = null,
    @SerialName("download_count") val downloadCount: Long = 0,
)

@Serializable
data class HarhubSearchResult(
    val apps: List<HarhubApp>,
    val total: Int,
)