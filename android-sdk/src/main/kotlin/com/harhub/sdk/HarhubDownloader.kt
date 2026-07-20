package com.harhub.sdk

import com.harhub.sdk.model.HarhubAsset
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.security.MessageDigest

sealed class DownloadResult {
    data class Success(val file: File) : DownloadResult()
    data class HashMismatch(val expected: String, val actual: String) : DownloadResult()
    data class Failure(val throwable: Throwable) : DownloadResult()
}

class HarhubDownloader(
    private val httpClient: OkHttpClient = OkHttpClient(),
) {

    /** Downloads [asset] from [url] into [destination], then verifies its
     * SHA256 against [HarhubAsset.sha256] before returning success. The
     * caller is responsible for choosing where to install/open the file.
     */
    suspend fun download(
        url: String,
        asset: HarhubAsset,
        destination: File,
    ): DownloadResult = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder().url(url).build()
            httpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return@withContext DownloadResult.Failure(
                        IllegalStateException("HTTP ${response.code} while downloading ${asset.fileName}")
                    )
                }

                val body = response.body ?: return@withContext DownloadResult.Failure(
                    IllegalStateException("Empty response body for ${asset.fileName}")
                )

                destination.outputStream().use { output ->
                    body.byteStream().copyTo(output)
                }
            }

            val actualHash = sha256Of(destination)
            if (!actualHash.equals(asset.sha256, ignoreCase = true)) {
                destination.delete()
                return@withContext DownloadResult.HashMismatch(
                    expected = asset.sha256,
                    actual = actualHash,
                )
            }

            DownloadResult.Success(destination)
        } catch (t: Throwable) {
            DownloadResult.Failure(t)
        }
    }

    private fun sha256Of(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1 shl 20)
            var read: Int
            while (input.read(buffer).also { read = it } != -1) {
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}