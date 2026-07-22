import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const UPLOAD_URL_TTL_SECONDS = 600;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }
  if (req.method !== "POST") return jsonError("Method not allowed", 405);

  const authHeader = req.headers.get("Authorization");
  if (!authHeader) return jsonError("Missing Authorization header", 401);

  const callerClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });

  const { data: userData, error: userError } = await callerClient.auth.getUser();
  if (userError || !userData?.user) return jsonError("Invalid or expired session", 401);

  let body: { app_slug?: string; file_name?: string };
  try {
    body = await req.json();
  } catch {
    return jsonError("Invalid JSON body", 400);
  }

  if (!body.app_slug || !body.file_name) {
    return jsonError("app_slug and file_name are required", 400);
  }
  if (body.file_name.includes("/") || body.file_name.includes("..")) {
    return jsonError("file_name must not contain path separators", 400);
  }

  const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, { auth: { persistSession: false } });

  const { data: developer } = await callerClient
    .from("developers")
    .select("id, verified")
    .eq("user_id", userData.user.id)
    .single();

  if (!developer) return jsonError("No developer profile linked to this account", 403);
  if (!developer.verified) {
    return jsonError("Your developer profile must be GitHub-verified before uploading proprietary binaries", 403);
  }

  const { data: app } = await callerClient
    .from("apps")
    .select("id, developer_id, visibility")
    .eq("slug", body.app_slug)
    .single();

  if (!app || app.developer_id !== developer.id) {
    return jsonError("App not found or not owned by this account", 404);
  }
  if (app.visibility !== "proprietary") {
    return jsonError("create-upload-url is only for proprietary apps — public apps should attach a public_url instead", 400);
  }

  const storagePath = `${app.id}/${body.file_name}`;

  const { data: signed, error: signError } = await admin.storage
    .from("private-apps")
    .createSignedUploadUrl(storagePath);

  if (signError || !signed) {
    return jsonError(`Failed to create signed upload URL: ${signError?.message}`, 500);
  }

  return new Response(
    JSON.stringify({
      upload_url: signed.signedUrl,
      token: signed.token,
      storage_path: storagePath,
      expires_in_seconds: UPLOAD_URL_TTL_SECONDS,
    }),
    { status: 200, headers: { "Content-Type": "application/json", ...CORS_HEADERS } },
  );
});