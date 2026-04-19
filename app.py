import os
import hashlib
import base64
import statistics
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextBox, LTChar, LTTextLine
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = "main"
CORS_ORIGIN = os.getenv("CORS_ORIGIN", f"https://{os.getenv('GITHUB_USER', '*')}.github.io")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_methods=["POST"],
    allow_headers=["*"],
)

_INDEX_HTML = Path("templates/index.html").read_text(encoding="utf-8")


def extract_pdf_metadata(pdf_bytes: bytes) -> dict:
    parser = PDFParser(BytesIO(pdf_bytes))
    doc = PDFDocument(parser)
    result = {"title": "", "author": ""}
    if doc.info:
        raw = doc.info[0]
        for key in ("title", "author"):
            val = raw.get(key.capitalize(), b"") or raw.get(key, b"")
            if isinstance(val, bytes):
                val = val.decode("utf-8", errors="replace")
            result[key] = str(val).strip()
    return result


def _join_lines(lines: list[str]) -> str:
    result = ""
    for line in lines:
        line = line.rstrip("\n")
        if not result:
            result = line
        elif result.endswith("-"):
            result = result[:-1] + line.lstrip()
        else:
            result = result.rstrip() + " " + line.lstrip()
    return result.strip()


def extract_blocks(pdf_bytes: bytes) -> list[dict]:
    laparams = LAParams(line_margin=0.5, word_margin=0.1, char_margin=2.0)
    blocks = []
    for page_layout in extract_pages(BytesIO(pdf_bytes), laparams=laparams):
        for element in page_layout:
            if isinstance(element, LTTextBox):
                lines, sizes = [], []
                for line in element:
                    if not isinstance(line, LTTextLine):
                        continue
                    line_text = line.get_text()
                    if not line_text.strip():
                        continue
                    lines.append(line_text)
                    sizes.extend(c.size for c in line if isinstance(c, LTChar))
                if lines and sizes:
                    blocks.append({"text": _join_lines(lines), "size": statistics.mean(sizes)})
    return blocks


def classify_blocks(blocks: list[dict]) -> list[dict]:
    if not blocks:
        return []
    median = statistics.median(b["size"] for b in blocks)
    result = []
    for b in blocks:
        s = b["size"]
        tag = "h1" if s >= median * 1.5 else "h2" if s >= median * 1.25 else "p"
        result.append({"tag": tag, "text": b["text"]})
    return result


def render_article(blocks: list[dict], title: str, author: str) -> str:
    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    rows = "\n".join(f"<{b['tag']}>{esc(b['text'])}</{b['tag']}>" for b in blocks)
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
{rows}
</div>
</body>
</html>"""


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
        # 422 = file already exists (sha required to update) → same content, just return URL
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

    meta = extract_pdf_metadata(pdf_bytes)
    title = meta["title"] or (file.filename or "document").removesuffix(".pdf")
    author = meta["author"]

    blocks = classify_blocks(extract_blocks(pdf_bytes))
    words = sum(len(b["text"].split()) for b in blocks)
    html = render_article(blocks, title, author)

    url = await push_to_github(f"{sha_id}.html", html)
    return JSONResponse({"url": url, "title": title, "words": words})
