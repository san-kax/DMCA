import asyncio
import json
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from checker import _check_url_with_browser
from playwright.async_api import async_playwright
from counter_notice import generate_counter_notice

load_dotenv()

app = FastAPI(title="DMCA Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request / Response Models ---

class CheckRequest(BaseModel):
    urls: List[str]
    site_name: str = ""


class CompanyInfo(BaseModel):
    name: Optional[str] = ""
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""


class NoticeData(BaseModel):
    id: Optional[int] = None
    lumen_url: Optional[str] = ""
    title: Optional[str] = ""
    type: Optional[str] = "DMCA"
    content: Optional[str] = ""
    recipient_name: Optional[str] = "Google LLC"
    affected_url: Optional[str] = ""
    source: Optional[str] = "google_search"


class CounterNoticeRequest(BaseModel):
    notice: NoticeData
    company: CompanyInfo


# --- Routes ---

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")


@app.post("/api/check")
async def check_urls(request: CheckRequest):
    """
    Stream results via Server-Sent Events.
    Each URL is checked and emitted immediately as it completes.
    Frontend receives results one-by-one instead of waiting for all.
    """
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    api_key = os.getenv("SERPAPI_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="SERPAPI_KEY not configured.")

    urls = [u.strip() for u in request.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")

    async def event_stream():
        BATCH_SIZE = 2
        completed = 0
        total = len(urls)

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

            for i in range(0, total, BATCH_SIZE):
                batch = urls[i:i + BATCH_SIZE]
                batch_results = await asyncio.gather(
                    *[_check_url_with_browser(url, browser) for url in batch]
                )
                for result in batch_results:
                    completed += 1
                    payload = json.dumps({
                        "type": "result",
                        "data": result,
                        "completed": completed,
                        "total": total,
                    })
                    yield f"data: {payload}\n\n"

                if i + BATCH_SIZE < total:
                    await asyncio.sleep(1)

            await browser.close()

        # Signal completion
        yield f"data: {json.dumps({'type': 'done', 'total': total})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/counter-notice")
async def counter_notice(request: CounterNoticeRequest):
    notice_dict = request.notice.model_dump()
    company_dict = request.company.model_dump()

    pdf_bytes = generate_counter_notice(notice_dict, company_dict)

    notice_id = notice_dict.get("id") or "notice"
    filename = f"counter_notice_{notice_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
