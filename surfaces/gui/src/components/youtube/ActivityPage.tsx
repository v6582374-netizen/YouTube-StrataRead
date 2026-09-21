import { useTranslation } from "react-i18next";
import type { Activity } from "./types";
import { activityLabels } from "./activityLabels";
import { RuntimeEvents } from "./discovery/RuntimeEvents";
import { yt } from "./text";

export function ActivityPage({ activity, disconnected }: { activity: Activity | null; disconnected: boolean }) {
  useTranslation();
  const events = activity?.events || [];
  return <section className="yp-progress yp-activity" aria-label={yt("事件时间线")}>
    <p className="yp-progress-note" role="status">{disconnected ? yt("连接中断 · 正在重连") : !activity ? yt("正在加载活动…") : yt("最近 {{count}} 条 · 最新在前", { count: events.length })}</p>
    <RuntimeEvents events={events} labels={activityLabels()} />
  </section>;
}
