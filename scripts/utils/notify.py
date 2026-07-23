"""Sends a publish-notification email via the notify-publish Edge Function.
Best-effort: failures here never abort a publish run, they just get logged.

For proprietary apps, the emailed links point at the sign-download
endpoint (short-lived signed URLs, generated fresh on click) rather than
the permanent branch-mirror/Release URLs — those permanent URLs exist
for Harhub's internal mirroring, not for developers to hand out.
"""

import requests


def notify_publish(
    supabase_url: str,
    service_key: str,
    developer_id: str,
    app_slug: str,
    app_name: str,
    version: str,
    source: str,
    visibility: str,
    asset_urls: dict[str, str],
) -> None:
    if visibility == "proprietary":
        # Never email the permanent mirror URLs for proprietary apps —
        # always route through sign-download so links expire.
        email_urls = {
            file_name: f"{supabase_url.rstrip('/')}/functions/v1/sign-download?app={app_slug}&file={file_name}"
            for file_name in asset_urls
        }
    else:
        email_urls = asset_urls

    try:
        resp = requests.post(
            f"{supabase_url.rstrip('/')}/functions/v1/notify-publish",
            headers={"Authorization": f"Bearer {service_key}", "Content-Type": "application/json"},
            json={
                "developer_id": developer_id,
                "app_name": app_name,
                "app_slug": app_slug,
                "version": version,
                "source": source,
                "assets": [{"file_name": name, "url": url} for name, url in email_urls.items()],
            },
            timeout=15,
        )
        if resp.ok:
            result = resp.json()
            if result.get("sent"):
                print(f"  [email] notified {result.get('to')}")
            else:
                print(f"  [email] skipped: {result.get('reason')}")
        else:
            print(f"  [email] failed: {resp.status_code} {resp.text}")
    except Exception as exc:
        print(f"  [email] error (non-fatal): {exc}")