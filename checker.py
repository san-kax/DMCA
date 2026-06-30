import asyncio
import os
import re

import requests

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
SERPAPI_URL = "https://serpapi.com/search"

GSC_CLIENT_ID     = os.environ.get("GSC_CLIENT_ID", "")
GSC_CLIENT_SECRET = os.environ.get("GSC_CLIENT_SECRET", "")
GSC_REFRESH_TOKEN = os.environ.get("GSC_REFRESH_TOKEN", "")

# Domains where we use GSC URL Inspection API for indexing checks.
# Must be verified properties in Search Console under the same Google account.
GSC_DOMAINS = {"gambling.com", "casinos.com"}

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
    "/fi/": ("fi", "Helsinki,Uusimaa,Finland"),
    "/se/": ("se", "Stockholm,Stockholm,Sweden"),
    "/no/": ("no", "Oslo,Oslo,Norway"),
    "/dk/": ("dk", "Copenhagen,Capital Region,Denmark"),
}

# Domain-level geo detection (checked before path patterns)
_DOMAIN_GEO_MAP = {
    ".co.uk":          ("gb", "London,England,United Kingdom"),
    ".com.au":         ("au", "Sydney,New South Wales,Australia"),
    ".com.de":         ("de", "Berlin,Berlin,Germany"),
    ".net.nz":         ("nz", "Auckland,Auckland,New Zealand"),
    ".bonus.ca":       ("ca", "Toronto,Ontario,Canada"),
    ".bonusfinder.ie": ("ie", "Dublin,County Dublin,Ireland"),
    ".bonusfinder.it": ("it", "Rome,Lazio,Italy"),
    "bonus.ca":        ("ca", "Toronto,Ontario,Canada"),
    "bonusfinder.ie":  ("ie", "Dublin,County Dublin,Ireland"),
    "bonusfinder.it":  ("it", "Rome,Lazio,Italy"),
    "nettikasinot.com":("fi", "Helsinki,Uusimaa,Finland"),
    "vedonlyonti.com": ("fi", "Helsinki,Uusimaa,Finland"),
    "svenskacasino.se":("se", "Stockholm,Stockholm,Sweden"),
}


def _domain_of(url: str) -> str:
    """Return the registered domain (e.g. gambling.com) from a URL."""
    host = url.lower().split("//")[-1].split("/")[0].split("?")[0]
    host = host.lstrip("www.")
    return host


def _use_gsc(url: str) -> bool:
    domain = _domain_of(url)
    return any(domain == d or domain.endswith("." + d) for d in GSC_DOMAINS)


def _geo_for_url(url: str) -> tuple:
    lower = url.lower()
    for pattern, geo in _DOMAIN_GEO_MAP.items():
        if pattern in lower:
            return geo
    for pattern, geo in _GEO_MAP.items():
        if pattern in lower:
            return geo
    return ("us", "New York,New York,United States")


# ── GSC URL Inspection API ────────────────────────────────────────────────────

_gsc_access_token = None

def _get_gsc_access_token() -> str:
    global _gsc_access_token
    if _gsc_access_token:
        return _gsc_access_token
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id":     GSC_CLIENT_ID,
            "client_secret": GSC_CLIENT_SECRET,
            "refresh_token": GSC_REFRESH_TOKEN,
            "grant_type":    "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    _gsc_access_token = resp.json()["access_token"]
    return _gsc_access_token


def _gsc_inspect(url: str) -> dict:
    """Call GSC URL Inspection API and return the inspection result dict."""
    domain = _domain_of(url)
    # GSC property must match exactly as verified — try https:// prefix first
    site_url = f"https://www.{domain}/"
    token = _get_gsc_access_token()
    resp = requests.post(
        "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
        headers={"Authorization": f"Bearer {token}"},
        json={"inspectionUrl": url, "siteUrl": site_url},
        timeout=30,
    )
    if resp.status_code == 401:
        # Token expired mid-run, refresh once
        global _gsc_access_token
        _gsc_access_token = None
        token = _get_gsc_access_token()
        resp = requests.post(
            "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
            headers={"Authorization": f"Bearer {token}"},
            json={"inspectionUrl": url, "siteUrl": site_url},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


def _gsc_is_indexed(result: dict) -> bool:
    verdict = (
        result.get("inspectionResult", {})
              .get("indexStatusResult", {})
              .get("verdict", "")
    )
    return verdict == "PASS"


# ── SerpAPI ───────────────────────────────────────────────────────────────────

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


def _notice_type_from_content(content: str) -> str:
    c = content.lower()
    if "digital millennium copyright act" in c or "dmca" in c:
        return "DMCA Copyright"
    if "legal request" in c or "local law" in c:
        return "Legal Request (Local Law)"
    if "court order" in c:
        return "Court Order"
    return "Legal Notice"


def _extract_notices(dmca_block: dict, dmca_block2: dict, url: str) -> list:
    geo_confirmed = bool(dmca_block2.get("messages"))
    notices = []
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
            m = re.search(r'lumendatabase\.org/notices/(\d+)', str(dmca_block))
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
            "geo_confirmed":  geo_confirmed,
            "notice_type":    _notice_type_from_content(msg_content),
        })
    return notices


# ── Main check ────────────────────────────────────────────────────────────────

def check_single_url(url: str) -> dict:
    indexed = False
    indexed_error = None
    notices = []

    try:
        if _use_gsc(url) and GSC_CLIENT_ID and GSC_REFRESH_TOKEN:
            # GSC URL Inspection for owned properties (gambling.com, casinos.com)
            result  = _gsc_inspect(url)
            indexed = _gsc_is_indexed(result)
            if not indexed:
                # Page is not indexed. Use SerpAPI only to check for DMCA notices.
                gl, location = _geo_for_url(url)
                data  = _serpapi_query(url, gl=gl, location=location)
                data2 = _serpapi_query(url, gl=None)
                if _is_indexed(data) or _is_indexed(data2):
                    # SerpAPI disagrees — trust GSC, mark as not indexed but no notice
                    pass
                else:
                    dmca_block  = data.get("dmca_messages", {})
                    dmca_block2 = data2.get("dmca_messages", {})
                    if dmca_block.get("messages"):
                        notices = _extract_notices(dmca_block, dmca_block2, url)
        else:
            # SerpAPI for all other sites
            gl, location = _geo_for_url(url)
            data = _serpapi_query(url, gl=gl, location=location)
            if "error" in data:
                indexed_error = data["error"]
            else:
                indexed = _is_indexed(data)
                if not indexed:
                    data2    = _serpapi_query(url, gl=None)
                    indexed2 = _is_indexed(data2)
                    if indexed2:
                        indexed = True
                    else:
                        dmca_block  = data.get("dmca_messages", {})
                        dmca_block2 = data2.get("dmca_messages", {})
                        if dmca_block.get("messages"):
                            notices = _extract_notices(dmca_block, dmca_block2, url)

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
