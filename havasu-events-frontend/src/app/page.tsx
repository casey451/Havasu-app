"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getDiscover, trackClick, trackView, type EventItem } from "@/lib/api";

type TimelineItem = EventItem & {
  startDate: Date;
  endDate: Date | null;
  isActiveNow: boolean;
  isSoon: boolean;
  category: ActivityCategory;
  tags: string[];
};

type ViewMode = "today" | "week";
type ActivityCategory = "kids" | "fitness" | "nightlife" | "events";
type FilterOption = "all" | ActivityCategory;

const FILTER_OPTIONS: Array<{ id: FilterOption; label: string }> = [
  { id: "all", label: "All" },
  { id: "kids", label: "Kids" },
  { id: "fitness", label: "Fitness" },
  { id: "nightlife", label: "Nightlife" },
  { id: "events", label: "Events" },
];

function parseDate(value?: string): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function formatHourLabel(value: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(value);
}

function formatTimeRange(startDate: Date, endDate: Date | null): string {
  const start = formatHourLabel(startDate);
  const end = endDate ? formatHourLabel(endDate) : "";
  return end ? `${start} - ${end}` : start;
}

function getStartOfWeek(today: Date): Date {
  const local = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const day = local.getDay();
  const diffToMonday = (day + 6) % 7;
  local.setDate(local.getDate() - diffToMonday);
  return local;
}

function getDaysOfWeek(startOfWeek: Date): Date[] {
  return Array.from({ length: 7 }, (_, idx) => {
    const d = new Date(startOfWeek);
    d.setDate(startOfWeek.getDate() + idx);
    return d;
  });
}

function toDayKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function normalizeCategory(value?: string): ActivityCategory {
  const cat = (value || "").trim().toLowerCase();
  if (cat === "kids" || cat === "fitness" || cat === "nightlife" || cat === "events") {
    return cat;
  }
  return "events";
}

function normalizeTags(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const v of value) {
    const t = String(v || "").trim().toLowerCase();
    if (!t || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

type QuerySignals = {
  queryWords: string[];
  requiresNow: boolean;
  categoryHint: ActivityCategory | null;
};

function parseQuerySignals(query: string): QuerySignals {
  const q = query.trim().toLowerCase();
  const tokens = q.split(/[^a-z0-9]+/).filter(Boolean);
  const stopWords = new Set(["what", "whats", "something", "for", "my", "the", "a", "an", "to", "do", "stuff"]);
  const queryWords = tokens.filter((w) => !stopWords.has(w));
  const requiresNow = tokens.includes("now") || tokens.includes("open") || tokens.includes("live");
  const categoryHint = tokens.includes("kids")
    ? "kids"
    : tokens.includes("fitness") || tokens.includes("training")
      ? "fitness"
      : tokens.includes("night") || tokens.includes("nightlife")
        ? "nightlife"
        : null;
  return { queryWords, requiresNow, categoryHint };
}

function recommendationScore(item: TimelineItem, signals: QuerySignals): number {
  const hasLocation = Boolean((item.location || "").trim());
  const categoryMatchesHint = signals.categoryHint !== null && item.category === signals.categoryHint;
  const tagMatches = signals.queryWords.filter((word) => item.tags.includes(word)).length;
  const queryMatches = categoryMatchesHint || tagMatches > 0;
  let score = 0;
  if (item.isActiveNow) score += 100;
  if (queryMatches) score += 50;
  if (categoryMatchesHint) score += 25;
  score += tagMatches * 10;
  if (hasLocation) score += 10;
  if (item.isSoon) score += 8;
  const stableNoise = ((item.id || item.title || "").length % 7) / 100;
  return score + stableNoise;
}

export default function Home() {
  const [items, setItems] = useState<EventItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<ViewMode>("today");
  const [activeFilter, setActiveFilter] = useState<FilterOption>("all");
  const [query, setQuery] = useState("");
  const viewed = useRef<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await getDiscover();
        if (!active) return;
        setItems(data.popular || []);
      } catch (e) {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Failed to load discover");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const preparedRows = useMemo(() => {
    const now = new Date();
    return items
      .filter((item) => Boolean((item.id || "").trim()))
      .map((item) => {
        const startDate = parseDate(item.start_date);
        if (!startDate) return null;
        const endDate = parseDate((item as { end_date?: string }).end_date);
        const isActiveNow = Boolean(endDate && startDate <= now && now <= endDate);
        const minutesUntilStart = Math.floor((startDate.getTime() - now.getTime()) / (1000 * 60));
        const isSoon = !isActiveNow && minutesUntilStart >= 0 && minutesUntilStart <= 60;
        return {
          ...item,
          startDate,
          endDate,
          isActiveNow,
          isSoon,
          category: normalizeCategory(item.category),
          tags: normalizeTags(item.tags),
        } satisfies TimelineItem;
      })
      .filter((item): item is TimelineItem => item !== null);
  }, [items]);

  const filteredRows = useMemo(() => {
    const signals = parseQuerySignals(query);

    return preparedRows.filter((item) => {
      const categoryMatchesChip = activeFilter === "all" || item.category === activeFilter;
      const categoryMatchesQuery = signals.categoryHint === null || item.category === signals.categoryHint;
      const nowMatchesQuery = !signals.requiresNow || item.isActiveNow;
      const queryWordMatches =
        signals.queryWords.length === 0 ||
        signals.queryWords.some((word) => item.category === word || item.tags.includes(word));
      return categoryMatchesChip && categoryMatchesQuery && nowMatchesQuery && queryWordMatches;
    });
  }, [activeFilter, preparedRows, query]);

  const timelineGroups = useMemo(() => {
    const now = new Date();
    const todayRows = filteredRows.filter((item) => item.startDate.toDateString() === now.toDateString());
    todayRows.sort((a, b) => {
      if (a.isActiveNow !== b.isActiveNow) return a.isActiveNow ? -1 : 1;
      return a.startDate.getTime() - b.startDate.getTime();
    });

    const grouped = new Map<string, TimelineItem[]>();
    for (const item of todayRows) {
      const hourLabel = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(
        item.startDate
      );
      const existing = grouped.get(hourLabel) || [];
      existing.push(item);
      grouped.set(hourLabel, existing);
    }

    return Array.from(grouped.entries()).map(([hourLabel, groupedItems]) => ({
      hourLabel,
      items: groupedItems,
    }));
  }, [filteredRows]);

  const topPicks = useMemo(() => {
    const now = new Date();
    const signals = parseQuerySignals(query);
    const todaysItems = filteredRows.filter((item) => item.startDate.toDateString() === now.toDateString());
    return [...todaysItems]
      .sort((a, b) => recommendationScore(b, signals) - recommendationScore(a, signals))
      .slice(0, 3);
  }, [filteredRows, query]);

  const weekSections = useMemo(() => {
    const now = new Date();
    const startOfWeek = getStartOfWeek(now);
    const weekDays = getDaysOfWeek(startOfWeek);
    const weekKeys = new Set(weekDays.map(toDayKey));
    const itemsByDay: Record<string, TimelineItem[]> = {};
    for (const key of weekKeys) itemsByDay[key] = [];
    for (const item of filteredRows) {
      const key = toDayKey(item.startDate);
      if (weekKeys.has(key)) itemsByDay[key].push(item);
    }
    for (const key of Object.keys(itemsByDay)) {
      itemsByDay[key].sort((a, b) => a.startDate.getTime() - b.startDate.getTime());
    }
    return weekDays.map((dayDate) => {
      const key = toDayKey(dayDate);
      return {
        key,
        dayDate,
        items: itemsByDay[key] || [],
      };
    });
  }, [filteredRows]);

  const visibleItems = useMemo(() => {
    if (view === "today") {
      return timelineGroups.flatMap((group) => group.items);
    }
    return weekSections.flatMap((section) => section.items);
  }, [timelineGroups, view, weekSections]);

  useEffect(() => {
    for (const item of visibleItems) {
      const id = (item.id || "").trim();
      if (!id || viewed.current.has(id)) continue;
      viewed.current.add(id);
      void trackView(id);
    }
  }, [visibleItems]);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold">Today Timeline</h1>
      <p className="mt-1 text-sm text-zinc-600">What is happening around Lake Havasu today.</p>
      <div className="mt-4 rounded-lg border border-zinc-200 bg-white p-2">
        <div className="flex items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="What do you want to do?"
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
          />
          {query.trim() ? (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="rounded-md border border-zinc-300 px-2 py-2 text-xs text-zinc-600"
              aria-label="Clear search"
            >
              X
            </button>
          ) : null}
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Try: "something for kids", "what's open now", "fitness today"
        </p>
      </div>
      {query.trim() ? (
        <p className="mt-3 text-sm text-zinc-700">
          Showing results for: <span className="font-medium">{query.trim()}</span>
        </p>
      ) : null}
      <div className="mt-4 inline-flex rounded-md border border-zinc-200 bg-white p-1 text-sm">
        <button
          type="button"
          onClick={() => setView("today")}
          className={`rounded px-3 py-1.5 ${view === "today" ? "bg-zinc-900 text-white" : "text-zinc-700"}`}
        >
          Today
        </button>
        <button
          type="button"
          onClick={() => setView("week")}
          className={`rounded px-3 py-1.5 ${view === "week" ? "bg-zinc-900 text-white" : "text-zinc-700"}`}
        >
          Week
        </button>
      </div>
      <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
        {FILTER_OPTIONS.map((option) => {
          const isActive = activeFilter === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setActiveFilter(option.id)}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-sm ${
                isActive
                  ? "border-zinc-900 bg-zinc-900 text-white"
                  : "border-zinc-300 bg-white text-zinc-700"
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {loading ? <p className="mt-4 text-sm text-zinc-500">Loading...</p> : null}
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
      {!loading && !error && view === "today" && timelineGroups.length === 0 ? (
        <p className="mt-6 rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-700">
          No matching activities
        </p>
      ) : null}

      {view === "today" ? (
        <div className="mt-6 space-y-6">
          {topPicks.length > 0 ? (
            <section className="rounded-lg border border-zinc-300 bg-zinc-100 p-4">
              <h2 className="text-base font-semibold">Top Picks Today</h2>
              <ul className="mt-3 space-y-3">
                {topPicks.map((item, idx) => {
                  const id = (item.id || "").trim();
                  return (
                    <li
                      key={`top-pick-${id || item.title}-${idx}`}
                      className="rounded-lg border border-zinc-300 bg-white shadow-sm transition-shadow hover:shadow-md"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          if (id) void trackClick(id);
                        }}
                        className="w-full rounded-lg p-5 text-left transition-transform active:scale-[0.99]"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-lg font-semibold leading-tight">{item.title || "Untitled activity"}</p>
                          {item.isActiveNow ? (
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                              LIVE
                            </span>
                          ) : null}
                          {!item.isActiveNow && item.isSoon ? (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                              SOON
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-2 text-sm text-zinc-600">{item.location || "Lake Havasu"}</p>
                        <p className="mt-1 text-sm text-zinc-700">{formatTimeRange(item.startDate, item.endDate)}</p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}
          {timelineGroups.map((group) => (
            <section key={group.hourLabel}>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">{group.hourLabel}</h2>
              <ul className="space-y-3">
                {group.items.map((item, idx) => {
                  const id = (item.id || "").trim();
                  return (
                    <li
                      key={`${id || item.title}-${idx}`}
                      className="rounded-lg border border-zinc-200 bg-white shadow-sm transition-shadow hover:shadow-md"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          if (id) void trackClick(id);
                        }}
                        className="w-full rounded-lg p-4 text-left transition-transform active:scale-[0.99]"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-base font-semibold leading-tight">{item.title || "Untitled activity"}</p>
                          {item.isActiveNow ? (
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                              LIVE
                            </span>
                          ) : null}
                          {!item.isActiveNow && item.isSoon ? (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                              SOON
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-2 text-sm text-zinc-600">{item.location || "Lake Havasu"}</p>
                        <p className="mt-1 text-sm text-zinc-700">{formatTimeRange(item.startDate, item.endDate)}</p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <div className="mt-6 space-y-6">
          {!loading && !error && weekSections.every((section) => section.items.length === 0) ? (
            <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-700">No matching activities</p>
          ) : null}
          {weekSections.map((section) => {
            const isToday = toDayKey(section.dayDate) === toDayKey(new Date());
            const dayLabel = new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(section.dayDate);
            const dayDate = new Intl.DateTimeFormat("en-US", { month: "2-digit", day: "2-digit" }).format(
              section.dayDate
            );
            return (
              <section
                key={section.key}
                className={`rounded-lg border p-4 ${
                  isToday ? "border-zinc-900 bg-zinc-50" : "border-zinc-200 bg-white"
                }`}
              >
                <h2 className={`mb-3 text-sm ${isToday ? "font-bold text-zinc-900" : "font-semibold text-zinc-700"}`}>
                  {dayLabel} {dayDate}
                </h2>
                {section.items.length === 0 ? <p className="text-sm text-zinc-500">No activities</p> : null}
                {section.items.length > 0 ? (
                  <ul className="space-y-3">
                    {section.items.map((item, idx) => {
                      const id = (item.id || "").trim();
                      return (
                        <li
                          key={`${id || item.title}-${idx}`}
                          className="rounded-lg border border-zinc-200 bg-white shadow-sm transition-shadow hover:shadow-md"
                        >
                          <button
                            type="button"
                            onClick={() => {
                              if (id) void trackClick(id);
                            }}
                            className="w-full rounded-lg p-4 text-left transition-transform active:scale-[0.99]"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="text-base font-semibold leading-tight">{item.title || "Untitled activity"}</p>
                              {item.isActiveNow ? (
                                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                  LIVE
                                </span>
                              ) : null}
                              {!item.isActiveNow && item.isSoon ? (
                                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                                  SOON
                                </span>
                              ) : null}
                            </div>
                            <p className="mt-2 text-sm text-zinc-600">{item.location || "Lake Havasu"}</p>
                            <p className="mt-1 text-sm text-zinc-700">{formatTimeRange(item.startDate, item.endDate)}</p>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </section>
            );
          })}
        </div>
      )}
    </main>
  );
}
