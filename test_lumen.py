import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("SERPAPI_KEY")

async def test(url, location):
    params = {
        "engine": "google",
        "q": f"site:{url}",
        "api_key": API_KEY,
        "num": 10,
        "location": location,
    }
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get("https://serpapi.com/search", params=params)
        data = r.json()

    organic = data.get("organic_results", [])
    dmca = data.get("dmca_messages")
    loc_used = data.get("search_parameters", {}).get("location", location)

    print(f"\nURL: {url}")
    print(f"Location used: {loc_used}")
    print(f"Organic results: {len(organic)}")
    for r in organic:
        print(f"  link: {r.get('link')}")
    print(f"DMCA notice: {'YES - ' + [hw['link'] for msg in dmca.get('messages',[]) for hw in msg.get('highlighted_words',[]) if 'lumendatabase' in hw.get('link','')][0] if dmca else 'No'}")

async def main():
    tests = [
        ("https://www.gambling.com/ie/online-casinos/no-deposit-bonus", "Ireland"),
        ("https://www.gambling.com/se/online-casinon/strategi/6-basta-online-casinon-med-hogst-utbetalning", "Sweden"),
        ("https://www.gambling.com/de/online-casinos/paysafecard", "Germany"),
    ]
    for url, location in tests:
        await test(url, location)
        await asyncio.sleep(1)

asyncio.run(main())
