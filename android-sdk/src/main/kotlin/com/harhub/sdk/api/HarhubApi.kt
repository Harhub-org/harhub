package com.harhub.sdk.api

import com.harhub.sdk.model.HarhubApp
import com.harhub.sdk.model.HarhubAsset
import com.harhub.sdk.model.HarhubRelease
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Path
import retrofit2.http.Query

/** Thin Retrofit interface over Supabase PostgREST for read-heavy, cacheable
 * queries (search/browse). Write operations (publish, upload) go through
 * the Supabase Kotlin SDK directly — see [com.harhub.sdk.HarhubClient].
 */
internal interface HarhubApi {

    @GET("rest/v1/apps")
    suspend fun searchApps(
        @Header("apikey") apiKey: String,
        @Query("name") nameFilter: String?,
        @Query("status") statusFilter: String = "eq.published",
        @Query("order") order: String = "download_count.desc",
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
    ): List<HarhubApp>

    @GET("rest/v1/apps")
    suspend fun getAppBySlug(
        @Header("apikey") apiKey: String,
        @Query("slug") slug: String,
        @Query("select") select: String = "*",
    ): List<HarhubApp>

    @GET("rest/v1/releases")
    suspend fun getReleases(
        @Header("apikey") apiKey: String,
        @Query("app_id") appIdFilter: String,
        @Query("order") order: String = "published_at.desc",
        @Query("limit") limit: Int = 20,
    ): List<HarhubRelease>

    @GET("rest/v1/assets")
    suspend fun getAssets(
        @Header("apikey") apiKey: String,
        @Query("release_id") releaseIdFilter: String,
    ): List<HarhubAsset>

    @GET("rest/v1/apps")
    suspend fun getAppById(
        @Header("apikey") apiKey: String,
        @Path("id") id: String,
        @Query("id") idFilter: String,
    ): List<HarhubApp>
}