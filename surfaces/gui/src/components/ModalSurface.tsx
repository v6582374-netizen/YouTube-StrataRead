import {
  type ReactNode, type RefObject, type MouseEvent, type KeyboardEvent,
  useEffect, useLayoutEffect, useMemo, useRef, useState,
} from "react";
import { createPortal } from "react-dom";

export type ModalInput = "pointer" | "keyboard";

/** Capture intent before async work; a later keystroke must not change its motion. */
export function useModalInteraction() {
  const source = useRef<{ input: ModalInput; target: HTMLElement | null }>({ input: "keyboard", target: null });
  const openInput = useRef<ModalInput>("keyboard");
  const closeInput = useRef<ModalInput>("keyboard");
  const returnFocusRef = useRef<HTMLElement | null>(null);
  return useMemo(() => ({
    openInput, closeInput, returnFocusRef,
    input: () => source.current.input,
    capture: {
      onClickCapture: (event: MouseEvent<HTMLElement>) => {
        source.current = {
          input: event.detail > 0 ? "pointer" : "keyboard",
          target: (event.target as HTMLElement).closest<HTMLElement>("button,a,summary,[tabindex]"),
        };
      },
      onKeyDownCapture: (event: KeyboardEvent<HTMLElement>) => {
        if (!event.isPropagationStopped()) source.current = { input: "keyboard", target: event.target as HTMLElement };
      },
    },
    begin: () => {
      openInput.current = source.current.input;
      const target = source.current.target;
      if (!target?.closest('[role="dialog"]')) returnFocusRef.current = target;
    },
    end: (input = source.current.input) => { closeInput.current = input; },
  }), []);
}
type ModalInteraction = ReturnType<typeof useModalInteraction>;

const controls = "button,input,select,textarea,a[href],summary,[tabindex],[contenteditable=true]";
function available(element: HTMLElement) {
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    if (parent instanceof HTMLDetailsElement && !parent.open &&
        !Array.from(parent.children).find(child => child.tagName === "SUMMARY")?.contains(element)) return false;
  }
  return element.isConnected && !element.matches(":disabled,[hidden],input[type=hidden]") &&
    !element.closest("[inert]") && element.getClientRects().length > 0 &&
    getComputedStyle(element).visibility !== "hidden";
}

export function ModalSurface({
  open, active = true, label, children, surfaceClassName = "", interaction,
  initialFocusRef, fallbackFocusRef, dismissOnBackdrop = false, onRequestClose,
}: {
  open: boolean;
  active?: boolean;
  label: string;
  children: ReactNode;
  surfaceClassName?: string;
  interaction: ModalInteraction;
  initialFocusRef?: RefObject<HTMLElement>;
  fallbackFocusRef?: RefObject<HTMLElement>;
  dismissOnBackdrop?: boolean;
  onRequestClose: () => void;
}) {
  const visible = open && active;
  const scrim = useRef<HTMLDivElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const [present, setPresent] = useState(false);
  const [phase, setPhase] = useState("open");
  const [reduced, setReduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const snapshot = useRef<{ children: ReactNode; surfaceClassName: string }>({ children: null, surfaceClassName: "" });
  const animations = useRef<Animation[]>([]);
  const generation = useRef(0);
  const initialized = useRef(false);
  const backdropPointer = useRef<number | null>(null);
  const latest = useRef({ active, visible, onRequestClose, initialFocusRef, fallbackFocusRef });
  latest.current = { active, visible, onRequestClose, initialFocusRef, fallbackFocusRef };

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return;
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useLayoutEffect(() => {
    if (visible) snapshot.current = { children, surfaceClassName };
  });
  useLayoutEffect(() => () => {
    generation.current++;
    animations.current.forEach(animation => animation.cancel());
    initialized.current = false;
  }, []);
  useLayoutEffect(() => {
    const node = surface.current;
    const shade = backdrop.current;
    if (!node || !shade || !scrim.current) return;
    const version = ++generation.current;
    const input = visible ? interaction.openInput.current : interaction.closeInput.current;
    // Read presentation BEFORE cancel: cancel exposes the underlying target styles.
    const current = getComputedStyle(node);
    const from = {
      opacity: initialized.current ? current.opacity : "0",
      transform: initialized.current ? current.transform : "scale(0.97)",
    };
    const shadeFrom = initialized.current ? getComputedStyle(shade).opacity : "0";
    animations.current.forEach(animation => animation.cancel());
    animations.current = [];
    scrim.current.inert = !visible;
    const target = { opacity: visible ? "1" : "0", transform: reduced ? "none" : visible ? "scale(1)" : "scale(0.97)" };
    Object.assign(node.style, target);
    shade.style.opacity = target.opacity;
    initialized.current = visible || present;
    if (!active || input === "keyboard" || typeof node.animate !== "function") {
      setPresent(visible);
      initialized.current = visible;
      if (!visible) snapshot.current = { children: null, surfaceClassName: "" };
      setPhase("open");
      return;
    }
    setPresent(true);
    setPhase(visible ? "entering" : "closing");
    const durationToken = current.getPropertyValue("--duration-modal").trim();
    const duration = durationToken ? parseFloat(durationToken) * (durationToken.endsWith("ms") ? 1 : 1000) : 200;
    const easing = current.getPropertyValue("--ease-out").trim() || "cubic-bezier(0.23, 1, 0.32, 1)";
    animations.current = [
      node.animate(reduced ? [{ opacity: from.opacity }, { opacity: target.opacity }] : [from, target], { duration, easing }),
      shade.animate([{ opacity: shadeFrom }, { opacity: target.opacity }], { duration, easing }),
    ];
    void Promise.all(animations.current.map(animation => animation.finished)).then(() => {
      if (version !== generation.current) return;
      animations.current = [];
      setPhase("open");
      if (!visible) {
        initialized.current = false;
        snapshot.current = { children: null, surfaceClassName: "" };
        setPresent(false);
      }
    }).catch(() => { /* Retargeting/unmount cancels the superseded animation. */ });
  }, [visible, active, reduced, interaction]);

  useLayoutEffect(() => {
    if (!visible || !surface.current || !scrim.current) return;
    const node = surface.current;
    const background = new Map<HTMLElement, boolean>();
    const isolate = () => {
      for (const element of Array.from(document.body.children)) {
        if (!(element instanceof HTMLElement) || element === scrim.current || background.has(element)) continue;
        background.set(element, element.inert);
        element.inert = true;
      }
    };
    isolate();
    const observer = new MutationObserver(isolate);
    observer.observe(document.body, { childList: true });
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const tabbable = () => Array.from(node.querySelectorAll<HTMLElement>(controls))
      .filter(element => element.tabIndex >= 0 && available(element));
    const focusInside = () => {
      const initial = latest.current.initialFocusRef?.current;
      (initial && available(initial) ? initial : tabbable()[0] || node).focus({ preventScroll: true });
    };
    let ownedFocus = true;
    const onFocus = (event: FocusEvent) => {
      ownedFocus = node.contains(event.target as Node);
      if (!ownedFocus) focusInside();
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !event.isComposing) {
        event.preventDefault();
        event.stopPropagation();
        interaction.end("keyboard");
        latest.current.onRequestClose();
      } else if (event.key === "Tab") {
        const items = tabbable();
        const index = items.indexOf(document.activeElement as HTMLElement);
        if (!items.length || index < 0 || (event.shiftKey ? index === 0 : index === items.length - 1)) {
          event.preventDefault();
          (event.shiftKey ? items[items.length - 1] || node : items[0] || node).focus({ preventScroll: true });
        }
      }
    };
    document.addEventListener("focusin", onFocus);
    document.addEventListener("keydown", onKey, true);
    focusInside();
    return () => {
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("keydown", onKey, true);
      observer.disconnect();
      background.forEach((inert, element) => { element.inert = inert; });
      document.body.style.overflow = overflow;
      // React restores the old focused DOM during commit. Restore after commit,
      // otherwise a retained exit surface can steal focus back before becoming inert.
      queueMicrotask(() => {
        if (!ownedFocus || !latest.current.active || latest.current.visible) return;
        const focused = document.activeElement;
        if (focused && focused !== document.body && !node.contains(focused)) return;
        const target = interaction.returnFocusRef.current;
        const fallback = latest.current.fallbackFocusRef?.current;
        if (target && available(target)) target.focus({ preventScroll: true });
        else if (fallback && available(fallback)) fallback.focus({ preventScroll: true });
      });
    };
  }, [visible, interaction]);

  // A content replacement inside an open surface may remove the focused control.
  useLayoutEffect(() => {
    const node = surface.current;
    if (visible && node && !node.contains(document.activeElement)) {
      (Array.from(node.querySelectorAll<HTMLElement>(controls)).find(available) || node).focus({ preventScroll: true });
    }
  });

  if (!visible && !present) return null;
  const content = visible ? { children, surfaceClassName } : snapshot.current;
  return createPortal(
    <div ref={scrim} className="modal-scrim"
      data-modal-state={visible ? phase : "closing"} aria-hidden={!visible || undefined}
      onPointerDown={event => {
        backdropPointer.current = event.target === event.currentTarget && event.button === 0 ? event.pointerId : null;
      }}
      onPointerCancel={() => { backdropPointer.current = null; }}
      onPointerUp={event => {
        const dismiss = backdropPointer.current === event.pointerId && event.target === event.currentTarget;
        backdropPointer.current = null;
        if (dismiss && dismissOnBackdrop) {
          interaction.end("pointer");
          onRequestClose();
        }
      }}>
      <div ref={backdrop} className="modal-backdrop" />
      <div ref={surface} className={`modal-surface ${content.surfaceClassName}`} role={visible ? "dialog" : undefined} aria-modal={visible || undefined} aria-label={visible ? label : undefined} tabIndex={-1}>
        {content.children}
      </div>
    </div>, document.body,
  );
}
