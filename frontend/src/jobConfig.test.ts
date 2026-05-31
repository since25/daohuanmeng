import { describe, expect, it } from "vitest";
import {
  defaultPayload,
  loadStartJobPayload,
  saveStartJobPayload
} from "./jobConfig";

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

describe("job config storage", () => {
  it("loads defaults when no saved config exists", () => {
    const storage = new MemoryStorage();

    expect(loadStartJobPayload(storage)).toEqual(defaultPayload);
    expect(defaultPayload.delay_seconds).toBe(2);
  });

  it("saves and restores resolver and Nikki config", () => {
    const storage = new MemoryStorage();

    saveStartJobPayload(
      {
        ...defaultPayload,
        resolver_proxy: "http://proxy.example:7890",
        rewrite_resolver_url: true,
        nikki_api_secret: "secret",
        nikki_delay_timeout_ms: 7000
      },
      storage
    );

    expect(loadStartJobPayload(storage)).toMatchObject({
      resolver_proxy: "http://proxy.example:7890",
      rewrite_resolver_url: true,
      nikki_api_secret: "secret",
      nikki_delay_timeout_ms: 7000
    });
  });

  it("merges old partial config with current defaults", () => {
    const storage = new MemoryStorage();
    storage.setItem("daoyufan:start-job-payload", JSON.stringify({ max_pages: 8 }));

    expect(loadStartJobPayload(storage)).toEqual({
      ...defaultPayload,
      max_pages: 8
    });
  });
});
