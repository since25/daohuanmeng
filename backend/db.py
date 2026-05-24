from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS crawl_jobs (
                    id INTEGER PRIMARY KEY,
                    start_url TEXT NOT NULL,
                    current_url TEXT,
                    max_pages INTEGER NOT NULL,
                    delay_seconds REAL NOT NULL,
                    resolve_final_url INTEGER NOT NULL,
                    skip_cached_articles INTEGER NOT NULL,
                    use_resolver_cache INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    processed_count INTEGER NOT NULL,
                    success_count INTEGER NOT NULL,
                    error_count INTEGER NOT NULL,
                    cache_hit_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS post_pages (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    article_url TEXT NOT NULL UNIQUE,
                    title TEXT,
                    download_href TEXT,
                    resolved_download_url TEXT,
                    next_url TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    fetched_at TEXT,
                    resolved_at TEXT,
                    FOREIGN KEY (job_id) REFERENCES crawl_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS resolver_cache (
                    id INTEGER PRIMARY KEY,
                    download_href TEXT NOT NULL UNIQUE,
                    resolved_download_url TEXT,
                    error TEXT,
                    resolved_at TEXT NOT NULL
                );
                """
            )

    def create_job(
        self,
        *,
        start_url: str,
        max_pages: int,
        delay_seconds: float,
        resolve_final_url: bool,
        skip_cached_articles: bool,
        use_resolver_cache: bool,
    ) -> sqlite3.Row:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO crawl_jobs (
                    start_url,
                    max_pages,
                    delay_seconds,
                    resolve_final_url,
                    skip_cached_articles,
                    use_resolver_cache,
                    status,
                    processed_count,
                    success_count,
                    error_count,
                    cache_hit_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, 0, 0, 0, ?)
                """,
                (
                    start_url,
                    max_pages,
                    delay_seconds,
                    int(resolve_final_url),
                    int(skip_cached_articles),
                    int(use_resolver_cache),
                    _utc_now(),
                ),
            )
            return self.get_job(cursor.lastrowid, connection=connection)

    def get_job(
        self,
        job_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        if connection is not None:
            return connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

        with self._connection() as own_connection:
            return self.get_job(job_id, connection=own_connection)

    def update_job_status(
        self,
        job_id: int,
        status: str,
        *,
        current_url: str | None = None,
        error: str | None = None,
    ) -> sqlite3.Row | None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE crawl_jobs
                SET status = ?, current_url = ?, error = ?
                WHERE id = ?
                """,
                (status, current_url, error, job_id),
            )
            return self.get_job(job_id, connection=connection)

    def upsert_page(
        self,
        *,
        job_id: int,
        article_url: str,
        title: str | None = None,
        download_href: str | None = None,
        resolved_download_url: str | None = None,
        next_url: str | None = None,
        status: str = "pending",
        error: str | None = None,
        fetched_at: str | None = None,
        resolved_at: str | None = None,
    ) -> sqlite3.Row:
        if job_id is None:
            raise ValueError("job_id is required")

        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO post_pages (
                    job_id,
                    article_url,
                    title,
                    download_href,
                    resolved_download_url,
                    next_url,
                    status,
                    error,
                    fetched_at,
                    resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    article_url,
                    title,
                    download_href,
                    resolved_download_url,
                    next_url,
                    status,
                    error,
                    fetched_at,
                    resolved_at,
                ),
            )
            return self.get_page_by_url(article_url, connection=connection)

    def get_page_by_url(
        self,
        article_url: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        if connection is not None:
            return connection.execute(
                "SELECT * FROM post_pages WHERE article_url = ?",
                (article_url,),
            ).fetchone()

        with self._connection() as own_connection:
            return self.get_page_by_url(article_url, connection=own_connection)

    def save_resolver_cache(
        self,
        download_href: str,
        resolved_download_url: str | None,
        error: str | None,
    ) -> sqlite3.Row:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO resolver_cache (
                    download_href,
                    resolved_download_url,
                    error,
                    resolved_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (download_href, resolved_download_url, error, _utc_now()),
            )
            return self.get_resolver_cache(download_href, connection=connection)

    def get_resolver_cache(
        self,
        download_href: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        if connection is not None:
            return connection.execute(
                "SELECT * FROM resolver_cache WHERE download_href = ?",
                (download_href,),
            ).fetchone()

        with self._connection() as own_connection:
            return self.get_resolver_cache(download_href, connection=own_connection)
