import asyncio
import os
import re

import requests

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "deb856bba9367d89e13471cfd7c94f88a26bba5f7cacd9f27e9472421f93c56d")
SERPAPI_URL = "https://serpapi.com/search"
LUMEN_URL   = "https://lumendatabase.org/notices/search.json"


def check_single_url(url: str) -> dict:
    indexed = False
    indexed_error = None
    notices = []

    # ── 1. Indexed check via SerpAPI ─────────────────────────────────────────
    try:
        resp = requests.get(
            SERPAPI_URL,
            params={
                "engine":   "google",
                "q":        f"site:{url}",
                "num":      10,
                "api_key":  SERPAPI_KEY,
                "no_cache": "true",
                "hl":       "en",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            indexed_error = data["error"]
        else:
            organic = data.get("organic_results", [])
            state   = data.get("search_information", {}).get("organic_results_state", "")
            indexed = bool(organic) and "empty" not in state.lower()

    except Exception as exc:
        indexed_error = str(exc)

    # ── 2. DMCA check via Lumen Database API ─────────────────────────────────
    try:
        lumen_resp = requests.get(
            LUMEN_URL,
            params={
                "works.urls[]": url,
                "per_page":     10,
                "sort_by":      "date_sent desc",
            },
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if lumen_resp.status_code == 200:
            for notice in lumen_resp.json().get("notices", []):
                nid = notice.get("id")
                notices.append({
                    "id":             nid,
                    "lumen_url":      f"https://lumendatabase.org/notices/{nid}" if nid else None,
                    "content":        notice.get("title", ""),
                    "recipient_name": notice.get("recipient_name", "Google LLC"),
                    "affected_url":   url,
                    "source":         "lumen_api",
                })
    except Exception:
        pass

    return {
        "url":           url,
        "indexed":       indexed,
        "indexed_error": indexed_error,
        "notices":       notices,
    }


# ── Async shims (app.py calls these) ─────────────────────────────────────────

async def _check_url_with_browser(url: str, browser=None) -> dict:
    return check_single_url(url)


async def check_url(url: str, api_key: str = "") -> dict:
    return check_single_url(url)


async def check_all_urls(urls: list, site_name: str, api_key: str = "") -> list:
    results = []
    for url in urls:
        results.append(check_single_url(url))
        await asyncio.sleep(0.5)
    return results
