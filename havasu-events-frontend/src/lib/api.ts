const BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const ADMIN_TOKEN = (process.env.NEXT_PUBLIC_ADMIN_TOKEN || "").trim();

type ApiError = { detail?: string; error?: string; message?: string };

export type EventItem = {
  id?: string;
  event_ref?: string;
  title?: string;
  start_date?: string;
  end_date?: string;
  location?: string;
  category?: string;
  tags?: string[];
  view_count?: number;
  click_count?: number;
  source?: string;
};

export type DiscoverResponse = {
  today: EventItem[];
  weekend: EventItem[];
  popular: EventItem[];
};

export type AIRecommendation = {
  id: string;
  score: number;
  reason: string;
};

export async function getDiscover(): Promise<DiscoverResponse> {
  const res = await fetch(`${BASE_URL}/discover`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as DiscoverResponse;
}

export async function submitEvent(data: {
  title: string;
  start_date: string;
  location: string;
}): Promise<{ success: boolean; duplicate?: boolean; id?: string }> {
  const res = await fetch(`${BASE_URL}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: data.title,
      start_date: data.start_date,
      location: data.location,
      category: "event",
      description: "",
      tags: [],
    }),
  });
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as { success: boolean; duplicate?: boolean; id?: string };
}

export async function submitActivity(data: {
  title: string;
  location: string;
  category: string;
  tags: string[];
  description: string;
  time_slots: Array<{
    start_time: string;
    end_time: string;
    day_of_week?: number | null;
    date?: string | null;
    recurring: boolean;
  }>;
}): Promise<{ success: boolean; duplicate?: boolean; id?: string }> {
  const res = await fetch(`${BASE_URL}/submit-activity`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as { success: boolean; duplicate?: boolean; id?: string };
}

export async function aiRecommend(query: string): Promise<AIRecommendation[]> {
  const res = await fetch(`${BASE_URL}/ai/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as AIRecommendation[];
}

export async function aiClick(query: string, clicked_id: string): Promise<void> {
  if (!query.trim() || !clicked_id.trim()) return;
  await fetch(`${BASE_URL}/ai/click`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, clicked_id }),
  });
}

export async function trackView(id: string): Promise<void> {
  if (!id) return;
  await fetch(`${BASE_URL}/track/view`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

export async function trackClick(id: string): Promise<void> {
  if (!id) return;
  await fetch(`${BASE_URL}/track/click`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

export async function getAdminPending(): Promise<
  Array<{ id: string; title: string; start_date?: string; location?: string; status?: string }>
> {
  const res = await fetch(`${BASE_URL}/admin/pending`, {
    headers: adminHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await readApiError(res));
  return (await res.json()) as Array<{ id: string; title: string; start_date?: string; location?: string; status?: string }>;
}

export async function approveSubmission(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/admin/approve?id=${encodeURIComponent(id)}`, {
    method: "POST",
    headers: adminHeaders(),
  });
  if (!res.ok) throw new Error(await readApiError(res));
}

function adminHeaders(): HeadersInit {
  if (!ADMIN_TOKEN) {
    throw new Error("Missing NEXT_PUBLIC_ADMIN_TOKEN");
  }
  return { Authorization: `Bearer ${ADMIN_TOKEN}` };
}

async function readApiError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as ApiError;
    return body.detail || body.error || body.message || `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}
