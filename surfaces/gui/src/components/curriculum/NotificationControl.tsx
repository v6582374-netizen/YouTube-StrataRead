import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCourseNotificationStatus, isTauri, platformOS, setCourseNotificationsEnabled, type CourseNotificationStatus } from "../../tauri";

export function NotificationControl() {
  const { t } = useTranslation();
  const desktop = isTauri() && platformOS() === "macos";
  const [status, setStatus] = useState<CourseNotificationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const revision = useRef(0);
  const changing = useRef(false);

  useEffect(() => {
    if (!desktop) return;
    let mounted = true;
    const refresh = async () => {
      if (changing.current) return;
      const request = ++revision.current;
      try {
        const next = await getCourseNotificationStatus();
        if (mounted && request === revision.current) { setStatus(next); setFailed(false); }
      } catch {
        if (mounted && request === revision.current) setFailed(true);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 5_000);
    window.addEventListener("focus", refresh);
    return () => { mounted = false; window.clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [desktop]);

  const change = async () => {
    if (!status || changing.current) return;
    changing.current = true;
    ++revision.current;
    setBusy(true);
    try { setStatus(await setCourseNotificationsEnabled(!status.enabled)); setFailed(false); }
    catch { setFailed(true); }
    finally { changing.current = false; setBusy(false); }
  };
  const state = !desktop ? "unsupported" : failed || status?.error ? "unavailable"
    : !status ? "checking" : !status.enabled ? "off" : status.permission;

  return (
    <div className="curriculum-notification-control">
      <label>
        <input type="checkbox" role="switch" aria-label={t("curriculum.notifications.label")}
          checked={status?.enabled ?? true} disabled={!desktop || !status || busy || status.permission === "unsupported"}
          onChange={() => void change()} />
        <span>{t("curriculum.notifications.label")}</span>
      </label>
      <p role="status" className={state === "denied" || state === "unavailable" ? "needs-attention" : undefined}>
        {t(`curriculum.notifications.${state}`)}
      </p>
    </div>
  );
}
