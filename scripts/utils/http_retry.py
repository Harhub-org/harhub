"""Retry wrapper for GitHub API calls — backs off on rate limits (403/429
with rate-limit headers) and transient 5xx errors, instead of failing the
whole sync run on the first hiccup.
"""

import time

import requests


def github_request(method: str, url: str, max_retries: int = 4, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 30)
    delay = 2.0

    for attempt in range(1, max_retries + 1):
        resp = requests.request(method, url, timeout=timeout, **kwargs)

        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            reset_at = int(resp.headers.get("x-ratelimit-reset", 0))
            wait_seconds = max(reset_at - time.time(), 1)
            wait_seconds = min(wait_seconds, 300)  # cap at 5 minutes so CI doesn't hang forever
            print(f"  [rate-limit] GitHub API exhausted, waiting {wait_seconds:.0f}s...")
            time.sleep(wait_seconds)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries:
                resp.raise_for_status()
            print(f"  [retry] {resp.status_code} on {url}, attempt {attempt}/{max_retries}, waiting {delay:.0f}s...")
            time.sleep(delay)
            delay *= 2
            continue

        return resp

    return resp