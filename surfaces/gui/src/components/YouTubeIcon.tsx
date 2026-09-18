import { siYoutube } from "simple-icons";

/** Official YouTube play mark from Simple Icons; never a generic video glyph. */
export function YouTubeIcon({ size = 18 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill={`#${siYoutube.hex}`} aria-hidden="true" className="shrink-0"><path d={siYoutube.path} /></svg>;
}
