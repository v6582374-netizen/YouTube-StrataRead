import { useCallback, useEffect, useRef, useState } from "react";
import { youtubeCapability as call } from "../api";
import { YouTubeIcon } from "./YouTubeIcon";

type ReadingState = "inbox" | "to-read" | "reading" | "read";
type Asset = { video_id: string; channel_id: string; channel_title: string; title: string; url: string; published_at: string; preparation_state: string; failure_reason: string | null; reading_state: ReadingState; manuscript_version: number | null };
type Inspection = Asset & { source_trace: { video_url: string; transcript_available: boolean }; generation_records: { manuscript_version: number; created_at: number }[] };
type Activity = { queued: number; acquiring: number; generating: number; ready: number; failed: number; unavailable: number; drain_paused: boolean; batch: { completed: number; limit: number }; model: string; model_ready: boolean; discovery_error: string | null; volume: { transcript_characters: number; manuscript_characters: number }; failures: { video_id: string; title: string; reason: string; state: string }[] };
type Connection = { configured: boolean; authorized: boolean; subscription_count: number };
type Source = { channel_id: string; title: string };
const states: Record<string, string> = { queued: "排队", acquiring: "获取字幕", generating: "生成稿件", ready: "就绪", failed: "失败", unavailable: "字幕不可用" };
const tabs: [ReadingState | "all", string][] = [["inbox", "收件箱"], ["to-read", "待读"], ["reading", "阅读中"], ["read", "已读"], ["all", "全部稿件"]];
const button = "rounded-lg border border-line px-3 py-2 text-xs text-ink bg-panel hover:bg-chromeHover disabled:opacity-50 whitespace-nowrap";
const field = "rounded-lg border border-line bg-panel text-ink px-3 py-2 text-sm min-w-0";
const formatError = (e: unknown) => e instanceof Error ? e.message : String(e);

export function YouTubeView({ onModelSettings }: { onModelSettings: () => void }) {
  const [view, setView] = useState<ReadingState | "all">("inbox");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Inspection | null>(null);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [query, setQuery] = useState("");
  const [transcript, setTranscript] = useState(false);
  const [channel, setChannel] = useState("");
  const [preparation, setPreparation] = useState("");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [pulse, setPulse] = useState(false);
  const [connect, setConnect] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [connectionMessage, setConnectionMessage] = useState("");
  const [deleting, setDeleting] = useState(false);
  const revision = useRef(0);
  const connectionRevision = useRef(0);
  const selection = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    const current = ++revision.current;
    const filters: Record<string, unknown> = { query, include_transcript: transcript };
    if (view !== "all") filters.reading_state = view;
    if (channel) filters.channel_id = channel;
    if (preparation) filters.preparation_state = preparation;
    if (after) filters.published_after = new Date(after).getTime() / 1000;
    if (before) filters.published_before = new Date(`${before}T23:59:59`).getTime() / 1000;
    const [list, progress] = await Promise.all([
      call<{ assets: Asset[] }>("library.list", filters), call<Activity>("activity.snapshot"),
    ]);
    if (current !== revision.current) return;
    setAssets(list.assets); setActivity(progress);
    if (selection.current && !list.assets.some(x => x.video_id === selection.current)) {
      selection.current = null; setSelected(null);
    }
  }, [view, query, transcript, channel, preparation, after, before]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const update = async () => {
      try { await refresh(); } catch (e) { if (alive) setMessage(formatError(e)); }
      if (alive) timer = setTimeout(update, 3000);
    };
    void update();
    return () => { alive = false; revision.current++; clearTimeout(timer); };
  }, [refresh]);
  useEffect(() => { void call<{ sources: Source[] }>("collection.subscription_sources").then(x => setSources(x.sources)).catch(() => {}); }, []);

  const action = async (work: () => Promise<void>) => {
    setBusy(true); setMessage("");
    try { await work(); await refresh(); } catch (e) { setMessage(formatError(e)); }
    finally { setBusy(false); }
  };
  const inspect = async (asset: Asset) => {
    selection.current = asset.video_id;
    try {
      const result = await call<Inspection>("library.inspect", { video_id: asset.video_id });
      if (selection.current === asset.video_id) setSelected(result);
    } catch (e) { setMessage(formatError(e)); }
  };
  const connectAction = async (capability: string, args = {}) => {
    connectionRevision.current++;
    setBusy(true); setConnectionMessage(capability === "connection.configure" ? "正在保存，请在 Automic Vault 中完成授权…" : "正在处理，请完成浏览器或 Vault 中的授权…");
    try {
      setConnection(await call<Connection>(capability, args));
      setClientSecret(""); setConnectionMessage("操作成功。");
      setSources((await call<{ sources: Source[] }>("collection.subscription_sources")).sources);
    } catch (e) { setConnectionMessage(formatError(e)); }
    finally { setBusy(false); }
  };
  const openConnection = () => {
    setConnect(true); setConnectionMessage("正在检查连接状态…");
    const current = ++connectionRevision.current;
    void call<Connection>("connection.status").then(status => {
      if (current === connectionRevision.current) { setConnection(status); setConnectionMessage(""); }
    }).catch(e => { if (current === connectionRevision.current) setConnectionMessage(formatError(e)); });
  };
  const move = (state: ReadingState) => action(async () => {
    if (selected) setSelected(await call<Inspection>("library.set_reading_state", { video_id: selected.video_id, reading_state: state }));
  });

  return <main className="flex-1 min-w-0 overflow-y-auto bg-paper text-ink" aria-label="YouTube 资料库">
    <div className="max-w-6xl mx-auto p-6 space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div><h1 className="flex items-center gap-2 text-xl font-semibold"><YouTubeIcon size={26} />YouTube</h1><p className="text-sm text-muted mt-1">订阅更新，整理为你的本地阅读资料库。</p></div>
        <div className="flex gap-2 items-center">
          <div className="relative">
            <button className={button} onClick={() => setPulse(!pulse)} aria-expanded={pulse} aria-controls="youtube-activity">● 活动 {activity ? activity.queued + activity.acquiring + activity.generating : 0}</button>
            {pulse && <section id="youtube-activity" aria-label="批处理活动" className="absolute z-30 right-0 top-full mt-2 w-80 max-w-[85vw] max-h-[65vh] overflow-y-auto rounded-xl border border-line bg-panel shadow-xl p-4 space-y-3">
              <h2 className="font-semibold">批处理活动</h2>
              <p className="text-sm text-muted">{activity?.drain_paused ? "已请求暂停，当前项完成后停止" : !activity?.model_ready ? "等待模型配置" : activity?.acquiring ? "正在获取字幕" : activity?.generating ? "正在生成稿件" : "等待新更新"}</p>
              <dl className="grid grid-cols-2 gap-2 text-sm"><dt>本轮已处理 / 上限</dt><dd>{activity?.batch.completed ?? 0} / {activity?.batch.limit ?? 100}</dd><dt>就绪 / 失败 / 不可用</dt><dd>{activity?.ready ?? 0} / {activity?.failed ?? 0} / {activity?.unavailable ?? 0}</dd><dt>字幕 / 稿件字符</dt><dd>{activity?.volume.transcript_characters ?? 0} / {activity?.volume.manuscript_characters ?? 0}</dd></dl>
              {activity?.failures.map(f => <div key={f.video_id} className="border-t border-line pt-2 text-xs"><strong>{f.title}</strong><p className="text-muted my-1 break-words">{f.reason}</p>{f.state === "failed" && <button className={button} disabled={busy} onClick={() => void action(async () => { await call("activity.retry", { video_id: f.video_id }); })}>重试此项</button>}</div>)}
              <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={() => void action(async () => { await call(activity?.drain_paused ? "activity.resume" : "activity.drain_pause"); })}>{activity?.drain_paused ? "恢复批次" : "排空后暂停"}</button><button className={button} disabled={busy || !activity?.failed} onClick={() => void action(async () => { await call("activity.retry_all_failed"); })}>重试全部失败项</button></div>
            </section>}
          </div>
          <button className={button} onClick={openConnection}>连接 YouTube</button>
        </div>
      </header>
      <div className="flex flex-wrap justify-between items-center gap-2 text-xs text-muted"><span>生成模型：{activity?.model || "读取中"} · 沿用 Edison 设置</span><button className={button} onClick={onModelSettings}>模型设置</button></div>
      {activity && !activity.model_ready && <p role="status" className="rounded-lg border border-line bg-panel p-3 text-sm">请先在模型设置中连接模型。新资料会保持排队，不会因缺少 API Key 而失败。</p>}
      {(message || activity?.discovery_error) && <p role="status" className="text-sm break-words">{message || activity?.discovery_error}</p>}
      <nav className="flex flex-wrap gap-2" aria-label="阅读状态">{tabs.map(([key,label]) => <button key={key} aria-pressed={view === key} className={`${button} ${view === key ? "font-semibold !bg-chromeHover" : ""}`} onClick={() => setView(key)}>{label}</button>)}</nav>
      <div className="flex flex-wrap gap-2 items-center">
        <input aria-label="搜索稿件" placeholder="搜索标题、频道或正文" className={`${field} flex-1 basis-48`} value={query} onChange={e => setQuery(e.target.value)} />
        <select aria-label="频道" className={field} value={channel} onChange={e => setChannel(e.target.value)}><option value="">全部频道</option>{sources.map(s => <option key={s.channel_id} value={s.channel_id}>{s.title}</option>)}</select>
        <select aria-label="准备状态" className={field} value={preparation} onChange={e => setPreparation(e.target.value)}><option value="">全部状态</option>{Object.entries(states).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select>
        <label className="text-xs text-muted flex items-center gap-1"><input type="checkbox" checked={transcript} onChange={e => setTranscript(e.target.checked)} />包含原始字幕</label>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <label className="text-xs text-muted">发布自 <input type="date" aria-label="起始日期" className={field} value={after} onChange={e => setAfter(e.target.value)} /></label>
        <label className="text-xs text-muted">至 <input type="date" aria-label="结束日期" className={field} value={before} onChange={e => setBefore(e.target.value)} /></label>
        <button className={button} disabled={busy} onClick={() => void action(async () => { await call("collection.refresh_updates"); })}>刷新更新</button>
        <button className={button} disabled={busy} onClick={() => void action(async () => { await call("collection.backfill_updates", {days:7,limit:100}); })}>导入最近 7 天</button>
      </div>
      <div className={`grid gap-5 ${selected ? "xl:grid-cols-[minmax(0,1fr)_280px]" : ""}`}>
        <section aria-label="稿件列表" className="space-y-2 min-w-0">
          {!assets.length && <div className="text-center py-20 text-muted"><YouTubeIcon size={32}/><h2 className="mt-4 text-ink">这里还没有资料</h2><p className="text-sm mt-2">连接订阅后，新更新会在本机准备。也可以调整搜索条件。</p></div>}
          {assets.map(a => <button key={a.video_id} onClick={() => void inspect(a)} className={`w-full text-left p-4 rounded-xl border border-line bg-panel hover:bg-chromeHover ${selected?.video_id === a.video_id ? "ring-1 ring-current" : ""}`}><span className="text-xs text-muted">{states[a.preparation_state] || a.preparation_state} · {tabs.find(([k]) => k===a.reading_state)?.[1]}{a.manuscript_version ? ` · v${a.manuscript_version}` : ""}</span><h2 className="font-medium mt-1 break-words">{a.title}</h2><p className="text-xs text-muted mt-2">{a.channel_title} · {a.published_at ? new Date(a.published_at).toLocaleDateString() : "日期未知"}</p>{a.failure_reason && <p className="text-xs text-muted mt-2 break-words">{a.failure_reason}</p>}</button>)}
        </section>
        {selected && <aside aria-label="来源检查器" className="border border-line rounded-xl p-4 bg-panel space-y-3 self-start min-w-0">
          <h2 className="font-semibold break-words">{selected.title}</h2><p className="text-xs text-muted">{selected.channel_title} · {states[selected.preparation_state]}</p>
          <a className="text-sm underline break-all" href={selected.source_trace.video_url} target="_blank" rel="noreferrer">原始 YouTube 视频</a><p className="text-xs text-muted">定时字幕：{selected.source_trace.transcript_available ? "已保留" : "暂无"} · 稿件 {selected.manuscript_version ? `v${selected.manuscript_version}` : "尚未生成"}</p>
          {!!selected.manuscript_version && <><div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={() => void action(async () => { const d = await call<{markdown:string}>("documents.get", {video_id:selected.video_id}); await navigator.clipboard.writeText(d.markdown); setMessage("Markdown 已复制。"); })}>复制 Markdown</button><button className={button} disabled={busy} onClick={() => void action(async () => { await call("documents.open", {video_id:selected.video_id}); })}>用默认应用打开</button></div><label className="text-sm block">阅读状态<select className={`${field} block w-full mt-2`} value={selected.reading_state} onChange={e => void move(e.target.value as ReadingState)} disabled={busy}>{tabs.filter(([k]) => k!=="all").map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label></>}
          <div className="flex flex-wrap gap-2"><button className={button} disabled={busy || ["queued","acquiring","generating"].includes(selected.preparation_state)} onClick={() => void action(async () => { setSelected(await call<Inspection>("library.regenerate", {video_id:selected.video_id})); })}>生成新版本</button><button className={button} disabled={busy} onClick={() => setDeleting(true)}>删除资料</button></div>
          {deleting && <div className="text-sm space-y-2"><p>将删除这份资料及所有稿件和字幕。</p><button className={button} onClick={() => void action(async () => { await call("library.delete", {video_id:selected.video_id}); setSelected(null); selection.current=null; setDeleting(false); })}>确认删除</button><button className={button} onClick={() => setDeleting(false)}>取消</button></div>}
        </aside>}
      </div>
    </div>
    {connect && <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-5"><section role="dialog" aria-modal="true" aria-label="连接 YouTube" className="rounded-2xl border border-line bg-panel shadow-xl p-6 w-full max-w-md space-y-4"><div className="flex justify-between"><h2 className="font-semibold">连接 YouTube</h2><button onClick={() => setConnect(false)} aria-label="关闭">×</button></div><p className="text-sm text-muted">使用个人 Google OAuth 客户端。测试模式下，请在 Google Cloud 的测试用户名单中添加登录邮箱。</p>{connectionMessage && <p role="status" className="text-sm break-words">{connectionMessage}</p>}{!connection?.configured ? <form className="space-y-3" onSubmit={e => {e.preventDefault();void connectAction("connection.configure", {client_id:clientId,client_secret:clientSecret});}}><label className="block text-xs">Client ID<input className={`${field} block w-full mt-1`} required value={clientId} onChange={e=>setClientId(e.target.value)} /></label><label className="block text-xs">Client Secret<input className={`${field} block w-full mt-1`} type="password" required value={clientSecret} onChange={e=>setClientSecret(e.target.value)} /></label><button className={button} disabled={busy}>{busy ? "正在保存…" : "保存到 Automic Vault"}</button></form> : !connection.authorized ? <button className={button} disabled={busy} onClick={()=>void connectAction("connection.authorize")}>在浏览器中授权并导入订阅</button> : <><p>已连接 · {connection.subscription_count} 个订阅</p><button className={button} disabled={busy} onClick={()=>void connectAction("connection.disconnect")}>断开授权</button></>}</section></div>}
  </main>;
}
