// backend/supabase/functions/sign-download/index.ts

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const SIGNED_URL_TTL_SECONDS = 300;
const RATE_LIMIT_MAX = 10;
const RATE_LIMIT_WINDOW_MINUTES = 5;

const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false },
});

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function hashIp(ip: string): Promise<string> {
  const data = new TextEncoder().encode(ip);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const appSlug = url.searchParams.get("app");
  const fileName = url.searchParams.get("file");
  const requestedVersion = url.searchParams.get("version");

  if (!appSlug || !fileName) {
    return jsonError("Missing required query params: app, file", 400);
  }

  const { data: app, error: appError } = await supabase
    .from("apps")
    .select("id, visibility, status")
    .eq("slug", appSlug)
    .single();

  if (appError || !app) {
    return jsonError("App not found", 404);
  }
  if (app.visibility !== "proprietary") {
    return jsonError("This app does not use signed downloads", 400);
  }
  if (app.status !== "published") {
    return jsonError("This app is not currently available", 404);
  }

  let releaseQuery = supabase
    .from("releases")
    .select("id, version")
    .eq("app_id", app.id);

  releaseQuery = requestedVersion
    ? releaseQuery.eq("version", requestedVersion)
    : releaseQuery.eq("is_latest", true);

  const { data: release, error: releaseError } = await releaseQuery.single();

  if (releaseError || !release) {
    return jsonError("Release not found", 404);
  }

  const { data: asset, error: assetError } = await supabase
    .from("assets")
    .select("id, storage_bucket, storage_path")
    .eq("release_id", release.id)
    .eq("file_name", fileName)
    .single();

  if (assetError || !asset || !asset.storage_bucket || !asset.storage_path) {
    return jsonError("Asset not found", 404);
  }

  const forwardedFor = req.headers.get("x-forwarded-for") ?? "unknown";
  const ipHash = await hashIp(forwardedFor);

  const windowStart = new Date(Date.now() - RATE_LIMIT_WINDOW_MINUTES * 60_000).toISOString();

  const { count } = await supabase
    .from("rate_limit_log")
    .select("*", { count: "exact", head: true })
    .eq("ip_hash", ipHash)
    .eq("asset_id", asset.id)
    .gte("requested_at", windowStart);

  if ((count ?? 0) >= RATE_LIMIT_MAX) {
    return jsonError("Too many download requests for this file — please wait a few minutes.", 429);
  }

  await supabase.from("rate_limit_log").insert({ ip_hash: ipHash, asset_id: asset.id });

  if (Math.random() < 0.05) {
    await supabase.rpc("prune_rate_limit_log");
  }

  const { data: signed, error: signError } = await supabase.storage
    .from(asset.storage_bucket)
    .createSignedUrl(asset.storage_path, SIGNED_URL_TTL_SECONDS);

  if (signError || !signed) {
    return jsonError("Failed to generate signed URL", 500);
  }

  const authHeader = req.headers.get("Authorization");
  let userId: string | null = null;
  if (authHeader) {
    const { data: userData } = await supabase.auth.getUser(
      authHeader.replace("Bearer ", ""),
    );
    userId = userData?.user?.id ?? null;
  }

  await supabase.from("download_history").insert({
    asset_id: asset.id,
    user_id: userId,
    ip_hash: ipHash,
    user_agent: req.headers.get("user-agent") ?? null,
  });

  await supabase.rpc("increment_download_count", { target_asset_id: asset.id });

  return new Response(null, {
    status: 302,
    headers: { Location: signed.signedUrl },
  });
});