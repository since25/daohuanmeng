import tempfile
import unittest
from pathlib import Path

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
            "proxy": "http://127.0.0.1:8080",
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

    def test_start_rejects_second_active_job(self):
        first = self.client.post("/api/job/start", json=self.start_payload())
        second = self.client.post("/api/job/start", json=self.start_payload())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "running")
        self.assertEqual(second.status_code, 409)

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
        self.assertIn("https://daoyu.fan/3199.html", csv_export.text)


if __name__ == "__main__":
    unittest.main()
