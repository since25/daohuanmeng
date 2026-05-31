import { ResultRow } from "./api";

export type ResultFilterField =
  | "all"
  | "title"
  | "article_url"
  | "download_href"
  | "resolved_download_url"
  | "error";

export interface ResultFilters {
  query: string;
  field: ResultFilterField;
  status: string;
}

export interface PaginatedResults {
  page: number;
  pageRows: ResultRow[];
  pageSize: number;
  totalPages: number;
  totalRows: number;
}

export type ResultSortField = "title" | "record_time";
export type ResultSortDirection = "asc" | "desc";

export interface ResultSort {
  field: ResultSortField;
  direction: ResultSortDirection;
}

const searchableFields: Exclude<ResultFilterField, "all">[] = [
  "title",
  "article_url",
  "download_href",
  "resolved_download_url",
  "error"
];

export function resultRecordTime(row: ResultRow): string | null {
  return row.fetched_at ?? row.resolved_at ?? null;
}

export function filterResults(rows: ResultRow[], filters: ResultFilters): ResultRow[] {
  const normalizedQuery = filters.query.trim().toLowerCase();
  const fields = filters.field === "all" ? searchableFields : [filters.field];

  return rows.filter((row) => {
    const matchesStatus = filters.status === "all" || row.status === filters.status;
    if (!matchesStatus) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    return fields.some((field) => {
      const value = row[field];
      return String(value ?? "").toLowerCase().includes(normalizedQuery);
    });
  });
}

export function sortResults(rows: ResultRow[], sort: ResultSort): ResultRow[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    let result = 0;
    if (sort.field === "title") {
      result = String(left.title ?? "").localeCompare(String(right.title ?? ""), "zh-Hans");
    } else {
      result = String(resultRecordTime(left) ?? "").localeCompare(String(resultRecordTime(right) ?? ""));
    }

    if (result === 0) {
      result = left.id - right.id;
    }
    return result * direction;
  });
}

export function getRecentResults(rows: ResultRow[], limit: number): ResultRow[] {
  return sortResults(rows, { field: "record_time", direction: "desc" }).slice(0, limit);
}

export function paginateResults(
  rows: ResultRow[],
  page: number,
  pageSize: number
): PaginatedResults {
  const totalRows = rows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;

  return {
    page: safePage,
    pageRows: rows.slice(start, start + pageSize),
    pageSize,
    totalPages,
    totalRows
  };
}
