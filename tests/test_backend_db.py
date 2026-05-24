import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.db import Repository


class BackendDbTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "daoyufan.sqlite3"
        self.repo = Repository(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_job(self):
        return self.repo.create_job(
            start_url="https://daoyu.fan/3199.html",
            max_pages=25,
            delay_seconds=1.5,
            resolve_final_url=True,
            skip_cached_articles=False,
            use_resolver_cache=True,
        )

    def test_initialize_is_idempotent(self):
        self.repo.initialize()
        self.repo.initialize()

        job = self.create_job()

        self.assertEqual(job["start_url"], "https://daoyu.fan/3199.html")

    def test_unique_article_url_reuses_row_and_preserves_first_title(self):
        self.repo.initialize()
        job = self.create_job()

        first = self.repo.upsert_page(
            job_id=job["id"],
            article_url="https://daoyu.fan/3199.html",
            title="First title",
            download_href="https://daoyu.fan/goto?down=first",
            resolved_download_url="https://files.example/first",
            next_url="https://daoyu.fan/3200.html",
            status="fetched",
            error=None,
        )
        second = self.repo.upsert_page(
            job_id=job["id"],
            article_url="https://daoyu.fan/3199.html",
            title="Changed title",
            download_href="https://daoyu.fan/goto?down=changed",
            resolved_download_url="https://files.example/changed",
            next_url="https://daoyu.fan/3201.html",
            status="resolved",
            error="changed",
        )
        row = self.repo.get_page_by_url("https://daoyu.fan/3199.html")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(row["title"], "First title")
        self.assertEqual(row["download_href"], "https://daoyu.fan/goto?down=first")
        self.assertEqual(row["resolved_download_url"], "https://files.example/first")
        self.assertEqual(row["next_url"], "https://daoyu.fan/3200.html")
        self.assertEqual(row["status"], "fetched")
        self.assertIsNone(row["error"])

    def test_upsert_page_requires_job_id(self):
        self.repo.initialize()

        with self.assertRaises(TypeError):
            self.repo.upsert_page(
                article_url="https://daoyu.fan/3199.html",
                status="fetched",
            )

    def test_upsert_page_rejects_null_job_id(self):
        self.repo.initialize()

        with self.assertRaises(ValueError):
            self.repo.upsert_page(
                job_id=None,
                article_url="https://daoyu.fan/3199.html",
                status="fetched",
            )

    def test_post_pages_schema_rejects_null_job_id(self):
        self.repo.initialize()

        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO post_pages (article_url, status)
                    VALUES (?, ?)
                    """,
                    ("https://daoyu.fan/3199.html", "fetched"),
                )
        finally:
            connection.close()

    def test_resolver_cache_reuses_download_href_and_preserves_first_resolved_url(self):
        self.repo.initialize()

        first = self.repo.save_resolver_cache(
            "https://daoyu.fan/goto?down=first",
            "https://files.example/first",
            None,
        )
        second = self.repo.save_resolver_cache(
            "https://daoyu.fan/goto?down=first",
            "https://files.example/changed",
            "changed",
        )
        row = self.repo.get_resolver_cache("https://daoyu.fan/goto?down=first")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(row["resolved_download_url"], "https://files.example/first")
        self.assertIsNone(row["error"])

    def test_job_lifecycle_persists_defaults_and_status_updates(self):
        self.repo.initialize()

        created = self.repo.create_job(
            start_url="https://daoyu.fan/3199.html",
            max_pages=10,
            delay_seconds=0.25,
            resolve_final_url=False,
            skip_cached_articles=True,
            use_resolver_cache=False,
        )
        loaded = self.repo.get_job(created["id"])

        self.assertEqual(loaded["status"], "pending")
        self.assertEqual(loaded["processed_count"], 0)
        self.assertEqual(loaded["success_count"], 0)
        self.assertEqual(loaded["error_count"], 0)
        self.assertEqual(loaded["cache_hit_count"], 0)
        self.assertEqual(loaded["resolve_final_url"], 0)
        self.assertEqual(loaded["skip_cached_articles"], 1)
        self.assertEqual(loaded["use_resolver_cache"], 0)
        self.assertIsNone(loaded["started_at"])
        self.assertIsNone(loaded["finished_at"])

        self.repo.update_job_status(
            created["id"],
            "running",
            current_url="https://daoyu.fan/3200.html",
            error="temporary failure",
        )
        updated = self.repo.get_job(created["id"])

        self.assertEqual(updated["status"], "running")
        self.assertEqual(updated["current_url"], "https://daoyu.fan/3200.html")
        self.assertEqual(updated["error"], "temporary failure")


if __name__ == "__main__":
    unittest.main()
