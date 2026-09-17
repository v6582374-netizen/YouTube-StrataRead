import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import "./styles.css";

type LibrarySnapshot = {
  workspace: { label: string; status: string };
  counts: { inbox: number; to_read: number; reading: number; read: number };
  inbox: unknown[];
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

async function loadSnapshot(): Promise<LibrarySnapshot> {
  return invoke<LibrarySnapshot>("library_snapshot");
}

function App() {
  const [snapshot, setSnapshot] = useState<LibrarySnapshot | null>(null);
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [showConnection, setShowConnection] = useState(false);
  const [view, setView] = useState<"inbox" | "sources">("inbox");
  const [sources, setSources] = useState<SubscriptionSource[]>([]);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function hydrateConnection(): Promise<ConnectionStatus> {
    const status = await invoke<ConnectionStatus>("connection_status");
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
        setSnapshot(await loadSnapshot());
        await hydrateConnection();
      } catch (cause) {
        setMessage(cause instanceof Error ? cause.message : String(cause));
      }
    })();
  }, []);

  const counts = snapshot?.counts ?? { inbox: 0, to_read: 0, reading: 0, read: 0 };

  async function inspectConnection() {
    setBusy(true);
    setMessage(null);
    try {
      await hydrateConnection();
      setShowConnection(true);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function configure(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const status = await invoke<ConnectionStatus>("configure_connection", {
        clientId,
        clientSecret,
      });
      setConnection(status);
      setClientSecret("");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function authorize() {
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
        <button className="connect-button" onClick={() => void inspectConnection()} disabled={busy}>
          {connection?.authorized ? `已连接 · ${connection.subscription_count} 个订阅` : "连接 YouTube"}
        </button>
      </header>
      <section className="workspace">
        <nav className="sidebar" aria-label="资料库导航">
          <p>资料库</p>
          <button className={view === "inbox" ? "active" : ""} onClick={() => setView("inbox")}>收件箱 <b>{counts.inbox}</b></button>
          <button>待读 <b>{counts.to_read}</b></button>
          <button>已读 <b>{counts.read}</b></button>
          <button>全部稿件</button>
          <p className="source-heading">来源</p>
          <button className={view === "sources" ? "active" : ""} onClick={() => setView("sources")}>订阅频道 <b>{connection?.subscription_count ?? 0}</b></button>
        </nav>
        <section className="library">
          <div className="library-heading">
            <div>
              <p>本地资料库</p>
              <h1>{view === "inbox" ? "收件箱" : "订阅频道"}</h1>
              <span>{message ?? (view === "inbox" ? "连接 YouTube 后，已准备的稿件会出现在这里。" : "已从你的 YouTube 账号导入的本地来源。")}</span>
            </div>
            <span className="quiet-pulse" title="活动将在后续批次中显示" />
          </div>
          {view === "inbox" ? (
            <div className="empty-state">
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
            {!connection?.configured ? (
              <form onSubmit={(event) => void configure(event)}>
                <label>Google OAuth Client ID<input value={clientId} onChange={(event) => setClientId(event.target.value)} required /></label>
                <label>Google OAuth Client Secret<input type="password" value={clientSecret} onChange={(event) => setClientSecret(event.target.value)} required /></label>
                <button className="primary-button" disabled={busy}>保存到 Automic Vault</button>
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
