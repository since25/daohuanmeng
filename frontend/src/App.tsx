import {
  AlertCircle,
  Database,
  Download,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  Square,
  Table2
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  exportUrl,
  getJob,
  getResults,
  JobState,
  pauseJob,
  ResultRow,
  resolveResult,
  resumeJob,
  startJob,
  StartJobPayload,
  stopJob
} from "./api";
import {
  clearStartJobPayload,
  defaultPayload,
  loadStartJobPayload,
  saveStartJobPayload
} from "./jobConfig";
import {
  filterResults,
  getRecentResults,
  paginateResults,
  ResultFilterField,
  ResultSortDirection,
  ResultSortField,
  resultRecordTime,
  sortResults
} from "./results";

type Tab = "dashboard" | "results" | "cache" | "settings";

const emptyJob: JobState = { status: "idle" };
const resultsPageSize = 25;

function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [payload, setPayload] = useState<StartJobPayload>(() => loadStartJobPayload());
  const [job, setJob] = useState<JobState>(emptyJob);
  const [results, setResults] = useState<ResultRow[]>([]);
  const [query, setQuery] = useState("");
  const [queryField, setQueryField] = useState<ResultFilterField>("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortField, setSortField] = useState<ResultSortField>("record_time");
  const [sortDirection, setSortDirection] = useState<ResultSortDirection>("desc");
  const [resultsPage, setResultsPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [resolvingRowId, setResolvingRowId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const active = job.status === "running" || job.status === "pausing";
  const paused = job.status === "paused";

  async function refresh() {
    const [jobState, rows] = await Promise.all([getJob(), getResults()]);
    setJob(jobState);
    setResults(rows);
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!active && !paused) {
      return;
    }
    const timer = window.setInterval(() => {
      refresh().catch((error) => setMessage(error.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, paused]);

  const filteredResults = useMemo(() => {
    return filterResults(results, {
      query,
      field: queryField,
      status: statusFilter
    });
  }, [query, queryField, results, statusFilter]);

  const sortedResults = useMemo(() => {
    return sortResults(filteredResults, {
      field: sortField,
      direction: sortDirection
    });
  }, [filteredResults, sortDirection, sortField]);

  useEffect(() => {
    setResultsPage(1);
  }, [query, queryField, sortDirection, sortField, statusFilter]);

  const paginatedResults = useMemo(() => {
    return paginateResults(sortedResults, resultsPage, resultsPageSize);
  }, [sortedResults, resultsPage]);

  const errorRows = results.filter((row) => row.error || row.status === "error");
  const resolvedCount = results.filter((row) => row.resolved_download_url).length;

  async function runAction(action: () => Promise<JobState>) {
    setBusy(true);
    setMessage(null);
    try {
      const nextJob = await action();
      setJob(nextJob);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onStart(event: FormEvent) {
    event.preventDefault();
    await runAction(() => startJob(payload));
  }

  async function onResolveRow(row: ResultRow) {
    setResolvingRowId(row.id);
    setMessage(null);
    try {
      await resolveResult(row.id, payload);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setResolvingRowId(null);
    }
  }

  function onSaveConfig() {
    saveStartJobPayload(payload);
    setMessage("配置已保存");
  }

  function onResetConfig() {
    clearStartJobPayload();
    setPayload(defaultPayload);
    setMessage("已恢复默认配置");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">D</span>
          <div>
            <h1>DaoyuFan Console</h1>
            <p>本地抓取控制台</p>
          </div>
        </div>

        <nav className="tabs" aria-label="console sections">
          <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>
            <Play size={16} /> 控制
          </button>
          <button className={tab === "results" ? "active" : ""} onClick={() => setTab("results")}>
            <Table2 size={16} /> 结果
          </button>
          <button className={tab === "cache" ? "active" : ""} onClick={() => setTab("cache")}>
            <Database size={16} /> 缓存
          </button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            <Settings size={16} /> 设置
          </button>
        </nav>

        <form className="config-form" onSubmit={onStart}>
          <label>
            起始文章页
            <input
              value={payload.start_url}
              onChange={(event) => setPayload({ ...payload, start_url: event.target.value })}
            />
          </label>
          <div className="split">
            <label>
              页数
              <input
                min={1}
                type="number"
                value={payload.max_pages}
                onChange={(event) =>
                  setPayload({ ...payload, max_pages: Number(event.target.value) })
                }
              />
            </label>
            <label>
              延迟
              <input
                min={0}
                step={0.1}
                type="number"
                value={payload.delay_seconds}
                onChange={(event) =>
                  setPayload({ ...payload, delay_seconds: Number(event.target.value) })
                }
              />
            </label>
          </div>
          <label>
            代理
            <input
              value={payload.proxy ?? ""}
              onChange={(event) =>
                setPayload({ ...payload, proxy: event.target.value || null })
              }
            />
          </label>
          <Toggle
            checked={payload.resolve_final_url}
            label="解析最终网盘链接"
            onChange={(checked) => setPayload({ ...payload, resolve_final_url: checked })}
          />
          <Toggle
            checked={payload.skip_cached_articles}
            label="跳过已抓文章"
            onChange={(checked) => setPayload({ ...payload, skip_cached_articles: checked })}
          />
          <Toggle
            checked={payload.use_resolver_cache}
            label="复用解析缓存"
            onChange={(checked) => setPayload({ ...payload, use_resolver_cache: checked })}
          />
          <Toggle
            checked={payload.rewrite_resolver_url}
            label="下载跳转改写到 Worker"
            onChange={(checked) => setPayload({ ...payload, rewrite_resolver_url: checked })}
          />
          <label>
            文章处理代理
            <input
              placeholder="http://proxy-gateway.local:7890"
              value={payload.resolver_proxy ?? ""}
              onChange={(event) =>
                setPayload({ ...payload, resolver_proxy: event.target.value || null })
              }
            />
          </label>
          <label>
            Nikki API
            <input
              value={payload.nikki_api_base ?? ""}
              onChange={(event) =>
                setPayload({ ...payload, nikki_api_base: event.target.value || null })
              }
            />
          </label>
          <div className="split">
            <label>
              Nikki 密钥
              <input
                type="password"
                value={payload.nikki_api_secret ?? ""}
                onChange={(event) =>
                  setPayload({ ...payload, nikki_api_secret: event.target.value || null })
                }
              />
            </label>
            <label>
              策略组
              <input
                value={payload.nikki_proxy_group ?? ""}
                onChange={(event) =>
                  setPayload({ ...payload, nikki_proxy_group: event.target.value || null })
                }
              />
            </label>
          </div>
          <div className="split">
            <label>
              嗅探超时(ms)
              <input
                min={500}
                step={500}
                type="number"
                value={payload.nikki_delay_timeout_ms}
                onChange={(event) =>
                  setPayload({ ...payload, nikki_delay_timeout_ms: Number(event.target.value) })
                }
              />
            </label>
            <label>
              嗅探 URL
              <input
                value={payload.nikki_delay_test_url}
                onChange={(event) =>
                  setPayload({ ...payload, nikki_delay_test_url: event.target.value })
                }
              />
            </label>
          </div>
          <div className="config-actions">
            <button onClick={onSaveConfig} type="button">
              <Save size={16} /> 保存配置
            </button>
            <button onClick={onResetConfig} type="button">
              <RotateCcw size={16} /> 恢复默认
            </button>
          </div>
          <div className="command-row">
            <button className="primary" disabled={busy || active || paused} type="submit">
              <Play size={16} /> 启动
            </button>
            <button disabled={busy || !active} onClick={() => runAction(pauseJob)} type="button">
              <Pause size={16} /> 暂停
            </button>
            <button disabled={busy || !paused} onClick={() => runAction(resumeJob)} type="button">
              <RotateCcw size={16} /> 恢复
            </button>
            <button disabled={busy || (!active && !paused)} onClick={() => runAction(stopJob)} type="button">
              <Square size={16} /> 停止
            </button>
          </div>
        </form>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">JOB #{job.id ?? "-"}</p>
            <h2>{statusLabel(job.status)}</h2>
          </div>
          <div className="top-actions">
            <button onClick={() => refresh().catch((error) => setMessage(error.message))}>
              <RefreshCw size={16} /> 刷新
            </button>
            <a className="button-link" href={exportUrl("json")}>
              <Download size={16} /> JSON
            </a>
            <a className="button-link" href={exportUrl("csv")}>
              <Download size={16} /> CSV
            </a>
          </div>
        </header>

        {message ? (
          <div className="notice">
            <AlertCircle size={16} /> {message}
          </div>
        ) : null}

        {tab === "dashboard" && (
          <Dashboard
            errorRows={errorRows}
            job={job}
            onResolveRow={onResolveRow}
            resolvingRowId={resolvingRowId}
            resolvedCount={resolvedCount}
            results={results}
          />
        )}
        {tab === "results" && (
          <ResultsView
            page={paginatedResults.page}
            pageRows={paginatedResults.pageRows}
            pageSize={paginatedResults.pageSize}
            query={query}
            queryField={queryField}
            setPage={setResultsPage}
            setQueryField={setQueryField}
            setQuery={setQuery}
            setSortDirection={setSortDirection}
            setSortField={setSortField}
            setStatusFilter={setStatusFilter}
            sortDirection={sortDirection}
            sortField={sortField}
            statusFilter={statusFilter}
            totalPages={paginatedResults.totalPages}
            totalRows={paginatedResults.totalRows}
            onResolveRow={onResolveRow}
            resolvingRowId={resolvingRowId}
          />
        )}
        {tab === "cache" && (
          <CacheView
            articleCount={results.length}
            cacheHits={job.cache_hit_count ?? 0}
            resolvedCount={resolvedCount}
          />
        )}
        {tab === "settings" && <SettingsView payload={payload} />}
      </section>
    </main>
  );
}

function Dashboard({
  errorRows,
  job,
  onResolveRow,
  resolvingRowId,
  resolvedCount,
  results
}: {
  errorRows: ResultRow[];
  job: JobState;
  onResolveRow: (row: ResultRow) => void;
  resolvingRowId: number | null;
  resolvedCount: number;
  results: ResultRow[];
}) {
  return (
    <>
      <section className="metrics">
        <Metric label="已处理" value={job.processed_count ?? 0} />
        <Metric label="成功" value={job.success_count ?? 0} />
        <Metric label="错误" value={job.error_count ?? 0} />
        <Metric label="缓存命中" value={job.cache_hit_count ?? 0} />
        <Metric label="已解析" value={resolvedCount} />
        <Metric label="延迟" value={`${job.delay_seconds ?? 0}s`} />
      </section>

      <section className="current-band">
        <div>
          <p>当前 URL</p>
          <strong>{job.current_url ?? job.start_url ?? "-"}</strong>
        </div>
        <div>
          <p>最近错误</p>
          <strong>{job.error ?? "-"}</strong>
        </div>
      </section>

      <ResultsTable
        rows={getRecentResults(results, 5)}
        onResolveRow={onResolveRow}
        resolvingRowId={resolvingRowId}
      />

      <section className="error-panel">
        <h3>错误记录</h3>
        {errorRows.length === 0 ? (
          <p className="muted">暂无错误</p>
        ) : (
          errorRows.map((row) => (
            <div className="error-line" key={row.id}>
              <span>{row.article_url}</span>
              <strong>{row.error}</strong>
            </div>
          ))
        )}
      </section>
    </>
  );
}

function ResultsView({
  page,
  pageRows,
  pageSize,
  query,
  queryField,
  setPage,
  setQueryField,
  setQuery,
  setSortDirection,
  setSortField,
  setStatusFilter,
  sortDirection,
  sortField,
  statusFilter,
  totalPages,
  totalRows,
  onResolveRow,
  resolvingRowId
}: {
  page: number;
  pageRows: ResultRow[];
  pageSize: number;
  query: string;
  queryField: ResultFilterField;
  setPage: (value: number) => void;
  setQueryField: (value: ResultFilterField) => void;
  setQuery: (value: string) => void;
  setSortDirection: (value: ResultSortDirection) => void;
  setSortField: (value: ResultSortField) => void;
  setStatusFilter: (value: string) => void;
  sortDirection: ResultSortDirection;
  sortField: ResultSortField;
  statusFilter: string;
  totalPages: number;
  totalRows: number;
  onResolveRow: (row: ResultRow) => void;
  resolvingRowId: number | null;
}) {
  return (
    <>
      <div className="filter-row">
        <label className="search-box">
          <Search size={16} />
          <input
            placeholder="搜索标题、URL、错误"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <select
          value={queryField}
          onChange={(event) => setQueryField(event.target.value as ResultFilterField)}
        >
          <option value="all">全部字段</option>
          <option value="title">标题</option>
          <option value="article_url">文章 URL</option>
          <option value="download_href">下载 href</option>
          <option value="resolved_download_url">最终 URL</option>
          <option value="error">错误</option>
        </select>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">全部状态</option>
          <option value="fetched">fetched</option>
          <option value="resolving">resolving</option>
          <option value="resolved">resolved</option>
          <option value="error">error</option>
        </select>
        <select
          value={sortField}
          onChange={(event) => setSortField(event.target.value as ResultSortField)}
        >
          <option value="record_time">记录时间</option>
          <option value="title">标题</option>
        </select>
        <select
          value={sortDirection}
          onChange={(event) => setSortDirection(event.target.value as ResultSortDirection)}
        >
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
      </div>
      <ResultsTable rows={pageRows} onResolveRow={onResolveRow} resolvingRowId={resolvingRowId} />
      <div className="pagination-row">
        <span>
          第 {page} / {totalPages} 页，当前每页 {pageSize} 条，共 {totalRows} 条
        </span>
        <div>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} type="button">
            上一页
          </button>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} type="button">
            下一页
          </button>
        </div>
      </div>
    </>
  );
}

function CacheView({
  articleCount,
  cacheHits,
  resolvedCount
}: {
  articleCount: number;
  cacheHits: number;
  resolvedCount: number;
}) {
  return (
    <section className="cache-grid">
      <Metric label="文章缓存" value={articleCount} />
      <Metric label="解析缓存" value={resolvedCount} />
      <Metric label="本次命中" value={cacheHits} />
    </section>
  );
}

function SettingsView({ payload }: { payload: StartJobPayload }) {
  return (
    <section className="settings-list">
      <div><span>默认代理</span><strong>{payload.proxy ?? "-"}</strong></div>
      <div><span>文章处理代理</span><strong>{payload.resolver_proxy ? "已配置" : "-"}</strong></div>
      <div><span>Nikki 策略组</span><strong>{payload.nikki_proxy_group ?? "-"}</strong></div>
      <div><span>默认页数</span><strong>{payload.max_pages}</strong></div>
      <div><span>默认延迟</span><strong>{payload.delay_seconds}s</strong></div>
      <div><span>最终 URL 解析</span><strong>{payload.resolve_final_url ? "开启" : "关闭"}</strong></div>
      <div><span>下载跳转 Worker 改写</span><strong>{payload.rewrite_resolver_url ? "开启" : "关闭"}</strong></div>
    </section>
  );
}

function ResultsTable({
  rows,
  onResolveRow,
  resolvingRowId
}: {
  rows: ResultRow[];
  onResolveRow: (row: ResultRow) => void;
  resolvingRowId: number | null;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>标题</th>
            <th>记录时间</th>
            <th>文章 URL</th>
            <th>下载 href</th>
            <th>最终 URL</th>
            <th>状态</th>
            <th>错误</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="empty-cell">暂无结果</td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.id}>
                <td>{row.title ?? "-"}</td>
                <td>{formatRecordTime(resultRecordTime(row))}</td>
                <td><a href={row.article_url} target="_blank">{row.article_url}</a></td>
                <td>{row.download_href ?? "-"}</td>
                <td>{row.resolved_download_url ?? "-"}</td>
                <td><span className={`status-pill ${row.status}`}>{row.status}</span></td>
                <td>{row.error ?? "-"}</td>
                <td>
                  {row.download_href ? (
                    <button
                      className="compact-button"
                      disabled={resolvingRowId === row.id}
                      onClick={() => onResolveRow(row)}
                      type="button"
                    >
                      <RefreshCw size={14} /> {resolvingRowId === row.id ? "解析中" : "重新解析"}
                    </button>
                  ) : "-"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function formatRecordTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Toggle({
  checked,
  label,
  onChange
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input checked={checked} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function statusLabel(status: JobState["status"]): string {
  const labels: Record<JobState["status"], string> = {
    idle: "空闲",
    pending: "等待中",
    running: "运行中",
    pausing: "暂停中",
    paused: "已暂停",
    completed: "已完成",
    failed: "失败",
    stopped: "已停止",
    migrated: "迁移记录"
  };
  return labels[status] ?? status;
}

export default App;
