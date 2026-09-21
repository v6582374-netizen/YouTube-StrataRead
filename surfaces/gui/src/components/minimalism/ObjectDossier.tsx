import { mt } from "./text";
import { useEffect, useRef, useState } from "react";
import { minimalismCapability } from "../../api";
import { Icon } from "../Icon";
import { ObjectImage } from "./ObjectImage";
import {
  type ObjectRecord,
  type Snapshot,
  type Preview,
  type MemoryBlock,
  METADATA,
  field,
  button,
  primary,
  message,
} from "./types";
export async function fileData(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(mt("无法读取文件。")));
    reader.readAsDataURL(file);
  });
}
export function ObjectDossier({
  object,
  snapshot,
  run,
  onBack,
  onImageSettings,
}: {
  object: ObjectRecord;
  snapshot: Snapshot;
  run: (action: string, args?: Record<string, unknown>) => Promise<boolean>;
  onBack: () => void;
  onImageSettings: () => void;
}) {
  const [blocks, setBlocks] = useState<MemoryBlock[]>(object.memoryBlocks);
  const [custom, setCustom] = useState(object.customMetadata);
  const [newField, setNewField] = useState("");
  const [generating, setGenerating] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [photoBusy, setPhotoBusy] = useState(false);
  const [inspectedPhoto, setInspectedPhoto] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const draftRevision = useRef(0);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const [saving, setSaving] = useState(false);
  const save = (changes: Record<string, unknown>) =>
    run("asset.save", { id: object.id, changes });
  const archived = snapshot.collections.some(
    (c) => c.id === object.collectionID && c.role === "archive",
  );
  async function saveMemories() {
    const revision = draftRevision.current;
    setSaving(true);
    const ok = await save({ memoryBlocks: blocks, customMetadata: custom });
    if (ok && revision === draftRevision.current) setDirty(false);
    setSaving(false);
  }
  async function upload(files: File[]) {
    setPhotoBusy(true);
    setError("");
    try {
      for (const file of files) {
        if (file.size > 30 * 1024 * 1024)
          throw new Error(mt("每张图片不能超过 30 MB。"));
        if (
          !(await run("asset.photo.add", {
            id: object.id,
            data: await fileData(file),
          }))
        )
          break;
      }
    } catch (e) {
      setError(message(e));
    } finally {
      setPhotoBusy(false);
    }
  }
  async function discard() {
    if (preview)
      await minimalismCapability("cover.discard", {
        preview: preview.preview,
      }).catch(() => {});
    setPreview(null);
  }
  async function generate() {
    if (generating) return;
    setGenerating(true);
    setError("");
    const config = await minimalismCapability<{
      ready: boolean;
    }>("image.settings").catch(() => null);
    if (!config?.ready) {
      setGenerating(false);
      onImageSettings();
      return;
    }
    await discard();
    setGenerating(true);
    try {
      setPreview(
        await minimalismCapability<Preview>("cover.generate", {
          id: object.id,
        }),
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setGenerating(false);
    }
  }
  const date = object.acquisitionDate || object.createdAt;
  const days = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(date)) / 86400000),
  );
  return (
    <section
      aria-label={mt("物品档案")}
      className="max-w-5xl mx-auto px-5 sm:px-8 py-5"
    >
      <header className="flex flex-wrap items-center gap-2 mb-7">
        <button
          className={button}
          onClick={() => {
            if (!dirty || window.confirm(mt("记忆内容尚未保存，仍要返回？"))) {
              void discard();
              onBack();
            }
          }}
        >
          <Icon name="arrowLeft" />
          {mt("返回")}
        </button>
        <div className="flex-1" />
        {dirty && (
          <button className={primary} disabled={saving} onClick={saveMemories}>
            {saving ? mt("保存中…") : mt("保存记忆")}
          </button>
        )}
        <button className={button} disabled={generating} onClick={generate}>
          <Icon name={generating ? "clock" : "sparkle"} />
          {generating ? mt("生成中…") : mt("生成封面")}
        </button>
        <details className="relative">
          <summary
            className={`${button} cursor-pointer list-none`}
            aria-label={mt("物品操作")}
          >
            <Icon name="moreHorizontal" />
          </summary>
          <div className="absolute right-0 top-full mt-2 z-20 w-44 rounded-xl border border-line bg-paper p-2 shadow-lg flex flex-col gap-1">
            <button
              className={button}
              onClick={() =>
                void run(archived ? "asset.unarchive" : "asset.archive", {
                  id: object.id,
                })
              }
            >
              {archived ? mt("取消归档") : mt("归档物品")}
            </button>
            {object.coverImagePath && (
              <button
                className={button}
                onClick={() => {
                  if (window.confirm(mt("移除当前 AI 封面？档案照片会保留。")))
                    void run("asset.cover.remove", { id: object.id });
                }}
              >
                {mt("移除封面")}
              </button>
            )}
            <button
              className={button}
              onClick={() => {
                if (window.confirm(mt("将物品移入回收站？")))
                  void run("asset.trash", { id: object.id }).then((ok) => {
                    if (ok) onBack();
                  });
              }}
            >
              {mt("移入回收站")}
            </button>
          </div>
        </details>
      </header>
      {error && (
        <p role="alert" className="text-red-500 text-[13px] mb-4">
          {mt(error)}
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-[minmax(180px,0.8fr)_minmax(240px,1.2fr)] gap-8">
        <div>
          <div className="aspect-[4/5] rounded-xl overflow-hidden border border-line">
            <ObjectImage
              path={object.coverImagePath}
              name={object.name}
              contain
            />
          </div>
          <div className="flex justify-between mt-3 text-[11px] text-muted">
            <span>
              {object.coverProvenance === "aiGenerated"
                ? mt("AI 生成封面")
                : mt("尚无封面")}
            </span>
            <span>
              {mt("相伴 ")}
              {days}
              {mt(" 天")}
            </span>
          </div>
        </div>
        <div className="min-w-0">
          <input
            aria-label={mt("物品名称")}
            defaultValue={object.name}
            className="w-full bg-transparent text-2xl font-semibold text-ink outline-none border-b border-transparent focus:border-line pb-2"
            onBlur={(e) => {
              if (e.target.value !== object.name)
                void save({ name: e.target.value });
            }}
          />
          <label className="flex items-center gap-3 mt-4 mb-7 text-[12px] text-muted">
            {mt("集合 ")}
            <select
              aria-label={mt("物品所属集合")}
              className="bg-transparent text-ink outline-none max-w-full"
              value={object.collectionID || ""}
              onChange={(e) =>
                void run("asset.move", {
                  id: object.id,
                  collectionID: e.target.value || null,
                })
              }
            >
              <option value="">{mt("未分类")}</option>
              {snapshot.collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.role === "archive" ? mt("归档") : c.name}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-x-5 gap-y-4">
            {Object.entries(METADATA)
              .filter(
                ([key]) =>
                  snapshot.preferences.visibleMetadataFields.includes(key) ||
                  (key === "purchasePrice"
                    ? object.purchasePriceRMB != null
                    : Boolean(object[key as keyof ObjectRecord])),
              )
              .map(([key, label]) => {
                const property =
                  key === "purchasePrice" ? "purchasePriceRMB" : key;
                const raw = object[property as keyof ObjectRecord];
                const value =
                  key === "acquisitionDate"
                    ? String(raw || "").slice(0, 10)
                    : String(raw ?? "");
                return (
                  <label key={key} className="block text-[11px] text-muted">
                    {mt(label)}
                    <input
                      aria-label={mt(label)}
                      type={
                        key === "acquisitionDate"
                          ? "date"
                          : key === "purchasePrice"
                            ? "number"
                            : "text"
                      }
                      min={key === "purchasePrice" ? 0 : undefined}
                      step={key === "purchasePrice" ? 1 : undefined}
                      defaultValue={value}
                      className="mt-1 w-full min-w-0 border-b border-transparent focus:border-line bg-transparent text-[13px] text-ink outline-none py-1"
                      placeholder="—"
                      onBlur={(e) => {
                        if (e.target.value !== value)
                          void save({
                            [property]:
                              key === "purchasePrice"
                                ? e.target.value === ""
                                  ? null
                                  : Number(e.target.value)
                                : key === "acquisitionDate"
                                  ? e.target.value
                                    ? `${e.target.value}T00:00:00Z`
                                    : null
                                  : e.target.value,
                          });
                      }}
                    />
                  </label>
                );
              })}
          </div>
          {object.coverImagePath && object.collectionID && !archived && (
            <button
              className={`${button} mt-6`}
              onClick={() =>
                void run("collection.save", {
                  id: object.collectionID,
                  changes: { representativeAssetID: object.id },
                })
              }
            >
              {mt("设为集合封面")}
            </button>
          )}
          {object.coverImagePath && !archived && (
            <div className="flex flex-wrap gap-2 mt-2">
              <button
                className={button}
                onClick={() =>
                  void run("preferences.save", {
                    preferences: { allObjectsRepresentativeAssetID: object.id },
                  })
                }
              >
                {mt("设为全部封面")}
              </button>
              {!object.collectionID && (
                <button
                  className={button}
                  onClick={() =>
                    void run("preferences.save", {
                      preferences: {
                        unfiledObjectsRepresentativeAssetID: object.id,
                      },
                    })
                  }
                >
                  {mt("设为未分类封面")}
                </button>
              )}
            </div>
          )}
          <details
            className="mt-7 rounded-lg border border-line p-3"
            onPaste={(e) => {
              const files = Array.from(e.clipboardData.files);
              if (files.length) {
                e.preventDefault();
                void upload(files);
              }
            }}
            onDragOver={(e) => {
              if (e.dataTransfer.types.includes("Files")) e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              void upload(Array.from(e.dataTransfer.files));
            }}
          >
            <summary className="cursor-pointer text-[13px] text-muted">
              {mt("档案照片 · ")}
              {object.archivePhotoPaths.length}
            </summary>
            <div className="flex flex-wrap gap-2 mt-3">
              {object.archivePhotoPaths.map((path) => (
                <div key={path} className="w-20">
                  <button
                    className="w-20 h-24 rounded-lg overflow-hidden"
                    aria-label={mt("查看档案照片")}
                    onClick={() => setInspectedPhoto(path)}
                  >
                    <ObjectImage path={path} name={mt("档案照片")} />
                  </button>
                  <button
                    className="w-full mt-1 text-[11px] text-muted hover:text-ink"
                    onClick={() => {
                      if (window.confirm(mt("删除这张档案照片？")))
                        void run("asset.photo.remove", { id: object.id, path });
                    }}
                  >
                    {mt("删除")}
                  </button>
                </div>
              ))}
            </div>
            <label className={`${button} mt-3 cursor-pointer`}>
              {photoBusy ? mt("导入中…") : mt("添加照片")}
              <input
                aria-label={mt("添加档案照片")}
                type="file"
                accept="image/*,.heic,.heif,.tif,.tiff"
                multiple
                className="sr-only"
                disabled={photoBusy}
                onChange={(e) => {
                  void upload(Array.from(e.target.files || []));
                  e.target.value = "";
                }}
              />
            </label>
            <p className="text-[11px] text-muted mt-2">
              {mt(
                "也可拖入或粘贴。照片作为事实记录保存，最多前四张用于封面生成。",
              )}
            </p>
          </details>
        </div>
      </div>
      <div className="mt-10 border-t border-line pt-5">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-sm font-medium text-ink">{mt("记忆")}</h2>
          <button
            className={button}
            onClick={() => {
              const date = new Date().toISOString();
              setBlocks([
                ...blocks,
                {
                  id: crypto.randomUUID(),
                  text: "",
                  createdAt: date,
                  updatedAt: date,
                },
              ]);
              draftRevision.current += 1;
              setDirty(true);
            }}
          >
            {mt("添加记忆")}
          </button>
        </div>
        {blocks.map((block, index) => (
          <div key={block.id} className="border-b border-line py-3 flex gap-2">
            <textarea
              aria-label={mt("记忆 ") + (index + 1)}
              className="w-full resize-y min-h-24 bg-transparent text-[15px] leading-7 text-ink outline-none"
              placeholder={mt("留下一段记忆…")}
              value={block.text}
              onChange={(e) => {
                setBlocks(
                  blocks.map((b) =>
                    b.id === block.id ? { ...b, text: e.target.value } : b,
                  ),
                );
                draftRevision.current += 1;
                setDirty(true);
              }}
            />
            <button
              aria-label={mt("删除记忆 ") + (index + 1)}
              className="self-start p-2 text-muted hover:text-ink"
              onClick={() => {
                setBlocks(blocks.filter((b) => b.id !== block.id));
                draftRevision.current += 1;
                setDirty(true);
              }}
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
        {!blocks.length && (
          <p className="text-[13px] text-muted py-3">{mt("还没有记忆。")}</p>
        )}
      </div>
      <details className="mt-7">
        <summary className="cursor-pointer text-[13px] text-muted">
          {mt("自定义资料 · ")}
          {Object.keys(custom).length}
        </summary>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
          {Object.entries(custom).map(([key, value]) => (
            <label key={key} className="text-[12px] text-muted">
              {key}
              <div className="flex gap-1 mt-1">
                <input
                  className={field}
                  value={value}
                  onChange={(e) => {
                    setCustom({ ...custom, [key]: e.target.value });
                    draftRevision.current += 1;
                    setDirty(true);
                  }}
                />
                <button
                  className={button}
                  aria-label={mt("删除字段 ") + key}
                  onClick={() => {
                    const updated = { ...custom };
                    delete updated[key];
                    setCustom(updated);
                    draftRevision.current += 1;
                    setDirty(true);
                  }}
                >
                  <Icon name="x" size={12} />
                </button>
              </div>
            </label>
          ))}
        </div>
        <form
          className="flex gap-2 mt-4"
          onSubmit={(e) => {
            e.preventDefault();
            const name = newField.trim();
            if (name && !(name in custom)) {
              setCustom({ ...custom, [name]: "" });
              setNewField("");
              draftRevision.current += 1;
              setDirty(true);
            }
          }}
        >
          <input
            className={field}
            aria-label={mt("新字段名称")}
            placeholder={mt("字段名称")}
            value={newField}
            onChange={(e) => setNewField(e.target.value)}
          />
          <button className={button} disabled={!newField.trim()}>
            {mt("添加字段")}
          </button>
        </form>
      </details>
      {dirty && (
        <div className="sticky bottom-3 mt-6 flex justify-end">
          <button
            className={`${primary} shadow-lg`}
            disabled={saving}
            onClick={saveMemories}
          >
            {saving ? mt("保存中…") : mt("保存记忆与资料")}
          </button>
        </div>
      )}
      {(preview || inspectedPhoto) && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-6"
          role="dialog"
          aria-modal="true"
          aria-label={preview ? mt("封面预览") : mt("档案照片")}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              void discard();
              setInspectedPhoto(null);
            }
          }}
        >
          <div className="bg-paper border border-line rounded-2xl p-5 max-w-lg w-full shadow-xl">
            <div className="h-[min(60vh,550px)] rounded-lg overflow-hidden">
              {preview ? (
                <img
                  alt={mt("AI 封面预览")}
                  src={`data:${preview.mime};base64,${preview.data}`}
                  className="w-full h-full object-contain"
                />
              ) : (
                <ObjectImage
                  path={inspectedPhoto}
                  name={mt("档案照片")}
                  contain
                />
              )}
            </div>
            {preview ? (
              <>
                <p className="text-[12px] text-muted mt-3">
                  {preview.used_reference
                    ? mt("基于档案照片生成")
                    : mt("未使用参考照片")}
                  {mt(" · 采用后替换当前封面")}
                </p>
                <div className="flex justify-end gap-2 mt-4">
                  <button autoFocus className={button} onClick={discard}>
                    {mt("取消")}
                  </button>
                  <button className={button} onClick={generate}>
                    {mt("重新生成")}
                  </button>
                  <button
                    className={primary}
                    onClick={async () => {
                      if (
                        await run("asset.cover.apply", {
                          id: object.id,
                          preview: preview.preview,
                        })
                      )
                        await discard();
                    }}
                  >
                    {mt("采用封面")}
                  </button>
                </div>
              </>
            ) : (
              <button
                autoFocus
                className={`${button} mt-4`}
                onClick={() => setInspectedPhoto(null)}
              >
                {mt("关闭")}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
