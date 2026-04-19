PdfToHtmlLink# PDF → Kobo · Claude Code tutorial

## What you're building
Upload a PDF → get a `github.io` URL → paste into Instapaper → read on Kobo.

## Prerequisites
- Claude Code installed
- Python 3.10+
- GitHub repo with Pages enabled on `main`
- GitHub token with `repo` scope

---

## 1. Start Claude Code

```bash
mkdir pdfhost && cd pdfhost
claude
```

---

## 2. Describe the app

Paste this as your first prompt:

```
Build a FastAPI app that converts uploaded PDFs to clean readable HTML
and publishes each one to a GitHub Pages repo via the GitHub Contents API.

Stack: Python, FastAPI, pdfminer.six, httpx, Jinja2.

POST /upload
- Accepts a PDF file (multipart)
- Extracts text with pdfminer.six using layout-aware LAParams
- Detects headings by font size (>=1.5x median = h1, >=1.25x = h2)
- Extracts PDF metadata for title and author
- Renders a clean self-contained article.html (Georgia serif, no JS,
  single #article-content div — optimised for Instapaper's parser)
- Pushes the HTML to GitHub via Contents API as {sha256_12chars}.html
- If the file already exists on GitHub (409), return the existing URL
- Returns JSON: { url, title, words }
  where url = https://{GITHUB_USER}.github.io/{GITHUB_REPO}/{id}.html

GET /
- Serves a simple upload UI with drag-and-drop, progress indicator,
  and a copy button for the returned URL

Env vars: GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO
Include requirements.txt and a .env.example
```

---

## 3. Test locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your values
uvicorn app:app --reload
```

Open `http://localhost:8000`, upload a PDF, verify the `github.io` URL
renders correctly in the browser and that Instapaper picks up the title.

---

## 4. Deploy via Coolify

```bash
git init && git add . && git commit -m "init"
# push to your GitHub repo
```

In Coolify: add the repo as a new service, set the three env vars
(`GITHUB_TOKEN`, `GITHUB_USER`, `GITHUB_REPO`), deploy.

---

## Iterating

Just describe changes in plain English:

```
Add a rate limit of 10 uploads per IP per hour, in-memory, no Redis.
```

```
The Instapaper parser isn't finding the title — add og:title and
og:description meta tags to article.html.
```

Use **Escape** to stop Claude mid-task if it goes the wrong way.
Use **`/compact`** if the session gets long and slow.