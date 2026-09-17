import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import "./styles.css";

type LibrarySnapshot = {
  workspace: { label: string; status: string };
  counts: { inbox: number; to_read: number; reading: number; read: number };
  inbox: unknown[];
};

type Asset = {
  video_id: string;
  channel_title: string;
  title: string;
  published_at: string;
  preparation_state: string;
  failure_reason: string | null;
  reading_state: "inbox" | "to-read" | "reading" | "read";
  manuscript_version: number | null;
};

type Inspection = Asset & { source_trace: { video_url: string; transcript_available: boolean; transcript_path: string | null } };

type Activity = {
  queued: number;
  acquiring: number;
  generating: number;
  ready: number;
  unavailable: number;
  failed: number;
  drain_paused: boolean;
  volume: { transcript_characters: number; manuscript_characters: number };
  cost_estimate: number | null;
  failures: { video_id: string; title: string; state: string; reason: string | null }[];
  batch: { limit: number; completed: number };
};

type ConnectionStatus = {
  configured: boolean;
  authorized: boolean;
  subscription_count: number;
};

type SubscriptionSource = {
  channel_id: string;
  title: string;
  description: string;
  thumbnail_url: string | null;
  subscribed_at: string | null;
};

// Coalesce concurrent startup reads (including StrictMode's effect replay).
let pendingConnection: Promise<ConnectionStatus> | null = null;
function loadConnectionStatus(): Promise<ConnectionStatus> {
  if (!pendingConnection) {
    pendingConnection = invoke<ConnectionStatus>("connection_status").finally(() => {
      pendingConnection = null;
    });
  }
  return pendingConnection;
}

async function loadSnapshot(): Promise<LibrarySnapshot> {
  return invoke<LibrarySnapshot>("library_snapshot");
}

function App() {
  const [snapshot, setSnapshot] = useState<LibrarySnapshot | null>(null);
  const connectionRevision = useRef(0);
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [showConnection, setShowConnection] = useState(false);
  const [view, setView] = useState<"inbox" | "to-read" | "read" | "all" | "sources">("inbox");
  const [sources, setSources] = useState<SubscriptionSource[]>([]);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Inspection | null>(null);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [showActivity, setShowActivity] = useState(false);
  const [query, setQuery] = useState("");
  const [includeTranscript, setIncludeTranscript] = useState(false);
  const [channelFilter, setChannelFilter] = useState("");
  const [preparationFilter, setPreparationFilter] = useState("");
  const [publishedAfter, setPublishedAfter] = useState("");
  const [publishedBefore, setPublishedBefore] = useState("");

  async function refreshInbox(backfill = false) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await invoke<{ discovered: number; truncated: boolean }>(
        backfill ? "collection_backfill_updates" : "collection_refresh_updates",
        backfill ? { days: 7, limit: 100 } : {},
      );
      await refreshLibrary();
      setMessage(result.truncated ? "已达到本轮导入上限。" : `发现 ${result.discovered} 条新更新。`);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function refreshLibrary(readingState?: string) {
    const filters: Record<string, string | boolean | number> = {};
    if (readingState) filters.reading_state = readingState;
    if (query.trim()) {
      filters.query = query;
      filters.include_transcript = includeTranscript;
    }
    if (channelFilter) filters.channel_id = channelFilter;
    if (preparationFilter) filters.preparation_state = preparationFilter;
    if (publishedAfter) filters.published_after = new Date(publishedAfter).getTime() / 1000;
    if (publishedBefore) filters.published_before = new Date(`${publishedBefore}T23:59:59`).getTime() / 1000;
    const result = await invoke<{ assets: Asset[] }>("library_list", { filters });
    setAssets(result.assets);
    setSelected((current) => current && result.assets.some((asset) => asset.video_id === current.video_id) ? current : null);
    setActivity(await invoke<Activity>("activity_snapshot"));
    setSnapshot(await loadSnapshot());
  }

  async function hydrateConnection(): Promise<ConnectionStatus> {
    const revision = connectionRevision.current;
    const status = await loadConnectionStatus();
    if (revision !== connectionRevision.current) return status;
    setConnection(status);
    if (status.subscription_count > 0) {
      const result = await invoke<{ sources: SubscriptionSource[] }>("subscription_sources");
      setSources(result.sources);
    }
    return status;
  }

  useEffect(() => {
    void (async () => {
      try {
        await Promise.all([refreshLibrary(), hydrateConnection()]);
      } catch (cause) {
        setMessage(cause instanceof Error ? cause.message : String(cause));
      }
    })();
  }, []);

  useEffect(() => {
    let active = true;
    let unlisten: (() => void) | undefined;
    void listen<Activity>("activity-snapshot", () => {
      void refreshLibrary(view === "all" || view === "sources" ? undefined : view).catch(() => undefined);
    }).then((stop) => { if (active) unlisten = stop; else stop(); });
    return () => { active = false; unlisten?.(); };
  }, [view, query, includeTranscript, channelFilter, preparationFilter, publishedAfter, publishedBefore]);

  const counts = snapshot?.counts ?? { inbox: 0, to_read: 0, reading: 0, read: 0 };

  async function selectView(next: "inbox" | "to-read" | "read" | "all" | "sources") {
    setView(next);
    setSelected(null);
    if (next !== "sources") await refreshLibrary(next === "all" ? undefined : next);
  }

  async function inspect(asset: Asset) {
    setSelected(await invoke<Inspection>("library_inspect", { videoId: asset.video_id }));
  }

  async function setReadingState(readingState: Asset["reading_state"]) {
    if (!selected) return;
    await invoke("library_set_reading_state", { videoId: selected.video_id, readingState });
    await refreshLibrary(view === "all" || view === "sources" ? undefined : view);
  }

  async function copyMarkdown() {
    if (!selected) return;
    const document = await invoke<{ markdown: string }>("document_get", { videoId: selected.video_id });
    await navigator.clipboard.writeText(document.markdown);
    setMessage("Markdown 已复制。");
  }

  function inspectConnection() {
    setShowConnection(true);
    setMessage(null);
  }

  async function configure(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    connectionRevision.current += 1;
    setBusy(true);
    setMessage("正在保存凭据，请在 Automic Vault 中完成授权…");
    try {
      const status = await invoke<ConnectionStatus>("configure_connection", {
        clientId,
        clientSecret,
      });
      setConnection(status);
      setClientSecret("");
      setMessage("凭据已保存，现在可以授权 YouTube。");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function authorize() {
    connectionRevision.current += 1;
    setBusy(true);
    setMessage("正在浏览器中等待 Google 授权…");
    try {
      const status = await invoke<ConnectionStatus>("authorize_connection");
      setConnection(status);
      const result = await invoke<{ sources: SubscriptionSource[] }>("subscription_sources");
      setSources(result.sources);
      setView("sources");
      setMessage("订阅来源已导入本地资料库。");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    connectionRevision.current += 1;
    setBusy(true);
    try {
      setConnection(await invoke<ConnectionStatus>("disconnect_connection"));
      setMessage("YouTube 授权已断开；已导入的本地来源仍被保留。");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="toolbar">
        <div className="window-controls" aria-hidden="true"><i /><i /><i /></div>
        <strong>视频资料库</strong>
        <span className="workspace-status">{snapshot?.workspace.label ?? "正在连接本地工作区"}</span>
        <button className="activity-button" onClick={() => setShowActivity(!showActivity)}><span className={`quiet-pulse ${activity?.acquiring || activity?.generating ? "working" : ""}`} />活动 {activity ? activity.queued + activity.acquiring + activity.generating : 0}</button>
        <button className="connect-button" onClick={() => void inspectConnection()} disabled={busy}>
          {connection?.authorized ? `已连接 · ${connection.subscription_count} 个订阅` : "连接 YouTube"}
        </button>
        {showActivity && <section className="activity-panel"><strong>批处理活动</strong><p>{activity?.acquiring ? "正在获取字幕" : activity?.generating ? "正在生成稿件" : "等待下一项工作"}</p><dl><dt>批次进度</dt><dd>{activity ? `${activity.batch.completed}/${activity.batch.limit}` : "0/100"}</dd><dt>排队</dt><dd>{activity?.queued ?? 0}</dd><dt>完成</dt><dd>{activity?.ready ?? 0}</dd><dt>失败</dt><dd>{activity?.failed ?? 0}</dd><dt>不可用</dt><dd>{activity?.unavailable ?? 0}</dd><dt>字幕字符</dt><dd>{activity?.volume.transcript_characters ?? 0}</dd><dt>稿件字符</dt><dd>{activity?.volume.manuscript_characters ?? 0}</dd><dt>成本</dt><dd>{activity?.cost_estimate ?? "未估算"}</dd></dl>{activity?.failures.length ? <div className="activity-failures">{activity.failures.map((failure) => <p className="activity-failure" key={failure.video_id}>{failure.title}：{failure.reason || failure.state}{failure.state === "failed" && <button disabled={busy} onClick={() => void (async () => { await invoke("activity_retry", { videoId: failure.video_id }); await refreshLibrary(); })()}>重试此项</button>}</p>)}</div> : null}<button disabled={busy} onClick={() => void (async () => { await invoke(activity?.drain_paused ? "activity_resume" : "activity_drain_pause"); await refreshLibrary(); })()}>{activity?.drain_paused ? "恢复批次" : "排空后暂停"}</button><button disabled={busy || !activity?.failed} onClick={() => void (async () => { await invoke("activity_retry_all_failed"); await refreshLibrary(); })()}>重试全部失败项</button></section>}
      </header>
      <section className="workspace">
        <nav className="sidebar" aria-label="资料库导航">
          <p>资料库</p>
          <button className={view === "inbox" ? "active" : ""} onClick={() => void selectView("inbox")}>收件箱 <b>{counts.inbox}</b></button>
          <button className={view === "to-read" ? "active" : ""} onClick={() => void selectView("to-read")}>待读 <b>{counts.to_read}</b></button>
          <button className={view === "read" ? "active" : ""} onClick={() => void selectView("read")}>已读 <b>{counts.read}</b></button>
          <button className={view === "all" ? "active" : ""} onClick={() => void selectView("all")}>全部稿件</button>
          <p className="source-heading">来源</p>
          <button className={view === "sources" ? "active" : ""} onClick={() => void selectView("sources")}>订阅频道 <b>{connection?.subscription_count ?? 0}</b></button>
        </nav>
        <section className="library">
          <div className="library-heading">
            <div>
              <p>本地资料库</p>
              <h1>{view === "sources" ? "订阅频道" : view === "to-read" ? "待读" : view === "read" ? "已读" : view === "all" ? "全部稿件" : "收件箱"}</h1>
              <span>{message ?? (view === "sources" ? "已从你的 YouTube 账号导入的本地来源。" : "新更新会在本机完成准备并保留状态。")}</span>
            </div>
            <div className="inbox-actions">
              {view !== "sources" && <><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void refreshLibrary(view === "all" ? undefined : view)} placeholder="搜索稿件" /><label><input type="checkbox" checked={includeTranscript} onChange={(event) => setIncludeTranscript(event.target.checked)} /> 搜索原始字幕</label><select value={channelFilter} onChange={(event) => setChannelFilter(event.target.value)} aria-label="频道筛选"><option value="">全部频道</option>{sources.map((source) => <option key={source.channel_id} value={source.channel_id}>{source.title}</option>)}</select><select value={preparationFilter} onChange={(event) => setPreparationFilter(event.target.value)} aria-label="准备状态筛选"><option value="">全部状态</option><option value="queued">排队</option><option value="acquiring">获取中</option><option value="generating">生成中</option><option value="ready">就绪</option><option value="unavailable">不可用</option><option value="failed">失败</option></select><input type="date" value={publishedAfter} onChange={(event) => setPublishedAfter(event.target.value)} aria-label="起始日期" /><input type="date" value={publishedBefore} onChange={(event) => setPublishedBefore(event.target.value)} aria-label="结束日期" /><button onClick={() => void refreshLibrary(view === "all" ? undefined : view)} disabled={busy}>搜索</button></>}
              <button onClick={() => void refreshInbox()} disabled={busy}>刷新更新</button>
              <button onClick={() => void refreshInbox(true)} disabled={busy}>导入最近 7 天</button>
            </div>
          </div>
          {view !== "sources" ? (
            assets.length > 0 ? (
              <div className="library-body"><div className="candidate-list">
                {assets.map((item) => <button className={`candidate-card ${selected?.video_id === item.video_id ? "selected" : ""}`} onClick={() => void inspect(item)} key={item.video_id}><span>{item.preparation_state}</span><h2>{item.title}</h2><p>{item.channel_title} · {item.published_at} · {item.reading_state}{item.manuscript_version ? ` · v${item.manuscript_version}` : ""}</p>{item.failure_reason && <small>{item.failure_reason}</small>}</button>)}
              </div><aside className="inspector">{selected ? <><p className="eyebrow">来源追溯</p><h2>{selected.title}</h2><p>{selected.channel_title}</p><dl><dt>准备状态</dt><dd>{selected.preparation_state}</dd><dt>阅读状态</dt><dd>{selected.reading_state}</dd><dt>稿件版本</dt><dd>{selected.manuscript_version ? `v${selected.manuscript_version}` : "尚未生成"}</dd><dt>原始视频</dt><dd><a href={selected.source_trace.video_url} target="_blank" rel="noreferrer" title={selected.source_trace.video_url}>打开来源</a></dd><dt>定时字幕</dt><dd>{selected.source_trace.transcript_available ? "已保留" : "不可用"}</dd></dl>{selected.manuscript_version && <div className="inspector-actions"><button disabled={busy} onClick={() => void copyMarkdown()}>复制 Markdown</button><button disabled={busy} onClick={() => void invoke("document_open", { videoId: selected.video_id })}>用默认应用打开</button></div>}<div className="inspector-actions"><button disabled={busy} onClick={() => void setReadingState("to-read")}>移至待读</button>{selected.preparation_state === "failed" && <button disabled={busy} onClick={() => void (async () => { await invoke("activity_retry", { videoId: selected.video_id }); await refreshLibrary(); })()}>重试此项</button>}<button disabled={busy} onClick={() => void setReadingState("read")}>标为已读</button><button disabled={busy} onClick={() => void (async () => { await invoke("library_regenerate", { videoId: selected.video_id }); await refreshLibrary(); })()}>生成新版本</button><button className="danger" disabled={busy} onClick={() => void (async () => { await invoke("library_delete", { videoId: selected.video_id }); await refreshLibrary(); })()}>删除资料</button></div></> : <>选择一项资料以查看来源和稿件交接操作。</>}</aside></div>
            ) : <div className="empty-state">
              <div className="markdown-mark">MD</div>
              <h2>资料库已经就绪</h2>
              <p>配置个人 YouTube 订阅源后，新的更新将以 Markdown 稿件进入这里。</p>
            </div>
          ) : (
            <div className="source-list">
              {sources.length === 0 ? <p>尚未导入订阅来源。</p> : sources.map((source) => (
                <article key={source.channel_id} className="source-card">
                  <div><span className="source-avatar">{source.title.slice(0, 1).toUpperCase()}</span></div>
                  <div><h2>{source.title}</h2><p>{source.description || "没有频道说明"}</p></div>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
      {showConnection && (
        <div className="connection-scrim" role="presentation">
          <section className="connection-panel" role="dialog" aria-modal="true" aria-label="连接 YouTube">
            <button className="close-button" onClick={() => setShowConnection(false)} aria-label="关闭">×</button>
            <p className="eyebrow">个人订阅源</p>
            <h2>连接 YouTube</h2>
            <p>使用你自己的 Google OAuth 客户端。凭据只存入本机 Automic Vault。</p>
            {message && <p role="status" aria-live="polite">{message}</p>}
            {!connection?.configured ? (
              <form onSubmit={(event) => void configure(event)}>
                <label>Google OAuth Client ID<input value={clientId} onChange={(event) => setClientId(event.target.value)} required /></label>
                <label>Google OAuth Client Secret<input type="password" value={clientSecret} onChange={(event) => setClientSecret(event.target.value)} required /></label>
                <button className="primary-button" disabled={busy} aria-busy={busy}>{busy ? "正在保存…" : "保存到 Automic Vault"}</button>
              </form>
            ) : !connection.authorized ? (
              <button className="primary-button" onClick={() => void authorize()} disabled={busy}>在浏览器中授权并导入订阅</button>
            ) : (
              <div className="connection-ready">
                <strong>已导入 {connection.subscription_count} 个订阅来源</strong>
                <button onClick={() => void disconnect()} disabled={busy}>断开授权</button>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
