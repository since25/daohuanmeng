import { StartJobPayload } from "./api";

export const defaultPayload: StartJobPayload = {
  start_url: "https://daoyu.fan/3199.html",
  max_pages: 2,
  delay_seconds: 2,
  proxy: "http://127.0.0.1:8080",
  resolve_final_url: true,
  skip_cached_articles: true,
  use_resolver_cache: true,
  resolver_proxy: null,
  rewrite_resolver_url: false,
  nikki_api_base: null,
  nikki_api_secret: null,
  nikki_proxy_group: "daoyufan-resolver-pool",
  nikki_delay_test_url: "https://www.gstatic.com/generate_204",
  nikki_delay_timeout_ms: 5000
};

const storageKey = "daoyufan:start-job-payload";

export interface JobConfigStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function browserStorage(): JobConfigStorage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

function isRecord(value: unknown): value is Partial<StartJobPayload> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function loadStartJobPayload(storage = browserStorage()): StartJobPayload {
  if (!storage) {
    return defaultPayload;
  }

  const raw = storage.getItem(storageKey);
  if (!raw) {
    return defaultPayload;
  }

  try {
    const parsed = JSON.parse(raw);
    if (!isRecord(parsed)) {
      return defaultPayload;
    }
    return { ...defaultPayload, ...parsed };
  } catch {
    return defaultPayload;
  }
}

export function saveStartJobPayload(
  payload: StartJobPayload,
  storage = browserStorage()
): void {
  storage?.setItem(storageKey, JSON.stringify(payload));
}

export function clearStartJobPayload(storage = browserStorage()): void {
  storage?.removeItem(storageKey);
}
