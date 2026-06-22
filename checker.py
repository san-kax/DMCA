import asyncio
import os
import re

import requests

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "deb856bba9367d89e13471cfd7c94f88a26bba5f7cacd9f27e9472421f93c56d")
SERPAPI_URL = "https://serpapi.com/search"


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

            # ── DMCA check — SerpAPI exposes dmca_messages directly ───────────
            dmca_block = data.get("dmca_messages", {})
            for msg in dmca_block.get("messages", []):
                msg_content = msg.get("content", "")
                lumen_url = None
                lumen_id  = None

                # Try highlighted_words first
                for hw in msg.get("highlighted_words", []):
                    link = hw.get("link", "")
                    m = re.search(r'lumendatabase\.org/notices/(\d+)', link)
                    if m:
                        lumen_id  = int(m.group(1))
                        lumen_url = link
                        break

                # Fallback: search entire message + raw dmca_block JSON string
                if lumen_id is None:
                    raw_dmca = str(dmca_block)
                    m = re.search(r'lumendatabase\.org/notices/(\d+)', raw_dmca)
                    if m:
                        lumen_id  = int(m.group(1))
                        lumen_url = f"https://lumendatabase.org/notices/{lumen_id}"

                notices.append({
                    "id":             lumen_id,
                    "lumen_url":      lumen_url,
                    "content":        msg_content,
                    "recipient_name": "Google LLC",
                    "affected_url":   url,
                    "source":         "serpapi_dmca",
                })

    except Exception as exc:
        indexed_error = str(exc)

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
