import { useCallback, useEffect, useRef, useState } from "react";
import { youtubeCapability as call } from "../api";
import { Icon } from "./Icon";
import { YouTubeIcon } from "./YouTubeIcon";
import { Dialog } from "./youtube/Dialog";
import { DocumentViews, ChannelAvatar } from "./youtube/DocumentViews";
import {
  Activity,
  Asset,
  Connection,
  Inspection,
  Layout,
  Preferences,
  Prompt,
  Source,
  dateLabel,
} from "./youtube/types";
import "./youtube/youtube.css";

const layoutKey = "edison:youtube:layout";
const layouts: [Layout, string][] = [
  ["timeline", "时间流"],
  ["library", "文档库"],
  ["channels", "频道索引"],
];
const errorMessage = (e: unknown) =>
  e instanceof Error ? e.message : String(e);
function savedLayout(): Layout {
  try {
    const value = localStorage.getItem(layoutKey);
    return layouts.some(([k]) => k === value) ? (value as Layout) : "timeline";
  } catch {
    return "timeline";
  }
}

export function YouTubeView({
  onModelSettings,
}: {
  onModelSettings: () => void;
}) {
  const [layout, setLayout] = useState<Layout>(savedLayout);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [prefs, setPrefs] = useState<Preferences>({
    sources: [],
    excluded_channels: [],
  });
  const [activity, setActivity] = useState<Activity | null>(null);
  const [query, setQuery] = useState("");
  const [period, setPeriod] = useState("7");
  const [channel, setChannel] = useState("");
  const [unread, setUnread] = useState(false);
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState<
    "channels" | "prompt" | "connection" | "document" | null
  >(null);
  const [panelMessage, setPanelMessage] = useState("");
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelReady, setPanelReady] = useState(false);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [channelSearch, setChannelSearch] = useState("");
  const [prompt, setPrompt] = useState("");
  const [defaultPrompt, setDefaultPrompt] = useState("");
  const [savedPrompt, setSavedPrompt] = useState("");
  const [connection, setConnection] = useState<Connection | null>(null);
  const [connectionChecking, setConnectionChecking] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const connectionEpoch = useRef(0);
  const connectionRequest = useRef<Promise<Connection> | null>(null);
  const checkConnection = async () => {
    const epoch = connectionEpoch.current;
    setConnectionChecking(true);
    setConnectionError(false);
    if (!connectionRequest.current) {
      const request = call<Connection>("connection.status");
      connectionRequest.current = request;
      void request
        .finally(() => {
          if (connectionRequest.current === request)
            connectionRequest.current = null;
        })
        .catch(() => {});
    }
    try {
      const result = await connectionRequest.current;
      if (epoch === connectionEpoch.current) setConnection(result);
      return result;
    } catch (error) {
      if (epoch === connectionEpoch.current) {
        setConnection(null);
        setConnectionError(true);
      }
      throw error;
    } finally {
      if (epoch === connectionEpoch.current) setConnectionChecking(false);
    }
  };
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [selected, setSelected] = useState<Inspection | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pulse, setPulse] = useState(false);
  const revision = useRef(0),
    panelRevision = useRef(0);
  const pulseRef = useRef<HTMLDivElement>(null);
  const preferences = useCallback(async () => {
    const value = await call<Preferences>("collection.preferences");
    setPrefs(value);
    return value;
  }, []);
  const refresh = useCallback(async () => {
    const version = ++revision.current;
    const filters: Record<string, unknown> = {
      query,
      documents_only: true,
      unread_only: unread,
    };
    if (channel) filters.channel_id = channel;
    if (period === "custom") {
      if (after)
        filters.published_after =
          new Date(`${after}T00:00:00`).getTime() / 1000;
      if (before)
        filters.published_before =
          new Date(`${before}T23:59:59`).getTime() / 1000;
      if (after && before && after > before) {
        setMessage("开始日期不能晚于结束日期。");
        setLoading(false);
        return;
      }
    } else if (period !== "all") {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      start.setDate(start.getDate() - Number(period) + 1);
      filters.published_after = start.getTime() / 1000;
    }
    const [list, progress] = await Promise.all([
      call<{ assets: Asset[] }>("library.list", filters),
      call<Activity>("activity.snapshot"),
    ]);
    if (version !== revision.current) return;
    setAssets(list.assets);
    setSelected((current) => {
      if (!current) return current;
      const latest = list.assets.find(
        (asset) => asset.video_id === current.video_id,
      );
      return latest ? { ...current, ...latest } : current;
    });
    setActivity(progress);
    setLoading(false);
  }, [query, period, channel, unread, after, before]);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const update = async () => {
      try {
        await refresh();
      } catch (e) {
        if (alive) {
          setMessage(errorMessage(e));
          setLoading(false);
        }
      }
      if (alive) timer = setTimeout(update, 4000);
    };
    void update();
    return () => {
      alive = false;
      revision.current++;
      clearTimeout(timer);
    };
  }, [refresh]);
  useEffect(() => {
    void preferences().catch((e) => setMessage(errorMessage(e)));
  }, [preferences]);
  useEffect(() => {
    if (!pulse) return;
    const close = (e: PointerEvent) => {
      if (!pulseRef.current?.contains(e.target as Node)) setPulse(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPulse(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [pulse]);
  const action = async (work: () => Promise<void>) => {
    setBusy(true);
    setMessage("");
    try {
      await work();
      await refresh();
    } catch (e) {
      setMessage(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const close = () => {
    panelRevision.current++;
    setPanel(null);
    setPanelMessage("");
    setConfirmDelete(false);
  };
  const openPanel = async (kind: NonNullable<typeof panel>, asset?: Asset) => {
    const version = ++panelRevision.current;
    setPanel(kind);
    setPanelMessage("");
    setPanelLoading(true);
    setPanelReady(false);
    setSelected(null);
    setPrompt("");
    setConfirmDelete(false);
    try {
      if (kind === "channels") {
        void checkConnection().catch(() => {});
        const value = await preferences();
        if (version === panelRevision.current) {
          setExcluded(value.excluded_channels);
          setChannelSearch("");
        }
      }
      if (kind === "prompt") {
        const value = await call<Prompt>("generation.prompt");
        if (version === panelRevision.current) {
          setPrompt(value.prompt);
          setSavedPrompt(value.prompt);
          setDefaultPrompt(value.default_prompt);
        }
      }
      if (kind === "connection") {
        await checkConnection();
      }
      if (kind === "document" && asset) {
        const value = await call<Inspection>("library.inspect", {
          video_id: asset.video_id,
        });
        if (version === panelRevision.current) setSelected(value);
      }
      if (version === panelRevision.current) setPanelReady(true);
    } catch (e) {
      if (version === panelRevision.current) setPanelMessage(errorMessage(e));
    } finally {
      if (version === panelRevision.current) setPanelLoading(false);
    }
  };
  const panelAction = async (work: () => Promise<void>) => {
    setBusy(true);
    setPanelMessage("");
    try {
      await work();
    } catch (e) {
      setPanelMessage(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const connectAction = (capability: string, args = {}) =>
    panelAction(async () => {
      connectionEpoch.current++;
      connectionRequest.current = null;
      setConnectionChecking(false);
      setConnectionError(false);
      setPanelMessage(
        capability === "connection.configure"
          ? "正在保存，请在 Automic Vault 中完成授权…"
          : "请完成浏览器或 Vault 中的授权…",
      );
      const result = await call<Connection>(capability, args);
      setConnection(result);
      setClientSecret("");
      setPanelMessage(
        capability === "connection.authorize"
          ? `YouTube 已连接，已导入 ${result.subscription_count} 个订阅。`
          : capability === "connection.disconnect"
            ? "YouTube 授权已断开，已有文档仍保留。"
            : "客户端已保存，请继续在浏览器中授权 YouTube。",
      );
      await preferences();
    });
  const selectLayout = (value: Layout) => {
    setLayout(value);
    try {
      localStorage.setItem(layoutKey, value);
    } catch {
      /* Private browsing does not block the switch. */
    }
  };
  const sources: Source[] = [
    ...new Map(
      [
        ...prefs.sources,
        ...assets.map((a) => ({
          channel_id: a.channel_id,
          title: a.channel_title,
        })),
      ].map((s) => [s.channel_id, s]),
    ).values(),
  ];
  const status = activity?.drain_paused
    ? "更新已暂停"
    : activity && !activity.model_ready
      ? "等待模型设置"
      : prefs.sources.length
        ? "自动更新中"
        : "尚未连接";
  const clearFilters = () => {
    setQuery("");
    setPeriod("all");
    setChannel("");
    setUnread(false);
    setAfter("");
    setBefore("");
    setMessage("");
  };
  const selectedId = selected?.video_id;
  return (
    <main className="yp-main" aria-label="YouTube 资料库">
      <header className="yp-head">
        <div className="yp-header">
          <h1>
            <YouTubeIcon size={25} />
            YouTube
          </h1>
          <div className="yp-tools">
            <div ref={pulseRef} style={{ position: "relative" }}>
              <button
                className="yp-sync"
                onClick={() => setPulse(!pulse)}
                aria-expanded={pulse}
                aria-controls="youtube-activity"
              >
                <span
                  className={`yp-dot ${activity?.drain_paused ? "pending" : ""}`}
                />
                {status}
              </button>
              {pulse && (
                <section
                  id="youtube-activity"
                  className="yp-popover"
                  aria-label="自动更新"
                >
                  <h2>自动更新</h2>
                  <p>
                    {activity?.drain_paused
                      ? "当前文档完成后暂停后续更新。"
                      : activity?.generating
                        ? "正在生成阅读文档。"
                        : activity?.acquiring
                          ? "正在获取字幕。"
                          : "等待新的订阅更新。"}
                  </p>
                  <div className="yp-summary">
                    <span>待处理 {activity?.queued ?? 0} 篇</span>
                    <span>已生成 {activity?.ready ?? 0} 篇</span>
                  </div>
                  {activity && !activity.model_ready && (
                    <button className="yp-btn" onClick={onModelSettings}>
                      连接生成模型
                    </button>
                  )}
                  {activity?.discovery_error && (
                    <p>{activity.discovery_error}</p>
                  )}
                  {activity?.failures.map((f) => (
                    <div className="yp-job" key={f.video_id}>
                      <div>
                        {f.title}
                        <small>{f.reason}</small>
                      </div>
                      {f.state === "failed" && (
                        <button
                          className="yp-link"
                          disabled={busy}
                          onClick={() =>
                            void action(async () => {
                              await call("activity.retry", {
                                video_id: f.video_id,
                              });
                            })
                          }
                        >
                          重试
                        </button>
                      )}
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                      className="yp-btn"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          await call(
                            activity?.drain_paused
                              ? "activity.resume"
                              : "activity.drain_pause",
                          );
                        })
                      }
                    >
                      {activity?.drain_paused
                        ? "恢复自动更新"
                        : "完成当前文档后暂停"}
                    </button>
                    {!!activity?.failed && (
                      <button
                        className="yp-btn"
                        disabled={busy}
                        onClick={() =>
                          void action(async () => {
                            await call("activity.retry_all_failed");
                          })
                        }
                      >
                        重试失败项
                      </button>
                    )}
                    <button
                      className="yp-iconbtn"
                      title="立即检查更新"
                      aria-label="立即检查更新"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          await call("collection.refresh_updates");
                          setMessage("已检查订阅更新。");
                        })
                      }
                    >
                      <Icon name="refresh" />
                    </button>
                  </div>
                </section>
              )}
            </div>
            <button
              className="yp-iconbtn yp-labeled"
              onClick={() => void openPanel("channels")}
            >
              <Icon name="sidebar" />
              订阅频道
            </button>
            <button
              className="yp-iconbtn yp-labeled"
              onClick={() => void openPanel("prompt")}
            >
              <Icon name="pencil" />
              生成规则
            </button>
          </div>
        </div>
        <div className="yp-subline">
          <strong>阅读文档</strong>
          <span>·</span>
          <span>
            {
              prefs.sources.filter(
                (s) => !prefs.excluded_channels.includes(s.channel_id),
              ).length
            }{" "}
            个频道
            {prefs.excluded_channels.length
              ? ` · 已排除 ${prefs.excluded_channels.length} 个`
              : ""}
          </span>
        </div>
        <div className="yp-filterbar">
          <label className="yp-search">
            <Icon name="search" />
            <input
              type="search"
              aria-label="搜索文档"
              placeholder="搜索文档"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="按时间筛选"
            value={period}
            onChange={(e) => {
              setPeriod(e.target.value);
              setMessage("");
            }}
          >
            <option value="7">最近 7 天</option>
            <option value="1">今天</option>
            <option value="30">最近 30 天</option>
            <option value="all">全部时间</option>
            <option value="custom">自定时间</option>
          </select>
          {layout !== "channels" && (
            <select
              aria-label="按频道筛选"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            >
              <option value="">全部频道</option>
              {sources.map((s) => (
                <option key={s.channel_id} value={s.channel_id}>
                  {s.title}
                </option>
              ))}
            </select>
          )}
          <select
            aria-label="阅读筛选"
            value={unread ? "unread" : "all"}
            onChange={(e) => setUnread(e.target.value === "unread")}
          >
            <option value="all">全部文档</option>
            <option value="unread">未读文档</option>
          </select>
          <span className="yp-count">{assets.length} 篇</span>
          <div className="yp-layouts" role="group" aria-label="呈现形式">
            {layouts.map(([value, label]) => (
              <button
                key={value}
                aria-label={label}
                title={label}
                aria-pressed={layout === value}
                onClick={() => selectLayout(value)}
              >
                <LayoutIcon kind={value} />
              </button>
            ))}
          </div>
        </div>
        {period === "custom" && (
          <div className="yp-filterbar" style={{ paddingTop: 12 }}>
            <label>
              从{" "}
              <input
                className="yp-time-input"
                type="date"
                aria-label="起始日期"
                value={after}
                onChange={(e) => {
                  setAfter(e.target.value);
                  setMessage("");
                }}
              />
            </label>
            <label>
              至{" "}
              <input
                className="yp-time-input"
                type="date"
                aria-label="结束日期"
                value={before}
                onChange={(e) => {
                  setBefore(e.target.value);
                  setMessage("");
                }}
              />
            </label>
          </div>
        )}
      </header>
      <div className="yp-content">
        {message && (
          <p className="yp-inline-status" role="status">
            {message}
          </p>
        )}
        {loading ? (
          <p className="yp-inline-status">正在加载文档…</p>
        ) : !assets.length && layout !== "channels" ? (
          <div className="yp-empty">
            <Icon name="file" size={28} />
            <h2>
              {prefs.sources.length
                ? "没有找到文档"
                : "把订阅更新，变成阅读文档"}
            </h2>
            <p>
              {prefs.sources.length
                ? "可以调整筛选，或查看自动更新的准备进度。"
                : "连接 YouTube 后，自动处理你订阅的频道。"}
            </p>
            <button
              className="yp-btn"
              onClick={
                prefs.sources.length
                  ? clearFilters
                  : () => void openPanel("connection")
              }
            >
              {prefs.sources.length ? "清除筛选" : connection?.authorized ? "已连接 YouTube" : "连接 YouTube"}
            </button>
          </div>
        ) : (
          <DocumentViews
            layout={layout}
            assets={assets}
            sources={sources}
            channel={channel}
            onChannel={setChannel}
            onSelect={(a) => void openPanel("document", a)}
            searching={!!query.trim()}
          />
        )}
      </div>
      {panel === "channels" && (
        <Dialog
          title="订阅频道"
          subtitle="默认自动生成所有订阅频道的阅读文档。"
          onClose={close}
          footer={
            <>
              <span>
                {
                  prefs.sources.filter((s) => !excluded.includes(s.channel_id))
                    .length
                }{" "}
                个频道已开启
              </span>
              <div>
                <button className="yp-btn" onClick={close}>
                  取消
                </button>{" "}
                <button
                  className="yp-btn primary"
                  disabled={busy || panelLoading || !panelReady}
                  onClick={() =>
                    void panelAction(async () => {
                      setPrefs(
                        await call<Preferences>("collection.set_exclusions", {
                          excluded_channels: excluded,
                        }),
                      );
                      close();
                      setMessage("频道设置已保存。");
                      await refresh();
                    })
                  }
                >
                  保存
                </button>
              </div>
            </>
          }
        >
          <div className="yp-inline-note">
            关闭频道后，不再领取它的新文档；正在生成的文档会完成，已有文档仍保留。新导入的订阅默认开启。
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button
              className="yp-btn"
              onClick={() => void openPanel("connection")}
            >
              {connection?.authorized && (
                <span className="yp-dot" aria-hidden="true" />
              )}
              {connection?.authorized ? "已连接 YouTube" : "连接 YouTube"}
            </button>
            <span
              role="status"
              className="yp-inline-status"
              style={{ padding: "7px 0" }}
            >
              {connectionChecking
                ? "正在确认连接状态…"
                : connectionError
                  ? "连接状态未知，请重试"
                  : connection?.authorized
                    ? `${connection.subscription_count} 个订阅`
                    : connection
                      ? "未连接"
                      : ""}
            </span>
            <button
              className="yp-btn"
              disabled={busy}
              onClick={() =>
                void panelAction(async () => {
                  await call("connection.refresh_subscriptions");
                  const next = await preferences();
                  setExcluded(next.excluded_channels);
                  setPanelMessage("订阅已同步。");
                })
              }
            >
              同步订阅
            </button>
          </div>
          <label className="yp-search">
            <Icon name="search" />
            <input
              aria-label="搜索订阅频道"
              placeholder="搜索订阅频道"
              value={channelSearch}
              onChange={(e) => setChannelSearch(e.target.value)}
            />
          </label>
          {panelLoading ? (
            <p>正在读取频道…</p>
          ) : (
            prefs.sources
              .filter((s) =>
                s.title.toLowerCase().includes(channelSearch.toLowerCase()),
              )
              .map((s) => (
                <div className="yp-channel-row" key={s.channel_id}>
                  <ChannelAvatar name={s.title} />
                  <div>
                    <strong>{s.title}</strong>
                  </div>
                  <label className="yp-switch">
                    <input
                      type="checkbox"
                      aria-label={`自动生成 ${s.title}`}
                      checked={!excluded.includes(s.channel_id)}
                      onChange={(e) =>
                        setExcluded(
                          e.target.checked
                            ? excluded.filter((x) => x !== s.channel_id)
                            : [...excluded, s.channel_id],
                        )
                      }
                    />
                    <span />
                  </label>
                </div>
              ))
          )}
          {!panelLoading && !prefs.sources.length && (
            <p className="yp-inline-status">尚未导入订阅。请先连接 YouTube。</p>
          )}
          {panelMessage && (
            <p className="yp-error" role="status">
              {panelMessage}
            </p>
          )}
        </Dialog>
      )}
      {panel === "prompt" && (
        <Dialog
          title="生成规则"
          subtitle="决定新文档如何翻译、去重与组织内容。"
          onClose={close}
          footer={
            <>
              <span>
                {prompt === savedPrompt ? "已保存的规则" : "有未保存的修改"}
              </span>
              <div>
                <button className="yp-btn" onClick={close}>
                  取消
                </button>{" "}
                <button
                  className="yp-btn primary"
                  disabled={
                    busy || panelLoading || !panelReady || !prompt.trim()
                  }
                  onClick={() =>
                    void panelAction(async () => {
                      await call("generation.set_prompt", { prompt });
                      close();
                      setMessage("生成规则已保存。");
                    })
                  }
                >
                  保存规则
                </button>
              </div>
            </>
          }
        >
          <div className="yp-inline-note">
            修改仅用于之后生成的文档。已有文档保持不变。
          </div>
          <label htmlFor="youtube-prompt">Prompt</label>
          <textarea
            id="youtube-prompt"
            className="yp-textarea"
            value={prompt}
            maxLength={64000}
            disabled={panelLoading || !panelReady}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="yp-meta">
            <button
              className="yp-link"
              disabled={panelLoading || !panelReady}
              onClick={() => setPrompt(defaultPrompt)}
            >
              使用默认规则
            </button>
            <span>{prompt.length} 字</span>
          </div>
          {panelMessage && (
            <p className="yp-error" role="status">
              {panelMessage}
            </p>
          )}
        </Dialog>
      )}
      {panel === "connection" && (
        <Dialog
          title="连接 YouTube"
          subtitle="使用个人 Google OAuth 客户端，凭据保存在 Automic Vault。"
          onClose={close}
        >
          {panelLoading ? (
            <p>正在检查连接状态…</p>
          ) : !connection?.configured ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void connectAction("connection.configure", {
                  client_id: clientId,
                  client_secret: clientSecret,
                });
              }}
            >
              <label>
                Client ID
                <input
                  className="yp-modal-field"
                  required
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                />
              </label>
              <label>
                Client Secret
                <input
                  className="yp-modal-field"
                  required
                  type="password"
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                />
              </label>
              <button
                className="yp-btn primary"
                style={{ marginTop: 16 }}
                disabled={busy}
              >
                {busy ? "正在保存…" : "保存到 Automic Vault"}
              </button>
            </form>
          ) : !connection.authorized ? (
            <button
              className="yp-btn primary"
              disabled={busy}
              onClick={() => void connectAction("connection.authorize")}
            >
              在浏览器中授权并导入订阅
            </button>
          ) : (
            <>
              <p>已连接 · {connection.subscription_count} 个订阅</p>
              <button
                className="yp-btn"
                disabled={busy}
                onClick={() => void connectAction("connection.disconnect")}
              >
                断开授权
              </button>
            </>
          )}
          <p className="yp-inline-status">
            测试模式下，请将登录邮箱加入 Google Cloud 的测试用户名单。
          </p>
          {panelMessage && (
            <p className="yp-inline-status" role="status">
              {panelMessage}
            </p>
          )}
        </Dialog>
      )}
      {panel === "document" && (
        <Dialog
          title="文档信息"
          subtitle={selected?.channel_title}
          detail
          onClose={close}
          footer={
            selected && !panelLoading ? (
              <>
                <span>
                  {selected.reading_state === "read" ? "已读" : "未读"} · v
                  {selected.manuscript_version}
                </span>
                <button
                  className="yp-link"
                  disabled={busy}
                  onClick={() =>
                    void panelAction(async () => {
                      setSelected(
                        await call<Inspection>("library.set_reading_state", {
                          video_id: selectedId,
                          reading_state:
                            selected.reading_state === "read"
                              ? "inbox"
                              : "read",
                        }),
                      );
                      await refresh();
                    })
                  }
                >
                  {selected.reading_state === "read" ? "标为未读" : "标为已读"}
                </button>
              </>
            ) : null
          }
        >
          {panelLoading ? (
            <p>正在读取文档信息…</p>
          ) : (
            selected && (
              <>
                <ChannelAvatar name={selected.channel_title} />
                <h3>{selected.title}</h3>
                <dl>
                  <dt>发布日期</dt>
                  <dd>{dateLabel(selected.published_at)}</dd>
                  <dt>来源字幕</dt>
                  <dd>
                    {selected.source_trace.transcript_available
                      ? "已保留时间戳"
                      : "暂无"}
                  </dd>
                  <dt>原始视频</dt>
                  <dd>
                    <a
                      className="yp-link"
                      href={selected.source_trace.video_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打开 YouTube
                    </a>
                  </dd>
                </dl>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <button
                    className="yp-btn primary"
                    disabled={busy}
                    onClick={() =>
                      void panelAction(async () => {
                        await call("documents.open", { video_id: selectedId });
                        setPanelMessage("已交给默认应用打开。");
                      })
                    }
                  >
                    用默认应用打开
                  </button>
                  <button
                    className="yp-btn"
                    disabled={busy}
                    onClick={() =>
                      void panelAction(async () => {
                        const d = await call<{ markdown: string }>(
                          "documents.get",
                          { video_id: selectedId },
                        );
                        await navigator.clipboard.writeText(d.markdown);
                        setPanelMessage("Markdown 已复制。");
                      })
                    }
                  >
                    <Icon name="copy" />
                    复制正文
                  </button>
                </div>
                <div style={{ display: "flex", gap: 16, marginTop: 22 }}>
                  <button
                    className="yp-link"
                    disabled={
                      busy ||
                      ["queued", "acquiring", "generating"].includes(
                        selected.preparation_state,
                      )
                    }
                    onClick={() =>
                      void panelAction(async () => {
                        setSelected(
                          await call<Inspection>("library.regenerate", {
                            video_id: selectedId,
                          }),
                        );
                        setPanelMessage("已排队生成新版本，旧版本仍保留。");
                        await refresh();
                      })
                    }
                  >
                    生成新版本
                  </button>
                  <button
                    className="yp-link"
                    disabled={busy}
                    onClick={() => setConfirmDelete(true)}
                  >
                    删除文档
                  </button>
                </div>
                {confirmDelete && (
                  <div className="yp-inline-note" style={{ marginTop: 16 }}>
                    删除这份资料及全部稿件和字幕？
                    <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                      <button
                        className="yp-btn"
                        onClick={() => setConfirmDelete(false)}
                      >
                        取消
                      </button>
                      <button
                        className="yp-btn"
                        disabled={busy}
                        onClick={() =>
                          void panelAction(async () => {
                            await call("library.delete", {
                              video_id: selectedId,
                            });
                            close();
                            await refresh();
                          })
                        }
                      >
                        确认删除
                      </button>
                    </div>
                  </div>
                )}
              </>
            )
          )}
          {panelMessage && (
            <p className="yp-inline-status" role="status">
              {panelMessage}
            </p>
          )}
        </Dialog>
      )}
    </main>
  );
}
function LayoutIcon({ kind }: { kind: Layout }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      aria-hidden="true"
    >
      {kind === "timeline" ? (
        <>
          <path d="M6 4h11M6 10h11M6 16h11" />
          <circle cx="2.5" cy="4" r=".8" />
          <circle cx="2.5" cy="10" r=".8" />
          <circle cx="2.5" cy="16" r=".8" />
        </>
      ) : kind === "library" ? (
        <>
          <rect x="2" y="2" width="6" height="6" rx="1" />
          <rect x="12" y="2" width="6" height="6" rx="1" />
          <rect x="2" y="12" width="6" height="6" rx="1" />
          <rect x="12" y="12" width="6" height="6" rx="1" />
        </>
      ) : (
        <>
          <rect x="2" y="2" width="16" height="16" rx="2" />
          <path d="M8 2v16M11 6h4M11 10h4M11 14h4" />
        </>
      )}
    </svg>
  );
}
