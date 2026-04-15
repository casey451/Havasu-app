PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  status_code INTEGER,
  html TEXT NOT NULL,
  content_sha256 TEXT
);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  type TEXT NOT NULL,
  source_url TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  title TEXT GENERATED ALWAYS AS (json_extract(payload_json, '$.title')) STORED,
  start_date TEXT GENERATED ALWAYS AS (json_extract(payload_json, '$.start_date')) STORED,
  weekday TEXT GENERATED ALWAYS AS (json_extract(payload_json, '$.weekday')) STORED,
  raw_page_id INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  item_key TEXT,
  FOREIGN KEY (raw_page_id) REFERENCES raw_pages(id) ON DELETE CASCADE,
  CHECK (
    type != 'event'
    OR (
      json_extract(payload_json, '$.start_date') IS NOT NULL
      AND length(trim(cast(json_extract(payload_json, '$.start_date') AS text))) > 0
    )
  )
);

CREATE INDEX IF NOT EXISTS idx_items_source_type ON items (source, type);

-- Business accounts + user-submitted events (Phase 2.5)
CREATE TABLE IF NOT EXISTS businesses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'business')),
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_businesses_role ON businesses (role);
CREATE INDEX IF NOT EXISTS idx_businesses_status ON businesses (status);

-- Public business listings (structured entity for discovery / AI), separate from login `businesses` rows.
CREATE TABLE IF NOT EXISTS business_profiles (
  id TEXT PRIMARY KEY,
  owner_business_id INTEGER NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  category TEXT NOT NULL,
  category_group TEXT NOT NULL,
  tags TEXT NOT NULL,
  phone TEXT,
  website TEXT,
  address TEXT,
  city TEXT NOT NULL DEFAULT 'Lake Havasu',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY (owner_business_id) REFERENCES businesses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_business_profiles_owner ON business_profiles (owner_business_id);
CREATE INDEX IF NOT EXISTS idx_business_profiles_group ON business_profiles (category_group);
CREATE INDEX IF NOT EXISTS idx_business_profiles_active ON business_profiles (is_active);

CREATE TABLE IF NOT EXISTS user_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_id INTEGER NOT NULL,
  business_profile_id TEXT,
  title TEXT NOT NULL,
  description TEXT,
  start_date TEXT NOT NULL,
  start_time TEXT,
  end_time TEXT,
  location_label TEXT,
  venue_name TEXT,
  address TEXT,
  tags TEXT,
  category TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE,
  FOREIGN KEY (business_profile_id) REFERENCES business_profiles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_events_business ON user_events (business_id);
CREATE INDEX IF NOT EXISTS idx_user_events_start_date ON user_events (start_date);

-- Public no-auth submissions (pending moderation)
CREATE TABLE IF NOT EXISTS user_submissions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  category TEXT NOT NULL CHECK (category IN ('event', 'service')),
  start_date TEXT,
  location TEXT NOT NULL DEFAULT 'Lake Havasu',
  source TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
  is_featured INTEGER NOT NULL DEFAULT 0,
  featured_until TEXT,
  view_count INTEGER NOT NULL DEFAULT 0,
  click_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_submissions_status ON user_submissions (status);
CREATE INDEX IF NOT EXISTS idx_user_submissions_start_date ON user_submissions (start_date);

-- Activities + recurring/dated time slots (time-slot engine)
CREATE TABLE IF NOT EXISTS activities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('event', 'schedule')),
  category TEXT NOT NULL DEFAULT 'events' CHECK (category IN ('kids', 'fitness', 'nightlife', 'events')),
  tags TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('pending', 'approved', 'rejected')),
  view_count INTEGER NOT NULL DEFAULT 0,
  click_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activities_status ON activities (status);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities (type);

CREATE TABLE IF NOT EXISTS time_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id INTEGER NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  day_of_week INTEGER,
  date TEXT,
  recurring INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
  CHECK (
    (date IS NOT NULL AND day_of_week IS NULL)
    OR (date IS NULL AND day_of_week IS NOT NULL)
  ),
  CHECK (day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)),
  CHECK (recurring IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_time_slots_activity ON time_slots (activity_id);
CREATE INDEX IF NOT EXISTS idx_time_slots_date ON time_slots (date);
CREATE INDEX IF NOT EXISTS idx_time_slots_weekday ON time_slots (day_of_week);
