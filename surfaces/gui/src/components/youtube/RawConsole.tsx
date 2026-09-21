import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ConsoleEntry } from "./types";
import { yt } from "./text";
import { getCurrentLanguage } from "../../i18n";

export function RawConsole({ entries, stale, now }: { entries: ConsoleEntry[]; stale: boolean; now: number }) {
  useTranslation();
  const viewport = useRef<HTMLPreElement>(null);
  const [following, setFollowing] = useState(true);
  const latest = entries[entries.length - 1];
  useEffect(() => {
    if (following && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [latest?.sequence, following]);
  const elapsed = latest ? Math.max(0, Math.floor(now / 1000 - latest.occurred_at)) : 0;
  return <section className="yp-console" aria-label={yt("原始控制台")}>
    <header className="yp-console-head">
      <h2>{yt("原始控制台")}</h2>
      <span>{stale ? yt("连接中断 · 正在重连") : latest ? yt("距上次输出 {{seconds}} 秒", { seconds: elapsed }) : yt("等待执行输出")}</span>
      <button className="yp-btn" aria-pressed={following} onClick={() => setFollowing(value => !value)}>{yt("跟随输出")}</button>
    </header>
    <p className="yp-progress-note">{yt("实际执行记录 · 最近 500 条 · 每 4 秒刷新。等待模型响应时可能暂时没有新输出。")}</p>
    <pre ref={viewport} className="yp-console-output" tabIndex={0} aria-label={yt("执行输出")}
      onScroll={event => {
        const element = event.currentTarget;
        setFollowing(element.scrollHeight - element.scrollTop - element.clientHeight < 24);
      }}><code>{entries.length ? entries.map(entry => `${new Date(entry.occurred_at * 1000).toLocaleTimeString(getCurrentLanguage(), { hour12: false })} [${entry.video_id}] ${entry.message}`).join("\n") : yt("尚无执行输出。新任务开始后，记录会出现在这里。")}</code></pre>
  </section>;
}
