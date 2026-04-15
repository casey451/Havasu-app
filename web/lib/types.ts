/** Normalized item shape from FastAPI (`finalize_api_list`, expand=false). */
export type NormalizedEvent = {
  /** Stable public id when present (same as `event_ref`). */
  id?: string;
  title: string;
  type: string;
  start_date: string;
  end_date: string;
  weekday: string;
  start_time: string;
  end_time: string;
  /** Same as `location_label` for a simple consumer shape. */
  location?: string;
  location_label: string;
  source: string;
  source_url: string;
  source_urls?: string[];
  description?: string;
  date?: string;
  has_start_time: boolean;
  has_end_time: boolean;
  has_location: boolean;
  business_id?: number;
  tags?: string[];
  category?: string;
  trust_score?: number;
  is_featured?: boolean;
  featured_until?: string;
  /** `u-{id}` user event or `c-{id}` stored item — for public URLs */
  event_ref?: string;
  /** From linked business profile when present (user events). */
  business_name?: string;
  business_category?: string;
  debug_source_type?: string;
};

/** GET /public/event/{event_ref} (expand=true merged payload). */
export type PublicEventDetail = NormalizedEvent & {
  venue_name?: string;
  address?: string;
  short_description?: string;
  item_db_id?: number;
  user_event_id?: number;
};

export type TodayResponse = {
  date: string;
  weekday: string;
  events: NormalizedEvent[];
  recurring: NormalizedEvent[];
};

export type WeekResponse = {
  start: string;
  end: string;
  events: NormalizedEvent[];
  recurring_by_weekday: Record<string, NormalizedEvent[]>;
};

export type DiscoverResponse = {
  today: NormalizedEvent[];
  weekend: NormalizedEvent[];
  popular: NormalizedEvent[];
};

export type PendingBusiness = {
  id: number;
  email: string;
  name: string;
  status: string;
};

/** GET /auth/me */
export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: string;
  status: string;
};

/** GET /business/events item */
export type BusinessEvent = {
  id: number;
  business_id: number;
  business_profile_id?: string | null;
  title: string;
  description: string | null;
  start_date: string;
  start_time: string | null;
  end_time: string | null;
  location_label: string | null;
  venue_name?: string | null;
  address?: string | null;
  tags?: string[];
  category?: string | null;
  created_at: string;
  updated_at: string;
};

export type BusinessEventInput = {
  title: string;
  description: string;
  start_date: string;
  start_time?: string | null;
  end_time?: string | null;
  location_label?: string | null;
  venue_name?: string | null;
  address?: string | null;
  tags?: string[];
  category?: string | null;
};

/** GET /business/list item, GET /business/create response */
export type BusinessProfile = {
  id: string;
  name: string;
  description: string;
  category: string;
  category_group: string;
  tags: string[];
  phone?: string | null;
  website?: string | null;
  address?: string | null;
  city: string;
  is_active: boolean;
  created_at: string;
};

/** GET /business/{id} */
export type BusinessProfileDetail = BusinessProfile & {
  upcoming_events: BusinessEvent[];
};

/** PUT /business/me (create or update) */
export type BusinessProfileInput = {
  name: string;
  description: string;
  category: string;
  phone?: string | null;
  website?: string | null;
  address?: string | null;
  city?: string | null;
  is_active: boolean;
};

/** GET /search — always `results` array; `ai` null or suggestion bullets. */
export type SearchResponse = {
  results: NormalizedEvent[];
  ai: { suggestions: string[] } | null;
};

export type SubmitInput = {
  title: string;
  description?: string;
  tags?: string[];
  category: "event" | "service";
  start_date?: string | null;
  location: string;
};

export type SubmitResponse = {
  success: boolean;
  id: string;
};

export type TrackResponse = {
  success: boolean;
};

export type NotificationFeedItem = {
  id: string;
  event_ref: string;
  title: string;
  type: string;
  start_date: string;
  source: string;
  is_featured?: boolean;
  featured_until?: string;
  created_at?: string;
  updated_at?: string;
};

export type NotificationFeedResponse = {
  items: NotificationFeedItem[];
};

export type AdminSubmission = {
  id: string;
  title: string;
  status: "pending" | "approved" | "rejected";
  category: string;
  location: string;
  created_at: string;
  view_count: number;
  click_count: number;
  ctr: number;
  is_featured?: boolean;
};
