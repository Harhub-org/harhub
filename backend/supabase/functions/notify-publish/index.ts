// backend/supabase/functions/notify-publish/index.ts
//
// POST /functions/v1/notify-publish
// Called internally (service_role only, not exposed to browsers) by the
// three publish pipelines — harhub.yml, harhub-build.yml, harhub-sync.yml —
// right after a successful publish. Looks up the developer's email via
// Supabase Auth admin API and sends a download-link notification.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY")!;
const EMAIL_FROM = Deno.env.get("NOTIFY_EMAIL_FROM")!;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, { auth: { persistSession: false } });

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

interface NotifyBody {
  developer_id: string;
  app_name: string;
  app_slug: string;
  version: string;
  source: "manual" | "build" | "sync";
  assets: { file_name: string; url: string }[];
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return jsonError("Method not allowed", 405);
  }

  // Internal-only: caller must present the service_role key itself,
  // since this function is meant to be invoked by Harhub's own CI
  // scripts, never directly by an end user or the website.
  const authHeader = req.headers.get("Authorization") ?? "";
  if (authHeader !== `Bearer ${SERVICE_ROLE_KEY}`) {
    return jsonError("Forbidden", 403);
  }

  let body: Partial<NotifyBody>;
  try {
    body = await req.json();
  } catch {
    return jsonError("Invalid JSON body", 400);
  }

  if (!body.developer_id || !body.app_name || !body.app_slug || !body.version || !body.assets?.length) {
    return jsonError("developer_id, app_name, app_slug, version, and assets are required", 400);
  }

  const { data: developer, error: devError } = await admin
    .from("developers")
    .select("user_id, github_username")
    .eq("id", body.developer_id)
    .single();

  if (devError || !developer || !developer.user_id) {
    // No linked auth user yet (unclaimed placeholder profile) — nothing
    // to email, this is expected for auto-created developer rows.
    return new Response(JSON.stringify({ sent: false, reason: "no linked user" }), {
      status: 200,
      headers: { "Content-Type": "application/json", ...CORS_HEADERS },
    });
  }

  const { data: userData, error: userError } = await admin.auth.admin.getUserById(developer.user_id);
  if (userError || !userData?.user?.email) {
    return new Response(JSON.stringify({ sent: false, reason: "no email on account" }), {
      status: 200,
      headers: { "Content-Type": "application/json", ...CORS_HEADERS },
    });
  }

  const toEmail = userData.user.email;

  const sourceLabel = { manual: "manual publish", build: "built from source", sync: "auto-sync" }[body.source ?? "manual"];

  const assetListHtml = body.assets
    .map((a) => `<li><a href="${a.url}" style="color:#8B5CF6">${a.file_name}</a></li>`)
    .join("");

  const html = `
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color:#111">${body.app_name} ${body.version} is live</h2>
      <p style="color:#444">Your app was just published on Harhub (${sourceLabel}).</p>
      <ul style="padding-left: 18px;">${assetListHtml}</ul>
      <p style="color:#888; font-size: 13px; margin-top: 24px;">
        App slug: <code>${body.app_slug}</code><br>
        GitHub: <code>${developer.github_username}</code>
      </p>
    </div>
  `;

  const resendResp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: EMAIL_FROM,
      to: toEmail,
      subject: `${body.app_name} ${body.version} published on Harhub`,
      html,
    }),
  });

  if (!resendResp.ok) {
    const errText = await resendResp.text();
    console.error("Resend send failed:", errText);
    return jsonError(`Failed to send email: ${errText}`, 502);
  }

  return new Response(JSON.stringify({ sent: true, to: toEmail }), {
    status: 200,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
});