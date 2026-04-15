import type { NormalizedEvent } from "./types";

const STORAGE_KEY = "saved";

export type SavedItem = {
  id: string;
  title: string;
  type: string;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  location_label: string;
  source: string;
  source_url: string;
  description: string;
  tags: string[];
  event_ref?: string;
};

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof localStorage !== "undefined";
}

function normalizeSavedItem(raw: unknown): SavedItem | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.id !== "string" || !item.id.trim()) return null;
  return {
    id: item.id,
    title: typeof item.title === "string" ? item.title : "Untitled",
    type: typeof item.type === "string" ? item.type : "event",
    start_date: typeof item.start_date === "string" ? item.start_date : "",
    end_date: typeof item.end_date === "string" ? item.end_date : "",
    start_time: typeof item.start_time === "string" ? item.start_time : "",
    end_time: typeof item.end_time === "string" ? item.end_time : "",
    location_label: typeof item.location_label === "string" ? item.location_label : "",
    source: typeof item.source === "string" ? item.source : "",
    source_url: typeof item.source_url === "string" ? item.source_url : "",
    description: typeof item.description === "string" ? item.description : "",
    tags: Array.isArray(item.tags) ? item.tags.filter((t): t is string => typeof t === "string") : [],
    event_ref: typeof item.event_ref === "string" ? item.event_ref : undefined,
  };
}

export function getSaved(): SavedItem[] {
  if (!isBrowser()) return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(normalizeSavedItem)
      .filter((x): x is SavedItem => x !== null);
  } catch {
    return [];
  }
}

function setSaved(items: SavedItem[]): void {
  if (!isBrowser()) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export function getEventSaveId(item: Partial<NormalizedEvent>): string | null {
  const ref = typeof item.event_ref === "string" ? item.event_ref.trim() : "";
  if (ref) return ref;
  const id = typeof item.id === "string" ? item.id.trim() : "";
  if (id) return id;
  const src = typeof item.source_url === "string" ? item.source_url.trim() : "";
  if (src) return src;
  return null;
}

export function toSavedItem(item: Partial<NormalizedEvent>): SavedItem | null {
  const id = getEventSaveId(item);
  if (!id) return null;
  return {
    id,
    title: item.title || "Untitled",
    type: item.type || "event",
    start_date: item.start_date || "",
    end_date: item.end_date || "",
    start_time: item.start_time || "",
    end_time: item.end_time || "",
    location_label: item.location_label || "",
    source: item.source || "",
    source_url: item.source_url || "",
    description: item.description || "",
    tags: Array.isArray(item.tags) ? item.tags : [],
    event_ref: item.event_ref,
  };
}

export function isSaved(id: string): boolean {
  return getSaved().some((i) => i.id === id);
}

export function saveItem(item: SavedItem): boolean {
  if (!item?.id) return false;
  const current = getSaved();
  if (current.some((i) => i.id === item.id)) return false;
  setSaved([item, ...current]);
  return true;
}

export function removeItem(id: string): void {
  if (!id) return;
  const updated = getSaved().filter((i) => i.id !== id);
  setSaved(updated);
}
