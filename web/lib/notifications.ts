import { getNotificationsFeed } from "./api";
import type { NotificationFeedItem } from "./types";

const STORAGE_KEY = "seenNotificationIds";
const BOOTSTRAP_KEY = "notificationsBootstrapped";
const SESSION_SEEN = new Set<string>();

function canNotify(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

function readSeenStorage(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(STORAGE_KEY) || "[]";
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((x): x is string => typeof x === "string" && !!x.trim()));
  } catch {
    return new Set();
  }
}

function writeSeenStorage(ids: Set<string>): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids).slice(-500)));
}

function toMs(dateIso: string): number | null {
  const s = (dateIso || "").trim();
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

export function isSoonFeatured(item: NotificationFeedItem, nowMs = Date.now()): boolean {
  if (!item.is_featured) return false;
  const eventMs = toMs(item.start_date);
  if (eventMs === null) return false;
  const delta = eventMs - nowMs;
  const maxWindow = 48 * 60 * 60 * 1000;
  return delta >= 0 && delta <= maxWindow;
}

export function shouldNotifyForItem(
  item: NotificationFeedItem,
  seen: Set<string>,
  nowMs = Date.now(),
): boolean {
  if (!item.id || seen.has(item.id)) return false;
  // New approved events notify once; featured-soon items use tailored copy.
  return true;
}

export function requestNotificationPermissionOnce(): void {
  if (!canNotify()) return;
  if (Notification.permission !== "default") return;
  void Notification.requestPermission().catch(() => undefined);
}

function showBrowserNotification(item: NotificationFeedItem): void {
  if (!canNotify()) return;
  if (Notification.permission !== "granted") return;
  const soonFeatured = isSoonFeatured(item);
  const body = soonFeatured
    ? `Happening soon: ${item.title}`
    : `New event: ${item.title}`;
  const n = new Notification("Lake Havasu", { body });
  n.onclick = () => {
    const target = item.event_ref ? `/event/${encodeURIComponent(item.event_ref)}` : "/";
    window.open(target, "_blank");
  };
}

export async function pollNotificationsFeed(): Promise<void> {
  try {
    const feed = await getNotificationsFeed(20);
    if (!Array.isArray(feed.items) || feed.items.length === 0) return;
    const seen = readSeenStorage();
    const isBootstrapped =
      typeof window !== "undefined" && localStorage.getItem(BOOTSTRAP_KEY) === "1";
    if (!isBootstrapped) {
      for (const item of feed.items) {
        if (item.id) seen.add(item.id);
      }
      writeSeenStorage(seen);
      if (typeof window !== "undefined") localStorage.setItem(BOOTSTRAP_KEY, "1");
      return;
    }
    for (const item of feed.items) {
      if (!shouldNotifyForItem(item, seen)) continue;
      showBrowserNotification(item);
      seen.add(item.id);
      SESSION_SEEN.add(item.id);
    }
    writeSeenStorage(seen);
  } catch {
    // silent retry on next polling cycle
  }
}

export function hasSeenInSession(id: string): boolean {
  return SESSION_SEEN.has(id);
}
