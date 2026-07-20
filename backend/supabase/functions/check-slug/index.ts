// backend/supabase/functions/check-slug/index.ts
//
// GET /functions/v1/check-slug?slug=myapp
//
// Public, unauthenticated. Returns { available: boolean }.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, { auth: { persistSession: false } });

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const slug = url.searchParams.get("slug");

  if (!slug || !/^[a-z0-9-]{2,64}$/.test(slug)) {
    return new Response(
      JSON.stringify({ error: "slug must be 2-64 chars, lowercase letters/numbers/hyphens only" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  const { data } = await supabase.from("apps").select("id").eq("slug", slug).maybeSingle();

  return new Response(JSON.stringify({ available: data === null }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});