import { useTranslation } from "react-i18next";
import { yt } from "./youtube/text";
import { useEffect, useState } from "react";
import { youtubeCapability as call } from "../api";
import { PanelHead } from "./IntegrationsView";
import { NoticeStack } from "./NoticeStack";

type Stage = "initial" | "review" | "revision" | "composition";
type Config = {
  version: number;
  country: string;
  prompts: Record<Stage, Record<string, string>>;
  max_calls: number;
  max_tokens: number;
};
type Response = { settings: Config; defaults: Config; required: Record<Stage, Record<string, string[]>>; legacy_settings?: string | null };
const input = "w-full rounded-lg border border-line bg-paper px-3 py-2 text-[13px] text-ink focus:border-accent outline-none";
const button = "rounded-lg border border-line px-3 py-2 text-[13px] hover:bg-panel disabled:opacity-40";

export function YouTubeTranslationSettings() {
  useTranslation();
  const stages: [Stage, string][] = [
    ["initial", yt("初译")], ["review", yt("审校")], ["revision", yt("修订")], ["composition", yt("成稿整理")],
  ];
  const [data, setData] = useState<Response | null>(null);
  const [draft, setDraft] = useState<Config | null>(null);
  const [stage, setStage] = useState<Stage>("initial");
  const [variant, setVariant] = useState("user");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    void call<Response>("translation.settings").then((value) => {
      setData(value); setDraft(value.settings);
    }).catch((e) => setError(String(e.message || e)));
  };
  useEffect(load, []);
  const dirty = !!data && JSON.stringify(draft) !== JSON.stringify(data.settings);
  useEffect(() => {
    if (!dirty) return;
    const prevent = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  const save = async () => {
    if (!draft) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const value = await call<Response>("translation.set_settings", { settings: draft });
      setData(value); setDraft(value.settings); setMessage(yt("已保存，后续新任务使用这些设置。"));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const edit = (role: string, value: string) => {
    if (!draft) return;
    setMessage("");
    setDraft({ ...draft, prompts: { ...draft.prompts, [stage]: { ...draft.prompts[stage], [role]: value } } });
  };
  return <section aria-label={yt("YouTube 生成规则")}>
    <PanelHead title={yt("YouTube 生成规则")} sub={yt("修改只影响后续新任务。")} />
    <NoticeStack messages={[error, message].map(value => value ? yt(value) : "")} />
    {!data || !draft ? <button className={button} onClick={load}>{error ? yt("重新加载") : yt("加载中…")}</button> : <>
      <div className="flex flex-wrap gap-2 mb-5" role="tablist" aria-label={yt("翻译阶段")}>
        {stages.map(([key, label]) => <button key={key} role="tab" aria-selected={stage === key}
          className={button + (stage === key ? " bg-panel text-accent" : " text-muted")}
          onClick={() => { setStage(key); setVariant("user"); }}>{label}</button>)}
      </div>
      <fieldset disabled={busy} className="space-y-5">
        {stage !== "composition" && <label className="block text-[13px] font-medium">{yt("任务模板类型")}<select aria-label={yt("任务模板类型")} className={input + " mt-2"} value={variant} onChange={(event) => setVariant(event.target.value)}>
            {Object.keys(draft.prompts[stage]).filter((key) => key !== "system").map((key) => <option key={key} value={key}>{({ user: yt("单段文本"), multichunk_user: yt("多段文本"), user_region: yt("单段文本 · 指定地区"), multichunk_user_region: yt("多段文本 · 指定地区") } as Record<string, string>)[key]}</option>)}
          </select>
        </label>}
        {["system", variant].map((role) => <div key={role}>
          <label htmlFor={`translation-${role}`} className="block text-[13px] font-medium mb-2">{role === "system" ? yt("系统提示词") : yt("任务模板")}</label>
          <textarea id={`translation-${role}`} className={input + " leading-relaxed resize-y"}
            rows={role === "system" ? 5 : 11} value={draft.prompts[stage][role]} maxLength={64000}
            onChange={(event) => edit(role, event.target.value)} />
          {role !== "system" && <p className="mt-2 text-[12px] text-muted">{yt("必需占位符：")}{data.required[stage][role].map((key) => "{" + key + "}").join(" · ")}</p>}
        </div>)}
        <button className={button} onClick={() => {
          setMessage(""); setDraft({ ...draft, prompts: { ...draft.prompts, [stage]: { ...data.defaults.prompts[stage] } } });
        }}>{yt("恢复本阶段默认提示词")}</button>
        <label className="block text-[13px] font-medium">{yt("译文地区（可选）")}<input aria-label={yt("译文地区")} className={input + " mt-2"} value={draft.country} maxLength={100} placeholder={yt("留空则使用不指定地区的审校模板")} onChange={(event) => setDraft({ ...draft, country: event.target.value })} />
        </label>
        <div className="rounded-xl2 border border-line bg-panel p-4 space-y-3">
          <h3 className="text-[13px] font-medium">{yt("每条视频的处理预算")}</h3>
          <div className="grid grid-cols-2 gap-4">
            <label className="text-[12px] text-muted">{yt("最多模型调用次数")}<input aria-label={yt("最多模型调用次数")} type="number" min={1} max={2000} className={input + " mt-2"}
                value={draft.max_calls} onChange={(event) => setDraft({ ...draft, max_calls: Number(event.target.value) })} />
            </label>
            <label className="text-[12px] text-muted">{yt("累计 token 上限")}<input aria-label={yt("累计 token 上限")} type="number" min={1000} max={10000000} className={input + " mt-2"}
                value={draft.max_tokens} onChange={(event) => setDraft({ ...draft, max_tokens: Number(event.target.value) })} />
            </label>
          </div>
          <p className="text-[12px] text-muted leading-relaxed">{yt("超出预算将舍弃本次未完成结果，不自动重试。字幕和历史稿件保留。模型未报告用量时按保守上界计入预算。")}</p>
        </div>
      </fieldset>
      {data.legacy_settings && <details className="mt-5 text-[12px] text-muted">
        <summary>{yt("查看保留的旧版模板")}</summary>
        <p className="my-2">{yt("旧版使用不同输出协议，已完整保留供查阅；当前任务使用上方的上游模板。")}</p>
        <pre className="whitespace-pre-wrap break-words max-h-64 overflow-auto">{data.legacy_settings}</pre>
      </details>}
      <div className="flex items-center gap-3 mt-5">
        <button className="rounded-lg bg-accent text-white px-4 py-2 text-[13px] disabled:opacity-40" disabled={busy || !dirty} onClick={() => void save()}>{busy ? yt("保存中…") : yt("保存设置")}</button>
        <span role="status" className="text-[12px] text-muted">{dirty ? yt("有未保存的修改") : yt("已保存")}</span>
      </div>
    </>}
  </section>;
}
