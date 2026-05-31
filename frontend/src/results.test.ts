import { describe, expect, it } from "vitest";
import { filterResults, getRecentResults, paginateResults, sortResults } from "./results";
import { ResultRow } from "./api";

function row(overrides: Partial<ResultRow>): ResultRow {
  return {
    id: overrides.id ?? 1,
    job_id: 1,
    article_url: overrides.article_url ?? "https://daoyu.fan/1.html",
    title: overrides.title ?? "默认标题",
    download_href: overrides.download_href ?? null,
    resolved_download_url: overrides.resolved_download_url ?? null,
    next_url: overrides.next_url ?? null,
    status: overrides.status ?? "fetched",
    error: overrides.error ?? null,
    fetched_at: overrides.fetched_at ?? null,
    resolved_at: overrides.resolved_at ?? null
  };
}

describe("result table helpers", () => {
  it("filters by explicit field and status", () => {
    const rows = [
      row({ id: 1, title: "Alpha", article_url: "https://daoyu.fan/a.html", status: "resolved" }),
      row({ id: 2, title: "Beta", article_url: "https://daoyu.fan/b.html", status: "error", error: "HTTP Error 502" })
    ];

    const filtered = filterResults(rows, {
      query: "502",
      field: "error",
      status: "error"
    });

    expect(filtered.map((item) => item.id)).toEqual([2]);
  });

  it("returns only the current page", () => {
    const rows = Array.from({ length: 25 }, (_, index) => row({ id: index + 1 }));

    const page = paginateResults(rows, 2, 10);

    expect(page.totalPages).toBe(3);
    expect(page.pageRows.map((item) => item.id)).toEqual([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
  });

  it("returns the five most recent rows for the dashboard", () => {
    const rows = Array.from({ length: 7 }, (_, index) =>
      row({
        id: index + 1,
        fetched_at: `2026-05-24T07:0${index}:00+00:00`
      })
    );

    expect(getRecentResults(rows, 5).map((item) => item.id)).toEqual([7, 6, 5, 4, 3]);
  });

  it("sorts by title and record time in both directions", () => {
    const rows = [
      row({ id: 1, title: "Beta", fetched_at: "2026-05-24T07:00:00+00:00" }),
      row({ id: 2, title: "Alpha", fetched_at: "2026-05-24T09:00:00+00:00" }),
      row({ id: 3, title: "Gamma", fetched_at: "2026-05-24T08:00:00+00:00" })
    ];

    expect(sortResults(rows, { field: "title", direction: "asc" }).map((item) => item.id)).toEqual([2, 1, 3]);
    expect(sortResults(rows, { field: "record_time", direction: "desc" }).map((item) => item.id)).toEqual([2, 3, 1]);
  });
});
