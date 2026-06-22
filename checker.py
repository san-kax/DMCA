import asyncio
import os
import re

import requests

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
SERPAPI_URL = "https://serpapi.com/search"

# Map URL path segment → (gl, location) for SerpAPI
# location pin ensures Google uses the right regional datacenter
_GEO_MAP = {
    "/uk/": ("gb", "London,England,United Kingdom"),
    "/gb/": ("gb", "London,England,United Kingdom"),
    "/ie/": ("ie", "Dublin,County Dublin,Ireland"),
    "/nz/": ("nz", "Auckland,Auckland,New Zealand"),
    "/ca/": ("ca", "Toronto,Ontario,Canada"),
    "/au/": ("au", "Sydney,New South Wales,Australia"),
    "/us/": ("us", "New York,New York,United States"),
    "/za/": ("za", "Johannesburg,Gauteng,South Africa"),
    "/in/": ("in", "Mumbai,Maharashtra,India"),
    "/de/": ("de", "Berlin,Berlin,Germany"),
    "/fr/": ("fr", "Paris,Ile-de-France,France"),
    "/es/": ("es", "Madrid,Community of Madrid,Spain"),
    "/it/": ("it", "Rome,Lazio,Italy"),
}

def _geo_for_url(url: str) -> tuple:
    lower = url.lower()
    for pattern, geo in _GEO_MAP.items():
        if pattern in lower:
            return geo
    return ("us", "New York,New York,United States")


def _serpapi_query(url: str, gl: str = None, location: str = None) -> dict:
    params = {
        "engine":   "google",
        "q":        f"site:{url}",
        "num":      10,
        "api_key":  SERPAPI_KEY,
        "hl":       "en",
        "no_cache": "true",
    }
    if gl:
        params["gl"] = gl
    if location:
        params["location"] = location
    resp = requests.get(SERPAPI_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _is_indexed(data: dict) -> bool:
    organic = data.get("organic_results", [])
    state   = data.get("search_information", {}).get("organic_results_state", "")
    return bool(organic) and "empty" not in state.lower()


def check_single_url(url: str) -> dict:
    indexed = False
    indexed_error = None
    notices = []

    try:
        # First call: geo-targeted with location pin
        gl, location = _geo_for_url(url)
        data = _serpapi_query(url, gl=gl, location=location)

        if "error" in data:
            indexed_error = data["error"]
        else:
            indexed = _is_indexed(data)

            if not indexed:
                # Second call: no geo — confirm the page is truly not indexed
                data2    = _serpapi_query(url, gl=None)
                indexed2 = _is_indexed(data2)

                if indexed2:
                    # Geo-targeted call missed it; trust the global call
                    indexed = True
                else:
                    # Both calls agree: not indexed — extract DMCA notices
                    dmca_block = data.get("dmca_messages", {})
                    for msg in dmca_block.get("messages", []):
                        msg_content = msg.get("content", "")
                        lumen_url = None
                        lumen_id  = None

                        for hw in msg.get("highlighted_words", []):
                            link = hw.get("link", "")
                            m = re.search(r'lumendatabase\.org/notices/(\d+)', link)
                            if m:
                                lumen_id  = int(m.group(1))
                                lumen_url = link
                                break

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
