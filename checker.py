import asyncio
import re
import urllib.parse

from playwright.async_api import async_playwright, Browser


GOOGLE_DOMAIN_MAP = {
    "at": "google.at",
    "be": "google.be",
    "br": "google.com.br",
    "ca": "google.ca",
    "de": "google.de",
    "dk": "google.dk",
    "es": "google.es",
    "gr": "google.gr",
    "ie": "google.ie",
    "in": "google.co.in",
    "it": "google.it",
    "mx": "google.com.mx",
    "nl": "google.nl",
    "nz": "google.co.nz",
    "pe": "google.com.pe",
    "ro": "google.ro",
    "se": "google.se",
    "uk": "google.co.uk",
    "us": "google.com",
}


def _country_code_from_url(url: str) -> str:
    try:
        path = urllib.parse.urlparse(url).path.strip("/")
        code = path.split("/")[0].lower()
        return code if code in GOOGLE_DOMAIN_MAP else "us"
    except Exception:
        return "us"


async def _check_url_with_browser(url: str, browser: Browser) -> dict:
    """Check a single URL using an existing browser instance."""
    # Use google.com for all searches — the real browser's IP determines country
    # routing already. Country-TLD domains cause rate-limit timeouts under parallel load.
    search_url = f"https://www.google.com/search?q=site:{url}&num=10"

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = await context.new_page()

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        content = await page.content()
        text = await page.inner_text("body")
    except Exception as e:
        await context.close()
        return {"url": url, "indexed": False, "indexed_error": str(e), "notices": []}
    finally:
        await context.close()

    # --- Indexed check ---
    url_norm = url.rstrip("/").lower()
    no_results_phrases = [
        "did not match any documents",
        "no results found",
        "your search did not match",
    ]
    if any(phrase in text.lower() for phrase in no_results_phrases):
        indexed = False
    else:
        indexed = url_norm in content.lower()

    # --- DMCA notice check ---
    notices = []
    dmca_phrases = [
        "in response to a complaint we received under the us digital millennium copyright act",
        "in response to multiple complaints we received under the",
        "removed from this page",
    ]
    has_dmca_message = any(phrase in text.lower() for phrase in dmca_phrases)

    if has_dmca_message and not indexed:
        lumen_ids = re.findall(r'lumendatabase\.org/notices/(\d+)', content)
        lumen_urls = re.findall(r'(https://lumendatabase\.org/notices/\d+)', content)

        dmca_text_match = re.search(
            r'(in response to (?:a|multiple) complaint[^<]{0,500})',
            text,
            re.IGNORECASE | re.DOTALL,
        )
        dmca_text = dmca_text_match.group(1).strip()[:400] if dmca_text_match else ""

        if lumen_ids:
            for i, lid in enumerate(lumen_ids):
                lurl = lumen_urls[i] if i < len(lumen_urls) else f"https://lumendatabase.org/notices/{lid}"
                notices.append({
                    "id": int(lid),
                    "lumen_url": lurl,
                    "content": dmca_text,
                    "recipient_name": "Google LLC",
                    "affected_url": url,
                    "source": "google_search_direct",
                })
        else:
            notices.append({
                "id": None,
                "lumen_url": None,
                "content": dmca_text,
                "recipient_name": "Google LLC",
                "affected_url": url,
                "source": "google_search_direct",
            })

    return {"url": url, "indexed": indexed, "indexed_error": None, "notices": notices}


async def check_url(url: str, api_key: str = "") -> dict:
    """Single URL check — launches its own browser instance (used by main.py SSE stream)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        result = await _check_url_with_browser(url, browser)
        await browser.close()
    return result


async def check_all_urls(urls: list, site_name: str, api_key: str = "") -> list:
    """Check all URLs sharing a single browser in parallel batches of 2."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        BATCH_SIZE = 2
        results = []
        for i in range(0, len(urls), BATCH_SIZE):
            batch = urls[i:i + BATCH_SIZE]
            batch_results = await asyncio.gather(
                *[_check_url_with_browser(url, browser) for url in batch]
            )
            results.extend(batch_results)
            if i + BATCH_SIZE < len(urls):
                await asyncio.sleep(1)

        await browser.close()
    return results
