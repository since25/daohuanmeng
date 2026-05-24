export interface BatchImportItem {
  title: string | null;
  url: string;
  source_page?: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseBatchImport(raw: string): BatchImportItem[] {
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) {
    throw new Error("批量导入内容必须是 JSON 数组");
  }

  return parsed.map((item, index) => {
    if (!isRecord(item)) {
      throw new Error(`第 ${index + 1} 条不是对象`);
    }
    const url = String(item.url ?? "").trim();
    if (!url) {
      throw new Error(`第 ${index + 1} 条缺少 url`);
    }
    try {
      new URL(url);
    } catch {
      throw new Error(`第 ${index + 1} 条 url 格式不正确`);
    }

    const sourcePage = item.source_page;
    return {
      title: item.title == null ? null : String(item.title),
      url,
      source_page: typeof sourcePage === "number" ? sourcePage : null
    };
  });
}
