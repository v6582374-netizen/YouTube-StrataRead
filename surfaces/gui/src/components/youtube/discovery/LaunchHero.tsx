import { useTranslation } from "react-i18next";
import { yt } from "../text";
// Adapted directly from Vegapunk PrototypeLaunchHero. See docs/upstream/vegapunk-discovery.
export type Milestone = { id: string; label: string; summary?: string; state: "done" | "active" | "pending" };
export function LaunchHero({ live, offline, observedStage, signalCopy, milestones, metrics }: {
  live: boolean; offline: boolean; observedStage: string; signalCopy: string;
  milestones: Milestone[]; metrics: {label: string; value: string | number; note: string}[];
}) {
  useTranslation();
  return (
    <section className={`discovery-prototype-panel discovery-hero-panel discovery-beacon-hero ${!live ? "is-standby" : ""} ${!milestones.length ? "is-idle" : ""} ${offline ? "is-error" : ""}`} aria-label={yt("当前处理概览")}>
      <div className="discovery-beacon-signal">
        <div className="discovery-beacon-signal-head">
          <div className="discovery-beacon-orb" aria-hidden="true"><span /></div>
          <div className="min-w-0">
            <h2 className="discovery-launch-title discovery-beacon-title">{observedStage}</h2>
            {signalCopy && <p className="discovery-beacon-copy">{signalCopy}</p>}
          </div>
        </div>
        {!!milestones.length && <div className="discovery-beacon-track" aria-label={yt("处理阶段")}>
          <div className="discovery-beacon-track-head"><strong>{yt("处理阶段")}</strong></div>
          <div className="discovery-beacon-stage-list">
            {milestones.map((milestone) => {
              const state = milestone.state;
              return (
                <div key={milestone.id} className={`discovery-beacon-stage is-${state}`}>
                  <strong>{milestone.label}</strong>
                  <span>{milestone.summary ?? (state === "done" ? yt("已完成") : state === "active" ? yt("进行中") : yt("等待开始"))}</span>
                  <em>{state === "done" ? yt("完成") : state === "active" ? yt("进行中") : yt("待处理")}</em>
                </div>
              );
            })}
          </div>
        </div>}

      </div>
      <div className="discovery-beacon-metrics">
        {metrics.map(metric => <div className="discovery-beacon-metric" key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div>)}
      </div>
    </section>
  );
}
