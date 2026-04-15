import type {
  AuthUser,
  BusinessEvent,
  BusinessEventInput,
  BusinessProfile,
  BusinessProfileDetail,
  BusinessProfileInput,
  NormalizedEvent,
  PendingBusiness,
  PublicEventDetail,
  SearchResponse,
  SubmitInput,
  SubmitResponse,
  TrackResponse,
  NotificationFeedResponse,
  NotificationFeedItem,
  AdminSubmission,
  DiscoverResponse,
  TodayResponse,
  WeekResponse,
} from "./types";

const API_PREFIX = process.env.NEXT_PUBLIC_API_BASE ?? "/api/backend";

function resolveApiUrl(path: string): string {
  const p = `${API_PREFIX.replace(/\/$/, "")}${path}`;
  if (typeof window !== "undefined") {
    return p;
  }
  const origin =
    process.env.NEXT_PRIVATE_ORIGIN?.replace(/\/$/, "") ?? "http://127.0.0.1:3000";
  return `${origin}${p}`;
}

async function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
  const res = await fetch(resolveApiUrl(`${path}${qs}`), {
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

async function apiFetch<T>(
  path: string,
  init: RequestInit & { token?: string | null },
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (init.token) {
    headers.set("Authorization", `Bearer ${init.token}`);
  }
  const res = await fetch(resolveApiUrl(path), {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path}: ${res.status} ${text.slice(0, 300)}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const ct = res.headers.get("content-type");
  if (!ct?.includes("application/json")) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function getItems(): Promise<NormalizedEvent[]> {
  return apiGet<NormalizedEvent[]>("/items");
}

export async function getToday(): Promise<TodayResponse> {
  return apiGet<TodayResponse>("/today");
}

export async function getWeek(): Promise<WeekResponse> {
  return apiGet<WeekResponse>("/week");
}

export async function getDiscover(): Promise<DiscoverResponse> {
  return apiGet<DiscoverResponse>("/discover");
}

export async function getPublicEvent(eventRef: string): Promise<PublicEventDetail> {
  const enc = encodeURIComponent(eventRef);
  return apiGet<PublicEventDetail>(`/public/event/${enc}`);
}

export async function getBusinessProfile(profileId: string): Promise<BusinessProfileDetail> {
  const enc = encodeURIComponent(profileId);
  return apiGet<BusinessProfileDetail>(`/business/${enc}`);
}

/** Alias for public detail fetch. */
export async function getBusiness(profileId: string): Promise<BusinessProfileDetail> {
  return getBusinessProfile(profileId);
}

export async function listBusinesses(limit = 100): Promise<BusinessProfile[]> {
  return apiGet<BusinessProfile[]>("/business/list", {
    limit: String(Math.min(500, Math.max(1, limit))),
  });
}

export async function getMyBusinessProfile(token: string): Promise<BusinessProfile | null> {
  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(resolveApiUrl("/business/me"), {
    method: "GET",
    headers,
    cache: "no-store",
  });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`/business/me: ${res.status} ${text.slice(0, 300)}`);
  }
  return res.json() as Promise<BusinessProfile>;
}

export async function saveMyBusinessProfile(
  token: string,
  body: BusinessProfileInput,
): Promise<BusinessProfile> {
  return apiFetch<BusinessProfile>("/business/me", {
    method: "PUT",
    token,
    body: JSON.stringify(body),
  });
}

/** Defensive parse for GET /search — always returns arrays and a nullable `ai`. */
export function normalizeSearchResponse(data: unknown): SearchResponse {
  if (!data || typeof data !== "object") {
    return { results: [], ai: null };
  }
  const o = data as Record<string, unknown>;
  const results = Array.isArray(o.results) ? (o.results as NormalizedEvent[]) : [];
  if (o.ai === undefined || o.ai === null) {
    return { results, ai: null };
  }
  if (typeof o.ai !== "object") {
    return { results, ai: null };
  }
  const rawAi = o.ai as Record<string, unknown>;
  const s = rawAi.suggestions;
  const suggestions = Array.isArray(s)
    ? (s.filter((x): x is string => typeof x === "string") as string[])
    : [];
  return { results, ai: { suggestions } };
}

export async function searchEvents(query: string): Promise<SearchResponse> {
  const q = query.trim();
  if (!q) {
    return { results: [], ai: null };
  }
  const raw = await apiGet<unknown>("/search", { q });
  return normalizeSearchResponse(raw);
}

export async function submitItem(body: SubmitInput): Promise<SubmitResponse> {
  return apiFetch<SubmitResponse>("/submit", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function trackView(id: string): Promise<TrackResponse> {
  return apiFetch<TrackResponse>("/track/view", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export async function trackClick(id: string): Promise<TrackResponse> {
  return apiFetch<TrackResponse>("/track/click", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export function normalizeNotificationFeed(data: unknown): NotificationFeedResponse {
  if (!data || typeof data !== "object") return { items: [] };
  const o = data as Record<string, unknown>;
  if (!Array.isArray(o.items)) return { items: [] };
  const items = o.items
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x): NotificationFeedItem => ({
      id: typeof x.id === "string" ? x.id : "",
      event_ref: typeof x.event_ref === "string" ? x.event_ref : "",
      title: typeof x.title === "string" ? x.title : "Untitled",
      type: typeof x.type === "string" ? x.type : "event",
      start_date: typeof x.start_date === "string" ? x.start_date : "",
      source: typeof x.source === "string" ? x.source : "",
      is_featured: !!x.is_featured,
      featured_until: typeof x.featured_until === "string" ? x.featured_until : "",
      created_at: typeof x.created_at === "string" ? x.created_at : "",
      updated_at: typeof x.updated_at === "string" ? x.updated_at : "",
    }))
    .filter((x) => !!x.id);
  return { items };
}

export async function getNotificationsFeed(limit = 20): Promise<NotificationFeedResponse> {
  const raw = await apiGet<unknown>("/notifications/feed", { limit: String(Math.max(1, Math.min(50, limit))) });
  return normalizeNotificationFeed(raw);
}

export async function listAdminSubmissions(
  status: "pending" | "approved" | "rejected" = "approved",
): Promise<AdminSubmission[]> {
  return apiGet<AdminSubmission[]>("/admin/submissions", { status });
}

// --- Auth ---

export async function login(email: string, password: string): Promise<{ access_token: string }> {
  return apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(
  email: string,
  password: string,
  name: string,
): Promise<AuthUser> {
  return apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export async function getMe(token: string): Promise<AuthUser> {
  return apiFetch("/auth/me", { method: "GET", token });
}

// --- Business ---

export async function listBusinessEvents(token: string): Promise<BusinessEvent[]> {
  return apiFetch("/business/events", { method: "GET", token });
}

export async function createBusinessEvent(
  token: string,
  body: BusinessEventInput,
): Promise<BusinessEvent> {
  return apiFetch("/business/events", {
    method: "POST",
    token,
    body: JSON.stringify(body),
  });
}

export async function updateBusinessEvent(
  token: string,
  id: number,
  body: BusinessEventInput,
): Promise<BusinessEvent> {
  return apiFetch(`/business/events/${id}`, {
    method: "PUT",
    token,
    body: JSON.stringify(body),
  });
}

export async function deleteBusinessEvent(token: string, id: number): Promise<void> {
  await apiFetch<void>(`/business/events/${id}`, {
    method: "DELETE",
    token,
  });
}

// --- Admin ---

export async function listPendingBusinesses(token: string): Promise<PendingBusiness[]> {
  return apiFetch<PendingBusiness[]>("/admin/pending-businesses", {
    method: "GET",
    token,
  });
}

export async function approveBusiness(token: string, businessId: number): Promise<void> {
  await apiFetch(`/admin/approve-business/${businessId}`, {
    method: "POST",
    token,
  });
}

export async function rejectBusiness(token: string, businessId: number): Promise<void> {
  await apiFetch(`/admin/reject-business/${businessId}`, {
    method: "POST",
    token,
  });
}
