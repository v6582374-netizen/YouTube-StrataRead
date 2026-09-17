import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import "./styles.css";

type LibrarySnapshot = {
  workspace: { label: string; status: string };
  counts: { inbox: number; to_read: number; reading: number; read: number };
  inbox: unknown[];
};

async function loadSnapshot(): Promise<LibrarySnapshot> {
  return invoke<LibrarySnapshot>("library_snapshot");
}

function App() {
  const [snapshot, setSnapshot] = useState<LibrarySnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadSnapshot().then(setSnapshot).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : String(cause));
    });
  }, []);

  const counts = snapshot?.counts ?? { inbox: 0, to_read: 0, reading: 0, read: 0 };

  return (
    <main className="app-shell">
      <header className="toolbar">
        <div className="window-controls" aria-hidden="true"><i /><i /><i /></div>
        <strong>视频资料库</strong>
        <span className="workspace-status">{snapshot?.workspace.label ?? "正在连接本地工作区"}</span>
      </header>
      <section className="workspace">
        <nav className="sidebar" aria-label="资料库导航">
          <p>资料库</p>
          <button className="active">收件箱 <b>{counts.inbox}</b></button>
          <button>待读 <b>{counts.to_read}</b></button>
          <button>已读 <b>{counts.read}</b></button>
          <button>全部稿件</button>
        </nav>
        <section className="library">
          <div className="library-heading">
            <div>
              <p>本地资料库</p>
              <h1>收件箱</h1>
              <span>{error ?? "连接 YouTube 后，已准备的稿件会出现在这里。"}</span>
            </div>
            <span className="quiet-pulse" title="活动将在后续批次中显示" />
          </div>
          <div className="empty-state">
            <div className="markdown-mark">MD</div>
            <h2>资料库已经就绪</h2>
            <p>配置个人 YouTube 订阅源后，新的更新将以 Markdown 稿件进入这里。</p>
          </div>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
