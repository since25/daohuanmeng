from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.db import Repository, _utc_now
from backend.http_client import HttpClient
from backend.models import StartJobOptions
from backend.parser import parse_article_page


FetchHtmlCallable = Callable[[str, str | None], str]
ResolveUrlCallable = Callable[[str, str | None], str]


class JobRunner:
    def __init__(
        self,
        repository: Repository,
        *,
        fetch_html: FetchHtmlCallable | None = None,
        resolve_url: ResolveUrlCallable | None = None,
    ):
        self.repository = repository
        self._fetch_html = fetch_html
        self._resolve_url = resolve_url
        self._job_options: dict[int, StartJobOptions] = {}
        self._seen_urls: dict[int, set[str]] = {}

    def start(self, options: StartJobOptions) -> dict[str, Any]:
        self.repository.initialize()
        active_job = self.repository.get_active_job()
        if active_job is not None:
            raise RuntimeError("an active job already exists")

        created = self.repository.create_job(
            start_url=options.start_url,
            max_pages=options.max_pages,
            delay_seconds=options.delay_seconds,
            resolve_final_url=options.resolve_final_url,
            skip_cached_articles=options.skip_cached_articles,
            use_resolver_cache=options.use_resolver_cache,
        )
        self._job_options[created["id"]] = options
        self._seen_urls[created["id"]] = set()
        running = self.repository.update_job(
            created["id"],
            status="running",
            current_url=options.start_url,
            started_at=_utc_now(),
            error=None,
        )
        return self._serialize_job(running)

    def pause(self) -> dict[str, Any]:
        job = self._require_active_job()
        if job["status"] == "running":
            job = self.repository.update_job(job["id"], status="pausing")
        return self._serialize_job(job)

    def resume(self) -> dict[str, Any]:
        job = self._require_active_job()
        if job["status"] != "paused":
            raise RuntimeError("job is not paused")
        resumed = self.repository.update_job(job["id"], status="running")
        return self._serialize_job(resumed)

    def stop(self) -> dict[str, Any]:
        job = self._require_active_job()
        stopped = self.repository.update_job(
            job["id"],
            status="stopped",
            finished_at=_utc_now(),
        )
        return self._serialize_job(stopped)

    def tick_until_idle_for_tests(self) -> None:
        while True:
            job = self.repository.get_active_job()
            if job is None:
                return
            if job["status"] == "paused":
                return
            if job["status"] == "pending":
                self.repository.update_job(
                    job["id"],
                    status="running",
                    current_url=job["current_url"] or job["start_url"],
                    started_at=job["started_at"] or _utc_now(),
                    error=None,
                )
                continue
            if job["status"] not in {"running", "pausing"}:
                return
            if job["processed_count"] >= job["max_pages"]:
                self.repository.update_job(
                    job["id"],
                    status="completed",
                    current_url=None,
                    finished_at=_utc_now(),
                    error=None,
                )
                continue
            self._process_current_url(job)

    def _process_current_url(self, job) -> None:
        job_id = job["id"]
        options = self._get_job_options(job)
        current_url = job["current_url"] or job["start_url"]
        seen_urls = self._seen_urls.setdefault(job_id, set())

        if current_url is None:
            self.repository.update_job(
                job_id,
                status="completed",
                current_url=None,
                finished_at=_utc_now(),
                error=None,
            )
            return

        if current_url in seen_urls:
            self.repository.update_job(
                job_id,
                status="completed",
                current_url=None,
                finished_at=_utc_now(),
                error=None,
            )
            return

        cached_page = self.repository.get_page_by_url(current_url)
        if cached_page is not None and options.skip_cached_articles:
            cached_error = cached_page["error"]
            next_url = cached_page["next_url"]
            self._finish_step(
                job,
                current_url=current_url,
                next_url=next_url,
                error_message=cached_error,
                processed_delta=1,
                success_delta=0 if cached_error else 1,
                error_delta=1 if cached_error else 0,
                cache_hit_delta=1,
            )
            return

        try:
            html = self._fetch_page_html(current_url, options.proxy)
            parsed = parse_article_page(html, current_url)
            resolved_download_url = None
            error_message = None
            status = "fetched"
            resolved_at = None

            if parsed["download_href"] and options.resolve_final_url:
                resolved_at = _utc_now()
                resolved_download_url, error_message = self._resolve_download_url(
                    parsed["download_href"],
                    options,
                )
                if error_message:
                    status = "error"
                elif resolved_download_url:
                    status = "resolved"

            self.repository.upsert_page(
                job_id=job_id,
                article_url=current_url,
                title=parsed["title"],
                download_href=parsed["download_href"],
                resolved_download_url=resolved_download_url,
                next_url=parsed["next_url"],
                status=status,
                error=error_message,
                fetched_at=_utc_now(),
                resolved_at=resolved_at,
            )
            self._finish_step(
                job,
                current_url=current_url,
                next_url=parsed["next_url"],
                error_message=error_message,
                processed_delta=1,
                success_delta=0 if error_message else 1,
                error_delta=1 if error_message else 0,
                cache_hit_delta=0,
            )
        except Exception as exc:
            error_message = str(exc)
            self.repository.upsert_page(
                job_id=job_id,
                article_url=current_url,
                status="error",
                error=error_message,
                fetched_at=_utc_now(),
            )
            self._finish_step(
                job,
                current_url=current_url,
                next_url=None,
                error_message=error_message,
                processed_delta=1,
                success_delta=0,
                error_delta=1,
                cache_hit_delta=0,
            )

    def _finish_step(
        self,
        job,
        *,
        current_url: str,
        next_url: str | None,
        error_message: str | None,
        processed_delta: int,
        success_delta: int,
        error_delta: int,
        cache_hit_delta: int,
    ) -> None:
        job_id = job["id"]
        seen_urls = self._seen_urls.setdefault(job_id, set())
        seen_urls.add(current_url)

        safe_next_url = next_url
        if safe_next_url in seen_urls:
            safe_next_url = None

        next_processed_count = job["processed_count"] + processed_delta

        if error_message and safe_next_url is None:
            self.repository.update_job(
                job_id,
                status="failed",
                current_url=None,
                error=error_message,
                finished_at=_utc_now(),
                processed_delta=processed_delta,
                success_delta=success_delta,
                error_delta=error_delta,
                cache_hit_delta=cache_hit_delta,
            )
            return

        if job["status"] == "pausing":
            self.repository.update_job(
                job_id,
                status="paused",
                current_url=safe_next_url,
                error=error_message,
                processed_delta=processed_delta,
                success_delta=success_delta,
                error_delta=error_delta,
                cache_hit_delta=cache_hit_delta,
            )
            return

        if next_processed_count >= job["max_pages"] or safe_next_url is None:
            self.repository.update_job(
                job_id,
                status="completed",
                current_url=None,
                error=error_message,
                finished_at=_utc_now(),
                processed_delta=processed_delta,
                success_delta=success_delta,
                error_delta=error_delta,
                cache_hit_delta=cache_hit_delta,
            )
            return

        self.repository.update_job(
            job_id,
            status="running",
            current_url=safe_next_url,
            error=error_message,
            processed_delta=processed_delta,
            success_delta=success_delta,
            error_delta=error_delta,
            cache_hit_delta=cache_hit_delta,
        )

    def _resolve_download_url(
        self,
        download_href: str,
        options: StartJobOptions,
    ) -> tuple[str | None, str | None]:
        if options.use_resolver_cache:
            cached = self.repository.get_resolver_cache(download_href)
            if cached is not None:
                return cached["resolved_download_url"], cached["error"]

        try:
            resolved_download_url = self._resolve_final_url(download_href, options.proxy)
        except Exception as exc:
            error_message = str(exc)
            self.repository.save_resolver_cache(download_href, None, error_message)
            return None, error_message

        self.repository.save_resolver_cache(download_href, resolved_download_url, None)
        return resolved_download_url, None

    def _fetch_page_html(self, url: str, proxy: str | None) -> str:
        if self._fetch_html is not None:
            return self._fetch_html(url, proxy)
        return HttpClient(proxy).fetch_html(url)

    def _resolve_final_url(self, url: str, proxy: str | None) -> str:
        if self._resolve_url is not None:
            return self._resolve_url(url, proxy)
        return HttpClient(proxy).resolve_final_url(url)

    def _require_active_job(self):
        job = self.repository.get_active_job()
        if job is None:
            raise RuntimeError("no active job")
        return job

    def _get_job_options(self, job) -> StartJobOptions:
        cached = self._job_options.get(job["id"])
        if cached is not None:
            return cached

        options = StartJobOptions(
            start_url=job["start_url"],
            max_pages=job["max_pages"],
            delay_seconds=job["delay_seconds"],
            proxy=None,
            resolve_final_url=bool(job["resolve_final_url"]),
            skip_cached_articles=bool(job["skip_cached_articles"]),
            use_resolver_cache=bool(job["use_resolver_cache"]),
        )
        self._job_options[job["id"]] = options
        return options

    def _serialize_job(self, row) -> dict[str, Any]:
        state = dict(row)
        state["resolve_final_url"] = bool(state["resolve_final_url"])
        state["skip_cached_articles"] = bool(state["skip_cached_articles"])
        state["use_resolver_cache"] = bool(state["use_resolver_cache"])
        return state
