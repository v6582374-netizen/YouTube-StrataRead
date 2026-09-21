import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Icon } from "./Icon";

export function NoticeStack({ messages }: { messages: string[] }) {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState<string[]>([]);
  const signature = JSON.stringify([...new Set(messages.filter(Boolean))]);
  useEffect(() => {
    const active: string[] = JSON.parse(signature);
    setDismissed(previous => previous.filter(message => active.includes(message)));
  }, [signature]);
  const active: string[] = JSON.parse(signature);
  return createPortal(
    <div className="notice-stack" aria-label={t("common.notifications")}>
      {active.filter(message => !dismissed.includes(message)).map(message => (
        <div className="notice-card" key={message}>
          <span role="status">{message}</span>
          <button type="button" aria-label={t("common.dismiss_notification")}
            onClick={() => setDismissed(previous => [...previous, message])}>
            <Icon name="x" size={16} />
          </button>
        </div>
      ))}
    </div>, document.body,
  );
}
