"""
Daily DMCA check — runs all CSVs in urls/ and posts results to Slack.
"""
import csv
import io
import os
import sys
from datetime import date
from pathlib import Path

import requests

from checker import check_single_url

SERPAPI_KEY       = os.environ.get("SERPAPI_KEY", "")
SLACK_WEBHOOK     = os.environ.get("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN   = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID  = "C0BC3FKT5A7"
URLS_DIR          = Path(__file__).parent / "urls"


def load_urls(csv_path: Path) -> list[str]:
    import csv as _csv
    urls = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = _csv.reader(f)
        rows = list(reader)
    if not rows:
        return []
    # Skip header row if first cell looks like a column name
    start = 1 if rows[0][0].strip().lower() in ("url", "urls", "link", "links") else 0
    for row in rows[start:]:
        if row:
            u = row[0].strip()
            if u:
                urls.append(u)
    return urls


def post_to_slack(message: str):
    if not SLACK_WEBHOOK:
        print("No SLACK_WEBHOOK_URL set — skipping Slack post")
        return
    resp = requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=10)
    if resp.status_code != 200:
        print(f"Slack webhook error: {resp.status_code} {resp.text}")


def upload_csv_to_slack(csv_bytes: bytes, filename: str, title: str):
    if not SLACK_BOT_TOKEN:
        print("No SLACK_BOT_TOKEN set — skipping CSV upload")
        return

    # Step 1: get upload URL
    resp = requests.post(
        "https://slack.com/api/files.getUploadURLExternal",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        json={"filename": filename, "length": len(csv_bytes)},
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"Slack getUploadURL error: {data}")
        return

    upload_url = data["upload_url"]
    file_id    = data["file_id"]

    # Step 2: upload file content
    resp = requests.post(upload_url, data=csv_bytes, timeout=30)
    if resp.status_code != 200:
        print(f"Slack upload error: {resp.status_code} {resp.text}")
        return

    # Step 3: complete upload and share to channel
    resp = requests.post(
        "https://slack.com/api/files.completeUploadExternal",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        json={
            "files": [{"id": file_id, "title": title}],
            "channel_id": SLACK_CHANNEL_ID,
        },
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"Slack completeUpload error: {data}")
    else:
        print(f"CSV uploaded to Slack: {filename}")


def build_csv(all_results: list[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["URL", "Indexed", "DMCA Notice", "Lumen URL", "Error"])
    for r in all_results:
        notice_ids = ", ".join(str(n["id"]) for n in r["notices"] if n.get("id")) or ("Yes" if r["notices"] else "")
        lumen_urls = ", ".join(n.get("lumen_url") or "" for n in r["notices"])
        writer.writerow([
            r["url"],
            "Yes" if r["indexed"] else "No",
            notice_ids,
            lumen_urls,
            r.get("indexed_error") or "",
        ])
    return output.getvalue().encode("utf-8")


def run():
    csv_files = sorted(URLS_DIR.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in urls/")
        sys.exit(0)

    today     = date.today().strftime("%d %b %Y")
    today_fn  = date.today().strftime("%Y-%m-%d")
    all_dmca  = []
    all_results = []
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
        all_results.extend(results)

    # Build and post Slack summary message
    message = "\n".join(summary_lines)

    if all_dmca:
        message += "\n\n*🚨 Notices Found:*"
        for r in all_dmca:
            for n in r["notices"]:
                nid           = n.get("id", "N/A")
                lurl          = n.get("lumen_url", "")
                geo_confirmed = n.get("geo_confirmed", True)
                notice_date   = n.get("notice_date", "")
                lumen_txt     = f" · <{lurl}|View Notice>" if lurl else ""
                date_txt      = f" · {notice_date}" if notice_date else ""
                warning       = "" if geo_confirmed else " ⚠️ _geo-specific — verify manually_"
                message += f"\n• `{r['url']}`  →  Notice #{nid}{lumen_txt}{date_txt}{warning}"
    else:
        message += "\n\n✅ No DMCA notices found today."

    print("\n── Slack message ──")
    print(message)
    post_to_slack(message)

    # Upload full CSV report to Slack
    csv_bytes = build_csv(all_results)
    upload_csv_to_slack(
        csv_bytes,
        filename=f"dmca_report_{today_fn}.csv",
        title=f"DMCA Monitor Full Report — {today}",
    )


if __name__ == "__main__":
    run()
