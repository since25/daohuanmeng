from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, fields, replace
from typing import Any

from backend.db import Repository, _utc_now
from backend.http_client import HttpClient
from backend.models import StartJobOptions
from backend.nikki import NikkiProxyRotator
from backend.parser import parse_article_page
from rewrite_rules import rewrite_url


FetchHtmlCallable = Callable[[str, str | None], str]
ResolveUrlCallable = Callable[[str, str | None], str]
SleepCallable = Callable[[float], None]
RotateResolverProxyCallable = Callable[[], str]

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(
        self,
        repository: Repository,
        *,
        fetch_html: FetchHtmlCallable | None = None,
        resolve_url: ResolveUrlCallable | None = None,
        sleep: SleepCallable | None = None,
        rotate_resolver_proxy: RotateResolverProxyCallable | None = None,
        retry_attempts: int = 3,
    ):
        self.repository = repository
        self._fetch_html = fetch_html
        self._resolve_url = resolve_url
        self._sleep = sleep or time.sleep
        self._rotate_resolver_proxy = rotate_resolver_proxy
        self._retry_attempts = retry_attempts
        self._job_options: dict[int, StartJobOptions] = {}
        self._nikki_rotators: dict[tuple[str, str, str], NikkiProxyRotator] = {}
        self._seen_urls: dict[int, set[str]] = {}
        self._prepared_article_proxies: dict[int, dict[str, str | None]] = {}

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
            options_json=self._serialize_options(options),
        )
        self._job_options[created["id"]] = options
        self._seen_urls[created["id"]] = set()
        logger.info("job %s starting at %s", created["id"], options.start_url)
        running = self.repository.update_job(
            created["id"],
            status="running",
            current_url=options.start_url,
            started_at=_utc_now(),
            error=None,
        )
        return self._serialize_job(running)

    def start_batch(
        self,
        options: StartJobOptions,
        items: list[dict[str, object]],
    ) -> dict[str, Any]:
        self.repository.initialize()
        active_job = self.repository.get_active_job()
        if active_job is not None:
            raise RuntimeError("an active job already exists")
        if not items:
            raise RuntimeError("batch items are required")

        batch_options = replace(
            options,
            start_url="batch://manual-import",
            max_pages=len(items),
            skip_cached_articles=True if options.skip_cached_articles else False,
        )
        created = self.repository.create_job(
            start_url=batch_options.start_url,
            max_pages=batch_options.max_pages,
            delay_seconds=batch_options.delay_seconds,
            resolve_final_url=batch_options.resolve_final_url,
            skip_cached_articles=batch_options.skip_cached_articles,
            use_resolver_cache=batch_options.use_resolver_cache,
            job_type="batch",
            options_json=self._serialize_options(batch_options),
        )
        self.repository.add_batch_items(created["id"], items)
        self._job_options[created["id"]] = batch_options
        self._seen_urls[created["id"]] = set()
        first = self.repository.get_next_batch_item(created["id"])
        running = self.repository.update_job(
            created["id"],
            status="running",
            current_url=first["article_url"] if first is not None else None,
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
            if job["job_type"] == "batch":
                self._process_next_batch_item(job)
                continue
            self._process_current_url(job)

    def _process_next_batch_item(self, job) -> None:
        job_id = job["id"]
        options = self._get_job_options(job)
        item = self.repository.get_next_batch_item(job_id)
        if item is None:
            self.repository.update_job(
                job_id,
                status="completed",
                current_url=None,
                finished_at=_utc_now(),
            )
            return

        current_url = item["article_url"]
        cached_page = self.repository.get_page_by_url(current_url)
        if (
            cached_page is not None
            and options.skip_cached_articles
            and self._cached_page_is_complete(cached_page, options)
        ):
            self.repository.update_batch_item(item["id"], status="skipped")
            self._finish_batch_step(
                job,
                item_position=item["position"],
                current_url=current_url,
                error_message=None,
                processed_delta=1,
                success_delta=1,
                error_delta=0,
                cache_hit_delta=1,
                sleep_after_step=False,
            )
            return

        try:
            article_proxy = self._article_proxy_for_url(job_id, current_url, options)
            article_request_url = self._article_request_url(current_url, options)
            logger.info("batch job %s fetching %s", job_id, current_url)
            html = self._fetch_page_html(article_request_url, options, article_proxy)
            parsed = parse_article_page(html, current_url)
            resolved_download_url = None
            error_message = None
            status = "fetched"
            resolved_at = None

            if not parsed["title"] and item["title"]:
                parsed["title"] = item["title"]

            if options.resolve_final_url and not parsed["download_href"]:
                error_message = "download href not found"
                status = "error"
            elif parsed["download_href"] and options.resolve_final_url:
                self.repository.upsert_page(
                    job_id=job_id,
                    article_url=current_url,
                    title=parsed["title"],
                    download_href=parsed["download_href"],
                    resolved_download_url=None,
                    next_url=parsed["next_url"],
                    status="resolving",
                    error=None,
                    fetched_at=_utc_now(),
                    resolved_at=None,
                )
                resolved_at = _utc_now()
                resolved_download_url, error_message = self._resolve_download_url(
                    parsed["download_href"],
                    options,
                    article_proxy,
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
            self.repository.update_batch_item(
                item["id"],
                status="error" if error_message else "done",
                error=error_message,
            )
            self._finish_batch_step(
                job,
                item_position=item["position"],
                current_url=current_url,
                error_message=error_message,
                processed_delta=1,
                success_delta=0 if error_message else 1,
                error_delta=1 if error_message else 0,
                cache_hit_delta=0,
            )
        except Exception as exc:
            error_message = str(exc)
            logger.exception("batch job %s failed fetching %s", job_id, current_url)
            self.repository.upsert_page(
                job_id=job_id,
                article_url=current_url,
                title=item["title"],
                status="error",
                error=error_message,
                fetched_at=_utc_now(),
            )
            self.repository.update_batch_item(item["id"], status="error", error=error_message)
            self._finish_batch_step(
                job,
                item_position=item["position"],
                current_url=current_url,
                error_message=error_message,
                processed_delta=1,
                success_delta=0,
                error_delta=1,
                cache_hit_delta=0,
            )

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
        if (
            cached_page is not None
            and options.skip_cached_articles
            and self._cached_page_is_complete(cached_page, options)
        ):
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
            article_proxy = self._article_proxy_for_url(job_id, current_url, options)
            article_request_url = self._article_request_url(current_url, options)
            if article_request_url != current_url:
                logger.info(
                    "job %s fetching %s via worker %s",
                    job_id,
                    current_url,
                    article_request_url,
                )
            else:
                logger.info("job %s fetching %s", job_id, current_url)
            html = self._fetch_page_html(article_request_url, options, article_proxy)
            parsed = parse_article_page(html, current_url)
            resolved_download_url = None
            error_message = None
            status = "fetched"
            resolved_at = None

            if options.resolve_final_url and not parsed["download_href"]:
                error_message = "download href not found"
                status = "error"
            elif parsed["download_href"] and options.resolve_final_url:
                self.repository.upsert_page(
                    job_id=job_id,
                    article_url=current_url,
                    title=parsed["title"],
                    download_href=parsed["download_href"],
                    resolved_download_url=None,
                    next_url=parsed["next_url"],
                    status="resolving",
                    error=None,
                    fetched_at=_utc_now(),
                    resolved_at=None,
                )
                logger.info("job %s resolving %s", job_id, parsed["download_href"])
                resolved_at = _utc_now()
                resolved_download_url, error_message = self._resolve_download_url(
                    parsed["download_href"],
                    options,
                    article_proxy,
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
            logger.info("job %s saved %s as %s", job_id, current_url, status)
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
            logger.exception("job %s failed fetching %s", job_id, current_url)
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
        self._sleep_between_pages(
            job_id=job_id,
            options=self._get_job_options(job),
            next_url=safe_next_url,
        )

    def _finish_batch_step(
        self,
        job,
        *,
        item_position: int,
        current_url: str,
        error_message: str | None,
        processed_delta: int,
        success_delta: int,
        error_delta: int,
        cache_hit_delta: int,
        sleep_after_step: bool = True,
    ) -> None:
        job_id = job["id"]
        next_item = self.repository.peek_next_batch_item_after(job_id, item_position)
        next_url = next_item["article_url"] if next_item is not None else None
        next_processed_count = job["processed_count"] + processed_delta

        if job["status"] == "pausing":
            self.repository.update_job(
                job_id,
                status="paused",
                current_url=next_url,
                error=error_message,
                processed_delta=processed_delta,
                success_delta=success_delta,
                error_delta=error_delta,
                cache_hit_delta=cache_hit_delta,
            )
            return

        if next_processed_count >= job["max_pages"] or next_url is None:
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
            current_url=next_url,
            error=error_message,
            processed_delta=processed_delta,
            success_delta=success_delta,
            error_delta=error_delta,
            cache_hit_delta=cache_hit_delta,
        )
        if sleep_after_step:
            self._sleep_between_pages(
                job_id=job_id,
                options=self._get_job_options(job),
                next_url=next_url,
            )

    def _resolve_download_url(
        self,
        download_href: str,
        options: StartJobOptions,
        proxy: str | None,
    ) -> tuple[str | None, str | None]:
        if options.use_resolver_cache:
            cached = self.repository.get_resolver_cache(download_href)
            if cached is not None and cached["resolved_download_url"]:
                return cached["resolved_download_url"], cached["error"]

        resolver_url = self._resolver_request_url(download_href, options)
        current_proxy = proxy
        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                resolved_download_url = self._resolve_final_url(resolver_url, current_proxy)
                self.repository.save_resolver_cache(download_href, resolved_download_url, None)
                return resolved_download_url, None
            except Exception as exc:
                last_error = exc
                if attempt >= self._retry_attempts:
                    break
                logger.warning(
                    "resolve attempt %s/%s failed for %s: %s",
                    attempt,
                    self._retry_attempts,
                    resolver_url,
                    exc,
                )
                if options.resolver_proxy:
                    current_proxy = self._prepare_article_proxy(options)
                elif options.delay_seconds > 0:
                    self._sleep(options.delay_seconds)

        error_message = str(last_error or RuntimeError("resolve failed"))
        logger.warning("resolver failed for %s: %s", download_href, error_message)
        return None, error_message

    def resolve_page(self, page_id: int, options: StartJobOptions):
        page = self.repository.get_page_by_id(page_id)
        if page is None:
            raise RuntimeError("page not found")
        if not page["download_href"]:
            raise RuntimeError("download href not found")

        article_proxy = self._prepare_article_proxy(options)
        self.repository.upsert_page(
            job_id=page["job_id"],
            article_url=page["article_url"],
            title=page["title"],
            download_href=page["download_href"],
            resolved_download_url=None,
            next_url=page["next_url"],
            status="resolving",
            error=None,
            fetched_at=page["fetched_at"],
            resolved_at=None,
        )
        resolved_at = _utc_now()
        no_cache_options = replace(options, use_resolver_cache=False)
        resolved_download_url, error_message = self._resolve_download_url(
            page["download_href"],
            no_cache_options,
            article_proxy,
        )
        return self.repository.upsert_page(
            job_id=page["job_id"],
            article_url=page["article_url"],
            title=page["title"],
            download_href=page["download_href"],
            resolved_download_url=resolved_download_url,
            next_url=page["next_url"],
            status="error" if error_message else "resolved",
            error=error_message,
            fetched_at=page["fetched_at"],
            resolved_at=resolved_at,
        )

    def _fetch_page_html(self, url: str, options: StartJobOptions, proxy: str | None) -> str:
        return self._with_retries(
            "fetch",
            url,
            options,
            lambda: self._fetch_html(url, proxy)
            if self._fetch_html is not None
            else HttpClient(proxy).fetch_html(url),
        )

    def _resolve_final_url(self, url: str, proxy: str | None) -> str:
        if self._resolve_url is not None:
            return self._resolve_url(url, proxy)
        return HttpClient(proxy).resolve_final_url(url)

    def _resolver_request_url(self, download_href: str, options: StartJobOptions) -> str:
        if not options.rewrite_resolver_url:
            return download_href
        return rewrite_url(download_href) or download_href

    def _article_request_url(self, article_url: str, options: StartJobOptions) -> str:
        if not options.rewrite_resolver_url:
            return article_url
        return rewrite_url(article_url) or article_url

    def _article_proxy_for_url(
        self,
        job_id: int,
        article_url: str,
        options: StartJobOptions,
    ) -> str | None:
        prepared = self._prepared_article_proxies.setdefault(job_id, {})
        if article_url in prepared:
            return prepared.pop(article_url)
        return self._prepare_article_proxy(options)

    def _prepare_next_article_proxy(
        self,
        job_id: int,
        article_url: str,
        options: StartJobOptions,
    ) -> None:
        prepared = self._prepared_article_proxies.setdefault(job_id, {})
        if article_url not in prepared:
            prepared[article_url] = self._prepare_article_proxy(options)

    def _prepare_article_proxy(self, options: StartJobOptions) -> str | None:
        selected_node = self._prepare_resolver_proxy(options)
        if selected_node:
            logger.info("selected article proxy node: %s", selected_node)
        return options.resolver_proxy or options.proxy

    def _prepare_resolver_proxy(self, options: StartJobOptions) -> str | None:
        if not options.resolver_proxy:
            return None
        if self._rotate_resolver_proxy is not None:
            return self._rotate_resolver_proxy()
        if not (
            options.nikki_api_base
            and options.nikki_proxy_group
        ):
            return None

        key = (
            options.nikki_api_base,
            options.nikki_api_secret or "",
            options.nikki_proxy_group,
        )
        rotator = self._nikki_rotators.get(key)
        if rotator is None:
            rotator = NikkiProxyRotator(
                api_base=options.nikki_api_base,
                api_secret=options.nikki_api_secret,
                proxy_group=options.nikki_proxy_group,
                delay_test_url=options.nikki_delay_test_url,
                delay_timeout_ms=options.nikki_delay_timeout_ms,
            )
            self._nikki_rotators[key] = rotator
        return rotator.prepare_next_node()

    def _cached_page_is_complete(self, cached_page, options: StartJobOptions) -> bool:
        if cached_page["status"] == "error" or cached_page["error"]:
            return False
        if not options.resolve_final_url:
            return True
        return bool(cached_page["resolved_download_url"])

    def _with_retries(
        self,
        action: str,
        url: str,
        options: StartJobOptions,
        operation: Callable[[], str],
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt >= self._retry_attempts:
                    break
                logger.warning(
                    "%s attempt %s/%s failed for %s: %s",
                    action,
                    attempt,
                    self._retry_attempts,
                    url,
                    exc,
                )
                if options.delay_seconds > 0:
                    self._sleep(options.delay_seconds)
        raise last_error or RuntimeError(f"{action} failed")

    def _sleep_between_pages(
        self,
        *,
        job_id: int,
        options: StartJobOptions,
        next_url: str | None,
    ) -> None:
        if next_url and options.delay_seconds > 0:
            started_at = time.monotonic()
            try:
                self._prepare_next_article_proxy(job_id, next_url, options)
            except Exception as exc:
                logger.warning(
                    "preparing proxy for next page %s failed: %s",
                    next_url,
                    exc,
                )
            elapsed = time.monotonic() - started_at
            remaining_delay = max(0.0, options.delay_seconds - elapsed)
            logger.info("sleeping %.2fs before next page %s", options.delay_seconds, next_url)
            if remaining_delay > 0:
                self._sleep(remaining_delay)

    def _require_active_job(self):
        job = self.repository.get_active_job()
        if job is None:
            raise RuntimeError("no active job")
        return job

    def _get_job_options(self, job) -> StartJobOptions:
        cached = self._job_options.get(job["id"])
        if cached is not None:
            return cached

        options = self._deserialize_options(job) or StartJobOptions(
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

    def _serialize_options(self, options: StartJobOptions) -> str:
        return json.dumps(asdict(options), ensure_ascii=False)

    def _deserialize_options(self, job) -> StartJobOptions | None:
        try:
            raw = job["options_json"]
        except (IndexError, KeyError):
            return None
        if not raw:
            return None

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None

        allowed_fields = {field.name for field in fields(StartJobOptions)}
        filtered = {key: value for key, value in parsed.items() if key in allowed_fields}
        try:
            return StartJobOptions(**filtered)
        except TypeError:
            return None

    def _serialize_job(self, row) -> dict[str, Any]:
        state = dict(row)
        state["resolve_final_url"] = bool(state["resolve_final_url"])
        state["skip_cached_articles"] = bool(state["skip_cached_articles"])
        state["use_resolver_cache"] = bool(state["use_resolver_cache"])
        return state
