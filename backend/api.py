from __future__ import annotations

import csv
import io
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.db import Repository
from backend.job_runner import JobRunner
from backend.models import StartJobOptions


FetchHtmlCallable = Callable[[str, str | None], str]
ResolveUrlCallable = Callable[[str, str | None], str]


class StartJobRequest(BaseModel):
    start_url: str
    max_pages: int = Field(default=25, ge=1)
    delay_seconds: float = Field(default=0.5, ge=0)
    proxy: str | None = "http://127.0.0.1:8080"
    resolve_final_url: bool = True
    skip_cached_articles: bool = True
    use_resolver_cache: bool = True


def create_app(
    db_path: str | Path | None = None,
    *,
    auto_run: bool = True,
    fetch_html: FetchHtmlCallable | None = None,
    resolve_url: ResolveUrlCallable | None = None,
) -> FastAPI:
    database_path = Path(db_path) if db_path is not None else _default_db_path()
    repository = Repository(database_path)
    repository.initialize()
    runner = JobRunner(repository, fetch_html=fetch_html, resolve_url=resolve_url)
    worker_lock = threading.Lock()

    app = FastAPI(title="DaoyuFan Crawler Console")
    app.state.repository = repository
    app.state.runner = runner

    def run_until_idle_in_background() -> None:
        if not auto_run:
            return

        def worker() -> None:
            with worker_lock:
                runner.tick_until_idle_for_tests()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/job")
    def get_job() -> dict[str, Any]:
        job = repository.get_active_job() or repository.get_latest_job()
        if job is None:
            return {"status": "idle"}
        return _serialize_job(job)

    @app.post("/api/job/start")
    def start_job(payload: StartJobRequest) -> dict[str, Any]:
        try:
            state = runner.start(
                StartJobOptions(
                    start_url=payload.start_url,
                    max_pages=payload.max_pages,
                    delay_seconds=payload.delay_seconds,
                    proxy=payload.proxy,
                    resolve_final_url=payload.resolve_final_url,
                    skip_cached_articles=payload.skip_cached_articles,
                    use_resolver_cache=payload.use_resolver_cache,
                )
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        run_until_idle_in_background()
        return state

    @app.post("/api/job/pause")
    def pause_job() -> dict[str, Any]:
        try:
            return runner.pause()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/job/resume")
    def resume_job() -> dict[str, Any]:
        try:
            state = runner.resume()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        run_until_idle_in_background()
        return state

    @app.post("/api/job/stop")
    def stop_job() -> dict[str, Any]:
        try:
            return runner.stop()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/results")
    def get_results() -> list[dict[str, Any]]:
        return [_serialize_row(row) for row in repository.list_pages()]

    @app.get("/api/export/json")
    def export_json() -> list[dict[str, Any]]:
        return get_results()

    @app.get("/api/export/csv")
    def export_csv() -> Response:
        rows = get_results()
        output = io.StringIO()
        fieldnames = [
            "article_url",
            "title",
            "download_href",
            "resolved_download_url",
            "next_url",
            "status",
            "error",
            "fetched_at",
            "resolved_at",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="daoyufan-results.csv"'},
        )

    return app


def _default_db_path() -> Path:
    return Path(tempfile.gettempdir()) / "daoyufan-console.sqlite3"


def _serialize_job(row) -> dict[str, Any]:
    state = _serialize_row(row)
    state["resolve_final_url"] = bool(state["resolve_final_url"])
    state["skip_cached_articles"] = bool(state["skip_cached_articles"])
    state["use_resolver_cache"] = bool(state["use_resolver_cache"])
    return state


def _serialize_row(row) -> dict[str, Any]:
    return dict(row)
