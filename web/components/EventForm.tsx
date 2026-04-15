"use client";

import { useState } from "react";

import type { BusinessEvent, BusinessEventInput } from "@/lib/types";

const empty: BusinessEventInput = {
  title: "",
  description: "",
  start_date: "",
  start_time: "",
  end_time: "",
  location_label: "",
  venue_name: "",
  address: "",
  tags: [],
  category: "",
};

function toInput(ev?: BusinessEvent | null): BusinessEventInput {
  if (!ev) return { ...empty };
  return {
    title: ev.title,
    description: ev.description ?? "",
    start_date: ev.start_date,
    start_time: ev.start_time ?? "",
    end_time: ev.end_time ?? "",
    location_label: ev.location_label ?? "",
    venue_name: ev.venue_name ?? "",
    address: ev.address ?? "",
    tags: ev.tags ?? [],
    category: ev.category ?? "",
  };
}

function cleanPayload(v: BusinessEventInput): BusinessEventInput {
  const trim = (s: string | null | undefined) => {
    const t = (s ?? "").trim();
    return t === "" ? null : t;
  };
  const tagsRaw = (v.tags ?? [])
    .map((t) => String(t).trim())
    .filter(Boolean);
  const cat = (v.category ?? "").trim();
  return {
    title: v.title.trim(),
    description: (v.description ?? "").trim(),
    start_date: v.start_date.trim(),
    start_time: trim(v.start_time),
    end_time: trim(v.end_time),
    location_label: trim(v.location_label),
    venue_name: trim(v.venue_name),
    address: trim(v.address),
    tags: tagsRaw,
    category: cat === "" ? null : cat,
  };
}

export function EventForm({
  initial,
  onSubmit,
  submitLabel,
  disabled,
}: {
  initial?: BusinessEvent | null;
  onSubmit: (data: BusinessEventInput) => Promise<void>;
  submitLabel: string;
  disabled?: boolean;
}) {
  const [v, setV] = useState<BusinessEventInput>(() => toInput(initial));
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const cleaned = cleanPayload(v);
    if (!cleaned.description.trim()) {
      setErr("Description is required.");
      return;
    }
    if (!cleaned.location_label && !cleaned.venue_name && !cleaned.address) {
      setErr("Enter at least one of: location label, venue name, or address.");
      return;
    }
    setLoading(true);
    try {
      await onSubmit(cleaned);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  const field =
    "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100";

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-lg space-y-4">
      {err ? (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {err}
        </p>
      ) : null}
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Title *</label>
        <input
          className={field}
          required
          maxLength={120}
          value={v.title}
          onChange={(e) => setV({ ...v, title: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Description *</label>
        <textarea
          className={field}
          rows={4}
          required
          maxLength={2000}
          value={v.description ?? ""}
          onChange={(e) => setV({ ...v, description: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Start date (YYYY-MM-DD) *
        </label>
        <input
          className={field}
          required
          pattern="\d{4}-\d{2}-\d{2}"
          placeholder="2026-06-01"
          value={v.start_date}
          onChange={(e) => setV({ ...v, start_date: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Start time</label>
          <input
            className={field}
            placeholder="18:00"
            value={v.start_time ?? ""}
            onChange={(e) => setV({ ...v, start_time: e.target.value })}
            disabled={disabled || loading}
          />
        </div>
        <div>
          <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">End time</label>
          <input
            className={field}
            placeholder="20:00"
            value={v.end_time ?? ""}
            onChange={(e) => setV({ ...v, end_time: e.target.value })}
            disabled={disabled || loading}
          />
        </div>
      </div>
      <p className="text-xs text-zinc-500">
        Location: fill at least one of label, venue, or address.
      </p>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Location label</label>
        <input
          className={field}
          value={v.location_label ?? ""}
          onChange={(e) => setV({ ...v, location_label: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Venue name</label>
        <input
          className={field}
          value={v.venue_name ?? ""}
          onChange={(e) => setV({ ...v, venue_name: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Address</label>
        <input
          className={field}
          value={v.address ?? ""}
          onChange={(e) => setV({ ...v, address: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Tags (optional, comma-separated)
        </label>
        <input
          className={field}
          placeholder="e.g. music, outdoor"
          value={(v.tags ?? []).join(", ")}
          onChange={(e) =>
            setV({
              ...v,
              tags: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          disabled={disabled || loading}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Category (optional)</label>
        <input
          className={field}
          value={v.category ?? ""}
          onChange={(e) => setV({ ...v, category: e.target.value })}
          disabled={disabled || loading}
        />
      </div>
      <button
        type="submit"
        disabled={disabled || loading}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {loading ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}
