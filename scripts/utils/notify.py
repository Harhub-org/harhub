"""Sends a publish-notification email via the notify-publish Edge Function.
Best-effort: failures here never abort a publish run, they just get logged.
"""

import requests


def notify_publish(
    supabase_url: str,
    service_key: str,
    developer_id: str,
    app_name: str,
    app_slug: str,
    version: str,
    source: str,
    asset_urls: dict[str, str],
) -> None:
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
                "assets": [{"file_name": name, "url": url} for name, url in asset_urls.items()],
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