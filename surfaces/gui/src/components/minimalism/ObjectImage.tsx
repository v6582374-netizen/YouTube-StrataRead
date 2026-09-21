import { mt } from "./text";
import { useEffect, useRef, useState } from "react";
import { minimalismCapability } from "../../api";
export function ObjectImage({
  path,
  name,
  contain = false,
}: {
  path?: string | null;
  name: string;
  contain?: boolean;
}) {
  const [src, setSrc] = useState("");
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let alive = true;
    setSrc("");
    setFailed(false);
    if (!path) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        observer.disconnect();
        minimalismCapability<{
          data: string;
          mime: string;
        }>("image.get", { path })
          .then((image) => {
            if (alive) setSrc(`data:${image.mime};base64,${image.data}`);
          })
          .catch(() => {
            if (alive) setFailed(true);
          });
      },
      { rootMargin: "200px" },
    );
    if (ref.current) observer.observe(ref.current);
    return () => {
      alive = false;
      observer.disconnect();
    };
  }, [path]);
  return (
    <div
      ref={ref}
      className="h-full w-full bg-panel flex items-center justify-center overflow-hidden"
    >
      {src && !failed ? (
        <img
          src={src}
          alt={name}
          className={`w-full h-full ${contain ? "object-contain" : "object-cover"}`}
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="text-muted/50 text-[13px] px-5 text-center">
          {failed ? mt("图片暂不可用") : path ? "" : mt("尚无封面")}
        </span>
      )}
    </div>
  );
}
