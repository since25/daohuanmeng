import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api import create_app


ARTICLE_HTML = """
<html>
  <body>
    <h1 class="post-title mb-2 mb-lg-3">第一页标题</h1>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=watch">在线观看版本</a>
    </div>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=download">压缩包版本</a>
    </div>
  </body>
</html>
"""


class BackendApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "daoyufan.sqlite3"
        self.fetch_calls = []
        self.resolve_calls = []

        def fake_fetch(url, proxy=None):
            self.fetch_calls.append((url, proxy))
            return ARTICLE_HTML

        def fake_resolve(url, proxy=None):
            self.resolve_calls.append((url, proxy))
            return "https://share.feijipan.com/s/QOPtO6IO?code=6666"

        self.app = create_app(
            db_path=self.db_path,
            auto_run=False,
            fetch_html=fake_fetch,
            resolve_url=fake_resolve,
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def start_payload(self):
        return {
            "start_url": "https://daoyu.fan/3199.html",
            "max_pages": 1,
            "delay_seconds": 0,
            "proxy": "http://127.0.0.1:28880",
            "resolve_final_url": True,
            "skip_cached_articles": False,
            "use_resolver_cache": True,
        }

    def test_health(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_cors_allows_local_frontend_ports(self):
        response = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://127.0.0.1:5175",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://127.0.0.1:5175",
        )

    def test_cors_origin_regex_can_be_configured_for_server_frontend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "daoyufan.sqlite3"
            with patch.dict(
                "os.environ",
                {"DAOYUFAN_CORS_ORIGIN_REGEX": r"^http://192\.168\.7\.10:[0-9]+$"},
            ):
                client = TestClient(create_app(db_path=db_path, auto_run=False))

            response = client.options(
                "/api/health",
                headers={
                    "Origin": "http://192.168.7.10:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://192.168.7.10:5173",
        )

    def test_start_rejects_second_active_job(self):
        first = self.client.post("/api/job/start", json=self.start_payload())
        second = self.client.post("/api/job/start", json=self.start_payload())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "running")
        self.assertEqual(second.status_code, 409)

    def test_start_batch_imports_manual_urls_and_processes_them(self):
        response = self.client.post(
            "/api/job/start-batch",
            json={
                **self.start_payload(),
                "items": [
                    {"title": "导入标题一", "url": "https://daoyu.fan/3199.html", "source_page": 1},
                    {"title": "导入标题二", "url": "https://daoyu.fan/3200.html", "source_page": 1},
                ],
            },
        )
        self.app.state.runner.tick_until_idle_for_tests()

        self.assertEqual(response.status_code, 200)
        job = self.client.get("/api/job").json()
        results = self.client.get("/api/results").json()
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["processed_count"], 2)
        self.assertEqual(
            [row["article_url"] for row in results],
            ["https://daoyu.fan/3199.html", "https://daoyu.fan/3200.html"],
        )

    def test_pause_resume_and_stop(self):
        self.client.post("/api/job/start", json=self.start_payload())

        paused = self.client.post("/api/job/pause")
        self.app.state.runner.tick_until_idle_for_tests()
        resumed = self.client.post("/api/job/resume")
        stopped = self.client.post("/api/job/stop")

        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["status"], "pausing")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "running")
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["status"], "stopped")

    def test_results_and_exports(self):
        self.client.post("/api/job/start", json=self.start_payload())
        self.app.state.runner.tick_until_idle_for_tests()

        results = self.client.get("/api/results")
        json_export = self.client.get("/api/export/json")
        csv_export = self.client.get("/api/export/csv")

        self.assertEqual(results.status_code, 200)
        rows = results.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "第一页标题")
        self.assertEqual(
            rows[0]["resolved_download_url"],
            "https://share.feijipan.com/s/QOPtO6IO?code=6666",
        )
        self.assertEqual(json_export.status_code, 200)
        self.assertEqual(json_export.json()[0]["article_url"], "https://daoyu.fan/3199.html")
        self.assertEqual(csv_export.status_code, 200)
        self.assertIn("article_url,title,download_href", csv_export.text)

    def test_resolve_single_result_retries_download_href_without_refetching_article(self):
        repository = self.app.state.repository
        job = repository.create_job(
            start_url="https://daoyu.fan/3531.html",
            max_pages=1,
            delay_seconds=0,
            resolve_final_url=True,
            skip_cached_articles=False,
            use_resolver_cache=False,
        )
        page = repository.upsert_page(
            job_id=job["id"],
            article_url="https://daoyu.fan/3531.html",
            title="野结白",
            download_href="https://daoyu.fan/goto?down=download",
            resolved_download_url=None,
            next_url="https://daoyu.fan/3535.html",
            status="error",
            error="ssl eof",
        )

        response = self.client.post(
            f"/api/results/{page['id']}/resolve",
            json=self.start_payload(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "resolved")
        self.assertEqual(body["next_url"], "https://daoyu.fan/3535.html")
        self.assertEqual(body["resolved_download_url"], "https://share.feijipan.com/s/QOPtO6IO?code=6666")
        self.assertEqual(self.fetch_calls, [])
        self.assertEqual(
            self.resolve_calls,
            [("https://daoyu.fan/goto?down=download", "http://127.0.0.1:28880")],
        )

    def test_resolve_single_result_bypasses_existing_resolver_cache(self):
        repository = self.app.state.repository
        job = repository.create_job(
            start_url="https://daoyu.fan/3531.html",
            max_pages=1,
            delay_seconds=0,
            resolve_final_url=True,
            skip_cached_articles=False,
            use_resolver_cache=True,
        )
        repository.save_resolver_cache(
            "https://daoyu.fan/goto?down=download",
            "https://share.example/old-cache",
            None,
        )
        page = repository.upsert_page(
            job_id=job["id"],
            article_url="https://daoyu.fan/3531.html",
            title="野结白",
            download_href="https://daoyu.fan/goto?down=download",
            resolved_download_url="https://share.example/old-cache",
            next_url="https://daoyu.fan/3535.html",
            status="resolved",
            error=None,
        )

        response = self.client.post(
            f"/api/results/{page['id']}/resolve",
            json=self.start_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resolved_download_url"], "https://share.feijipan.com/s/QOPtO6IO?code=6666")
        self.assertEqual(
            self.resolve_calls,
            [("https://daoyu.fan/goto?down=download", "http://127.0.0.1:28880")],
        )


if __name__ == "__main__":
    unittest.main()
