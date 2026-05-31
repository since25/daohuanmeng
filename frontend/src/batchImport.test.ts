import { describe, expect, it } from "vitest";
import { parseBatchImport } from "./batchImport";

describe("batch import parser", () => {
  it("parses category collector JSON output", () => {
    const items = parseBatchImport(JSON.stringify([
      {
        source_page: 1,
        title: "宫徵羽合集",
        url: "https://daoyu.fan/45790.html"
      }
    ]));

    expect(items).toEqual([
      {
        source_page: 1,
        title: "宫徵羽合集",
        url: "https://daoyu.fan/45790.html"
      }
    ]);
  });

  it("rejects entries without a valid URL", () => {
    expect(() => parseBatchImport(JSON.stringify([{ title: "bad", url: "" }]))).toThrow(
      "第 1 条缺少 url"
    );
  });
});
