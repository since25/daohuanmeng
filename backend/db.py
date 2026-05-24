from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


_UNSET = object()
_ACTIVE_JOB_STATUSES = ("pending", "running", "pausing", "paused")


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
            self._migrate_post_pages_job_id_not_null(connection)

    def _migrate_post_pages_job_id_not_null(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(post_pages)").fetchall()
        }
        job_id_column = columns.get("job_id")
        if job_id_column is None or job_id_column["notnull"]:
            return

        migration_job_id = self._create_legacy_import_job(connection)
        connection.execute("ALTER TABLE post_pages RENAME TO post_pages_legacy")
        connection.executescript(
            """
            CREATE TABLE post_pages (
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
            """
        )
        connection.execute(
            """
            INSERT INTO post_pages (
                id,
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
            SELECT
                id,
                CASE
                    WHEN job_id IS NOT NULL
                        AND EXISTS (
                            SELECT 1 FROM crawl_jobs WHERE crawl_jobs.id = post_pages_legacy.job_id
                        )
                    THEN job_id
                    ELSE ?
                END,
                article_url,
                title,
                download_href,
                resolved_download_url,
                next_url,
                status,
                error,
                fetched_at,
                resolved_at
            FROM post_pages_legacy
            """,
            (migration_job_id,),
        )
        connection.execute("DROP TABLE post_pages_legacy")

    def _create_legacy_import_job(self, connection: sqlite3.Connection) -> int:
        now = _utc_now()
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
                created_at,
                started_at,
                finished_at,
                error
            )
            VALUES (
                'legacy://post-pages-migration',
                0,
                0,
                0,
                1,
                1,
                'migrated',
                0,
                0,
                0,
                0,
                ?,
                ?,
                ?,
                NULL
            )
            """,
            (now, now, now),
        )
        return cursor.lastrowid

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

    def get_latest_job(
        self,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        if connection is not None:
            return connection.execute(
                "SELECT * FROM crawl_jobs ORDER BY id DESC LIMIT 1",
            ).fetchone()

        with self._connection() as own_connection:
            return self.get_latest_job(connection=own_connection)

    def get_active_job(
        self,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        placeholders = ", ".join("?" for _ in _ACTIVE_JOB_STATUSES)
        query = (
            "SELECT * FROM crawl_jobs "
            f"WHERE status IN ({placeholders}) "
            "ORDER BY id DESC LIMIT 1"
        )
        if connection is not None:
            return connection.execute(query, _ACTIVE_JOB_STATUSES).fetchone()

        with self._connection() as own_connection:
            return self.get_active_job(connection=own_connection)

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

    def update_job(
        self,
        job_id: int,
        *,
        status: str | object = _UNSET,
        current_url: str | None | object = _UNSET,
        error: str | None | object = _UNSET,
        started_at: str | None | object = _UNSET,
        finished_at: str | None | object = _UNSET,
        processed_delta: int = 0,
        success_delta: int = 0,
        error_delta: int = 0,
        cache_hit_delta: int = 0,
    ) -> sqlite3.Row | None:
        assignments = []
        parameters = []

        if status is not _UNSET:
            assignments.append("status = ?")
            parameters.append(status)
        if current_url is not _UNSET:
            assignments.append("current_url = ?")
            parameters.append(current_url)
        if error is not _UNSET:
            assignments.append("error = ?")
            parameters.append(error)
        if started_at is not _UNSET:
            assignments.append("started_at = ?")
            parameters.append(started_at)
        if finished_at is not _UNSET:
            assignments.append("finished_at = ?")
            parameters.append(finished_at)
        if processed_delta:
            assignments.append("processed_count = processed_count + ?")
            parameters.append(processed_delta)
        if success_delta:
            assignments.append("success_count = success_count + ?")
            parameters.append(success_delta)
        if error_delta:
            assignments.append("error_count = error_count + ?")
            parameters.append(error_delta)
        if cache_hit_delta:
            assignments.append("cache_hit_count = cache_hit_count + ?")
            parameters.append(cache_hit_delta)

        if not assignments:
            return self.get_job(job_id)

        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE crawl_jobs
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                (*parameters, job_id),
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
                INSERT INTO post_pages (
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
                ON CONFLICT(article_url) DO UPDATE SET
                    job_id = excluded.job_id,
                    title = excluded.title,
                    download_href = excluded.download_href,
                    resolved_download_url = excluded.resolved_download_url,
                    next_url = excluded.next_url,
                    status = excluded.status,
                    error = excluded.error,
                    fetched_at = excluded.fetched_at,
                    resolved_at = excluded.resolved_at
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

    def get_page_by_id(
        self,
        page_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        if connection is not None:
            return connection.execute(
                "SELECT * FROM post_pages WHERE id = ?",
                (page_id,),
            ).fetchone()

        with self._connection() as own_connection:
            return self.get_page_by_id(page_id, connection=own_connection)

    def list_pages(
        self,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[sqlite3.Row]:
        if connection is not None:
            return list(
                connection.execute(
                    """
                    SELECT * FROM post_pages
                    ORDER BY id ASC
                    """
                ).fetchall()
            )

        with self._connection() as own_connection:
            return self.list_pages(connection=own_connection)

    def save_resolver_cache(
        self,
        download_href: str,
        resolved_download_url: str | None,
        error: str | None,
    ) -> sqlite3.Row:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO resolver_cache (
                    download_href,
                    resolved_download_url,
                    error,
                    resolved_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(download_href) DO UPDATE SET
                    resolved_download_url = CASE
                        WHEN resolver_cache.resolved_download_url IS NULL
                            AND excluded.resolved_download_url IS NOT NULL
                        THEN excluded.resolved_download_url
                        ELSE resolver_cache.resolved_download_url
                    END,
                    error = CASE
                        WHEN resolver_cache.resolved_download_url IS NULL
                            AND excluded.resolved_download_url IS NOT NULL
                        THEN NULL
                        ELSE resolver_cache.error
                    END,
                    resolved_at = CASE
                        WHEN resolver_cache.resolved_download_url IS NULL
                            AND excluded.resolved_download_url IS NOT NULL
                        THEN excluded.resolved_at
                        ELSE resolver_cache.resolved_at
                    END
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
