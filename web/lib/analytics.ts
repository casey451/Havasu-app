import { trackClick, trackView } from "./api";

const viewedIds = new Set<string>();

export function shouldTrackView(id: string | null | undefined): boolean {
  const k = (id || "").trim();
  if (!k) return false;
  if (viewedIds.has(k)) return false;
  viewedIds.add(k);
  return true;
}

export async function trackViewOnce(id: string | null | undefined): Promise<void> {
  if (!shouldTrackView(id)) return;
  try {
    await trackView((id || "").trim());
  } catch {
    // no-op: tracking should never break UI interactions
  }
}

export async function trackClickSafe(id: string | null | undefined): Promise<void> {
  const k = (id || "").trim();
  if (!k) return;
  try {
    await trackClick(k);
  } catch {
    // no-op
  }
}
