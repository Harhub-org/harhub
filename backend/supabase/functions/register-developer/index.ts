// backend/supabase/functions/register-developer/index.ts
//
// POST /functions/v1/register-developer
// Authorization: Bearer <user's JWT, from a normal email/password or
// GitHub OAuth sign-up via supabase.auth>
//
// Body:
// { "github_username": "hastagaming", "bio": "...", "website_url": "..." }
//
// If the caller signed in via GitHub OAuth (Supabase Auth "github"
// provider), their verified GitHub username is read from the JWT's
// identity data and MUST match the submitted github_username — this
// is what prevents someone from claiming a GitHub username they don't
// own. If the caller signed in via email/password, registration is
// still allowed but the profile is marked unverified until they link
// GitHub via OAuth later.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
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

function jsonOk(body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
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

  const callerClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });

  const { data: userData, error: userError } = await callerClient.auth.getUser();
  if (userError || !userData?.user) {
    return jsonError("Invalid or expired session", 401);
  }

  const user = userData.user;

  let body: { github_username?: string; bio?: string; website_url?: string };
  try {
    body = await req.json();
  } catch {
    return jsonError("Invalid JSON body", 400);
  }

  if (!body.github_username || !/^[a-zA-Z0-9-]{1,39}$/.test(body.github_username)) {
    return jsonError("A valid github_username is required", 400);
  }

  // Check whether this session came from GitHub OAuth, and if so,
  // extract the verified GitHub login from the identity data.
  const githubIdentity = user.identities?.find((i) => i.provider === "github");
  const verifiedGithubLogin = githubIdentity?.identity_data?.user_name as string | undefined;

  const verified = verifiedGithubLogin?.toLowerCase() === body.github_username.toLowerCase();

  if (githubIdentity && !verified) {
    return jsonError(
      `Your authenticated GitHub identity is '${verifiedGithubLogin}', which does not match the submitted github_username '${body.github_username}'.`,
      403,
    );
  }

  const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, { auth: { persistSession: false } });

  // Ensure a public.users row exists (mirrors auth.users on first login).
  await admin.from("users").upsert(
    {
      id: user.id,
      username: (user.email ?? body.github_username).split("@")[0].toLowerCase().replace(/[^a-z0-9_-]/g, "-"),
      role: "developer",
    },
    { onConflict: "id", ignoreDuplicates: true },
  );

  await admin
    .from("users")
    .update({ role: "developer" })
    .eq("id", user.id)
    .neq("role", "admin")
    .neq("role", "moderator");

  const { data: existing } = await admin
    .from("developers")
    .select("id, user_id")
    .eq("github_username", body.github_username)
    .maybeSingle();

  if (existing && existing.user_id !== user.id) {
    return jsonError(`GitHub username '${body.github_username}' is already linked to another account.`, 409);
  }

  const { data: developer, error: upsertError } = await admin
    .from("developers")
    .upsert(
      {
        user_id: user.id,
        github_username: body.github_username,
        bio: body.bio ?? null,
        website_url: body.website_url ?? null,
        verified,
      },
      { onConflict: "user_id" },
    )
    .select()
    .single();

  if (upsertError || !developer) {
    return jsonError(`Failed to register developer profile: ${upsertError?.message}`, 500);
  }

  return jsonOk({
    developer_id: developer.id,
    github_username: developer.github_username,
    verified: developer.verified,
    message: verified
      ? "Developer profile linked and verified via GitHub OAuth."
      : "Developer profile created, but unverified — sign in with GitHub OAuth to verify ownership of this username before publishing.",
  });
});