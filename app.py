import os
import hashlib
import base64
from pathlib import Path

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = "main"
CORS_ORIGIN = os.getenv("CORS_ORIGIN", f"https://{os.getenv('GITHUB_USER', '*')}.github.io")
INSTAPARSER_API_KEY = os.getenv("INSTAPARSER_API_KEY")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_methods=["POST"],
    allow_headers=["*"],
)

_INDEX_HTML = Path("templates/index.html").read_text(encoding="utf-8")


def render_article(html_body: str, title: str, author: str) -> str:
    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(author)}">
<title>{esc(title)}</title>
<style>
  body{{font-family:Georgia,serif;max-width:780px;margin:2em auto;padding:0 1.5em;line-height:1.7;color:#222}}
  h1{{font-size:1.8em;margin-top:1.5em}}
  h2{{font-size:1.4em;margin-top:1.2em}}
  p{{margin:.8em 0}}
</style>
</head>
<body>
<div id="article-content">
{html_body}
</div>
</body>
</html>"""


async def parse_pdf(pdf_bytes: bytes, filename: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://www.instaparser.com/api/1/pdf",
            headers={"Authorization": f"Bearer {INSTAPARSER_API_KEY}"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            data={"output": "html"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Instaparser error {resp.status_code}: {resp.text}")
    return resp.json()


async def push_to_github(filename: str, html: str) -> str:
    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{filename}"
    pages_url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    payload = {"message": f"Add {filename}", "content": base64.b64encode(html.encode()).decode(), "branch": GITHUB_BRANCH}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(api_url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            return pages_url
        if resp.status_code == 422:
            return pages_url
        raise HTTPException(status_code=502, detail=f"GitHub API {resp.status_code}: {resp.text}")


@app.get("/", response_class=HTMLResponse)
async def index():
    return _INDEX_HTML


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()
    sha_id = hashlib.sha256(pdf_bytes).hexdigest()[:12]

    data = await parse_pdf(pdf_bytes, file.filename)

    title = data.get("title") or file.filename.removesuffix(".pdf")
    author = data.get("author", "")
    words = data.get("words", 0)
    html_body = data.get("html", "")

    html = render_article(html_body, title, author)
    url = await push_to_github(f"{sha_id}.html", html)
    return JSONResponse({"url": url, "title": title, "words": words})
