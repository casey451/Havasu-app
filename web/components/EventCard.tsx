"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { trackClickSafe, trackViewOnce } from "@/lib/analytics";
import { isSaved, removeItem, saveItem, toSavedItem } from "@/lib/saved";
import type { NormalizedEvent } from "@/lib/types";

function formatTime(e: NormalizedEvent): string | null {
  if (!e.has_start_time) return null;
  const s = e.start_time?.trim() || "";
  if (!e.has_end_time || !e.end_time?.trim()) return s || null;
  return `${s} – ${e.end_time.trim()}`;
}

function locationLine(e: NormalizedEvent): string {
  if (!e.has_location) return "";
  return (e.location_label ?? "").trim();
}

export function EventCard({ event }: { event: NormalizedEvent }) {
  const time = formatTime(event);
  const loc = locationLine(event);
  const ref = event.event_ref;
  const saveId = toSavedItem(event)?.id ?? null;
  const canSave = !!saveId;
  const isUser = event.source === "user";
  const [saved, setSaved] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const subtleSource =
    !isUser && event.source?.trim()
      ? event.source
      : "";

  useEffect(() => {
    setSaved(saveId ? isSaved(saveId) : false);
  }, [saveId]);

  useEffect(() => {
    void trackViewOnce(saveId);
  }, [saveId]);

  function onToggleSave() {
    const savedEvent = toSavedItem(event);
    if (!savedEvent) return;
    if (saved) {
      removeItem(savedEvent.id);
      setSaved(false);
      setJustSaved(false);
      return;
    }
    const added = saveItem(savedEvent);
    if (added) {
      setSaved(true);
      setJustSaved(true);
      window.setTimeout(() => setJustSaved(false), 1800);
    }
  }

  const content = (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {event.title || "Untitled"}
        </h2>
        {isUser ? (
          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100">
            Local Business
          </span>
        ) : null}
        {event.is_featured ? (
          <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">
            Featured
          </span>
        ) : null}
      </div>
      {time ? (
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{time}</p>
      ) : null}
      {loc ? (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-500">{loc}</p>
      ) : null}
      {subtleSource ? (
        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">{subtleSource}</p>
      ) : null}
    </>
  );

  const className =
    "block rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition hover:border-zinc-300 hover:shadow dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-600";

  const controls = (
    <div className="mt-3 flex items-center gap-3">
      <button
        type="button"
        onClick={onToggleSave}
        disabled={!canSave}
        className="rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
      >
        {saved ? "Saved ✓" : "Save"}
      </button>
      {justSaved ? (
        <span className="text-xs text-emerald-600 dark:text-emerald-400">Saved to your list</span>
      ) : null}
    </div>
  );

  if (!ref) {
    return (
      <div className={className}>
        {content}
        {controls}
      </div>
    );
  }

  return (
    <div className={className}>
      <Link href={`/event/${encodeURIComponent(ref)}`} className="block">
        <div
          onClick={() => {
            void trackClickSafe(saveId);
          }}
        >
          {content}
        </div>
      </Link>
      {controls}
    </div>
  );
}
