import tempfile
import unittest
from pathlib import Path

from backend.db import Repository
from backend.job_runner import JobRunner
from backend.models import StartJobOptions


def build_article_html(
    *,
    title: str,
    download_href: str | None = None,
    next_url: str | None = None,
) -> str:
    download_groups = ""
    if download_href:
        download_groups = f"""
        <div class="btn-group">
          <a href="https://daoyu.fan/goto?down=watch">在线观看版本</a>
        </div>
        <div class="btn-group">
          <a href="{download_href}">压缩包版本</a>
        </div>
        """

    next_link = ""
    if next_url:
        next_link = f'<a class="entry-page-next" href="{next_url}">下一篇</a>'

    return f"""
    <html>
      <body>
        <h1 class="post-title mb-2 mb-lg-3">{title}</h1>
        {download_groups}
        {next_link}
      </body>
    </html>
    """


class BackendJobRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "daoyufan.sqlite3"
        self.repo = Repository(self.db_path)
        self.fetch_calls = []
        self.resolve_calls = []
        self.rotator_calls = []
        self.sleep_calls = []
        self.html_by_url = {}
        self.resolved_by_url = {}
        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=self.fake_resolve_url,
            sleep=self.fake_sleep,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def fake_fetch_html(self, url: str, proxy: str | None = None) -> str:
        self.fetch_calls.append((url, proxy))
        if url not in self.html_by_url:
            raise AssertionError(f"unexpected fetch: {url}")
        return self.html_by_url[url]

    def fake_resolve_url(self, url: str, proxy: str | None = None) -> str:
        self.resolve_calls.append((url, proxy))
        if url not in self.resolved_by_url:
            raise AssertionError(f"unexpected resolve: {url}")
        return self.resolved_by_url[url]

    def fake_sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)

    def make_options(
        self,
        *,
        start_url: str = "https://daoyu.fan/3199.html",
        max_pages: int = 10,
        delay_seconds: float = 0.0,
        proxy: str | None = "http://127.0.0.1:28880",
        resolve_final_url: bool = True,
        skip_cached_articles: bool = False,
        use_resolver_cache: bool = True,
        resolver_proxy: str | None = None,
        rewrite_resolver_url: bool = False,
        nikki_api_base: str | None = None,
        nikki_api_secret: str | None = None,
        nikki_proxy_group: str | None = None,
    ) -> StartJobOptions:
        return StartJobOptions(
            start_url=start_url,
            max_pages=max_pages,
            delay_seconds=delay_seconds,
            proxy=proxy,
            resolve_final_url=resolve_final_url,
            skip_cached_articles=skip_cached_articles,
            use_resolver_cache=use_resolver_cache,
            resolver_proxy=resolver_proxy,
            rewrite_resolver_url=rewrite_resolver_url,
            nikki_api_base=nikki_api_base,
            nikki_api_secret=nikki_api_secret,
            nikki_proxy_group=nikki_proxy_group,
        )

    def seed_existing_page(
        self,
        *,
        article_url: str,
        next_url: str | None,
        download_href: str | None = None,
        resolved_download_url: str | None = None,
        title: str = "Cached title",
    ) -> None:
        self.repo.initialize()
        seed_job = self.repo.create_job(
            start_url="https://daoyu.fan/seed.html",
            max_pages=1,
            delay_seconds=0.0,
            resolve_final_url=False,
            skip_cached_articles=False,
            use_resolver_cache=False,
        )
        self.repo.update_job_status(seed_job["id"], "completed")
        self.repo.upsert_page(
            job_id=seed_job["id"],
            article_url=article_url,
            title=title,
            download_href=download_href,
            resolved_download_url=resolved_download_url,
            next_url=next_url,
            status="resolved" if resolved_download_url else "fetched",
        )

    def test_start_creates_a_running_job(self):
        state = self.runner.start(self.make_options())

        self.assertEqual(state["status"], "running")
        self.assertEqual(state["current_url"], "https://daoyu.fan/3199.html")
        self.assertEqual(state["start_url"], "https://daoyu.fan/3199.html")
        self.assertIsNotNone(state["started_at"])

    def test_runner_saves_parsed_page(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )
        self.resolved_by_url["https://daoyu.fan/goto?down=bbb"] = (
            "https://share.example/file-1"
        )

        state = self.runner.start(self.make_options(max_pages=1))
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(page["title"], "第一页标题")
        self.assertEqual(page["download_href"], "https://daoyu.fan/goto?down=bbb")
        self.assertEqual(page["resolved_download_url"], "https://share.example/file-1")
        self.assertEqual(page["status"], "resolved")
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["success_count"], 1)

    def test_runner_resolves_single_download_button(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = """
        <html>
          <body>
            <h1 class="post-title mb-2 mb-lg-3">单按钮页</h1>
            <div class="btn-group">
              <a href="https://daoyu.fan/goto?down=only">压缩包</a>
            </div>
          </body>
        </html>
        """
        self.resolved_by_url["https://daoyu.fan/goto?down=only"] = (
            "https://share.example/only"
        )

        state = self.runner.start(self.make_options(max_pages=1))
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(page["download_href"], "https://daoyu.fan/goto?down=only")
        self.assertEqual(page["resolved_download_url"], "https://share.example/only")
        self.assertEqual(page["status"], "resolved")
        self.assertEqual(job["success_count"], 1)

    def test_runner_marks_missing_download_href_as_error_when_resolution_is_required(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="无下载按钮页",
        )

        state = self.runner.start(self.make_options(max_pages=1, resolve_final_url=True))
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(page["status"], "error")
        self.assertIn("download href not found", page["error"])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_count"], 1)

    def test_runner_reprocesses_unresolved_cached_article_when_resolution_is_required(self):
        self.seed_existing_page(
            article_url="https://daoyu.fan/3199.html",
            next_url=None,
            title="Old fetched page",
        )
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="Refetched page",
            download_href="https://daoyu.fan/goto?down=bbb",
        )
        self.resolved_by_url["https://daoyu.fan/goto?down=bbb"] = (
            "https://share.example/refetched"
        )

        state = self.runner.start(
            self.make_options(max_pages=1, skip_cached_articles=True, resolve_final_url=True)
        )
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(self.fetch_calls, [("https://daoyu.fan/3199.html", "http://127.0.0.1:28880")])
        self.assertEqual(page["title"], "Refetched page")
        self.assertEqual(page["status"], "resolved")
        self.assertEqual(job["cache_hit_count"], 0)

    def test_runner_retries_transient_resolver_errors_with_configured_delay(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )
        attempts = {"count": 0}

        def flaky_resolve(url: str, proxy: str | None = None) -> str:
            self.resolve_calls.append((url, proxy))
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("HTTP Error 502: Bad Gateway")
            return "https://share.example/recovered"

        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=flaky_resolve,
            sleep=self.fake_sleep,
        )

        state = self.runner.start(self.make_options(max_pages=1, delay_seconds=1.25))
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(len(self.resolve_calls), 3)
        self.assertEqual(self.sleep_calls, [1.25, 1.25])
        self.assertEqual(page["resolved_download_url"], "https://share.example/recovered")
        self.assertEqual(page["status"], "resolved")
        self.assertEqual(job["status"], "completed")

    def test_runner_rotates_once_per_article_and_uses_resolver_proxy_for_full_flow(self):
        first_article_url = "https://huanyu-proxy.daoyufan.workers.dev/3199.html"
        second_article_url = "https://huanyu-proxy.daoyufan.workers.dev/3200.html"
        self.html_by_url[first_article_url] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=first",
            next_url="https://daoyu.fan/3200.html",
        )
        self.html_by_url[second_article_url] = build_article_html(
            title="第二页标题",
            download_href="https://daoyu.fan/goto?down=second",
        )
        first_rewritten_url = "https://huanyu-proxy.daoyufan.workers.dev/goto?down=first"
        second_rewritten_url = "https://huanyu-proxy.daoyufan.workers.dev/goto?down=second"
        self.resolved_by_url[first_rewritten_url] = "https://share.example/first"
        self.resolved_by_url[second_rewritten_url] = "https://share.example/second"

        def fake_rotate() -> str:
            node = f"node-{len(self.rotator_calls) + 1}"
            self.rotator_calls.append(node)
            return node

        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=self.fake_resolve_url,
            sleep=self.fake_sleep,
            rotate_resolver_proxy=fake_rotate,
        )

        self.runner.start(
            self.make_options(
                max_pages=2,
                resolver_proxy="http://proxy.example:7890",
                rewrite_resolver_url=True,
                nikki_api_base="http://nikki.example:9090",
                nikki_api_secret="secret",
                nikki_proxy_group="daoyufan-resolver-pool",
            )
        )
        self.runner.tick_until_idle_for_tests()

        self.assertEqual(self.rotator_calls, ["node-1", "node-2"])
        self.assertEqual(
            self.fetch_calls,
            [
                (first_article_url, "http://proxy.example:7890"),
                (second_article_url, "http://proxy.example:7890"),
            ],
        )
        self.assertEqual(
            self.resolve_calls,
            [
                (first_rewritten_url, "http://proxy.example:7890"),
                (second_rewritten_url, "http://proxy.example:7890"),
            ],
        )

    def test_runner_rewrites_and_rotates_before_resolving_with_resolver_proxy(self):
        self.html_by_url["https://huanyu-proxy.daoyufan.workers.dev/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )
        rewritten_url = "https://huanyu-proxy.daoyufan.workers.dev/goto?down=bbb"
        self.resolved_by_url[rewritten_url] = "https://share.example/rewritten"

        def fake_rotate() -> str:
            self.rotator_calls.append("rotate")
            return "node-a"

        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=self.fake_resolve_url,
            sleep=self.fake_sleep,
            rotate_resolver_proxy=fake_rotate,
        )

        state = self.runner.start(
            self.make_options(
                max_pages=1,
                resolver_proxy="http://proxy.example:7890",
                rewrite_resolver_url=True,
                nikki_api_base="http://nikki.example:9090",
                nikki_api_secret="secret",
                nikki_proxy_group="daoyufan-resolver-pool",
            )
        )
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(self.rotator_calls, ["rotate"])
        self.assertEqual(
            self.resolve_calls,
            [(rewritten_url, "http://proxy.example:7890")],
        )
        self.assertEqual(page["resolved_download_url"], "https://share.example/rewritten")
        self.assertEqual(job["status"], "completed")

    def test_runner_switches_node_for_resolver_retry_within_article(self):
        self.html_by_url["https://huanyu-proxy.daoyufan.workers.dev/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )
        rewritten_url = "https://huanyu-proxy.daoyufan.workers.dev/goto?down=bbb"
        attempts = {"count": 0}

        def fake_rotate() -> str:
            node = f"node-{len(self.rotator_calls) + 1}"
            self.rotator_calls.append(node)
            return node

        def flaky_resolve(url: str, proxy: str | None = None) -> str:
            self.resolve_calls.append((url, proxy))
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary resolver failure")
            return "https://share.example/recovered"

        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=flaky_resolve,
            sleep=self.fake_sleep,
            rotate_resolver_proxy=fake_rotate,
        )

        self.runner.start(
            self.make_options(
                max_pages=1,
                delay_seconds=0,
                resolver_proxy="http://proxy.example:7890",
                rewrite_resolver_url=True,
            )
        )
        self.runner.tick_until_idle_for_tests()

        self.assertEqual(self.rotator_calls, ["node-1", "node-2"])
        self.assertEqual(
            self.resolve_calls,
            [
                (rewritten_url, "http://proxy.example:7890"),
                (rewritten_url, "http://proxy.example:7890"),
            ],
        )

    def test_runner_updates_existing_page_to_error_after_resolver_failure(self):
        self.seed_existing_page(
            article_url="https://daoyu.fan/3199.html",
            next_url=None,
            download_href="https://daoyu.fan/goto?down=bbb",
            title="Old page",
        )
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )

        def failing_resolve(url: str, proxy: str | None = None) -> str:
            self.resolve_calls.append((url, proxy))
            raise RuntimeError("HTTP Error 502: Bad Gateway")

        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=failing_resolve,
            sleep=self.fake_sleep,
        )

        state = self.runner.start(
            self.make_options(max_pages=1, skip_cached_articles=False, delay_seconds=0)
        )
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(len(self.resolve_calls), 3)
        self.assertEqual(page["title"], "第一页标题")
        self.assertEqual(page["status"], "error")
        self.assertIn("HTTP Error 502", page["error"])
        self.assertIsNone(page["resolved_download_url"])
        self.assertEqual(job["status"], "failed")

    def test_runner_applies_delay_between_pages(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            next_url="https://daoyu.fan/3200.html",
        )
        self.html_by_url["https://daoyu.fan/3200.html"] = build_article_html(
            title="第二页标题",
        )

        self.runner.start(
            self.make_options(max_pages=2, delay_seconds=0.75, resolve_final_url=False)
        )
        self.runner.tick_until_idle_for_tests()

        self.assertEqual(len(self.sleep_calls), 1)
        self.assertAlmostEqual(self.sleep_calls[0], 0.75, places=3)

    def test_runner_prepares_next_article_proxy_inside_delay_window(self):
        events = []
        self.html_by_url["https://huanyu-proxy.daoyufan.workers.dev/3199.html"] = build_article_html(
            title="第一页标题",
            next_url="https://daoyu.fan/3200.html",
        )
        self.html_by_url["https://huanyu-proxy.daoyufan.workers.dev/3200.html"] = build_article_html(
            title="第二页标题",
        )

        def fake_rotate() -> str:
            node = f"node-{len(self.rotator_calls) + 1}"
            self.rotator_calls.append(node)
            events.append(f"rotate:{node}")
            return node

        def fake_fetch(url: str, proxy: str | None = None) -> str:
            events.append(f"fetch:{url}")
            return self.fake_fetch_html(url, proxy)

        def fake_sleep(seconds: float) -> None:
            events.append(f"sleep:{seconds:.1f}")
            self.fake_sleep(seconds)

        self.runner = JobRunner(
            self.repo,
            fetch_html=fake_fetch,
            resolve_url=self.fake_resolve_url,
            sleep=fake_sleep,
            rotate_resolver_proxy=fake_rotate,
        )

        self.runner.start(
            self.make_options(
                max_pages=2,
                delay_seconds=2.0,
                resolve_final_url=False,
                resolver_proxy="http://proxy.example:7890",
                rewrite_resolver_url=True,
            )
        )
        self.runner.tick_until_idle_for_tests()

        self.assertEqual(
            events,
            [
                "rotate:node-1",
                "fetch:https://huanyu-proxy.daoyufan.workers.dev/3199.html",
                "rotate:node-2",
                "sleep:2.0",
                "fetch:https://huanyu-proxy.daoyufan.workers.dev/3200.html",
            ],
        )
        self.assertEqual(self.rotator_calls, ["node-1", "node-2"])

    def test_runner_skips_cached_article_urls_and_continues_from_saved_next_url(self):
        self.seed_existing_page(
            article_url="https://daoyu.fan/3199.html",
            next_url="https://daoyu.fan/3200.html",
            title="Cached page",
        )
        self.html_by_url["https://daoyu.fan/3200.html"] = build_article_html(
            title="第二页标题",
        )

        state = self.runner.start(
            self.make_options(
                max_pages=2,
                skip_cached_articles=True,
                resolve_final_url=False,
            )
        )
        self.runner.tick_until_idle_for_tests()
        job = self.repo.get_job(state["id"])
        page = self.repo.get_page_by_url("https://daoyu.fan/3200.html")

        self.assertEqual(self.fetch_calls, [("https://daoyu.fan/3200.html", "http://127.0.0.1:28880")])
        self.assertEqual(job["cache_hit_count"], 1)
        self.assertEqual(job["processed_count"], 2)
        self.assertEqual(page["title"], "第二页标题")

    def test_runner_reuses_resolver_cache(self):
        self.repo.initialize()
        self.repo.save_resolver_cache(
            "https://daoyu.fan/goto?down=bbb",
            "https://share.example/from-cache",
            None,
        )
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )

        state = self.runner.start(self.make_options(max_pages=1))
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(self.resolve_calls, [])
        self.assertEqual(page["resolved_download_url"], "https://share.example/from-cache")
        self.assertEqual(job["success_count"], 1)

    def test_resolve_final_url_false_skips_resolver(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=bbb",
        )

        state = self.runner.start(
            self.make_options(
                max_pages=1,
                resolve_final_url=False,
            )
        )
        self.runner.tick_until_idle_for_tests()
        page = self.repo.get_page_by_url("https://daoyu.fan/3199.html")
        job = self.repo.get_job(state["id"])

        self.assertEqual(self.resolve_calls, [])
        self.assertIsNone(page["resolved_download_url"])
        self.assertEqual(job["success_count"], 1)

    def test_pause_moves_running_to_pausing_to_paused(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            next_url="https://daoyu.fan/3200.html",
        )
        self.html_by_url["https://daoyu.fan/3200.html"] = build_article_html(
            title="第二页标题",
        )

        self.runner.start(self.make_options(max_pages=2, resolve_final_url=False))

        pausing = self.runner.pause()
        self.runner.tick_until_idle_for_tests()
        paused = self.repo.get_active_job()

        self.assertEqual(pausing["status"], "pausing")
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(paused["current_url"], "https://daoyu.fan/3200.html")
        self.assertEqual(self.fetch_calls, [("https://daoyu.fan/3199.html", "http://127.0.0.1:28880")])

    def test_resume_continues_from_current_url(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            next_url="https://daoyu.fan/3200.html",
        )
        self.html_by_url["https://daoyu.fan/3200.html"] = build_article_html(
            title="第二页标题",
        )

        state = self.runner.start(self.make_options(max_pages=2, resolve_final_url=False))
        self.runner.pause()
        self.runner.tick_until_idle_for_tests()

        resumed = self.runner.resume()
        self.runner.tick_until_idle_for_tests()
        job = self.repo.get_job(state["id"])
        second_page = self.repo.get_page_by_url("https://daoyu.fan/3200.html")

        self.assertEqual(resumed["status"], "running")
        self.assertEqual(
            self.fetch_calls,
            [
                ("https://daoyu.fan/3199.html", "http://127.0.0.1:28880"),
                ("https://daoyu.fan/3200.html", "http://127.0.0.1:28880"),
            ],
        )
        self.assertEqual(job["status"], "completed")
        self.assertEqual(second_page["title"], "第二页标题")

    def test_stop_moves_to_stopped(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
        )

        state = self.runner.start(self.make_options(max_pages=1, resolve_final_url=False))
        stopped = self.runner.stop()
        self.runner.tick_until_idle_for_tests()
        job = self.repo.get_job(state["id"])

        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(job["status"], "stopped")
        self.assertEqual(self.fetch_calls, [])

    def test_batch_job_processes_imported_urls_without_following_article_next_url(self):
        self.html_by_url["https://daoyu.fan/3199.html"] = build_article_html(
            title="第一页标题",
            download_href="https://daoyu.fan/goto?down=first",
            next_url="https://daoyu.fan/should-not-follow.html",
        )
        self.html_by_url["https://daoyu.fan/3200.html"] = build_article_html(
            title="第二页标题",
            download_href="https://daoyu.fan/goto?down=second",
        )
        self.resolved_by_url["https://daoyu.fan/goto?down=first"] = "https://share.example/first"
        self.resolved_by_url["https://daoyu.fan/goto?down=second"] = "https://share.example/second"

        state = self.runner.start_batch(
            self.make_options(max_pages=99),
            [
                {"title": "导入标题一", "url": "https://daoyu.fan/3199.html", "source_page": 1},
                {"title": "导入标题二", "url": "https://daoyu.fan/3200.html", "source_page": 1},
            ],
        )
        self.runner.tick_until_idle_for_tests()
        job = self.repo.get_job(state["id"])

        self.assertEqual(
            self.fetch_calls,
            [
                ("https://daoyu.fan/3199.html", "http://127.0.0.1:28880"),
                ("https://daoyu.fan/3200.html", "http://127.0.0.1:28880"),
            ],
        )
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["processed_count"], 2)
        self.assertIsNone(self.repo.get_page_by_url("https://daoyu.fan/should-not-follow.html"))

    def test_batch_job_skips_already_resolved_urls_by_default(self):
        self.seed_existing_page(
            article_url="https://daoyu.fan/3199.html",
            next_url=None,
            download_href="https://daoyu.fan/goto?down=old",
            resolved_download_url="https://share.example/already",
            title="Already resolved",
        )
        self.html_by_url["https://daoyu.fan/3200.html"] = build_article_html(
            title="第二页标题",
            download_href="https://daoyu.fan/goto?down=second",
        )
        self.resolved_by_url["https://daoyu.fan/goto?down=second"] = "https://share.example/second"

        state = self.runner.start_batch(
            self.make_options(max_pages=99, skip_cached_articles=True),
            [
                {"title": "已解析", "url": "https://daoyu.fan/3199.html"},
                {"title": "第二页标题", "url": "https://daoyu.fan/3200.html"},
            ],
        )
        self.runner.tick_until_idle_for_tests()
        job = self.repo.get_job(state["id"])

        self.assertEqual(self.fetch_calls, [("https://daoyu.fan/3200.html", "http://127.0.0.1:28880")])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["processed_count"], 2)
        self.assertEqual(job["cache_hit_count"], 1)


if __name__ == "__main__":
    unittest.main()
