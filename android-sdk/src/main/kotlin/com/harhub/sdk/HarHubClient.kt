package com.hastagaming.harhub.sdk

import com.hastagaming.harhub.sdk.api.HarhubApi
import com.hastagaming.harhub.sdk.model.AssetPlatform
import com.hastagaming.harhub.sdk.model.HarhubApp
import com.hastagaming.harhub.sdk.model.HarhubAsset
import com.hastagaming.harhub.sdk.model.HarhubRelease
import io.github.jantennert.supabase.createSupabaseClient
import io.github.jantennert.supabase.auth.Auth
import io.github.jantennert.supabase.auth.auth
import io.github.jantennert.supabase.auth.providers.builtin.Email
import io.github.jantennert.supabase.postgrest.Postgrest
import io.github.jantennert.supabase.storage.Storage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit
import retrofit2.converter.kotlinxserialization.asConverterFactory

class HarhubClient(
    private val supabaseUrl: String,
    private val supabaseAnonKey: String,
    enableLogging: Boolean = false,
) {

    private val supabase = createSupabaseClient(
        supabaseUrl = supabaseUrl,
        supabaseKey = supabaseAnonKey,
    ) {
        install(Postgrest)
        install(Auth)
        install(Storage)
    }

    private val json = Json { ignoreUnknownKeys = true }

    private val okHttpClient = OkHttpClient.Builder()
        .apply {
            if (enableLogging) {
                addInterceptor(HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.BASIC
                })
            }
        }
        .build()

    private val api: HarhubApi = Retrofit.Builder()
        .baseUrl("$supabaseUrl/")
        .client(okHttpClient)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(HarhubApi::class.java)

    suspend fun signIn(email: String, password: String) = withContext(Dispatchers.IO) {
        supabase.auth.signInWith(Email) {
            this.email = email
            this.password = password
        }
    }

    fun currentUserId(): String? = supabase.auth.currentUserOrNull()?.id

    suspend fun searchApps(query: String? = null, page: Int = 0, pageSize: Int = 20): List<HarhubApp> =
        withContext(Dispatchers.IO) {
            api.searchApps(
                apiKey = supabaseAnonKey,
                nameFilter = query?.let { "ilike.*$it*" },
                limit = pageSize,
                offset = page * pageSize,
            )
        }

    suspend fun getApp(slug: String): HarhubApp? = withContext(Dispatchers.IO) {
        api.getAppBySlug(apiKey = supabaseAnonKey, slug = "eq.$slug").firstOrNull()
    }

    suspend fun getReleases(appId: String): List<HarhubRelease> = withContext(Dispatchers.IO) {
        api.getReleases(apiKey = supabaseAnonKey, appIdFilter = "eq.$appId")
    }

    suspend fun getLatestRelease(appId: String): HarhubRelease? =
        getReleases(appId).firstOrNull { it.isLatest }

    suspend fun getAssets(releaseId: String): List<HarhubAsset> = withContext(Dispatchers.IO) {
        api.getAssets(apiKey = supabaseAnonKey, releaseIdFilter = "eq.$releaseId")
    }

    suspend fun getAssetsForPlatform(releaseId: String, platform: AssetPlatform): List<HarhubAsset> =
        getAssets(releaseId).filter { it.platform == platform }

    fun resolveDownloadUrl(app: HarhubApp, asset: HarhubAsset): String {
        return asset.publicUrl
            ?: "$supabaseUrl/functions/v1/sign-download?app=${app.slug}&file=${asset.fileName}"
    }
}