const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

export type JobStatus =
  | "idle"
  | "pending"
  | "running"
  | "pausing"
  | "paused"
  | "completed"
  | "failed"
  | "stopped"
  | "migrated";

export interface StartJobPayload {
  start_url: string;
  max_pages: number;
  delay_seconds: number;
  proxy: string | null;
  resolve_final_url: boolean;
  skip_cached_articles: boolean;
  use_resolver_cache: boolean;
}

export interface JobState {
  id?: number;
  status: JobStatus;
  start_url?: string;
  current_url?: string | null;
  max_pages?: number;
  delay_seconds?: number;
  resolve_final_url?: boolean;
  skip_cached_articles?: boolean;
  use_resolver_cache?: boolean;
  processed_count?: number;
  success_count?: number;
  error_count?: number;
  cache_hit_count?: number;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

export interface ResultRow {
  id: number;
  job_id: number;
  article_url: string;
  title: string | null;
  download_href: string | null;
  resolved_download_url: string | null;
  next_url: string | null;
  status: string;
  error: string | null;
  fetched_at: string | null;
  resolved_at: string | null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    },
    ...options
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function exportUrl(format: "json" | "csv"): string {
  return `${API_BASE}/api/export/${format}`;
}

export async function startJob(payload: StartJobPayload): Promise<JobState> {
  return request<JobState>("/api/job/start", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function pauseJob(): Promise<JobState> {
  return request<JobState>("/api/job/pause", { method: "POST" });
}

export async function resumeJob(): Promise<JobState> {
  return request<JobState>("/api/job/resume", { method: "POST" });
}

export async function stopJob(): Promise<JobState> {
  return request<JobState>("/api/job/stop", { method: "POST" });
}

export async function getJob(): Promise<JobState> {
  return request<JobState>("/api/job");
}

export async function getResults(): Promise<ResultRow[]> {
  return request<ResultRow[]>("/api/results");
}
