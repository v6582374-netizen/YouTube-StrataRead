export interface MemoryBlock {
  id: string;
  text: string;
  createdAt: string;
  updatedAt: string;
}
export interface ObjectRecord {
  id: string;
  name: string;
  memoryBlocks: MemoryBlock[];
  archivePhotoPaths: string[];
  coverImagePath?: string | null;
  coverProvenance: string;
  collectionID?: string | null;
  purchasePriceRMB?: number | null;
  acquisitionSource?: string;
  brand?: string;
  material?: string;
  acquisitionDate?: string | null;
  model?: string;
  condition?: string;
  serialNumber?: string;
  metadataNote?: string;
  customMetadata: Record<string, string>;
  deletedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  syncVersion: number;
}
export interface Collection {
  id: string;
  name: string;
  role: "user" | "archive";
  displayOrder: number;
  representativeAssetID?: string | null;
  coverImagePath?: string | null;
}
export interface Preferences {
  coverPromptTemplate: string;
  visibleMetadataFields: string[];
  allObjectsRepresentativeAssetID?: string | null;
  unfiledObjectsRepresentativeAssetID?: string | null;
}
export interface Snapshot {
  assets: ObjectRecord[];
  collections: Collection[];
  preferences: Preferences;
  migration: { imported?: boolean; assets?: number };
  image_ready: boolean;
}
export interface ImageSettings {
  base_url: string;
  model: string;
  has_key: boolean;
  ready: boolean;
}
export interface Preview {
  preview: string;
  data: string;
  mime: string;
  used_reference: boolean;
}
export const METADATA: Record<string, string> = {
  acquisitionSource: "获取来源",
  purchasePrice: "购入价格 · 元",
  brand: "品牌",
  material: "材质",
  acquisitionDate: "购入日期",
  model: "型号",
  condition: "成色",
  serialNumber: "序列号",
  metadataNote: "补充说明",
};
export const message = (e: unknown) =>
  e instanceof Error ? e.message : "操作未完成，请重试。";
export const field =
  "w-full min-w-0 rounded-lg border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-accent";
export const button =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[13px] text-ink hover:bg-chromeHover disabled:opacity-40 disabled:cursor-not-allowed";
export const primary =
  "inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[13px] text-white disabled:opacity-40";
