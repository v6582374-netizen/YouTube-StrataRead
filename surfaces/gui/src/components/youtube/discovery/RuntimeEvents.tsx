import { useTranslation } from "react-i18next";
import { yt } from "../text";
import { getCurrentLanguage } from "../../../i18n";
// Event rendering extracted from Vegapunk PrototypeRuntimeDesk; newest-first host contract.
import type { ProgressEvent } from "../types";
export function RuntimeEvents({ events, labels }: {events: ProgressEvent[]; labels: Record<string, string>}) {
  useTranslation();
  return <div className="discovery-runtime-desk is-live"><section className="discovery-runtime-pulse-panel">
    <div className="discovery-runtime-events">
      {events.length ? events.map(item => {
        const tone = item.stage === "failed" ? "danger" : item.stage === "unavailable" ? "warn" : "normal";
        const label = labels[item.stage] || item.stage;
        const stateLabel = label;
            return (
              <div key={item.sequence} className={`discovery-runtime-event discovery-runtime-event-in ${tone}`}>
                <span className="discovery-runtime-event-time">{new Date(item.occurred_at * 1000).toLocaleTimeString(getCurrentLanguage())}</span>
                <div className="discovery-runtime-event-copy">
                  <strong>{item.title}</strong>
                  <span>{item.detail || label}</span>
                </div>
                <span className="discovery-runtime-event-state">{stateLabel}</span>
              </div>
            );
      }) : <p className="discovery-runtime-empty">{yt("尚无处理事件，新活动会出现在这里。")}</p>}
    </div>
  </section></div>;
}
