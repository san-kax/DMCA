import asyncio
import time
from playwright.async_api import async_playwright
from checker import _check_url_with_browser

TEST_URLS = [
    # AT - was timing out before
    "https://www.gambling.com/at",
    "https://www.gambling.com/at/online-casinos/strategie/beste-online-casino-oesterreich-3610100",
    # BE - was timing out before
    "https://www.gambling.com/be/online-casinos/strategie/de-best-uitbetalende-casino-s-in-belgie",
    # DE - SerpAPI was wrong (showed not indexed)
    "https://www.gambling.com/de/online-casinos/paysafecard",
    "https://www.gambling.com/de/online-casinos",
    # IE - SerpAPI was wrong (showed not indexed)
    "https://www.gambling.com/ie/online-casinos/no-deposit-bonus",
    "https://www.gambling.com/ie",
    # CA - check accuracy
    "https://www.gambling.com/ca",
    "https://www.gambling.com/ca/online-casinos/no-deposit-bonus",
    # SE - SerpAPI was correct, confirm still works
    "https://www.gambling.com/se/online-casinon/strategi/6-basta-online-casinon-med-hogst-utbetalning",
]

async def main():
    print(f"Testing {len(TEST_URLS)} URLs with shared browser...\n")
    start = time.time()

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

        # Run 2 at a time — avoids Google rate-limit while still being faster than sequential
        BATCH_SIZE = 2
        for i in range(0, len(TEST_URLS), BATCH_SIZE):
            batch = TEST_URLS[i:i + BATCH_SIZE]
            t = time.time()
            results = await asyncio.gather(*[_check_url_with_browser(url, browser) for url in batch])
            elapsed = time.time() - t
            print(f"Batch {i//BATCH_SIZE + 1} done in {elapsed:.1f}s")
            for result in results:
                status = "INDEXED    " if result["indexed"] else "NOT INDEXED"
                notice = f"DMCA #{result['notices'][0]['id']}" if result["notices"] else "No notice"
                error = f" ERROR: {result['indexed_error'][:80]}" if result.get("indexed_error") else ""
                print(f"  {status} | {notice:<20} | {result['url']}{error}")

        await browser.close()

    print(f"\nTotal time: {time.time() - start:.1f}s")

asyncio.run(main())
