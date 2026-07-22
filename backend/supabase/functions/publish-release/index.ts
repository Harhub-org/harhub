// backend/supabase/functions/publish-release/index.ts
//
// POST /functions/v1/publish-release
// Authorization: Bearer <developer's user JWT>
//
// Body:
// {
//   "repo_owner": "hastagaming",
//   "repo_name": "myapp",
//   "app_slug": "myapp",
//   "app_name": "My App",
//   "version": "1.2.0",
//   "visibility": "proprietary",
//   "assets": [
//     { "file_name": "myapp.apk", "platform": "android", "arch": "universal",
//       "size_bytes": 1234567, "sha256": "...", "storage_path": "..." }
//   ]
// }
//
// Note: for proprietary assets, the caller must have already uploaded the
// binary to private-apps/{app_id}/{file_name} via a signed upload URL
// obtained from /functions/v1/create-upload-url (not shown here) — this
// function only records metadata, keeping the binary transfer separate
// from the authorization check.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const ALLOWED_PLATFORMS = new Set([
  "android", "windows", "linux", "macos", "appimage",
  "deb", "rpm", "zip", "targz", "jar", "plugin", "library",
]);

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

interface AssetInput {
  file_name: string;
  platform: string;
  arch?: string;
  size_bytes: number;
  sha256: string;
  storage_path?: string;
  public_url?: string;
}

interface PublishBody {
  repo_owner: string;
  repo_name: string;
  app_slug: string;
  app_name: string;
  version: string;
  visibility: "public" | "proprietary";
  assets: AssetInput[];
}

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function jsonOk(body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function validateBody(body: Partial<PublishBody>): string | null {
  if (!body.repo_owner || !body.repo_name) return "repo_owner and repo_name are required";
  if (!body.app_slug || !/^[a-z0-9-]{2,64}$/.test(body.app_slug)) return "app_slug is invalid";
  if (!body.version) return "version is required";
  if (body.visibility !== "public" && body.visibility !== "proprietary") return "visibility must be public or proprietary";
  if (!Array.isArray(body.assets) || body.assets.length === 0) return "at least one asset is required";

  for (const asset of body.assets) {
    if (!asset.file_name) return "every asset needs a file_name";
    if (!ALLOWED_PLATFORMS.has(asset.platform)) return `invalid platform: ${asset.platform}`;
    if (!asset.sha256 || asset.sha256.length !== 64) return `invalid sha256 for ${asset.file_name}`;
    if (!asset.size_bytes || asset.size_bytes <= 0) return `invalid size_bytes for ${asset.file_name}`;
    if (body.visibility === "proprietary" && !asset.storage_path) {
      return `storage_path is required for proprietary asset ${asset.file_name}`;
    }
    if (body.visibility === "public" && !asset.public_url) {
      return `public_url is required for public asset ${asset.file_name}`;
    }
  }

  return null;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return jsonError("Method not allowed", 405);
  }

  const authHeader = req.headers.get("Authorization");
  if (!authHeader) {
    return jsonError("Missing Authorization header", 401);
  }

  // Client bound to the caller's JWT so RLS (owns_app) is enforced —
  // this function does NOT use the service role for the ownership check,
  // only for the final writes once ownership is confirmed.
  const callerClient = createClient(SUPABASE_URL, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });

  const { data: userData, error: userError } = await callerClient.auth.getUser();
  if (userError || !userData?.user) {
    return jsonError("Invalid or expired session", 401);
  }

  const { data: developer } = await callerClient
    .from("developers")
    .select("id")
    .eq("user_id", userData.user.id)
    .single();

  if (!developer) {
    return jsonError("No developer profile linked to this account", 403);
  }

  let body: Partial<PublishBody>;
  try {
    body = await req.json();
  } catch {
    return jsonError("Invalid JSON body", 400);
  }

  const validationError = validateBody(body);
  if (validationError) {
    return jsonError(validationError, 400);
  }

  const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
    auth: { persistSession: false },
  });

  // Upsert app scoped to this developer — cannot hijack someone else's repo
  // because repo_owner/repo_name is unique and the developer_id is fixed
  // to the authenticated caller on first insert.
  const { data: app, error: appError } = await admin
    .from("apps")
    .upsert(
      {
        developer_id: developer.id,
        slug: body.app_slug,
        name: body.app_name ?? body.app_slug,
        repo_owner: body.repo_owner,
        repo_name: body.repo_name,
        repo_url: `https://github.com/${body.repo_owner}/${body.repo_name}`,
        visibility: body.visibility,
        status: "published",
      },
      { onConflict: "repo_owner,repo_name" },
    )
    .select()
    .single();

  if (appError || !app) {
    return jsonError(`Failed to upsert app: ${appError?.message}`, 500);
  }

  if (app.developer_id !== developer.id) {
    return jsonError("You do not own this repository's app entry", 403);
  }

  const { data: release, error: releaseError } = await admin
    .from("releases")
    .upsert(
      { app_id: app.id, version: body.version, is_latest: true },
      { onConflict: "app_id,version" },
    )
    .select()
    .single();

  if (releaseError || !release) {
    return jsonError(`Failed to upsert release: ${releaseError?.message}`, 500);
  }

  const assetRows = body.assets!.map((asset) => ({
    release_id: release.id,
    file_name: asset.file_name,
    platform: asset.platform,
    arch: asset.arch ?? "unknown",
    size_bytes: asset.size_bytes,
    sha256: asset.sha256,
    storage_bucket: body.visibility === "proprietary" ? "private-apps" : null,
    storage_path: body.visibility === "proprietary" ? asset.storage_path : null,
    public_url: body.visibility === "public" ? asset.public_url : null,
  }));

  const { error: assetsError } = await admin
    .from("assets")
    .upsert(assetRows, { onConflict: "release_id,file_name" });

  if (assetsError) {
    return jsonError(`Failed to upsert assets: ${assetsError.message}`, 500);
  }

  return new Response(
    JSON.stringify({
      app_id: app.id,
      release_id: release.id,
      version: body.version,
      asset_count: assetRows.length,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
});