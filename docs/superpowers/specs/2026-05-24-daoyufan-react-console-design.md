# DaoyuFan React Console Design

## Goal

Upgrade the current command-line crawler into a local front-end/back-end separated web console for single-job crawling, SQLite caching, optional final URL resolution, progress visibility, and export.

## Scope

The first version is a local single-user tool. It does not support multiple active jobs, job queues, or parallel crawling. Those are intentionally out of scope and are not planned for later phases.

The next phase may add scheduled runs and cloud deployment, but the first version should keep all storage and execution local.

## Product Shape

The console uses the "operations console first" layout:

- Left panel: job configuration and controls.
- Main panel: current job state, progress counters, and result table.
- Bottom panel: failures, logs, and export actions.

The user can set:

- Start article URL.
- Maximum pages.
- Delay between pages.
- Whether to resolve the final `share.feijipan.com` URL.
- Whether cached article URLs should be skipped.
- Whether cached download URLs should be reused.

The user can control:

- Start.
- Pause.
- Resume.
- Stop.
- Export JSON.
- Export CSV.

## Architecture

```text
React Console
  -> FastAPI Backend
    -> Single Job Runner
      -> Crawler Core
      -> Final URL Resolver
      -> SQLite Repository
```

The existing parsing code remains the core behavior:

- `download_extractor.py` extracts download button data.
- `post_chain_crawler.py` currently contains article parsing, next-link detection, and final URL resolution behavior.

During implementation, this logic should be split into reusable backend modules instead of remaining as one CLI-centered script.

## Backend Modules

### API Layer

FastAPI exposes:

- `GET /api/health`
- `GET /api/job`
- `POST /api/job/start`
- `POST /api/job/pause`
- `POST /api/job/resume`
- `POST /api/job/stop`
- `GET /api/results`
- `GET /api/export/json`
- `GET /api/export/csv`

Only one job can be active. If a job is already `running` or `pausing`, `POST /api/job/start` rejects the request.

### Job Runner

The runner is single-threaded or uses one controlled background task. It processes one URL at a time.

State transitions:

```text
idle -> running
running -> pausing -> paused
paused -> running
running -> stopped
running -> completed
running -> failed
```

Pause is cooperative. When the user clicks Pause, the job moves to `pausing`; the current page is allowed to finish, then the runner saves `current_url` and enters `paused`.

Resume continues from `current_url`. SQLite deduplication still applies, so previously fetched URLs are not fetched again unless the job is configured to force refresh.

Stop ends the job after the current page finishes and marks the job `stopped`.

### Crawler Core

For each article page:

- Fetch HTML through the configured local proxy.
- Extract `post-title mb-2 mb-lg-3`.
- Extract only the second download button href.
- Extract `entry-page-next`.
- Save the parsed result.

The runner stops when:

- `max_pages` is reached.
- `next_url` is missing.
- `next_url` has already been visited in this job.
- The user pauses or stops the job.
- A non-recoverable backend or database error occurs.

Single-page fetch or parse errors are saved on that page record. They do not automatically fail the entire job unless the backend cannot continue safely.

### Final URL Resolver

Final URL resolution is controlled by a job option.

When enabled:

- Look up `download_href` in `resolver_cache`.
- If cached, reuse the cached final URL or cached error.
- If missing, request the `goto?down=...` URL through the local proxy.
- Follow normal HTTP redirects.
- If the final response contains `meta refresh` or `location.replace(...)`, extract that URL.
- Save the result as `resolved_download_url`.

When disabled:

- Save only `download_href`.
- Leave `resolved_download_url` empty.

### SQLite Repository

SQLite is the source of truth for jobs, pages, resolver cache, errors, and timestamps.

Proposed tables:

```text
crawl_jobs
- id integer primary key
- start_url text not null
- current_url text
- max_pages integer not null
- delay_seconds real not null
- resolve_final_url integer not null
- skip_cached_articles integer not null
- use_resolver_cache integer not null
- status text not null
- processed_count integer not null
- success_count integer not null
- error_count integer not null
- cache_hit_count integer not null
- created_at text not null
- started_at text
- finished_at text
- error text

post_pages
- id integer primary key
- job_id integer not null
- article_url text not null
- title text
- download_href text
- resolved_download_url text
- next_url text
- status text not null
- error text
- fetched_at text
- resolved_at text
- unique(article_url)

resolver_cache
- id integer primary key
- download_href text not null unique
- resolved_download_url text
- error text
- resolved_at text not null
```

The `post_pages.article_url` unique constraint prevents repeated page fetches. The `resolver_cache.download_href` unique constraint prevents repeated final URL resolution.

## Frontend

The React console should be work-focused and dense rather than a marketing page.

Views:

- Dashboard: active job form, controls, progress summary, results table, error panel.
- Results: searchable table with filters for fetched, cached, resolved, error.
- Cache: article cache and resolver cache overview, with force-refresh actions.
- Settings: proxy URL, default delay, default max pages.

The first implementation can keep these views in one route with tabs.

Dashboard controls:

- Start URL input.
- Max pages input.
- Delay input.
- Resolve final URL toggle.
- Skip cached article URLs toggle.
- Use resolver cache toggle.
- Start, Pause, Resume, Stop buttons.

Dashboard status:

- Job status.
- Current URL.
- Processed pages.
- Success count.
- Error count.
- Cache hit count.
- Last error.

Results table columns:

- Title.
- Article URL.
- Download href.
- Resolved URL.
- Next URL.
- Status.
- Error.
- Fetched at.

## Error Handling

Expected recoverable errors:

- HTTP 502.
- Timeout.
- Missing title.
- Missing second download href.
- Missing final URL in `goto` response.

These are saved on page or resolver records and shown in the UI.

Non-recoverable errors:

- SQLite write failure.
- Invalid database schema.
- Job runner invariant failure.

These move the job to `failed`.

## Testing Strategy

Backend tests:

- Parser extracts title, second download href, and next URL.
- Resolver extracts `share.feijipan.com` from `meta refresh` and `location.replace(...)`.
- Repository enforces article URL uniqueness.
- Repository enforces resolver cache uniqueness.
- Job runner skips cached article URLs.
- Job runner reuses resolver cache.
- Job runner honors `resolve_final_url = false`.
- Job runner pauses cooperatively after current page.
- Job runner resumes from `current_url`.
- API rejects starting a new job while one is running.

Frontend tests:

- Start form sends expected options.
- Resolve final URL toggle affects start payload.
- Pause/Resume buttons reflect job status.
- Results table renders success and error rows.
- Export buttons call the expected endpoints.

Manual verification:

- Run backend and frontend locally.
- Start at `https://daoyu.fan/3199.html` with max pages `2`.
- Confirm SQLite stores two article rows.
- Confirm the second download href is stored.
- Confirm final URLs are resolved only when the toggle is on.
- Confirm starting the same URL again uses cache.

## Phase Two Candidates

Phase two may include:

- Scheduled runs.
- Cloud deployment.
- Authentication for deployed mode.
- More robust retry policy.
- Optional HTML snapshot storage.
- Batch URL import.

Multi-job execution and parallel crawling remain out of scope.
