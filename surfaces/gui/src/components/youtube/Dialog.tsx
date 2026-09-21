import { useTranslation } from "react-i18next";
import { yt } from "./text";
import { ReactNode, useEffect, useRef } from "react";
import { Icon } from "../Icon";

export function Dialog({
  title,
  subtitle,
  children,
  footer,
  onClose,
  detail = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  detail?: boolean;
}) {
  useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current
      ?.querySelector<HTMLElement>("button,input,textarea,select")
      ?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
      }
      if (event.key === "Tab") {
        const nodes = [
          ...(ref.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href]",
          ) || []),
        ];
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="yp-scrim"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        ref={ref}
        className={`yp-dialog ${detail ? "yp-detail" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="yp-dialoghead">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="yp-iconbtn" onClick={onClose} aria-label={yt("关闭")}>
            <Icon name="x" />
          </button>
        </header>
        <div className="yp-dialogbody">{children}</div>
        {footer && <footer className="yp-dialogfoot">{footer}</footer>}
      </section>
    </div>
  );
}
