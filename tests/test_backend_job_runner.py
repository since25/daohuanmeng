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
        self.html_by_url = {}
        self.resolved_by_url = {}
        self.runner = JobRunner(
            self.repo,
            fetch_html=self.fake_fetch_html,
            resolve_url=self.fake_resolve_url,
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

    def make_options(
        self,
        *,
        start_url: str = "https://daoyu.fan/3199.html",
        max_pages: int = 10,
        delay_seconds: float = 0.0,
        proxy: str | None = "http://127.0.0.1:8080",
        resolve_final_url: bool = True,
        skip_cached_articles: bool = False,
        use_resolver_cache: bool = True,
    ) -> StartJobOptions:
        return StartJobOptions(
            start_url=start_url,
            max_pages=max_pages,
            delay_seconds=delay_seconds,
            proxy=proxy,
            resolve_final_url=resolve_final_url,
            skip_cached_articles=skip_cached_articles,
            use_resolver_cache=use_resolver_cache,
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

        self.assertEqual(self.fetch_calls, [("https://daoyu.fan/3200.html", "http://127.0.0.1:8080")])
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
        self.assertEqual(self.fetch_calls, [("https://daoyu.fan/3199.html", "http://127.0.0.1:8080")])

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
                ("https://daoyu.fan/3199.html", "http://127.0.0.1:8080"),
                ("https://daoyu.fan/3200.html", "http://127.0.0.1:8080"),
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


if __name__ == "__main__":
    unittest.main()
