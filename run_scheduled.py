"""
Daily DMCA check — runs all CSVs in urls/ and posts results to Slack.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

from checker import check_single_url

SERPAPI_KEY    = os.environ.get("SERPAPI_KEY", "")
SLACK_WEBHOOK  = os.environ.get("SLACK_WEBHOOK_URL", "")
URLS_DIR       = Path(__file__).parent / "urls"


def load_urls(csv_path: Path) -> list[str]:
    urls = []
    with open(csv_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not lines:
        return []
    header = lines[0].strip().lower()
    start  = 1 if header in ("url", "urls", "link", "links") else 0
    for line in lines[start:]:
        u = line.strip()
        if u:
            urls.append(u)
    return urls


def post_to_slack(message: str):
    if not SLACK_WEBHOOK:
        print("No SLACK_WEBHOOK_URL set — skipping Slack post")
        return
    resp = requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=10)
    if resp.status_code != 200:
        print(f"Slack error: {resp.status_code} {resp.text}")


def run():
    csv_files = sorted(URLS_DIR.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in urls/")
        sys.exit(0)

    today = date.today().strftime("%d %b %Y")
    all_dmca = []
    summary_lines = [f"*📊 DMCA Monitor — {today}*\n"]

    for csv_path in csv_files:
        site_name = csv_path.stem
        urls = load_urls(csv_path)
        if not urls:
            continue

        print(f"\n── {site_name}: {len(urls)} URLs")
        results = []
        for url in urls:
            result = check_single_url(url)
            results.append(result)
            status = "DMCA" if result["notices"] else ("indexed" if result["indexed"] else "not indexed")
            print(f"  {status:12} {url}")

        indexed  = sum(1 for r in results if r["indexed"])
        dmca_hit = [r for r in results if r["notices"]]

        summary_lines.append(
            f"*{site_name}* — {len(urls)} checked · {indexed} indexed · {len(dmca_hit)} DMCA"
        )
        all_dmca.extend(dmca_hit)

    # Build Slack message
    message = "\n".join(summary_lines)

    if all_dmca:
        message += "\n\n*🚨 DMCA Notices Found:*"
        for r in all_dmca:
            for n in r["notices"]:
                nid      = n.get("id", "N/A")
                lurl     = n.get("lumen_url", "")
                lumen_txt = f" · <{lurl}|View Notice>" if lurl else ""
                message += f"\n• `{r['url']}`  →  Notice #{nid}{lumen_txt}"
    else:
        message += "\n\n✅ No DMCA notices found today."

    print("\n── Slack message ──")
    print(message)
    post_to_slack(message)


if __name__ == "__main__":
    run()
