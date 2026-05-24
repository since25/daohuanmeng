# DaoyuFan React Console MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local React + FastAPI + SQLite console that runs exactly one crawl job at a time, avoids duplicate URL fetches, optionally resolves final `share.feijipan.com` URLs, supports pause/resume/stop, and exports results.

**Architecture:** Split the current CLI crawler into reusable backend modules: parser, HTTP client, SQLite repository, single job runner, and FastAPI API. Build a React/Vite console that calls the API and renders job controls, progress, results, failures, and export buttons. Keep all execution local and serial; multi-job and parallel crawling are out of scope.

**Tech Stack:** Python 3.14, FastAPI, SQLite stdlib, unittest, React, Vite, TypeScript, browser fetch API.

---

## File Structure

- Create `backend/`: FastAPI backend package.
- Create `backend/parser.py`: Move article parser and redirect parser helpers out of `post_chain_crawler.py`.
- Create `backend/http_client.py`: Fetch article HTML and resolve download URLs through the configured proxy.
- Create `backend/db.py`: SQLite schema, migrations, and repository functions.
- Create `backend/job_runner.py`: Single-job crawl loop with pause/resume/stop.
- Create `backend/api.py`: FastAPI app and routes.
- Create `backend/models.py`: Small dataclasses or typed dict helpers shared by DB/API/job runner.
- Create `frontend/`: React/Vite console.
- Create `frontend/src/App.tsx`: Dashboard, tabs, forms, result table.
- Create `frontend/src/api.ts`: API client functions.
- Create `frontend/src/styles.css`: Work-focused console styling.
- Modify `requirements.txt`: Add FastAPI and ASGI server dependencies.
- Keep `post_chain_crawler.py`: CLI wrapper can call backend modules or stay as legacy fallback during migration.
- Add backend and frontend tests under `tests/` and `frontend/src/`.

## Task 1: Backend Parser Extraction

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/parser.py`
- Test: `tests/test_backend_parser.py`
- Modify: `post_chain_crawler.py`

- [ ] **Step 1: Write parser tests**

Create tests that prove:

```python
from backend.parser import parse_article_page, extract_html_redirect_url

def test_parse_article_page_takes_second_download_href():
    html = '''<h1 class="post-title mb-2 mb-lg-3">Booty徐莉芝 合集</h1>
    <div class="btn-group"><a href="https://daoyu.fan/goto?down=first">在线观看</a></div>
    <div class="btn-group"><a href="https://daoyu.fan/goto?down=second">压缩包</a></div>
    <a class="entry-page-next" href="/3203.html">下一篇</a>'''
    result = parse_article_page(html, "https://daoyu.fan/3199.html")
    assert result["title"] == "Booty徐莉芝 合集"
    assert result["download_href"] == "https://daoyu.fan/goto?down=second"
    assert result["next_url"] == "https://daoyu.fan/3203.html"

def test_extract_html_redirect_url_from_meta_refresh():
    html = '<meta http-equiv="refresh" content="0;url=https://share.feijipan.com/s/QOPtO6IO?code=6666">'
    assert extract_html_redirect_url(html) == "https://share.feijipan.com/s/QOPtO6IO?code=6666"
```

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_parser
```

Expected: fails because `backend.parser` does not exist.

- [ ] **Step 3: Implement parser module**

Move the parser behavior currently in `post_chain_crawler.py` into `backend/parser.py`:

```python
def parse_article_page(html: str, page_url: str) -> dict[str, object]:
    ...

def extract_html_redirect_url(html: str) -> str | None:
    ...
```

The parser must keep the existing behavior:

- `post-title mb-2 mb-lg-3` is the title source.
- only the second download href is returned.
- `entry-page-next` is resolved relative to the current page URL.
- final URL HTML redirects support `meta refresh` and `location.replace(...)`.

- [ ] **Step 4: Keep legacy CLI tests green**

Update `post_chain_crawler.py` to import the parser helpers from `backend.parser`, then run:

```bash
.venv/bin/python -m unittest tests.test_post_chain_crawler tests.test_backend_parser
```

Expected: all pass.

## Task 2: SQLite Repository

**Files:**
- Create: `backend/db.py`
- Test: `tests/test_backend_db.py`

- [ ] **Step 1: Write repository tests**

Cover schema creation, unique article URLs, resolver cache uniqueness, and job lifecycle persistence:

```python
from backend.db import Repository

def test_repository_reuses_article_by_unique_url(tmp_path):
    repo = Repository(tmp_path / "crawler.sqlite3")
    repo.initialize()
    first = repo.upsert_page(article_url="https://daoyu.fan/3199.html", title="A")
    second = repo.upsert_page(article_url="https://daoyu.fan/3199.html", title="B")
    assert first == second
    assert repo.get_page_by_url("https://daoyu.fan/3199.html")["title"] == "A"

def test_resolver_cache_reuses_download_href(tmp_path):
    repo = Repository(tmp_path / "crawler.sqlite3")
    repo.initialize()
    repo.save_resolver_cache("https://daoyu.fan/goto?down=x", "https://share.feijipan.com/s/a?code=6666", None)
    row = repo.get_resolver_cache("https://daoyu.fan/goto?down=x")
    assert row["resolved_download_url"].startswith("https://share.feijipan.com/")
```

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_db
```

Expected: fails because `backend.db` does not exist.

- [ ] **Step 3: Implement repository**

Use stdlib `sqlite3`. Add `Repository.initialize()` to create:

- `crawl_jobs`
- `post_pages`
- `resolver_cache`

Use `sqlite3.Row` for dict-like reads. Enforce:

- `post_pages.article_url unique`
- `resolver_cache.download_href unique`

- [ ] **Step 4: Verify DB tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_db
```

Expected: pass.

## Task 3: HTTP Client And Resolver

**Files:**
- Create: `backend/http_client.py`
- Test: `tests/test_backend_http_client.py`
- Modify: `post_chain_crawler.py`

- [ ] **Step 1: Write tests with mocked opener**

Test that:

- article fetch returns decoded HTML.
- final URL resolution returns `share.feijipan.com` from HTML redirect.
- opener does not pass `context` directly to `open()`.

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_http_client
```

Expected: fails because `backend.http_client` does not exist.

- [ ] **Step 3: Implement HTTP client**

Create:

```python
class HttpClient:
    def __init__(self, proxy: str | None, timeout: float = 30.0): ...
    def fetch_html(self, url: str) -> str: ...
    def resolve_final_url(self, url: str) -> str: ...
```

`resolve_final_url()` must:

- follow HTTP redirects.
- read the final HTML body.
- call `extract_html_redirect_url()`.
- fall back to `response.geturl()` if no HTML redirect is found.

- [ ] **Step 4: Verify existing crawler behavior**

Run:

```bash
.venv/bin/python post_chain_crawler.py --start "https://daoyu.fan/3199.html" --max-pages 1 --delay 0
```

Expected: output includes `resolved_download_url` beginning with `https://share.feijipan.com/`.

## Task 4: Single Job Runner

**Files:**
- Create: `backend/job_runner.py`
- Create: `backend/models.py`
- Test: `tests/test_backend_job_runner.py`

- [ ] **Step 1: Write job runner tests**

Cover:

- start creates a running job.
- runner saves parsed page.
- runner skips cached article URLs.
- resolver cache is reused.
- `resolve_final_url=False` skips resolver.
- pause moves `running -> pausing -> paused`.
- resume continues from `current_url`.
- stop moves to `stopped`.

Use fake fetch and fake resolver functions so tests are deterministic.

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_job_runner
```

Expected: fails because `backend.job_runner` does not exist.

- [ ] **Step 3: Implement runner**

Create a serial runner with methods:

```python
class JobRunner:
    def start(self, options: StartJobOptions) -> dict: ...
    def pause(self) -> dict: ...
    def resume(self) -> dict: ...
    def stop(self) -> dict: ...
    def tick_until_idle_for_tests(self) -> None: ...
```

The production API can run the loop in a background thread. Tests should use `tick_until_idle_for_tests()` or dependency injection to avoid timing flakiness.

- [ ] **Step 4: Verify runner tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_job_runner
```

Expected: pass.

## Task 5: FastAPI Backend

**Files:**
- Modify: `requirements.txt`
- Create: `backend/api.py`
- Create: `run_backend.py`
- Test: `tests/test_backend_api.py`

- [ ] **Step 1: Add dependencies**

Add to `requirements.txt`:

```text
fastapi>=0.110,<1
uvicorn>=0.29,<1
```

- [ ] **Step 2: Write API tests**

Use FastAPI `TestClient` to cover:

- `GET /api/health`
- `POST /api/job/start`
- rejecting start while running
- `POST /api/job/pause`
- `POST /api/job/resume`
- `POST /api/job/stop`
- `GET /api/results`
- export endpoints return JSON/CSV.

- [ ] **Step 3: Run red test**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_api
```

Expected: fails because API does not exist or dependencies are missing.

- [ ] **Step 4: Implement API**

`backend/api.py` should expose `create_app(db_path: str | None = None)`.

`run_backend.py` should run:

```python
import uvicorn
from backend.api import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
```

- [ ] **Step 5: Verify API tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_backend_api
```

Expected: pass.

## Task 6: React/Vite Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Scaffold minimal Vite app**

Create a React + TypeScript frontend with scripts:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "vite build",
    "test": "vitest run"
  }
}
```

- [ ] **Step 2: Build API client**

Create API functions:

```ts
export async function startJob(payload: StartJobPayload): Promise<JobState> { ... }
export async function pauseJob(): Promise<JobState> { ... }
export async function resumeJob(): Promise<JobState> { ... }
export async function stopJob(): Promise<JobState> { ... }
export async function getJob(): Promise<JobState> { ... }
export async function getResults(): Promise<ResultRow[]> { ... }
```

- [ ] **Step 3: Build dashboard UI**

`App.tsx` should render:

- left configuration panel.
- status counters.
- results table.
- errors/log panel.
- export buttons.

Controls map to API calls. Poll `GET /api/job` and `GET /api/results` while a job is running or paused.

- [ ] **Step 4: Add frontend verification**

Run:

```bash
cd frontend
npm install
npm run build
```

Expected: production build succeeds.

## Task 7: Local Run Scripts And Docs

**Files:**
- Create: `start_console.sh`
- Modify: `README.md`

- [ ] **Step 1: Add run script**

`start_console.sh` should:

- ensure `.venv`
- install Python requirements
- start FastAPI backend on `127.0.0.1:8765`
- start Vite frontend on `127.0.0.1:5173`
- print both URLs

- [ ] **Step 2: Update README**

Add console usage:

```bash
./start_mitm_proxy.sh
./start_console.sh
```

Then open:

```text
http://127.0.0.1:5173
```

- [ ] **Step 3: Verify docs commands**

Run the commands manually and confirm the UI loads.

## Task 8: End-To-End MVP Verification

**Files:**
- No new files unless bug fixes are required.

- [ ] **Step 1: Run backend tests**

```bash
.venv/bin/python -m unittest discover tests
```

Expected: all pass.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Run live crawl through the console**

Use the UI:

- start URL: `https://daoyu.fan/3199.html`
- max pages: `2`
- resolve final URL: on

Expected:

- two rows stored in SQLite.
- second download href is saved.
- resolved URL starts with `https://share.feijipan.com/`.
- running the same job again uses cached article URLs and resolver cache.

- [ ] **Step 4: Commit**

After tests and live verification pass:

```bash
git add .
git commit -m "feat: add local react crawler console"
```

- [ ] **Step 5: Push to GitHub**

Only after first-version testing is complete:

```bash
git push -u origin main
```

Remote:

```text
git@github.com:since25/daohuanmeng.git
```

## Self-Review

- Spec coverage: The plan covers React frontend, FastAPI backend, SQLite caching, single-job runner, pause/resume/stop, optional final URL resolution, exports, and no multi-job or parallel crawling.
- Placeholder scan: No TBD/TODO placeholders are intentionally left.
- Type consistency: Job state, result row, resolver cache, and API names are consistent across tasks.
