import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { youtubeCapability as call } from "../api";
import { yt } from "./youtube/text";
import { PanelHead } from "./IntegrationsView";
import { NoticeStack } from "./NoticeStack";

type Status = { enabled: boolean; present?: boolean; cookie_count?: number; updated_at?: number };
type Check = Status & { usable: boolean; signed_in: boolean; detail: string; saved?: boolean; checked_at?: number };
const input = "w-full rounded-lg border border-line bg-paper px-3 py-2 text-[13px] text-ink focus:border-accent outline-none font-mono";
const button = "rounded-lg border border-line px-3 py-2 text-[13px] hover:bg-panel disabled:opacity-40";

export function YouTubeSessionSettings() {
  useTranslation();
  const [status, setStatus] = useState<Status | null>(null);
  const [check, setCheck] = useState<Check | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"" | "test" | "replace">("");
  const [error, setError] = useState("");
  useEffect(() => {
    void call<Status>("session_cookies.status").then(setStatus).catch((e) => setError(String(e.message || e)));
  }, []);
  const run = async (kind: "test" | "replace") => {
    setBusy(kind); setError(""); setCheck(null);
    try {
      const result = await call<Check>(kind === "test" ? "session_cookies.test" : "session_cookies.replace", kind === "replace" ? { text } : {});
      setCheck(result); setStatus(result);
      if (result.saved) setText("");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(""); }
  };
  const updated = status?.updated_at ? new Date(status.updated_at * 1000).toLocaleString() : "";
  return <section aria-label={yt("YouTube 登录 Cookie")}>
    <PanelHead title={yt("YouTube 登录 Cookie")} sub={yt("服务器用它通过 YouTube 的机器人检查，才能判断 Shorts 和抓取字幕。")} />
    <NoticeStack messages={[error ? yt(error) : ""]} />
    {status && !status.enabled ? <p className="text-[13px] text-muted">{yt("此实例未启用登录 Cookie。")}</p> : <>
      <div className="rounded-xl2 border border-line bg-panel p-4 flex items-center justify-between gap-4 mb-5">
        <div className="text-[13px]">
          <div className="font-medium">{!status ? yt("加载中…") : status.present ? yt("已保存 {{count}} 个 Cookie", { count: status.cookie_count }) : yt("尚未保存 Cookie")}</div>
          {updated && <div className="text-[12px] text-muted mt-1">{yt("最后更新：{{time}}", { time: updated })}</div>}
        </div>
        <button className={button} disabled={!!busy || !status?.present} onClick={() => void run("test")}>{busy === "test" ? yt("测试中…") : yt("测试当前 Cookie")}</button>
      </div>
      {check && <div role="status" className={"rounded-lg border px-3 py-2 text-[13px] mb-5 " + (check.usable ? "border-green-600/40 text-green-700" : "border-red-600/40 text-red-700")}>
        {yt(check.detail)}{check.saved === false ? " " + yt("新 Cookie 未保存，原有 Cookie 保持不变。") : check.saved ? " " + yt("已保存并生效。") : ""}
      </div>}
      <label htmlFor="youtube-cookie-text" className="block text-[13px] font-medium mb-2">{yt("替换为新的 Cookie")}</label>
      <textarea id="youtube-cookie-text" className={input + " resize-y"} rows={6} value={text} maxLength={200000}
        placeholder={yt("粘贴 cookies.txt 内容，或 Cookie 请求头")} onChange={(event) => setText(event.target.value)} />
      <p className="mt-2 text-[12px] text-muted leading-relaxed">{yt("获取方式：打开一个新的无痕窗口并登录 YouTube，在同一标签页访问 youtube.com/robots.txt，按 F12 打开开发者工具，进入「网络」并刷新，点选这条请求，复制请求头中 Cookie 的整行值，粘贴到这里保存，然后关闭无痕窗口且不再打开。日常窗口里的 Cookie 会被 YouTube 轮换，很快失效。只会保留 youtube.com 与 google.com 的 Cookie。")}</p>
      <button className="mt-4 rounded-lg bg-accent text-white px-4 py-2 text-[13px] disabled:opacity-40" disabled={!!busy || !text.trim()} onClick={() => void run("replace")}>{busy === "replace" ? yt("测试中…") : yt("测试并保存")}</button>
    </>}
  </section>;
}
