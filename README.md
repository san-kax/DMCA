# DMCA Monitor

Checks URLs for Google indexing status and DMCA/Lumen notices using real browser searches.

## Run with Docker (recommended for team use)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Open a terminal in this folder and run:

```
docker build -t dmca-monitor .
docker run -p 8000:8000 dmca-monitor
```

3. Open http://localhost:8000

That's it. No Python or Playwright installation needed.

## Run locally (requires Python 3.10+)

```
pip install -r requirements.txt
playwright install chromium
python main.py
```

Open http://localhost:8000
